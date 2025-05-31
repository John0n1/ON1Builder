#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Chain Worker
=========================
Handles operations for a specific blockchain: init, monitoring, tx management.
License: MIT
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional

from eth_account.account import Account
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware

from on1builder.config.config import Configuration, APIConfig
from on1builder.core.nonce_core import NonceCore
from on1builder.core.transaction_core import TransactionCore
from on1builder.engines.safety_net import SafetyNet

from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.monitoring.txpool_monitor import TxpoolMonitor
from on1builder.persistence.db_manager import DatabaseManager, get_db_manager
from on1builder.utils.logger import setup_logging

logger = setup_logging("ChainWorker", level="INFO")


class ChainWorker:
    """Manages a single‐chain lifecycle: init, start, stop, metrics, monitoring."""

    def __init__(
        self,
        chain_cfg: Dict[str, Any],
        global_cfg: Configuration,
    ) -> None:
        self.chain_cfg = chain_cfg
        self.config: Configuration = global_cfg
        self.chain_id: str = str(chain_cfg.get("CHAIN_ID", "unknown"))
        self.chain_name: str = chain_cfg.get("CHAIN_NAME", f"chain-{self.chain_id}")

        # Endpoints
        self.http_endpoint: str = chain_cfg.get("HTTP_ENDPOINT", "")
        self.websocket_endpoint: str = chain_cfg.get("WEBSOCKET_ENDPOINT", "")
        self.ipc_endpoint: str = chain_cfg.get("IPC_ENDPOINT", "")

        # Wallet
        self.wallet_key: Optional[str] = chain_cfg.get("WALLET_KEY") or os.getenv("WALLET_KEY")
        self.wallet_address: Optional[str] = chain_cfg.get("WALLET_ADDRESS")

        # Components
        self.web3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self.api_config: Optional[APIConfig] = None
        self.db: Optional[DatabaseManager] = None
        self.nonce_core: Optional[NonceCore] = None
        self.safety_net: Optional[SafetyNet] = None
        self.market_monitor: Optional[MarketMonitor] = None
        self.txpool_monitor: Optional[TxpoolMonitor] = None
        self.transaction_core: Optional[TransactionCore] = None

        # State
        self.initialized: bool = False
        self.running: bool = False
        self._tasks: List[asyncio.Task[Any]] = []

        # Metrics
        self.metrics: Dict[str, Any] = {
            "chain_id": self.chain_id,
            "chain_name": self.chain_name,
            "wallet_balance_eth": 0.0,
            "last_gas_price_gwei": 0.0,
            "last_block_number": 0,
            "transaction_count": 0,
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0,
            "requests_per_second": 0.0,
        }
        self._last_metrics_ts = time.time()
        self._requests = 0

    async def initialize(self) -> bool:
        """Initialize Web3, account, configs, DB, cores and monitors."""
        try:
            logger.info(f"[{self.chain_name}] Initializing ChainWorker")

            # — Web3 —
            if not await self._init_web3():
                return False

            # — Account —
            if not self.wallet_key:
                logger.error("No WALLET_KEY available")
                return False
            self.account = Account.from_key(self.wallet_key)
            if self.wallet_address and self.wallet_address.lower() != self.account.address.lower():
                logger.warning("Configured WALLET_ADDRESS differs from key")

            # — Configs & API —
            self.api_config = APIConfig(self.config)
            await self.api_config.initialize()

            # — Persistence —
            self.db = await get_db_manager()

            # — Cores & Monitors —
            self.nonce_core = NonceCore(self.web3, self.config)
            await self.nonce_core.initialize()

            self.safety_net = SafetyNet(
                web3=self.web3,
                config=self.config,
                account_address=self.account.address,
                account=self.account,
                api_config=self.api_config,
            )
            await self.safety_net.initialize()

            self.market_monitor = MarketMonitor(
                web3=self.web3, config=self.config, api_config=self.api_config
            )
            await self.market_monitor.initialize()

            self.transaction_core = TransactionCore(
                web3=self.web3,
                account=self.account,
                configuration=self.config,
                api_config=self.api_config,
                market_monitor=self.market_monitor,
                txpool_monitor=None,  # set below
                nonce_core=self.nonce_core,
                safety_net=self.safety_net,
            )
            await self.transaction_core.initialize()

            tokens = self.config.get("MONITORED_TOKENS", [])
            self.txpool_monitor = TxpoolMonitor(
                web3=self.web3,
                safety_net=self.safety_net,
                nonce_core=self.nonce_core,
                api_config=self.api_config,
                monitored_tokens=tokens,
                configuration=self.config,
                market_monitor=self.market_monitor,
            )
            await self.txpool_monitor.initialize()
            self.transaction_core.txpool_monitor = self.txpool_monitor

            # — Warm‐up metrics —
            await self.get_wallet_balance()
            await self.get_gas_price()

            self.initialized = True
            logger.info(f"[{self.chain_name}] Initialization complete")
            return True

        except Exception as e:
            logger.exception(f"[{self.chain_name}] Initialization failed: {e}")
            return False

    async def start(self) -> None:
        """Start monitors and periodic tasks."""
        if not self.initialized:
            logger.error("Cannot start before initialize()")
            return
        if self.running:
            logger.warning("Already running")
            return

        logger.info(f"[{self.chain_name}] Starting worker")
        self.running = True

        # Launch txpool + market monitors
        self._tasks.append(asyncio.create_task(self.txpool_monitor.start_monitoring()))
        self._tasks.append(asyncio.create_task(self.market_monitor.schedule_updates()))

        # Periodic metrics and opportunity checks
        self._tasks.append(asyncio.create_task(self._periodic_metrics()))
        self._tasks.append(asyncio.create_task(self._periodic_opportunities()))

    async def stop(self) -> None:
        """Stop all tasks and monitors."""
        logger.info(f"[{self.chain_name}] Stopping worker")
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        await self.txpool_monitor.stop()
        await self.safety_net.stop()
        await self.market_monitor.stop()
        await self.nonce_core.close()

        logger.info(f"[{self.chain_name}] Stopped")

    # — Metrics —

    async def get_wallet_balance(self) -> float:
        """Fetch and record ETH balance."""
        try:
            bal = await self.web3.eth.get_balance(self.account.address)
            eth = float(self.web3.from_wei(bal, "ether"))
            self.metrics["wallet_balance_eth"] = eth
            return eth
        except Exception:
            return 0.0

    async def get_gas_price(self) -> float:
        """Fetch dynamic gas price via SafetyNet."""
        try:
            gwei = await self.safety_net.get_dynamic_gas_price()
            self.metrics["last_gas_price_gwei"] = gwei
            return gwei
        except Exception:
            return 0.0

    async def _periodic_metrics(self) -> None:
        interval = self.chain_cfg.get("METRICS_UPDATE_INTERVAL", 30)
        while self.running:
            try:
                # update chain head
                blk = await self.web3.eth.block_number
                self.metrics["last_block_number"] = blk
                # db stats
                if self.db:
                    cnt = await self.db.get_transaction_count(self.chain_id, self.account.address)
                    if cnt is not None:
                        self.metrics["transaction_count"] = cnt
                    prof = await self.db.get_profit_summary(self.chain_id, self.account.address)
                    if prof:
                        self.metrics["total_profit_eth"] = prof.get("total_profit_eth", 0.0)
                        self.metrics["total_gas_spent_eth"] = prof.get("total_gas_spent_eth", 0.0)
                # RPS
                now = time.time()
                elapsed = now - self._last_metrics_ts
                if elapsed >= 1:
                    self.metrics["requests_per_second"] = self._requests / elapsed
                    self._requests = 0
                    self._last_metrics_ts = now
                # log.debug if needed
            except Exception as e:
                logger.error(f"Metrics update error: {e}")
            await asyncio.sleep(interval)

    # — Opportunity scanning stub —

    async def _periodic_opportunities(self) -> None:
        interval = self.chain_cfg.get("OPPORTUNITY_CHECK_INTERVAL", 60)
        while self.running:
            try:
                # placeholder for actual opportunity logic
                logger.debug(f"[{self.chain_name}] Scanning opportunities…")
            except Exception as e:
                logger.error(f"Opportunity scan error: {e}")
            await asyncio.sleep(interval)

    # — Web3 setup & verify —

    async def _init_web3(self) -> bool:
        if not self.http_endpoint:
            logger.error("HTTP_ENDPOINT not configured")
            return False
        self.web3 = AsyncWeb3(AsyncHTTPProvider(self.http_endpoint))
        # Attempt POA middleware
        try:
            from web3.middleware import ExtraDataToPOAMiddleware
            logger.debug("Injecting ExtraDataToPOAMiddleware for POA chains")
            # This middleware is used for POA chains to handle extra data in blocks
            self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except ImportError:
            pass
        # verify
        return await self._verify_connection()

    async def _verify_connection(self) -> bool:
        try:
            onchain = await self.web3.eth.chain_id
            if str(onchain) != self.chain_id:
                logger.error(f"Chain ID mismatch: {onchain} != {self.chain_id}")
                return False
            blk = await self.web3.eth.get_block("latest")
            self.metrics["last_block_number"] = blk["number"]
            return True
        except Exception as e:
            logger.error(f"Web3 connection verify failed: {e}")
            return False

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – MainCore
=====================
Boot-straps every long-lived component, owns the single AsyncIO event-loop,
and exposes `.run()`, `.stop()`, and `.connect()` for callers (CLI, Flask UI, tests).
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from __future__ import annotations

import asyncio
import inspect
import time
import tracemalloc
from typing import Any, Dict, List, Optional

from eth_account import Account
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import AsyncHTTPProvider, IPCProvider, WebSocketProvider

from on1builder.config.config import APIConfig, Configuration
from on1builder.core.nonce_core import NonceCore
from on1builder.core.transaction_core import TransactionCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.engines.strategy_net import StrategyNet
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.monitoring.txpool_monitor import TxpoolMonitor
from on1builder.utils.logger import setup_logging
from on1builder.utils.strategyexecutionerror import StrategyExecutionError

logger = setup_logging("MainCore", level="DEBUG")

_POA_CHAINS: set[int] = {99, 100, 77, 7766, 56, 11155111}


class MainCore:
    logger = logger

    def __init__(self, configuration: Configuration) -> None:
        self.cfg = configuration
        self.web3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self._bg: List[asyncio.Task[Any]] = []
        self._running_evt = asyncio.Event()
        self._stop_evt = asyncio.Event()
        self.components: Dict[str, Any] = {}
        self.component_health: Dict[str, bool] = {}

        if not tracemalloc.is_tracing():
            tracemalloc.start()
        self._mem_snapshot = tracemalloc.take_snapshot()

    async def connect(self) -> bool:
        conn = self._connect_web3()
        web3 = await conn if inspect.isawaitable(conn) else conn

        try:
            connected = await web3.is_connected()
        except TypeError:
            connected = web3.is_connected()

        if connected:
            self.web3 = web3
            return True
        return False

    async def connect_websocket(self) -> bool:
        if not self.web3:
            logger.error("Web3.py is not installed")
            return False

        if not getattr(self.cfg, "WEBSOCKET_ENDPOINT", None):
            logger.warning("No WebSocket endpoint configured")
            return False

        retry_count = getattr(self.cfg, "CONNECTION_RETRY_COUNT", 3)
        retry_delay = getattr(self.cfg, "CONNECTION_RETRY_DELAY", 1.0)

        for attempt in range(retry_count + 1):
            try:
                provider = WebSocketProvider(self.cfg.WEBSOCKET_ENDPOINT)
                web3 = AsyncWeb3(provider)

                if hasattr(web3.eth, "chain_id"):
                    try:
                        chain_id = await web3.eth.chain_id
                    except TypeError:
                        chain_id = 1
                else:
                    chain_id = 1

                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")

                if hasattr(web3.is_connected, "__await__"):
                    connected = await web3.is_connected()
                else:
                    connected = web3.is_connected()

                if connected:
                    self.web3 = web3
                    logger.info(f"Connected to WebSocket endpoint: {self.cfg.WEBSOCKET_ENDPOINT}")
                    return True

            except Exception as e:
                if attempt < retry_count:
                    logger.warning(f"WebSocket connection attempt {attempt + 1}/{retry_count + 1} failed: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"All WebSocket connection attempts failed: {e}")
                    return False

        return False

    async def run(self) -> None:
        await self._bootstrap()
        self._running_evt.set()
        self._bg = []

        if "txpool_monitor" in self.components:
            self._bg.append(asyncio.create_task(self.components["txpool_monitor"].start_monitoring(), name="MM_run"))

        self._bg.append(asyncio.create_task(self._tx_processor(), name="TX_proc"))
        self._bg.append(asyncio.create_task(self._heartbeat(), name="Heartbeat"))

        try:
            await asyncio.shield(self._stop_evt.wait())
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.stop()
            logger.info("MainCore run() finished")

    async def stop(self) -> None:
        if self._stop_evt.is_set():
            return
        self._stop_evt.set()
        logger.info("MainCore stopping...")

        for task in self._bg:
            if not task.done():
                task.cancel()

        if self._bg:
            try:
                await asyncio.gather(*self._bg, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error during task shutdown: {e}")

        if getattr(self.web3, "provider", None) and hasattr(self.web3.provider, "disconnect"):
            try:
                await self.web3.provider.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting web3 provider: {e}")

        for name, component in self.components.items():
            if hasattr(component, "stop") and callable(component.stop):
                try:
                    await component.stop()
                    logger.debug(f"Component {name} stopped")
                except Exception as e:
                    logger.error(f"Error stopping component {name}: {e}")

        self._bg = []
        logger.info("MainCore stopped")

    async def _bootstrap(self) -> None:
        logger.info("Bootstrapping components...")
        await self.cfg.load()

        self.web3 = await self._connect_web3()
        if not self.web3:
            raise StrategyExecutionError("Failed to create Web3 connection")

        self.account = await self._create_account()
        if not self.account:
            raise StrategyExecutionError("Failed to create account")

        self.components["api_config"] = await self._mk_api_config()
        self.components["nonce_core"] = await self._mk_nonce_core()
        self.components["safety_net"] = await self._mk_safety_net()
        self.components["transaction_core"] = await self._mk_txcore()
        self.components["market_monitor"] = await self._mk_market_monitor()
        self.components["txpool_monitor"] = await self._mk_txpool_monitor()
        self.components["strategy_net"] = await self._mk_strategy_net()

        logger.info("All components initialized")

    async def _connect_web3(self) -> Optional[AsyncWeb3]:
        return await self._create_web3_connection()

    async def _mk_api_config(self) -> APIConfig:
        api = APIConfig(self.cfg)
        await api.initialize()
        return api

    async def _mk_nonce_core(self) -> NonceCore:
        return await self._create_nonce_core()

    async def _mk_safety_net(self) -> SafetyNet:
        return await self._create_safety_net()

    async def _mk_txcore(self) -> TransactionCore:
        return await self._create_transaction_core()

    async def _mk_market_monitor(self) -> MarketMonitor:
        return await self._create_market_monitor()

    async def _mk_txpool_monitor(self) -> TxpoolMonitor:
        return await self._create_txpool_monitor()

    async def _mk_strategy_net(self) -> StrategyNet:
        return await self._create_strategy_net()

    async def _create_web3_connection(self) -> Optional[AsyncWeb3]:
        try:
            if self.cfg.HTTP_ENDPOINT:
                provider = AsyncHTTPProvider(self.cfg.HTTP_ENDPOINT)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                logger.info(f"Connected to HTTP endpoint: {self.cfg.HTTP_ENDPOINT}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to HTTP endpoint: {e}")

        try:
            if self.cfg.WEBSOCKET_ENDPOINT:
                provider = WebSocketProvider(self.cfg.WEBSOCKET_ENDPOINT)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                logger.info(f"Connected to WebSocket endpoint: {self.cfg.WEBSOCKET_ENDPOINT}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to WebSocket endpoint: {e}")

        try:
            if self.cfg.IPC_ENDPOINT:
                provider = IPCProvider(self.cfg.IPC_ENDPOINT)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                logger.info(f"Connected to IPC endpoint: {self.cfg.IPC_ENDPOINT}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to IPC endpoint: {e}")

        logger.error("Failed to connect to any Web3 endpoint")
        return None

    async def _create_account(self) -> Optional[Account]:
        if hasattr(self.cfg, "WALLET_KEY") and self.cfg.WALLET_KEY:
            return Account.from_key(self.cfg.WALLET_KEY)
        logger.error("No WALLET_KEY provided in configuration")
        return None

    async def _create_nonce_core(self) -> NonceCore:
        nonce_core = NonceCore(self.web3, self.cfg)
        await nonce_core.initialize()
        return nonce_core

    async def _create_safety_net(self) -> SafetyNet:
        safety_net = SafetyNet(self.web3, self.cfg, self.account)
        await safety_net.initialize()
        return safety_net

    async def _create_transaction_core(self) -> TransactionCore:
        chain_id = await self.web3.eth.chain_id if self.web3 else 1
        tx_core = TransactionCore(
            self.web3,
            self.account,
            self.cfg,
            self.components["nonce_core"],
            self.components["safety_net"],
            chain_id=chain_id,
        )
        await tx_core.initialize()
        return tx_core

    async def _create_market_monitor(self) -> MarketMonitor:
        market_monitor = MarketMonitor(self.web3, self.cfg, self.components["api_config"])
        await market_monitor.initialize()
        return market_monitor

    async def _create_txpool_monitor(self) -> TxpoolMonitor:
        txpool_monitor = TxpoolMonitor(
            self.web3, self.cfg, self.components["market_monitor"]
        )
        await txpool_monitor.initialize()
        return txpool_monitor

    async def _create_strategy_net(self) -> StrategyNet:
        strategy_net = StrategyNet(
            self.web3,
            self.cfg,
            self.components["transaction_core"],
            self.components["safety_net"],
            self.components["market_monitor"],
        )
        await strategy_net.initialize()
        return strategy_net

    async def _heartbeat(self) -> None:
        interval = getattr(self.cfg, "HEARTBEAT_INTERVAL", 60)
        memory_report_interval = getattr(self.cfg, "MEMORY_REPORT_INTERVAL", 300)
        health_check_interval = getattr(self.cfg, "HEALTH_CHECK_INTERVAL", 10)

        last_memory_report = 0
        last_health_check = 0

        while not self._stop_evt.is_set():
            try:
                current_time = time.time()
                if current_time - last_health_check >= health_check_interval:
                    await self._check_component_health()
                    last_health_check = current_time

                if current_time - last_memory_report >= memory_report_interval:
                    await self._report_memory_usage()
                    last_memory_report = current_time

                logger.debug("MainCore heartbeat - System operational")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Heartbeat task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
                await asyncio.sleep(5)

    async def _tx_processor(self) -> None:
        interval = getattr(self.cfg, "TX_PROCESSOR_INTERVAL", 5)
        while not self._stop_evt.is_set():
            try:
                logger.debug("Transaction processor checking for new transactions")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Transaction processor task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in transaction processor: {e}")
                await asyncio.sleep(5)

    async def _check_component_health(self) -> None:
        for name, component in self.components.items():
            try:
                if hasattr(component, "check_health") and callable(component.check_health):
                    health_status = await component.check_health()
                    self.component_health[name] = health_status
                    if not health_status:
                        logger.warning(f"Component {name} reports unhealthy state")
                else:
                    self.component_health[name] = True
            except Exception as e:
                logger.error(f"Error checking health of {name}: {e}")
                self.component_health[name] = False

    async def _report_memory_usage(self) -> None:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            return
        try:
            current_snapshot = tracemalloc.take_snapshot()
            top_stats = current_snapshot.compare_to(self._mem_snapshot, "lineno")
            logger.info("Top 10 memory usage differences:")
            for stat in top_stats[:10]:
                logger.info(str(stat))
        except Exception as e:
            logger.error(f"Error generating memory report: {e}")

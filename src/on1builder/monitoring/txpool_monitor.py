#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – TxpoolMonitor
===========================
Monitors the Ethereum mempool through pending transaction filters or
block polling. Surfaces profitable transactions for StrategyNet.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil
from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound

from on1builder.config.config import APIConfig, Configuration
from on1builder.core.nonce_core import NonceCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.utils.logger import setup_logging

logger = setup_logging("TxpoolMonitor", level="DEBUG")


class TxpoolMonitor:
    """Watches the mempool (or latest blocks as a fallback) and surfaces
    profitable transactions for StrategyNet."""

    def __init__(
        self,
        web3: AsyncWeb3,
        safety_net: SafetyNet,
        nonce_core: NonceCore,
        api_config: APIConfig,
        monitored_tokens: List[str],
        configuration: Configuration,
        market_monitor: MarketMonitor,
    ) -> None:
        self.web3 = web3
        self.safety_net = safety_net
        self.nonce_core = nonce_core
        self.api_config = api_config
        self.market_monitor = market_monitor
        self.configuration = configuration

        # Normalize token list to lowercase addresses
        self.monitored_tokens: Set[str] = set()
        for t in monitored_tokens:
            if t.startswith("0x"):
                self.monitored_tokens.add(t.lower())
            else:
                addr = api_config.get_token_address(t)
                if addr:
                    self.monitored_tokens.add(addr.lower())
                else:
                    logger.warning(f"Could not find address for token symbol: {t}, skipping")

        # Queues for hashes, analysis, and profitable txs
        self._tx_hash_queue: asyncio.Queue[str] = asyncio.Queue()
        self._tx_analysis_queue: asyncio.Queue[Tuple[int, str]] = asyncio.Queue()
        self.profitable_transactions: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        self._tasks: List[asyncio.Task[Any]] = []
        self._running: bool = False

        self._processed_hashes: Set[str] = set()
        self._tx_cache: Dict[str, Dict[str, Any]] = {}

        max_parallel = configuration.get("MEMPOOL_MAX_PARALLEL_TASKS", 10)
        self._semaphore = asyncio.Semaphore(max_parallel)

        self._stop_event = asyncio.Event()

        # Simple queue control
        self.processed_txs: Set[str] = set()
        self.tx_queue: List[Tuple[str, Dict[str, Any]]] = []
        self.min_gas: int = configuration.get("MIN_GAS", 0)
        self.max_queue_size: int = configuration.get("MAX_QUEUE_SIZE", 1000)
        self.queue_event: asyncio.Event = asyncio.Event()
        self.use_txpool_api: bool = configuration.get("USE_TXPOOL_API", False)

    async def initialize(self) -> None:
        """Prepare for monitoring; does not start background tasks yet."""
        self._tx_hash_queue = asyncio.Queue()
        self._tx_analysis_queue = asyncio.Queue()
        self.profitable_transactions = asyncio.Queue()
        self._processed_hashes.clear()
        self._tx_cache.clear()
        self._running = False

    async def start_monitoring(self) -> None:
        """Start background tasks to collect and analyze transactions."""
        if self._running:
            return
        self._running = True

        self._tasks = [
            asyncio.create_task(self._collect_hashes(), name="TXM_collect_hashes"),
            asyncio.create_task(self._analysis_dispatcher(), name="TXM_analysis"),
        ]
        logger.info(f"TxpoolMonitor: started {len(self._tasks)} background tasks")
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Stop all background tasks."""
        if not self._running:
            return
        self._running = False
        logger.info("TxpoolMonitor: stopping…")

        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("TxpoolMonitor: stopped")

    async def _collect_hashes(self) -> None:
        """Collect tx hashes via pending-filter or block polling."""
        try:
            try:
                filt = await self.web3.eth.filter("pending")
                logger.debug("Using pending-tx filter for mempool monitoring")
            except Exception:
                filt = None
                logger.warning("No pending filters—falling back to block polling")

            if filt:
                await self._collect_from_filter(filt)
            else:
                await self._collect_from_blocks()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Fatal error in _collect_hashes: {e}")
            raise

    async def _collect_from_filter(self, filt: Any) -> None:
        while self._running:
            try:
                entries = await filt.get_new_entries()
                for h in entries:
                    await self._enqueue_hash(h.hex())
            except Exception:
                await asyncio.sleep(1)

    async def _collect_from_blocks(self) -> None:
        last = await self.web3.eth.block_number
        while self._running:
            try:
                current = await self.web3.eth.block_number
                for n in range(last + 1, current + 1):
                    block = await self.web3.eth.get_block(n, full_transactions=True)
                    for tx in block.transactions:  # type: ignore[attr-defined]
                        txh = (tx.hash if hasattr(tx, "hash") else tx["hash"]).hex()
                        await self._enqueue_hash(txh)
                last = current
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _enqueue_hash(self, tx_hash: str) -> None:
        if tx_hash in self._processed_hashes:
            return
        self._processed_hashes.add(tx_hash)
        await self._tx_hash_queue.put(tx_hash)

    async def _analysis_dispatcher(self) -> None:
        """Dispatch analysis tasks for incoming hashes."""
        while not self._stop_event.is_set():
            try:
                tx_hash = await self._tx_hash_queue.get()
                await self._semaphore.acquire()
                asyncio.create_task(self._process_transaction_safe(tx_hash))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dispatcher error: {e}")

    async def _process_transaction_safe(self, tx_hash: str) -> None:
        """Wrapper that handles exceptions in analysis."""
        try:
            await self._analyse_transaction(tx_hash)
        except Exception as e:
            logger.error(f"Error analyzing {tx_hash}: {e}")
        finally:
            self._semaphore.release()
            self._tx_hash_queue.task_done()

    async def _analyse_transaction(self, tx_hash: str) -> None:
        """Fetch, prioritize, and check profitability of a tx."""
        tx = await self._fetch_transaction(tx_hash)
        if not tx:
            return

        priority = self._calc_priority(tx)
        await self._tx_analysis_queue.put((priority, tx_hash))

        result = await self._is_profitable(tx_hash, tx)
        if result:
            await self.profitable_transactions.put(result)

    async def _fetch_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve tx data, with retries on not-found."""
        if tx_hash in self._tx_cache:
            return self._tx_cache[tx_hash]

        delay = self.configuration.get("MEMPOOL_RETRY_DELAY", 0.5)
        max_retries = self.configuration.get("MEMPOOL_MAX_RETRIES", 3)

        for _ in range(max_retries):
            try:
                tx = await self.web3.eth.get_transaction(tx_hash)
                self._tx_cache[tx_hash] = tx
                return tx
            except TransactionNotFound:
                await asyncio.sleep(delay)
                delay *= 1.5
            except Exception as e:
                logger.debug(f"Fetch tx {tx_hash} error: {e}")
                break
        return None

    def _calc_priority(self, tx: Dict[str, Any]) -> int:
        """Lower integers = higher priority (negate gas price)."""
        gp_legacy = tx.get("gasPrice", 0) or 0
        gp_1559 = tx.get("maxFeePerGas", 0) or 0
        effective = max(gp_legacy, gp_1559)
        return -int(effective)

    async def _is_profitable(
        self, tx_hash: str, tx: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Lightweight profit check: filter by monitored tokens and value."""
        to_addr = (tx.get("to") or "").lower()
        if to_addr not in self.monitored_tokens:
            return None

        value = tx.get("value", 0)
        if value <= 0:
            return None

        gas_used = await self.safety_net.estimate_gas(tx)
        gp = tx.get("gasPrice", tx.get("maxFeePerGas", 0))
        gp_gwei = float(self.web3.from_wei(gp, "gwei"))

        tx_data = {
            "output_token": to_addr,
            "amountIn": float(self.web3.from_wei(value, "ether")),
            "amountOut": float(self.web3.from_wei(value, "ether")),
            "gas_price": gp_gwei,
            "gas_used": gas_used,
        }

        safe, details = await self.safety_net.check_transaction_safety(tx_data)
        profit_passed = details["check_details"].get("profit_check", {}).get("passed", False)
        if safe and profit_passed:
            return {
                "is_profitable": True,
                "tx_hash": tx_hash,
                "tx": tx,
                "analysis": details,
                "strategy_type": "front_run",
            }
        return None

    async def is_healthy(self) -> bool:
        """Check health of the txpool monitor."""
        try:
            if not await self.web3.is_connected():
                logger.warning("Web3 connection is down")
                return False

            if self.use_txpool_api:
                try:
                    await self.web3.geth.txpool.status()
                except Exception as e:
                    logger.warning(f"Txpool API unavailable: {e}")

            if not await self.safety_net.is_healthy():
                logger.warning("SafetyNet is unhealthy")
                return False

            if self._stop_event.is_set():
                logger.warning("TxpoolMonitor has been stopped")
                return False

            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def _monitor_memory(self) -> None:
        """Periodically clean caches based on memory pressure."""
        interval = self.configuration.get("MEMORY_CHECK_INTERVAL", 300)
        max_cache = self.configuration.get("MAX_TXPOOL_CACHE_SIZE", 10000)

        while not self._stop_event.is_set():
            await asyncio.sleep(interval)
            mem = psutil.virtual_memory().percent
            logger.debug(f"Memory usage: {mem}%")

            if mem > 80:
                logger.warning(f"High memory usage ({mem}%), clearing caches")
                self.processed_txs.clear()
                self._tx_cache.clear()
            elif len(self.processed_txs) > max_cache:
                kept = list(self.processed_txs)[-max_cache:]
                self.processed_txs = set(kept)
                logger.info(f"Trimmed processed_txs to {max_cache} entries")

            logger.debug(
                f"TxpoolMonitor memory stats: {len(self.processed_txs)} processed txs, "
                f"{len(self.tx_queue)} queued"
            )

    async def stop_monitoring(self) -> None:
        """Alias for stop()."""
        await self.stop()

# txpool_monitor.py
"""
ON1Builder – TxpoolMonitor

Monitors the Ethereum mempool trough pending transaction filters or block polling.
Surfaces profitable transactions for StrategyNet
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound

from configuration import Configuration
from safety_net import SafetyNet
from nonce_core import NonceCore
from api_config import APIConfig
from market_monitor import MarketMonitor
from logger_on1 import setup_logging

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

        # normalise token list to lower-case addresses
        self.monitored_tokens = {
            (
                api_config.get_token_address(t).lower()
                if not t.startswith("0x")
                else t.lower()
            )
            for t in monitored_tokens
        }

        # queues -------------------------------------------------------------
        self._tx_hash_queue: asyncio.Queue[str] = asyncio.Queue()
        self._tx_analysis_queue: asyncio.Queue[str] = asyncio.Queue()
        self.profitable_transactions: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(
        )

        # task book-keeping
        self._tasks: List[asyncio.Task] = []
        self._running: bool = False

        # misc
        self._processed_hashes: set[str] = set()
        self._tx_cache: Dict[str, Dict[str, Any]] = {}

        # concurrency guard
        self._semaphore = asyncio.Semaphore(
            self.configuration.MEMPOOL_MAX_PARALLEL_TASKS
        )

    async def initialize(self) -> None:
        """Prepare for monitoring; does not start background tasks yet."""
        # ensure queues clean on hot-reload
        self._tx_hash_queue = asyncio.Queue()
        self._tx_analysis_queue = asyncio.Queue()
        self.profitable_transactions = asyncio.Queue()
        self._processed_hashes.clear()
        self._tx_cache.clear()
        self._running = False

    # ---------- public control ---------------------------------------------

    async def start_monitoring(self) -> None:
        if self._running:
            return
        self._running = True

        # spawn background tasks
        self._tasks = [
            asyncio.create_task(
                self._collect_hashes(),
                name="MM_collect_hashes"),
            asyncio.create_task(
                self._analysis_dispatcher(),
                name="MM_analysis_dispatcher"),
        ]
        logger.info(
            "TxpoolMonitor: started %d background tasks", len(
                self._tasks))

        # allow caller to await until stopped
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        logger.info("TxpoolMonitor: stopping…")

        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("TxpoolMonitor: stopped")

    # ---------- collectors --------------------------------------------------

    async def _collect_hashes(self) -> None:
        """Collect tx-hashes either via `eth_newPendingTransactionFilter`
        or by block-polling fallback."""
        try:
            try:
                filter_obj = await self.web3.eth.filter("pending")
                logger.debug("Using pending-tx filter for mempool monitoring")
            except Exception:
                filter_obj = None
                logger.warning(
                    "Node does not support pending filters – falling back to block polling"
                )

            if filter_obj:
                await self._collect_from_filter(filter_obj)
            else:
                await self._collect_from_blocks()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("Fatal error in _collect_hashes: %s", exc)
            raise

    async def _collect_from_filter(self, filter_obj: Any) -> None:
        while self._running:
            try:
                new_hashes = await filter_obj.get_new_entries()
                for h in new_hashes:
                    await self._enqueue_hash(h.hex())
            except Exception:
                await asyncio.sleep(1)

    async def _collect_from_blocks(self) -> None:
        last_block = await self.web3.eth.block_number
        while self._running:
            try:
                current = await self.web3.eth.block_number
                for n in range(last_block + 1, current + 1):
                    block = await self.web3.eth.get_block(n, full_transactions=True)
                    for tx in block.transactions:  # type: ignore[attr-defined]
                        txh = (
                            tx.hash if hasattr(
                                tx, "hash") else tx["hash"]).hex()
                        await self._enqueue_hash(txh)
                last_block = current
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _enqueue_hash(self, tx_hash: str) -> None:
        if tx_hash in self._processed_hashes:
            return
        self._processed_hashes.add(tx_hash)
        await self._tx_hash_queue.put(tx_hash)

    # ---------- dispatcher / analyser --------------------------------------

    async def _analysis_dispatcher(self) -> None:
        while self._running:
            tx_hash = await self._tx_hash_queue.get()
            await self._semaphore.acquire()
            asyncio.create_task(self._analyse_transaction(tx_hash))

    async def _analyse_transaction(self, tx_hash: str) -> None:
        try:
            tx = await self._fetch_transaction(tx_hash)
            if not tx:
                return

            priority = self._calc_priority(tx)
            # push into analysis queue according to priority
            await self._tx_analysis_queue.put((priority, tx_hash))

            # actual profitability analysis (single-thread for clarity)
            profitable = await self._is_profitable(tx_hash, tx)
            if profitable:
                await self.profitable_transactions.put(profitable)

        finally:
            self._semaphore.release()

    # ---------- helpers ----------------------------------------------------

    async def _fetch_transaction(
            self, tx_hash: str) -> Optional[Dict[str, Any]]:
        if tx_hash in self._tx_cache:
            return self._tx_cache[tx_hash]

        delay = self.configuration.MEMPOOL_RETRY_DELAY
        for _ in range(self.configuration.MEMPOOL_MAX_RETRIES):
            try:
                tx = await self.web3.eth.get_transaction(tx_hash)
                self._tx_cache[tx_hash] = tx
                return tx
            except TransactionNotFound:
                await asyncio.sleep(delay)
                delay *= 1.5
            except Exception:
                break
        return None

    # ---------- analysis ---------------------------------------------------

    def _calc_priority(self, tx: Dict[str, Any]) -> int:
        """Lower integer == higher priority for PriorityQueue.
        We negate gas-price so that higher gas = lower integer."""
        gp_legacy = tx.get("gasPrice", 0) or 0
        gp_1559 = tx.get("maxFeePerGas", 0) or 0
        effective_gp = max(gp_legacy, gp_1559)
        return -int(effective_gp)

    async def _is_profitable(
        self, tx_hash: str, tx: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Very lightweight profitability heuristic – just enough to
        surface to StrategyNet.  Heavy simulation lives elsewhere."""
        to_addr = (tx.get("to") or "").lower()
        if to_addr not in self.monitored_tokens:
            return None

        value = tx.get("value", 0)
        if value <= 0:
            return None

        gas_used_est = await self.safety_net.estimate_gas(tx)
        gas_price_gwei = self.web3.from_wei(
            tx.get("gasPrice", tx.get("maxFeePerGas", 0)), "gwei"
        )

        tx_data = {
            "output_token": to_addr,
            "amountIn": float(self.web3.from_wei(value, "ether")),
            "amountOut": float(self.web3.from_wei(value, "ether")),
            "gas_price": float(gas_price_gwei),
            "gas_used": float(gas_used_est),
        }

        safe, details = await self.safety_net.check_transaction_safety(
            tx_data, check_type="profit"
        )
        if safe and details.get("profit_ok", False):
            return {
                "is_profitable": True,
                "tx_hash": tx_hash,
                "tx": tx,
                "analysis": details,
                "strategy_type": "front_run",
            }
        return None

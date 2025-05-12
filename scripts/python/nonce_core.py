# nonce_core.py
"""
ON1Builder – NonceCore
======================
A lightweight nonce management system for Ethereum transactions.
It handles nonce caching, reservation, and periodic synchronization with the Ethereum blockchain.
It uses a local cache to store nonces and a background task to keep the cache in sync with the chain.
"""

from __future__ import annotations

import asyncio
import random
import contextlib
from typing import Optional, Set

from cachetools import TTLCache
from web3 import AsyncWeb3
from web3.exceptions import Web3ValueError

from configuration import Configuration
from logger_on1 import setup_logging

logger = setup_logging("Nonce_Core", level="DEBUG")


class NonceCore:
    """Manages Ethereum nonces with local caching + on-chain reconciliation."""

    def __init__(self, web3: AsyncWeb3, address: str, configuration: Configuration) -> None:
        self.web3 = web3
        self.cfg = configuration
        self.address = address.lower()

        # allow a handful of cached entries (nonce, timestamp)
        self._nonce_cache: TTLCache[str, int] = TTLCache(
            maxsize=32, ttl=self.cfg.NONCE_CACHE_TTL
        )

        # reservation set for tx we’ve fired but not yet seen mined
        self._reserved: Set[int] = set()

        # sync machinery
        self._lock = asyncio.Lock()
        self._periodic_task: Optional[asyncio.Task] = None
        self._running = False

    # ------------------------------------------------------------------ #
    # public interface                                                   #
    # ------------------------------------------------------------------ #

    async def initialize(self) -> None:
        if self._running:
            return

        await self._refresh_from_chain()
        self._running = True
        self._periodic_task = asyncio.create_task(self._periodic_sync_loop())
        logger.debug("NonceCore initialised – starting periodic sync task.")

    async def get_nonce(self) -> int:
        """Return the next free nonce & reserve it immediately."""
        if not self._running:
            await self.initialize()

        async with self._lock:
            base = self._nonce_cache.get(self.address, 0)
            nonce = base
            while nonce in self._reserved:
                nonce += 1

            # store and reserve
            self._nonce_cache[self.address] = nonce + 1  # advance pointer
            self._reserved.add(nonce)
            logger.debug("Handed out nonce %d (reserved set size=%d)", nonce, len(self._reserved))
            return nonce

    async def track_transaction(self, tx_hash: str, nonce: int) -> None:
        """Block until the supplied tx is mined or times-out, then un-reserve."""
        async def _wait():
            try:
                await self.web3.eth.wait_for_transaction_receipt(
                    tx_hash, timeout=self.cfg.NONCE_TRANSACTION_TIMEOUT
                )
            except Exception:
                pass

        asyncio.create_task(_wait())  # detached wait; we still un-reserve after timeout window

        # schedule un-reserve after timeout to avoid leaking
        asyncio.get_running_loop().call_later(
            self.cfg.NONCE_TRANSACTION_TIMEOUT, self._reserved.discard, nonce
        )

    async def refresh_nonce(self) -> None:
        """Manually force a cache refresh from chain."""
        await self._refresh_from_chain()

    async def stop(self) -> None:
        """Cancel background polling and clear cache."""
        self._running = False
        if self._periodic_task:
            self._periodic_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._periodic_task
            self._periodic_task = None
        self._reserved.clear()
        self._nonce_cache.clear()
        logger.debug("NonceCore stopped gracefully.")

    # ------------------------------------------------------------------ #
    # internals                                                          #
    # ------------------------------------------------------------------ #

    async def _refresh_from_chain(self) -> None:
        async with self._lock:
            try:
                on_chain = await self._fetch_with_retry()
                pending = await self._fetch_with_retry(pending=True)
                next_nonce = max(on_chain, pending, default=0)
                self._nonce_cache[self.address] = next_nonce
                logger.debug("Nonce refreshed – chain=%d pending=%d ► cache=%d", on_chain, pending, next_nonce)
            except Exception as exc:
                logger.error("Refresh nonce failed: %s", exc, exc_info=True)

    async def _fetch_with_retry(self, pending: bool = False) -> int:
        delay = self.cfg.NONCE_RETRY_DELAY
        for _ in range(self.cfg.NONCE_MAX_RETRIES):
            try:
                return await self.web3.eth.get_transaction_count(
                    self.address, "pending" if pending else "latest"
                )
            except Exception:
                await asyncio.sleep(delay + random.uniform(0, delay))
                delay *= 2
        raise Web3ValueError("Failed to fetch nonce after retries")

    async def _periodic_sync_loop(self) -> None:
        """Background task to keep local pointer in sync with the chain."""
        try:
            while self._running:
                await asyncio.sleep(self.cfg.NONCE_CACHE_TTL)
                await self._refresh_from_chain()
        except asyncio.CancelledError:
            pass

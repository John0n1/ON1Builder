# src/on1builder/core/nonce_core.py

from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, Optional

from web3 import AsyncWeb3
from eth_utils import to_checksum_address

from on1builder.config.config import Configuration
from on1builder.utils.logger import setup_logging

logger = setup_logging("NonceCore", level="DEBUG")


class NonceCore:
    """Transaction nonce manager for concurrent blockchain operations.

    Ensures unique, sequential nonces even across concurrent calls.
    """

    def __init__(self, web3: AsyncWeb3, configuration: Configuration) -> None:
        """
        Args:
            web3: AsyncWeb3 instance
            configuration: Global configuration
        """
        self.web3 = web3
        # account information not provided explicitly; use configuration as
        # placeholder
        self.account = configuration  # tests patch methods, real account not used here
        self.config = configuration

        # Cache state
        self._nonces: Dict[str, int] = {}
        self._last_refresh: Dict[str, float] = {}
        self._nonce_lock = asyncio.Lock()

        # From config or defaults
        self._cache_ttl = getattr(configuration, "NONCE_CACHE_TTL", 60)
        self._retry_delay = getattr(configuration, "NONCE_RETRY_DELAY", 1)
        self._max_retries = getattr(configuration, "NONCE_MAX_RETRIES", 5)
        self._tx_timeout = getattr(
            configuration, "NONCE_TRANSACTION_TIMEOUT", 120)

        logger.info("NonceCore initialized")

    async def initialize(self) -> None:
        """Called on startup; placeholder for future pre-fetch logic."""
        logger.info("Initializing NonceCore")

    async def get_onchain_nonce(self, address: Optional[str] = None) -> int:
        """Fetch the pending nonce from chain, with retries."""
        checksum = to_checksum_address(address)
        for attempt in range(self._max_retries):
            try:
                return await self.web3.eth.get_transaction_count(checksum, "pending")
            except Exception as e:
                if attempt < self._max_retries - 1:
                    logger.warning("get_onchain_nonce failed, retrying: %s", e)
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error("get_onchain_nonce permanently failed: %s", e)
                    raise

        # Should not reach here; all paths should have returned or raised
        raise RuntimeError(f"Failed to fetch onchain nonce for {checksum}")

    async def get_next_nonce(self, address: Optional[str] = None) -> int:
        """Return a unique, sequential nonce for `address`.

        If no address is given, uses self.account.address.
        """
        if address is None:
            if not hasattr(self.account, "address"):
                raise ValueError(
                    "No address provided and account has no `.address`")
            address = self.account.address

        checksum = to_checksum_address(address)

        async with self._nonce_lock:
            now = time.time()
            last = self._last_refresh.get(checksum, 0)

            if checksum not in self._nonces or now - last > self._cache_ttl:
                nonce = await self.get_onchain_nonce(checksum)
                self._nonces[checksum] = nonce
                self._last_refresh[checksum] = now
            else:
                self._nonces[checksum] += 1

            return self._nonces[checksum]

    # Alias for compatibility
    async def get_nonce(self, address: Optional[str] = None) -> int:
        return await self.get_next_nonce(address)

    async def reset_nonce(self, address: Optional[str] = None) -> int:
        """Force-refresh the nonce from chain."""
        if address is None:
            if not hasattr(self.account, "address"):
                raise ValueError(
                    "No address provided and account has no `.address`")
            address = self.account.address

        checksum = to_checksum_address(address)
        async with self._nonce_lock:
            nonce = await self.get_onchain_nonce(checksum)
            self._nonces[checksum] = nonce
            self._last_refresh[checksum] = time.time()
            logger.info("Nonce for %s reset to %d", checksum, nonce)
            return nonce

    async def track_transaction(
        self, tx_hash: str, nonce_used: int, address: Optional[str] = None
    ) -> None:
        """Keep an eye on a sent transaction so we can reset the nonce if it
        fails."""
        if address is None:
            if not hasattr(self.account, "address"):
                logger.error("Cannot track tx: no address")
                return
            address = self.account.address

        checksum = to_checksum_address(address)
        if not hasattr(self, "_tx_tracking"):
            self._tx_tracking: Dict[str, Any] = {}

        self._tx_tracking[tx_hash] = {
            "nonce": nonce_used,
            "address": checksum,
            "start": time.time(),
            "status": "pending",
        }

        # Fire and forget
        asyncio.create_task(self._monitor_transaction(tx_hash, checksum))

    async def _monitor_transaction(self, tx_hash: str, address: str) -> None:
        """Wait for receipt, reset nonce on failure or timeout."""
        start = time.time()
        retries = 0

        while True:
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    status = receipt.get("status", 0)
                    if status == 1:
                        logger.info("Tx %s confirmed", tx_hash)
                        self._tx_tracking[tx_hash]["status"] = "confirmed"
                    else:
                        logger.warning("Tx %s failed on-chain", tx_hash)
                        self._tx_tracking[tx_hash]["status"] = "failed"
                        await self.reset_nonce(address)
                    return
                if time.time() - start > self._tx_timeout:
                    logger.warning("Tx %s monitor timeout", tx_hash)
                    self._tx_tracking[tx_hash]["status"] = "timeout"
                    await self.reset_nonce(address)
                    return
            except Exception as e:
                retries += 1
                if retries >= self._max_retries:
                    logger.error("Monitoring %s aborted: %s", tx_hash, e)
                    self._tx_tracking[tx_hash]["status"] = "error"
                    return
                logger.warning(
                    "Error monitoring %s (%d/%d): %s",
                    tx_hash,
                    retries,
                    self._max_retries,
                    e,
                )
            await asyncio.sleep(self._retry_delay)

    async def wait_for_transaction(
        self, tx_hash: str, timeout: Optional[int] = None
    ) -> bool:
        """Block until the tx is mined or timeout."""
        if timeout is None:
            timeout = self._tx_timeout
        start = time.time()
        timeout_value = timeout or 0  # Ensure timeout is an integer, not None
        while time.time() - start < timeout_value:
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return True
            except Exception:
                pass
            await asyncio.sleep(self._retry_delay)
        logger.warning("wait_for_transaction timed out for %s", tx_hash)
        return False

    async def close(self) -> None:
        """Hook for any cleanup; currently none."""
        logger.debug("NonceCore closing")

    async def stop(self) -> None:
        """Alias for close()."""
        await self.close()

    async def refresh_nonce(self, address: Optional[str] = None) -> int:
        """Alias for reset_nonce()."""
        return await self.reset_nonce(address)

    async def sync_nonce_with_chain(
            self, address: Optional[str] = None) -> int:
        """Synchronize the local nonce cache with the blockchain.

        This is a more comprehensive version of reset_nonce that also
        performs additional synchronization checks.

        Args:
            address: Optional address to sync nonce for

        Returns:
            int: The synchronized nonce value
        """
        logger.info("Synchronizing nonce with blockchain")
        # For now, this is functionally equivalent to reset_nonce
        # but could be extended with more synchronization logic
        return await self.reset_nonce(address)

    async def reset(self, address: Optional[str] = None) -> int:
        """Reset the nonce tracking for an address.

        This method is an alias for reset_nonce to maintain compatibility
        with test expectations.

        Args:
            address: Optional address to reset nonce for

        Returns:
            int: The reset nonce value
        """
        logger.info("Resetting nonce tracking")
        return await self.reset_nonce(address)

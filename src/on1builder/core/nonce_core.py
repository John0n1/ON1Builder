#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – NonceCore
======================

Transaction nonce manager for concurrent blockchain operations.
Ensures unique, sequential nonces even across concurrent calls.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

from eth_utils import to_checksum_address
from web3 import AsyncWeb3

from on1builder.config.config import Configuration
from on1builder.utils.logger import get_logger

logger = get_logger(__name__)


class NonceCore:
    """Manages nonces for Ethereum accounts, ensuring uniqueness and ordering."""

    def __init__(
        self, 
        web3: AsyncWeb3, 
        configuration: Configuration,
        main_core: Optional[Any] = None  # Reference to MainCore for shared resources
    ) -> None:
        """
        Args:
            web3: AsyncWeb3 instance
            configuration: Global Configuration instance
            main_core: Optional reference to MainCore for shared resources
        """
        self.web3 = web3
        # Tests may patch `get_onchain_nonce`; real account not directly used here
        self.account = configuration
        self.config = configuration
        self.main_core = main_core

        # Access shared components from main_core if available
        self.db_manager = None
        self.notification_manager = None
        if main_core and hasattr(main_core, 'components'):
            self.db_manager = main_core.components.get("db_manager")
            if self.db_manager:
                logger.debug("NonceCore: Using shared DatabaseManager from MainCore")
                
            self.notification_manager = main_core.components.get("notification_manager")
            if self.notification_manager:
                logger.debug("NonceCore: Using shared NotificationManager from MainCore")

        # In-memory caches
        self._nonces: Dict[str, int] = {}
        self._last_refresh: Dict[str, float] = {}
        self._nonce_lock = asyncio.Lock()

        # Configuration-driven parameters
        self._cache_ttl: float = configuration.get("NONCE_CACHE_TTL", 60)
        self._retry_delay: float = configuration.get("NONCE_RETRY_DELAY", 1)
        self._max_retries: int = configuration.get("NONCE_MAX_RETRIES", 5)
        self._tx_timeout: float = configuration.get("NONCE_TRANSACTION_TIMEOUT", 120)

        logger.info("NonceCore initialized")

    async def initialize(self) -> None:
        """Perform any necessary initialization."""
        logger.info("Initializing NonceCore")
        
        # Verify web3 connection
        try:
            connected = await self.web3.is_connected()
            if not connected:
                logger.warning("NonceCore: Web3 connection not available")
        except Exception as e:
            logger.error(f"NonceCore: Error verifying Web3 connection: {e}")
            
        # Check if we have access to database
        if self.db_manager and hasattr(self.db_manager, "load_nonce_state"):
            try:
                # Try to load previously persisted nonce state
                nonce_state = await self.db_manager.load_nonce_state()
                if nonce_state:
                    # Only update with nonces from our current chain
                    chain_id = await self.web3.eth.chain_id
                    for address, data in nonce_state.items():
                        if data.get("chain_id") == chain_id:
                            # Use persisted nonce as a minimum value
                            self._nonces[address] = data.get("nonce", 0)
                            self._last_refresh[address] = time.time()
                            logger.debug(f"Loaded persisted nonce for {address}: {data.get('nonce')}")
            except Exception as e:
                logger.warning(f"Failed to load persisted nonce state: {e}")
                
        logger.debug("NonceCore initialization completed")

    async def get_onchain_nonce(self, address: Optional[str] = None) -> int:
        """Fetch the pending nonce from-chain, with retry logic.

        Args:
            address: Hex string of the account address

        Returns:
            The pending transaction count (nonce)
        """
        if address is None:
            raise ValueError("Address must be provided to fetch on-chain nonce")

        checksum = to_checksum_address(address)
        for attempt in range(1, self._max_retries + 1):
            try:
                nonce = await self.web3.eth.get_transaction_count(checksum, "pending")
                logger.debug(f"Fetched on-chain nonce {nonce} for {checksum}")
                return nonce
            except Exception as e:
                if attempt < self._max_retries:
                    logger.warning(f"get_onchain_nonce failed (attempt {attempt}), retrying: {e}")
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error(f"get_onchain_nonce permanently failed for {checksum}: {e}")
                    raise

    async def get_next_nonce(self, address: Optional[str] = None) -> int:
        """Return a sequential nonce for the given address, using a local cache.

        Args:
            address: Optional hex string of the account address

        Returns:
            The next nonce to use
        """
        if address is None:
            if not hasattr(self.account, "address"):
                raise ValueError("No address provided and account has no `.address`")
            address = self.account.address

        checksum = to_checksum_address(address)
        async with self._nonce_lock:
            now = time.time()
            last = self._last_refresh.get(checksum, 0)

            if checksum not in self._nonces or (now - last) > self._cache_ttl:
                nonce = await self.get_onchain_nonce(checksum)
                self._nonces[checksum] = nonce
                self._last_refresh[checksum] = now
                logger.debug(f"Nonce cache refreshed for {checksum}: {nonce}")
            else:
                self._nonces[checksum] += 1
                logger.debug(f"Nonce incremented for {checksum}: {self._nonces[checksum]}")

            return self._nonces[checksum]

    async def get_nonce(self, address: Optional[str] = None) -> int:
        """Alias for `get_next_nonce`."""
        return await self.get_next_nonce(address)

    async def reset_nonce(self, address: Optional[str] = None) -> int:
        """Force-refresh the stored nonce from-chain.

        Args:
            address: Optional hex string of the account address

        Returns:
            The refreshed nonce value
        """
        if address is None:
            if not hasattr(self.account, "address"):
                raise ValueError("No address provided and account has no `.address`")
            address = self.account.address

        checksum = to_checksum_address(address)
        async with self._nonce_lock:
            nonce = await self.get_onchain_nonce(checksum)
            self._nonces[checksum] = nonce
            self._last_refresh[checksum] = time.time()
            logger.info(f"Nonce for {checksum} reset to {nonce}")
            return nonce

    async def track_transaction(
        self, tx_hash: str, nonce_used: int, address: Optional[str] = None
    ) -> None:
        """Monitor a sent transaction and reset nonce on failure/timeout.

        Args:
            tx_hash: Transaction hash to track
            nonce_used: The nonce that was used for this tx
            address: Optional account address for tracking
        """
        if address is None:
            if not hasattr(self.account, "address"):
                logger.error("Cannot track tx: no address available")
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
        logger.debug(f"Tracking tx {tx_hash} at nonce {nonce_used} for {checksum}")
        
        # Store nonce info in database if available
        if self.db_manager and hasattr(self.db_manager, "store_nonce_state"):
            try:
                chain_id = await self.web3.eth.chain_id
                await self.db_manager.store_nonce_state(checksum, {
                    "nonce": nonce_used,
                    "chain_id": chain_id,
                    "last_update": time.time(),
                    "tx_hash": tx_hash
                })
                logger.debug(f"Persisted nonce {nonce_used} for {checksum}")
            except Exception as e:
                logger.warning(f"Failed to persist nonce state: {e}")

        # Launch background monitor
        asyncio.create_task(self._monitor_transaction(tx_hash, checksum))

    async def _monitor_transaction(self, tx_hash: str, address: str) -> None:
        """Background task: wait for receipt, handle success/failure/timeout."""
        start = time.time()
        retries = 0

        while True:
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    status = receipt.get("status", 0)
                    if status == 1:
                        logger.info(f"Tx {tx_hash} confirmed")
                        self._tx_tracking[tx_hash]["status"] = "confirmed"
                    else:
                        logger.warning(f"Tx {tx_hash} failed on-chain")
                        self._tx_tracking[tx_hash]["status"] = "failed"
                        await self.reset_nonce(address)
                    return

                if time.time() - start > self._tx_timeout:
                    logger.warning(f"Tx {tx_hash} monitor timeout")
                    self._tx_tracking[tx_hash]["status"] = "timeout"
                    await self.reset_nonce(address)
                    return

            except Exception as e:
                retries += 1
                if retries >= self._max_retries:
                    logger.error(f"Monitoring {tx_hash} aborted after {retries} retries: {e}")
                    self._tx_tracking[tx_hash]["status"] = "error"
                    return
                logger.warning(f"Error monitoring {tx_hash} ({retries}/{self._max_retries}): {e}")

            await asyncio.sleep(self._retry_delay)

    async def wait_for_transaction(
        self, tx_hash: str, timeout: Optional[int] = None
    ) -> bool:
        """Block until the transaction is mined or the timeout elapses.

        Args:
            tx_hash: Transaction hash to wait for
            timeout: Maximum seconds to wait

        Returns:
            True if tx mined before timeout, False otherwise
        """
        if timeout is None:
            timeout = self._tx_timeout

        start = time.time()
        while time.time() - start < timeout:
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return True
            except Exception:
                pass
            await asyncio.sleep(self._retry_delay)

        logger.warning(f"wait_for_transaction timed out for {tx_hash}")
        return False

    async def close(self) -> None:
        """Clean up resources and persist final state."""
        logger.debug("NonceCore shutting down")
        
        # Persist final nonce state if database is available
        if self.db_manager and hasattr(self.db_manager, "store_nonce_state"):
            try:
                chain_id = await self.web3.eth.chain_id
                # Store current nonce state for each address
                for address, nonce in self._nonces.items():
                    await self.db_manager.store_nonce_state(address, {
                        "nonce": nonce,
                        "chain_id": chain_id,
                        "last_update": time.time(),
                    })
                logger.debug(f"Final nonce state persisted for {len(self._nonces)} addresses")
            except Exception as e:
                logger.warning(f"Failed to persist final nonce state: {e}")
        
        # Clear in-memory caches
        self._nonces.clear()
        self._last_refresh.clear()
        if hasattr(self, "_tx_tracking"):
            self._tx_tracking.clear()
            
        logger.info("NonceCore closed")

    async def stop(self) -> None:
        """Alias for close()."""
        await self.close()

    async def refresh_nonce(self, address: Optional[str] = None) -> int:
        """Alias for `reset_nonce`."""
        return await self.reset_nonce(address)

    async def sync_nonce_with_chain(self, address: Optional[str] = None) -> int:
        """Synchronize local cache with on-chain nonce (alias for reset)."""
        logger.info("Synchronizing nonce with chain")
        return await self.reset_nonce(address)

    async def reset(self, address: Optional[str] = None) -> int:
        """Alias for `reset_nonce` to maintain compatibility."""
        logger.info("Resetting nonce tracking")
        return await self.reset_nonce(address)

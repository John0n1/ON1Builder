"""
ON1Builder - Nonce Core
======================

Manages transaction nonces across concurrent operations.
"""

from __future__ import annotations
import asyncio
import time
from typing import Dict, Optional

from web3 import AsyncWeb3
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from on1builder.config.config import Configuration
from on1builder.utils.logger import setup_logging

logger = setup_logging("NonceCore", level="DEBUG")


class NonceCore:
    """
    Transaction nonce manager for concurrent blockchain operations.
    
    This class ensures proper nonce management across concurrent operations
    to prevent nonce conflicts and transaction failures.
    """
    
    def __init__(self, web3: AsyncWeb3, config: Configuration) -> None:
        """
        Initialize nonce manager.
        
        Args:
            web3: Web3 provider instance
            config: Global configuration
        """
        self.web3 = web3
        self.config = config
        
        # Nonce tracking
        self._nonces: Dict[str, int] = {}
        self._nonce_lock = asyncio.Lock()
        self._last_refresh: Dict[str, float] = {}
        
        # Configuration
        self._cache_ttl = getattr(config, "NONCE_CACHE_TTL", 60)  # seconds
        self._retry_delay = getattr(config, "NONCE_RETRY_DELAY", 1)  # seconds
        self._max_retries = getattr(config, "NONCE_MAX_RETRIES", 5)
        self._tx_timeout = getattr(config, "NONCE_TRANSACTION_TIMEOUT", 120)  # seconds
        
        logger.info("NonceCore initialized")
    
    async def initialize(self) -> None:
        """
        Initialize nonce management system.
        
        This method is called during system startup to prepare the nonce
        tracking system. Currently, it just logs initialization but could
        be extended to perform startup tasks like pre-fetching nonces.
        """
        logger.info("Initializing NonceCore")
        # For now, initialization is handled in __init__
        # This method exists for API consistency with other components
    
    async def get_onchain_nonce(self, address: str) -> int:
        """
        Get the current nonce for an address from the blockchain.
        
        Args:
            address: Account address
            
        Returns:
            Current nonce value
        """
        checksum_address = to_checksum_address(address)
        for retry in range(self._max_retries):
            try:
                nonce = await self.web3.eth.get_transaction_count(checksum_address, 'pending')
                logger.debug(f"On-chain nonce for {address}: {nonce}")
                return nonce
            except Exception as e:
                if retry < self._max_retries - 1:
                    logger.warning(f"Error getting nonce, retrying: {str(e)}")
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error(f"Failed to get nonce after {self._max_retries} retries")
                    raise
    
    async def get_next_nonce(self, address: str) -> int:
        """
        Get the next available nonce for an address.
        
        This method ensures that concurrent calls get unique, sequential nonces.
        
        Args:
            address: Account address
            
        Returns:
            Next available nonce
        """
        checksum_address = to_checksum_address(address)
        
        async with self._nonce_lock:
            current_time = time.time()
            last_refresh = self._last_refresh.get(checksum_address, 0)
            
            # Refresh cache if expired
            if current_time - last_refresh > self._cache_ttl or checksum_address not in self._nonces:
                nonce = await self.get_onchain_nonce(checksum_address)
                self._nonces[checksum_address] = nonce
                self._last_refresh[checksum_address] = current_time
            else:
                # Increment the cached nonce
                self._nonces[checksum_address] += 1
                
            return self._nonces[checksum_address]
    
    async def get_nonce(self, address: Optional[str] = None) -> int:
        """
        Get the next available nonce for an address.
        
        This method is an alias for get_next_nonce for API compatibility.
        
        Args:
            address: Account address, uses default account if not specified
            
        Returns:
            Next available nonce
        """
        if address is None:
            # First try to use self.account if it exists
            if hasattr(self, 'account') and hasattr(self.account, 'address'):
                address = self.account.address
            # Otherwise use first tracked address
            elif self._nonces:
                address = next(iter(self._nonces.keys()))
            else:
                # Try to get from config if available
                try:
                    if hasattr(self.config, 'DEFAULT_ADDRESS') and self.config.DEFAULT_ADDRESS:
                        address = self.config.DEFAULT_ADDRESS
                    else:
                        raise ValueError("No addresses are being tracked and no default address available")
                except Exception as e:
                    logger.error(f"Failed to determine default address: {str(e)}")
                    raise ValueError("No addresses are being tracked, cannot determine default address") from e
            
        return await self.get_next_nonce(address)
    
    async def reset_nonce(self, address: str) -> int:
        """
        Reset the nonce for an address by getting the latest from the blockchain.
        
        Args:
            address: Account address
            
        Returns:
            Current on-chain nonce
        """
        checksum_address = to_checksum_address(address)
        
        async with self._nonce_lock:
            nonce = await self.get_onchain_nonce(checksum_address)
            self._nonces[checksum_address] = nonce
            self._last_refresh[checksum_address] = time.time()
            logger.info(f"Nonce reset for {address}: {nonce}")
            return nonce
    
    async def track_transaction(self, tx_hash: str, nonce_used: int, address: Optional[str] = None) -> None:
        """
        Track a sent transaction and its nonce.
        
        This method is called after a transaction is sent to ensure proper
        nonce tracking. It monitors transaction status and handles resubmissions 
        or nonce resets as needed.
        
        Args:
            tx_hash: Transaction hash
            nonce_used: Nonce used for the transaction
            address: The address that sent the transaction (optional)
        """
        # Resolve address if not provided
        if address is None:
            if hasattr(self, 'account') and hasattr(self.account, 'address'):
                address = self.account.address
            elif self._nonces:
                address = next(iter(self._nonces.keys()))
            elif hasattr(self.config, 'DEFAULT_ADDRESS') and self.config.DEFAULT_ADDRESS:
                address = self.config.DEFAULT_ADDRESS
            else:
                logger.error("Cannot track transaction: no address provided or available")
                return
                
        checksum_address = to_checksum_address(address)
        
        # Store mapping of tx_hash to nonce and address
        if not hasattr(self, '_tx_tracking'):
            self._tx_tracking = {}
            
        self._tx_tracking[tx_hash] = {
            'nonce': nonce_used,
            'address': checksum_address,
            'timestamp': time.time(),
            'status': 'pending'
        }
        
        logger.debug(f"Tracking transaction {tx_hash} with nonce {nonce_used} for address {checksum_address}")
        
        # Start a background task to monitor this transaction
        asyncio.create_task(self._monitor_transaction(tx_hash, checksum_address))
        
    async def _monitor_transaction(self, tx_hash: str, address: str) -> None:
        """
        Monitor a transaction until it's confirmed or times out.
        
        Args:
            tx_hash: Transaction hash to monitor
            address: Address that sent the transaction
        """
        start_time = time.time()
        retry_count = 0
        max_retries = self._max_retries
        
        while True:
            try:
                # Check if transaction was mined
                tx_receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                
                if tx_receipt is not None:
                    # Transaction was mined
                    if tx_receipt['status'] == 1:
                        logger.info(f"Transaction {tx_hash} confirmed successfully")
                        self._tx_tracking[tx_hash]['status'] = 'confirmed'
                    else:
                        logger.warning(f"Transaction {tx_hash} failed on-chain")
                        self._tx_tracking[tx_hash]['status'] = 'failed'
                        
                        # Reset nonce since the transaction failed
                        await self.reset_nonce(address)
                    
                    # Either way, we're done monitoring
                    return
                    
                # Check for timeout
                if time.time() - start_time > self._tx_timeout:
                    logger.warning(f"Transaction {tx_hash} monitoring timed out after {self._tx_timeout} seconds")
                    self._tx_tracking[tx_hash]['status'] = 'timeout'
                    
                    # Reset nonce to be safe
                    await self.reset_nonce(address)
                    return
                    
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Failed to monitor transaction {tx_hash} after {max_retries} retries: {str(e)}")
                    self._tx_tracking[tx_hash]['status'] = 'error'
                    return
                    
                logger.warning(f"Error monitoring transaction {tx_hash}, retry {retry_count}/{max_retries}: {str(e)}")
            
            # Wait before checking again
            await asyncio.sleep(self._retry_delay)
    
    async def refresh_nonce(self, address: Optional[str] = None) -> int:
        """
        Refresh the nonce for an address from the blockchain.
        
        Args:
            address: Account address, uses default if not specified
            
        Returns:
            Updated nonce value
        """
        if address is None:
            # Use first tracked address by default
            if not self._nonces:
                raise ValueError("No addresses are being tracked, cannot determine default")
            address = next(iter(self._nonces.keys()))
            
        return await self.reset_nonce(address)
    
    async def sync_nonce_with_chain(self, address: Optional[str] = None) -> int:
        """
        Synchronize cached nonce with blockchain nonce.
        
        This is an alias for refresh_nonce for API compatibility.
        
        Args:
            address: Account address, uses default if not specified
            
        Returns:
            Updated nonce value
        """
        return await self.refresh_nonce(address)
    
    async def wait_for_transaction(
        self, 
        tx_hash: str,
        timeout: Optional[int] = None
    ) -> bool:
        """
        Wait for a transaction to be mined.
        
        Args:
            tx_hash: Transaction hash to wait for
            timeout: Maximum time to wait in seconds, defaults to configured value
            
        Returns:
            True if transaction was mined, False if timeout
        """
        if timeout is None:
            timeout = self._tx_timeout
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    logger.debug(f"Transaction {tx_hash} mined, block: {receipt.blockNumber}")
                    return True
            except Exception:
                # Transaction not yet mined
                pass
                
            await asyncio.sleep(self._retry_delay)
            
        logger.warning(f"Transaction {tx_hash} not mined within {timeout} seconds")
        return False
    
    async def close(self) -> None:
        """Clean up resources."""
        logger.debug("Closing NonceCore")
        # Nothing to clean up currently
    
    async def stop(self) -> None:
        """
        Stop nonce manager (alias for close).
        
        This method exists for API compatibility with other components.
        """
        await self.close()
    
    async def reset(self) -> None:
        """
        Reset all nonce tracking data.
        
        This will clear all cached nonces, forcing fresh fetches from the chain.
        """
        async with self._nonce_lock:
            logger.info("Resetting all nonce tracking data")
            self._nonces.clear()
            self._last_refresh.clear()

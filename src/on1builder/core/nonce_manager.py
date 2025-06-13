# src/on1builder/core/nonce_manager.py
from __future__ import annotations

import asyncio
from typing import Optional

from web3 import AsyncWeb3

from on1builder.config.loaders import settings
from on1builder.utils.custom_exceptions import ConnectionError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.singleton import SingletonMeta

logger = get_logger(__name__)

class NonceManager(metaclass=SingletonMeta):
    """
    Manages transaction nonces for a single address to prevent race conditions
    and ensure sequential, unique nonces for all outgoing transactions.
    """

    def __init__(self, web3: AsyncWeb3, address: str):
        self._web3 = web3
        self._address = address
        self._nonce: Optional[int] = None
        self._lock = asyncio.Lock()
        logger.info(f"NonceManager initialized for address: {self._address}")

    async def _initialize_nonce(self):
        """Fetches the initial nonce from the blockchain."""
        for attempt in range(settings.connection_retry_count):
            try:
                # 'pending' includes transactions in the mempool
                self._nonce = await self._web3.eth.get_transaction_count(self._address, "pending")
                logger.info(f"Initial nonce for {self._address} set to: {self._nonce}")
                return
            except Exception as e:
                logger.warning(
                    f"Failed to fetch initial nonce (attempt {attempt + 1}): {e}. "
                    f"Retrying in {settings.connection_retry_delay}s..."
                )
                await asyncio.sleep(settings.connection_retry_delay)
        
        # If all attempts fail, raise an error
        raise ConnectionError(f"Could not fetch initial nonce for address {self._address} after multiple retries.")

    async def get_next_nonce(self) -> int:
        """
        Atomically retrieves and increments the current nonce.
        Initializes the nonce from the blockchain on the first call.

        Returns:
            The next nonce to be used for a transaction.
        """
        async with self._lock:
            if self._nonce is None:
                await self._initialize_nonce()

            if self._nonce is not None:
                current_nonce = self._nonce
                self._nonce += 1
                logger.debug(f"Providing nonce {current_nonce}, next will be {self._nonce}")
                return current_nonce
            
            # This should not be reached if _initialize_nonce is successful
            raise RuntimeError("Nonce could not be initialized.")

    async def resync_nonce(self) -> None:
        """
        Forcibly re-synchronizes the nonce with the blockchain.
        This is useful to recover from a state mismatch or after a manual transaction.
        """
        async with self._lock:
            logger.warning(f"Forcing nonce re-synchronization for address {self._address}...")
            # Set nonce to None to trigger re-initialization on the next `get_next_nonce` call
            self._nonce = None
            await self._initialize_nonce()
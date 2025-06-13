# src/on1builder/utils/web3_factory.py
import asyncio
from typing import Optional

from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers.auto import load_provider_from_uri
from web3.providers import AsyncHTTPProvider

# Try to import websocket provider, but make it optional
try:
    from web3.providers.websocket import WebSocketProviderV2
    WEBSOCKET_AVAILABLE = True
except ImportError:
    try:
        from web3.providers import WebSocketProvider as WebSocketProviderV2
        WEBSOCKET_AVAILABLE = True
    except ImportError:
        WebSocketProviderV2 = None
        WEBSOCKET_AVAILABLE = False

from on1builder.utils.logging_config import get_logger
from on1builder.utils.custom_exceptions import ConnectionError

logger = get_logger(__name__)

class Web3ConnectionFactory:
    """A factory for creating and managing AsyncWeb3 connections."""

    @classmethod
    async def create_connection(cls, chain_id: int) -> AsyncWeb3:
        """
        Creates a reliable AsyncWeb3 connection for a given chain ID.
        It tries WebSocket first, then falls back to HTTP.

        Args:
            chain_id: The ID of the chain to connect to.

        Returns:
            A configured and connected AsyncWeb3 instance.
            
        Raises:
            ConnectionError: If a connection cannot be established.
        """
        from on1builder.config.loaders import get_settings
        settings = get_settings()
        
        logger.info(f"Creating Web3 connection for chain ID: {chain_id}...")

        # Try WebSocket connection first if available, but with limited retries
        ws_url = settings.websocket_urls.get(chain_id)
        if ws_url and WEBSOCKET_AVAILABLE:
            connection = await cls._try_connect_with_limited_retries(
                chain_id,
                ws_url,
                "WebSocket",
                lambda url: WebSocketProviderV2(url),
                max_attempts=1  # Only try WebSocket once before falling back
            )
            if connection:
                return connection
        elif ws_url and not WEBSOCKET_AVAILABLE:
            logger.warning("WebSocket URL configured but WebSocket provider not available. Falling back to HTTP.")

        # Fallback to HTTP connection
        http_url = settings.rpc_urls.get(chain_id)
        if http_url:
            connection = await cls._try_connect(
                chain_id,
                http_url,
                "HTTP",
                lambda url: AsyncHTTPProvider(url)
            )
            if connection:
                return connection
        
        raise ConnectionError(f"Failed to establish any Web3 connection for chain ID: {chain_id}")

    @classmethod
    async def _try_connect_with_limited_retries(
        cls,
        chain_id: int,
        url: str,
        provider_type: str,
        provider_factory,
        max_attempts: int = 1
    ) -> Optional[AsyncWeb3]:
        """
        Attempts to connect using a specific provider, with limited retries.
        Used for WebSocket connections to fail fast and fallback to HTTP.
        """
        from on1builder.config.loaders import get_settings
        settings = get_settings()
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.debug(f"Attempt {attempt}: Connecting to {provider_type} endpoint for chain {chain_id} at {url}")
                provider = provider_factory(url)
                web3 = AsyncWeb3(provider)
                
                # Verify connection and chain ID
                if not await web3.is_connected():
                    raise ConnectionError("Provider reports not connected.")
                
                actual_chain_id = await web3.eth.chain_id
                if actual_chain_id != chain_id:
                    logger.warning(
                        f"Chain ID mismatch for {url}! "
                        f"Expected: {chain_id}, Got: {actual_chain_id}. "
                        "Proceeding, but this may cause issues."
                    )
                
                # Apply PoA middleware if necessary
                if chain_id in settings.poa_chains:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for PoA chain ID: {chain_id}")

                logger.info(f"Successfully connected to {provider_type} for chain ID {chain_id}.")
                return web3

            except Exception as e:
                logger.warning(
                    f"Failed to connect to {provider_type} for chain {chain_id} (Attempt {attempt}/{max_attempts}): {e}"
                )
                if attempt < max_attempts:
                    await asyncio.sleep(min(settings.connection_retry_delay, 2))  # Shorter delay for fast fallback
                else:
                    logger.info(f"Fast-failing {provider_type} for chain {chain_id} to allow HTTP fallback.")
                    return None
        return None

    @classmethod
    async def _try_connect(
        cls,
        chain_id: int,
        url: str,
        provider_type: str,
        provider_factory
    ) -> Optional[AsyncWeb3]:
        """
        Attempts to connect using a specific provider, with retries.
        """
        from on1builder.config.loaders import get_settings
        settings = get_settings()
        
        for attempt in range(1, settings.connection_retry_count + 1):
            try:
                logger.debug(f"Attempt {attempt}: Connecting to {provider_type} endpoint for chain {chain_id} at {url}")
                provider = provider_factory(url)
                web3 = AsyncWeb3(provider)
                
                # Verify connection and chain ID
                if not await web3.is_connected():
                    raise ConnectionError("Provider reports not connected.")
                
                actual_chain_id = await web3.eth.chain_id
                if actual_chain_id != chain_id:
                    logger.warning(
                        f"Chain ID mismatch for {url}! "
                        f"Expected: {chain_id}, Got: {actual_chain_id}. "
                        "Proceeding, but this may cause issues."
                    )
                
                # Apply PoA middleware if necessary
                if chain_id in settings.poa_chains:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for PoA chain ID: {chain_id}")

                logger.info(f"Successfully connected to {provider_type} for chain ID {chain_id}.")
                return web3

            except Exception as e:
                logger.warning(
                    f"Failed to connect to {provider_type} for chain {chain_id} (Attempt {attempt}/{settings.connection_retry_count}): {e}"
                )
                if attempt < settings.connection_retry_count:
                    await asyncio.sleep(settings.connection_retry_delay)
                else:
                    logger.error(f"All connection attempts to {provider_type} for chain {chain_id} failed.")
                    return None
        return None

# Convenience function for backward compatibility
async def create_web3_instance(chain_id: int) -> AsyncWeb3:
    """
    Creates an AsyncWeb3 instance for the specified chain ID.
    
    Args:
        chain_id: The chain ID to connect to.
        
    Returns:
        An initialized AsyncWeb3 instance.
        
    Raises:
        ConnectionError: If a connection cannot be established.
    """
    return await Web3ConnectionFactory.create_connection(chain_id)
# src/on1builder/utils/web3_factory.py
from __future__ import annotations

import asyncio
from typing import Optional, Dict

from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import AsyncHTTPProvider

# Try to import websocket provider, but make it optional
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
    """A factory for creating and managing AsyncWeb3 connections with connection pooling."""

    _connections: Dict[int, AsyncWeb3] = {}
    _connection_lock = asyncio.Lock()

    @classmethod
    async def create_connection(cls, chain_id: int, force_new: bool = False) -> AsyncWeb3:
        """
        Creates or returns a cached reliable AsyncWeb3 connection for a given chain ID.
        
        Args:
            chain_id: The ID of the chain to connect to
            force_new: If True, creates a new connection even if one is cached
            
        Returns:
            A configured and connected AsyncWeb3 instance
            
        Raises:
            ConnectionError: If a connection cannot be established
        """
        # Return cached connection if available and not forcing new
        if not force_new and chain_id in cls._connections:
            web3 = cls._connections[chain_id]
            if await cls._test_connection(web3):
                logger.debug(f"Using cached Web3 connection for chain {chain_id}")
                return web3
            else:
                logger.warning(f"Cached connection for chain {chain_id} is stale, creating new")
                del cls._connections[chain_id]

        async with cls._connection_lock:
            # Double-check after acquiring lock
            if not force_new and chain_id in cls._connections:
                web3 = cls._connections[chain_id]
                if await cls._test_connection(web3):
                    return web3
                del cls._connections[chain_id]

            logger.info(f"Creating new Web3 connection for chain {chain_id}")
            web3 = await cls._create_new_connection(chain_id)
            cls._connections[chain_id] = web3
            return web3

    @classmethod
    async def _create_new_connection(cls, chain_id: int) -> AsyncWeb3:
        """Create a new Web3 connection with fallback logic."""
        from on1builder.config.loaders import get_settings
        settings = get_settings()

        # Try WebSocket first if available
        ws_url = settings.websocket_urls.get(chain_id)
        if ws_url and WEBSOCKET_AVAILABLE:
            try:
                web3 = await cls._create_websocket_connection(chain_id, ws_url)
                if web3 and await cls._test_connection(web3):
                    logger.info(f"WebSocket connection established for chain {chain_id}")
                    return web3
            except Exception as e:
                logger.warning(f"WebSocket connection failed for chain {chain_id}: {e}")

        # Fallback to HTTP
        http_url = settings.rpc_urls.get(chain_id)
        if not http_url:
            raise ConnectionError(f"No RPC URL configured for chain {chain_id}", chain_id=chain_id)

        try:
            web3 = await cls._create_http_connection(chain_id, http_url)
            if web3 and await cls._test_connection(web3):
                logger.info(f"HTTP connection established for chain {chain_id}")
                return web3
        except Exception as e:
            raise ConnectionError(
                f"Failed to establish connection to chain {chain_id}",
                endpoint=http_url,
                chain_id=chain_id,
                cause=e
            )

        raise ConnectionError(f"All connection attempts failed for chain {chain_id}", chain_id=chain_id)

    @classmethod
    async def _create_websocket_connection(cls, chain_id: int, ws_url: str) -> Optional[AsyncWeb3]:
        """Create a WebSocket connection."""
        if not WEBSOCKET_AVAILABLE:
            return None
            
        try:
            provider = WebSocketProviderV2(ws_url)
            web3 = AsyncWeb3(provider)
            cls._configure_web3_instance(web3, chain_id)
            return web3
        except Exception as e:
            logger.debug(f"WebSocket connection creation failed: {e}")
            return None

    @classmethod
    async def _create_http_connection(cls, chain_id: int, http_url: str) -> AsyncWeb3:
        """Create an HTTP connection."""
        provider = AsyncHTTPProvider(http_url)
        web3 = AsyncWeb3(provider)
        cls._configure_web3_instance(web3, chain_id)
        return web3

    @classmethod
    def _configure_web3_instance(cls, web3: AsyncWeb3, chain_id: int) -> None:
        """Configure a Web3 instance with necessary middleware."""
        from on1builder.config.loaders import get_settings
        settings = get_settings()
        
        # Add PoA middleware for PoA chains
        if chain_id in settings.poa_chains:
            web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            logger.debug(f"PoA middleware added for chain {chain_id}")

    @classmethod
    async def _test_connection(cls, web3: AsyncWeb3) -> bool:
        """Test if a Web3 connection is working."""
        try:
            await asyncio.wait_for(web3.eth.get_block('latest'), timeout=5.0)
            return True
        except Exception:
            return False

    @classmethod
    async def close_all_connections(cls) -> None:
        """Close all cached connections."""
        async with cls._connection_lock:
            for chain_id, web3 in cls._connections.items():
                try:
                    if hasattr(web3.provider, 'disconnect'):
                        await web3.provider.disconnect()
                    logger.debug(f"Closed connection for chain {chain_id}")
                except Exception as e:
                    logger.warning(f"Error closing connection for chain {chain_id}: {e}")
            cls._connections.clear()


# Convenience function for backward compatibility
async def create_web3_instance(chain_id: int) -> AsyncWeb3:
    """
    Create a Web3 instance for the given chain ID.
    
    Args:
        chain_id: The chain ID to create a connection for
        
    Returns:
        Configured AsyncWeb3 instance
    """
    return await Web3ConnectionFactory.create_connection(chain_id)
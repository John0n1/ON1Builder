#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import asyncio

from aiohttp import ClientSession, ClientTimeout, TCPConnector
from web3 import AsyncWeb3
from web3._utils.async_caching import async_lock
from web3._utils.caching import generate_cache_key
from web3._utils.http_session_manager import DEFAULT_HTTP_TIMEOUT, HTTPSessionManager
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import AsyncHTTPProvider

# Try to import websocket provider, but make it optional
try:
    from web3.providers import WebSocketProvider as WebSocketProviderV2

    WEBSOCKET_AVAILABLE = True
except ImportError:
    WebSocketProviderV2 = None
    WEBSOCKET_AVAILABLE = False

from on1builder.utils.custom_exceptions import ConnectionError
from on1builder.utils.logging_config import get_logger

logger = get_logger(__name__)


class Web3ConnectionFactory:
    """A factory for creating and managing AsyncWeb3 connections with connection pooling."""

    _connections: dict[int, AsyncWeb3] = {}
    _connection_lock = asyncio.Lock()

    @classmethod
    async def create_connection(
        cls, chain_id: int, force_new: bool = False
    ) -> AsyncWeb3:
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
                logger.warning(
                    f"Cached connection for chain {chain_id} is stale, creating new"
                )
                del cls._connections[chain_id]

        async with cls._connection_lock:
            # Double-check after acquiring lock
            if not force_new and chain_id in cls._connections:
                web3 = cls._connections[chain_id]
                if await cls._test_connection(web3):
                    return web3
                del cls._connections[chain_id]

            logger.debug(f"Creating new Web3 connection for chain {chain_id}")
            web3 = await cls._create_new_connection(chain_id)
            cls._connections[chain_id] = web3
            return web3

    @classmethod
    async def _create_new_connection(cls, chain_id: int) -> AsyncWeb3:
        """Create a new Web3 connection with fallback logic."""
        from on1builder.config.loaders import get_settings

        settings = get_settings()

        # Try WebSocket first if available
        ws_url = settings.websocket_urls.get(chain_id) or settings.websocket_urls.get(
            str(chain_id)
        )
        if ws_url and WEBSOCKET_AVAILABLE:
            try:
                web3 = await cls._create_websocket_connection(chain_id, ws_url)
                if web3 and await cls._test_connection(web3):
                    logger.debug(
                        "WebSocket connection established for chain %s", chain_id
                    )
                    return web3
            except Exception as e:
                logger.warning(f"WebSocket connection failed for chain {chain_id}: {e}")

        # Fallback to HTTP
        http_url = settings.rpc_urls.get(chain_id) or settings.rpc_urls.get(
            str(chain_id)
        )
        if not http_url:
            raise ConnectionError(
                f"No RPC URL configured for chain {chain_id}", chain_id=chain_id
            )

        try:
            web3 = await cls._create_http_connection(chain_id, http_url)
            if web3 and await cls._test_connection(web3):
                logger.debug("HTTP connection established for chain ID: %s", chain_id)
                return web3
        except Exception as e:
            raise ConnectionError(
                f"Failed to establish connection to chain {chain_id}",
                endpoint=http_url,
                chain_id=chain_id,
                cause=e,
            )

        raise ConnectionError(
            f"All connection attempts failed for chain {chain_id}", chain_id=chain_id
        )

    @classmethod
    async def _create_websocket_connection(
        cls, chain_id: int, ws_url: str
    ) -> AsyncWeb3 | None:
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
        provider = QuietAsyncHTTPProvider(http_url)
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
            await asyncio.wait_for(web3.eth.get_block("latest"), timeout=5.0)
            return True
        except Exception:
            return False

    @classmethod
    async def close_all_connections(cls) -> None:
        """Close all cached connections."""
        async with cls._connection_lock:
            for chain_id, web3 in cls._connections.items():
                try:
                    if hasattr(web3.provider, "disconnect"):
                        await web3.provider.disconnect()
                    logger.debug(f"Closed connection for chain {chain_id}")
                except Exception as e:
                    logger.warning(
                        f"Error closing connection for chain {chain_id}: {e}"
                    )
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


class QuietHTTPSessionManager(HTTPSessionManager):
    """Custom session manager to avoid deprecated connector flags in web3."""

    async def async_cache_and_return_session(
        self,
        endpoint_uri,
        session: ClientSession | None = None,
        request_timeout=None,
    ) -> ClientSession:
        cache_key = generate_cache_key(f"{id(asyncio.get_event_loop())}:{endpoint_uri}")
        evicted_items = None

        async with async_lock(self.session_pool, self._lock):
            if cache_key not in self.session_cache:
                if session is None:
                    session = ClientSession(
                        raise_for_status=True,
                        connector=TCPConnector(
                            force_close=True, enable_cleanup_closed=False
                        ),
                    )

                cached_session, evicted_items = self.session_cache.cache(
                    cache_key, session
                )
                self.logger.debug(
                    "Async session cached: %s, %s", endpoint_uri, cached_session
                )
            else:
                cached_session = self.session_cache.get_cache_entry(cache_key)
                session_is_closed = cached_session.closed
                session_loop_is_closed = cached_session._loop.is_closed()

                warning = (
                    "Async session was closed"
                    if session_is_closed
                    else (
                        "Loop was closed for async session"
                        if session_loop_is_closed
                        else None
                    )
                )
                if warning:
                    self.logger.debug(
                        "%s: %s, %s. Creating and caching a new async session for uri.",
                        warning,
                        endpoint_uri,
                        cached_session,
                    )

                    self.session_cache._data.pop(cache_key)
                    if not session_is_closed:
                        await cached_session.close()
                    self.logger.debug(
                        "Async session closed and evicted from cache: %s",
                        cached_session,
                    )

                    _session = ClientSession(
                        raise_for_status=True,
                        connector=TCPConnector(
                            force_close=True, enable_cleanup_closed=False
                        ),
                    )
                    cached_session, evicted_items = self.session_cache.cache(
                        cache_key, _session
                    )
                    self.logger.debug(
                        "Async session cached: %s, %s", endpoint_uri, cached_session
                    )

        if evicted_items is not None:
            evicted_sessions = list(evicted_items.values())
            for evicted_session in evicted_sessions:
                self.logger.debug(
                    "Async session cache full. Session evicted from cache: %s",
                    evicted_session,
                )
            timeout = (
                request_timeout.total
                if isinstance(request_timeout, ClientTimeout) and request_timeout.total
                else DEFAULT_HTTP_TIMEOUT + 0.1
            )
            asyncio.create_task(
                self._async_close_evicted_sessions(timeout, evicted_sessions)
            )

        return cached_session


class QuietAsyncHTTPProvider(AsyncHTTPProvider):
    """AsyncHTTPProvider that uses QuietHTTPSessionManager."""

    def __init__(self, endpoint_uri=None, request_kwargs=None, **kwargs):
        super().__init__(
            endpoint_uri=endpoint_uri, request_kwargs=request_kwargs, **kwargs
        )
        self._request_session_manager = QuietHTTPSessionManager()

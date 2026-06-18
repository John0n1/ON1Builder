from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.utils import web3_factory as factory_module
from on1builder.utils.custom_exceptions import ConnectionError
from on1builder.utils.web3_factory import (
    QuietAsyncHTTPProvider,
    Web3ConnectionFactory,
    create_web3_instance,
)


@pytest.fixture(autouse=True)
def reset_factory():
    Web3ConnectionFactory._connections.clear()
    yield
    Web3ConnectionFactory._connections.clear()


@pytest.mark.asyncio
async def test_create_connection_uses_cache_and_replaces_stale(monkeypatch):
    fresh = object()
    stale = object()
    Web3ConnectionFactory._connections[1] = stale
    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_test_connection",
        classmethod(lambda cls, web3: AsyncMock(return_value=web3 is fresh)()),
    )
    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_create_new_connection",
        classmethod(lambda cls, chain_id: AsyncMock(return_value=fresh)()),
    )

    assert await Web3ConnectionFactory.create_connection(1) is fresh
    assert await Web3ConnectionFactory.create_connection(1) is fresh
    assert await Web3ConnectionFactory.create_connection(1, force_new=True) is fresh


@pytest.mark.asyncio
async def test_create_new_connection_prefers_websocket_then_http(monkeypatch):
    settings = SimpleNamespace(
        websocket_urls={1: "wss://rpc"}, rpc_urls={1: "https://rpc"}, poa_chains=[]
    )
    monkeypatch.setattr("on1builder.config.loaders.get_settings", lambda: settings)
    monkeypatch.setattr(factory_module, "WEBSOCKET_AVAILABLE", True)
    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_create_websocket_connection",
        classmethod(lambda cls, chain_id, url: AsyncMock(return_value="ws")()),
    )
    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_test_connection",
        classmethod(lambda cls, web3: AsyncMock(return_value=True)()),
    )
    assert await Web3ConnectionFactory._create_new_connection(1) == "ws"

    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_create_websocket_connection",
        classmethod(
            lambda cls, chain_id, url: AsyncMock(side_effect=RuntimeError("ws fail"))()
        ),
    )
    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_create_http_connection",
        classmethod(lambda cls, chain_id, url: AsyncMock(return_value="http")()),
    )
    assert await Web3ConnectionFactory._create_new_connection(1) == "http"

    settings.rpc_urls = {}
    with pytest.raises(ConnectionError):
        await Web3ConnectionFactory._create_new_connection(1)


@pytest.mark.asyncio
async def test_create_new_connection_wraps_http_errors(monkeypatch):
    settings = SimpleNamespace(
        websocket_urls={}, rpc_urls={1: "https://rpc"}, poa_chains=[]
    )
    monkeypatch.setattr("on1builder.config.loaders.get_settings", lambda: settings)
    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_create_http_connection",
        classmethod(
            lambda cls, chain_id, url: AsyncMock(side_effect=RuntimeError("bad http"))()
        ),
    )
    with pytest.raises(ConnectionError, match="Failed to establish connection"):
        await Web3ConnectionFactory._create_new_connection(1)


@pytest.mark.asyncio
async def test_websocket_and_http_connection_helpers(monkeypatch):
    monkeypatch.setattr(factory_module, "WEBSOCKET_AVAILABLE", False)
    assert (
        await Web3ConnectionFactory._create_websocket_connection(1, "wss://rpc") is None
    )

    monkeypatch.setattr(factory_module, "WEBSOCKET_AVAILABLE", True)
    monkeypatch.setattr(
        factory_module, "WebSocketProviderV2", lambda url: f"provider:{url}"
    )
    configured = []
    monkeypatch.setattr(
        Web3ConnectionFactory,
        "_configure_web3_instance",
        classmethod(lambda cls, web3, chain_id: configured.append((web3, chain_id))),
    )
    monkeypatch.setattr(
        factory_module, "AsyncWeb3", lambda provider: {"provider": provider}
    )
    assert await Web3ConnectionFactory._create_websocket_connection(1, "wss://rpc") == {
        "provider": "provider:wss://rpc"
    }
    assert configured[-1][1] == 1

    monkeypatch.setattr(
        factory_module,
        "AsyncWeb3",
        lambda provider: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert (
        await Web3ConnectionFactory._create_websocket_connection(1, "wss://rpc") is None
    )

    monkeypatch.setattr(
        factory_module, "AsyncWeb3", lambda provider: {"provider": provider}
    )
    monkeypatch.setattr(
        factory_module, "QuietAsyncHTTPProvider", lambda url: f"http:{url}"
    )
    assert await Web3ConnectionFactory._create_http_connection(2, "https://rpc") == {
        "provider": "http:https://rpc"
    }


def test_configure_web3_instance_adds_poa_middleware(monkeypatch):
    settings = SimpleNamespace(poa_chains=[137])
    monkeypatch.setattr("on1builder.config.loaders.get_settings", lambda: settings)
    onion = MagicMock()
    web3 = SimpleNamespace(middleware_onion=onion)
    Web3ConnectionFactory._configure_web3_instance(web3, 137)
    onion.inject.assert_called_once()


@pytest.mark.asyncio
async def test_test_connection_close_all_and_helper(monkeypatch):
    web3 = MagicMock()
    web3.eth.get_block = AsyncMock(return_value={})
    assert await Web3ConnectionFactory._test_connection(web3) is True
    web3.eth.get_block = AsyncMock(side_effect=RuntimeError("no"))
    assert await Web3ConnectionFactory._test_connection(web3) is False

    provider_one = SimpleNamespace(disconnect=AsyncMock())
    provider_two = SimpleNamespace(
        disconnect=AsyncMock(side_effect=RuntimeError("bad close"))
    )
    Web3ConnectionFactory._connections = {
        1: SimpleNamespace(provider=provider_one),
        2: SimpleNamespace(provider=provider_two),
        3: SimpleNamespace(provider=object()),
    }
    await Web3ConnectionFactory.close_all_connections()
    provider_one.disconnect.assert_awaited_once()
    provider_two.disconnect.assert_awaited_once()
    assert Web3ConnectionFactory._connections == {}

    monkeypatch.setattr(
        Web3ConnectionFactory,
        "create_connection",
        classmethod(lambda cls, chain_id: AsyncMock(return_value=f"conn:{chain_id}")()),
    )
    assert await create_web3_instance(5) == "conn:5"


def test_quiet_async_http_provider_uses_quiet_session_manager():
    provider = QuietAsyncHTTPProvider("https://rpc")
    assert (
        provider._request_session_manager.__class__.__name__
        == "QuietHTTPSessionManager"
    )

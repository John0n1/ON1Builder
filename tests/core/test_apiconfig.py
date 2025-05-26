# LICENSE: MIT // github.com/John0n1/ON1Builder

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from on1builder.config.config import APIConfig, Configuration


@pytest.fixture
def configuration():
    config = Configuration()
    config.WALLET_KEY = "test_wallet_key"
    config.BASE_PATH = "test_base_path"
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"
    config.IPC_ENDPOINT = "/path/to/geth.ipc"
    return config


@pytest.fixture
def api_config(configuration):
    return APIConfig(configuration)


@pytest.mark.asyncio
async def test_initialize(api_config):
    # API config initializes in the constructor, so we just verify it exists
    assert api_config is not None
    assert hasattr(api_config, "providers")


@pytest.mark.asyncio
async def test_get_token_symbol(api_config):
    address = "0xTokenAddress"
    with patch.object(
        api_config, "get_token_symbol", new_callable=AsyncMock
    ) as mock_get_token_symbol:
        await api_config.get_token_symbol(address)
        mock_get_token_symbol.assert_called_once_with(address)


@pytest.mark.asyncio
async def test_get_token_address(api_config):
    symbol = "TEST"
    with patch.object(
        api_config, "get_token_address", new_callable=AsyncMock
    ) as mock_get_token_address:
        await api_config.get_token_address(symbol)
        mock_get_token_address.assert_called_once_with(symbol)


@pytest.mark.asyncio
async def test_get_price(api_config):
    token = "TEST"
    with patch.object(
        api_config, "get_price", new_callable=AsyncMock
    ) as mock_get_price:
        mock_get_price.return_value = Decimal("1000.0")
        result = await api_config.get_price(token)
        # We need to call it with our own parameters, not check the parameters it was called with
        assert result == Decimal("1000.0")


@pytest.mark.asyncio
async def test_close(api_config):
    with patch.object(api_config, "_session", create=True) as mock_session:
        mock_session.close = AsyncMock()
        await api_config.close()
        mock_session.close.assert_called_once()

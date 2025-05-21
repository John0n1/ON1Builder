# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.config.config import Configuration

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
    from on1builder.config.config import APIConfig
    return APIConfig(configuration)

@pytest.fixture
def market_monitor(configuration, api_config):
    return MarketMonitor(configuration, api_config)

@pytest.mark.asyncio
async def test_initialize(market_monitor):
    with patch.object(market_monitor, 'initialize', new_callable=AsyncMock) as mock_initialize:
        await market_monitor.initialize()
        mock_initialize.assert_called_once()

@pytest.mark.asyncio
async def test_schedule_updates(market_monitor):
    with patch.object(market_monitor, 'schedule_updates', new_callable=AsyncMock) as mock_schedule_updates:
        await market_monitor.schedule_updates()
        mock_schedule_updates.assert_called_once()

@pytest.mark.asyncio
async def test_check_market_conditions(market_monitor):
    token_address = "0xTokenAddress"
    with patch.object(market_monitor, 'check_market_conditions', new_callable=AsyncMock) as mock_check_market_conditions:
        await market_monitor.check_market_conditions(token_address)
        mock_check_market_conditions.assert_called_once_with(token_address)

@pytest.mark.asyncio
async def test_predict_price_movement(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, 'predict_price_movement', new_callable=AsyncMock) as mock_predict_price_movement:
        await market_monitor.predict_price_movement(token_symbol)
        mock_predict_price_movement.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_market_features(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_market_features', new_callable=AsyncMock) as mock_get_market_features:
        await market_monitor._get_market_features(token_symbol)
        mock_get_market_features.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_trading_metrics(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_trading_metrics', new_callable=AsyncMock) as mock_get_trading_metrics:
        await market_monitor._get_trading_metrics(token_symbol)
        mock_get_trading_metrics.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_avg_transaction_value(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_avg_transaction_value', new_callable=AsyncMock) as mock_get_avg_transaction_value:
        await market_monitor._get_avg_transaction_value(token_symbol)
        mock_get_avg_transaction_value.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_transaction_count(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_transaction_count', new_callable=AsyncMock) as mock_get_transaction_count:
        await market_monitor._get_transaction_count(token_symbol)
        mock_get_transaction_count.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_trading_pairs_count(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_trading_pairs_count', new_callable=AsyncMock) as mock_get_trading_pairs_count:
        await market_monitor._get_trading_pairs_count(token_symbol)
        mock_get_trading_pairs_count.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_exchange_count(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_exchange_count', new_callable=AsyncMock) as mock_get_exchange_count:
        await market_monitor._get_exchange_count(token_symbol)
        mock_get_exchange_count.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_buy_sell_ratio(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_buy_sell_ratio', new_callable=AsyncMock) as mock_get_buy_sell_ratio:
        await market_monitor._get_buy_sell_ratio(token_symbol)
        mock_get_buy_sell_ratio.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_smart_money_flow(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_get_smart_money_flow', new_callable=AsyncMock) as mock_get_smart_money_flow:
        await market_monitor._get_smart_money_flow(token_symbol)
        mock_get_smart_money_flow.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_get_price_data(market_monitor):
    args = ("arg1", "arg2")
    kwargs = {"kwarg1": "value1"}
    with patch.object(market_monitor, 'get_price_data', new_callable=AsyncMock) as mock_get_price_data:
        await market_monitor.get_price_data(*args, **kwargs)
        mock_get_price_data.assert_called_once_with(*args, **kwargs)

@pytest.mark.asyncio
async def test_get_token_volume(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, 'get_token_volume', new_callable=AsyncMock) as mock_get_token_volume:
        await market_monitor.get_token_volume(token_symbol)
        mock_get_token_volume.assert_called_once_with(token_symbol)

@pytest.mark.asyncio
async def test_stop(market_monitor):
    with patch.object(market_monitor, 'stop', new_callable=AsyncMock) as mock_stop:
        await market_monitor.stop()
        mock_stop.assert_called_once()

@pytest.mark.asyncio
async def test_get_token_price(market_monitor):
    token_symbol = "TEST"
    data_type = "current"
    timeframe = 1
    vs_currency = "eth"
    with patch.object(market_monitor, 'get_token_price', new_callable=AsyncMock) as mock_get_token_price:
        await market_monitor.get_token_price(token_symbol, data_type, timeframe, vs_currency)
        mock_get_token_price.assert_called_once_with(token_symbol, data_type, timeframe, vs_currency)

@pytest.mark.asyncio
async def test_is_arbitrage_opportunity(market_monitor):
    token_symbol = "TEST"
    with patch.object(market_monitor, '_is_arbitrage_opportunity', new_callable=AsyncMock) as mock_is_arbitrage_opportunity:
        await market_monitor._is_arbitrage_opportunity(token_symbol)
        mock_is_arbitrage_opportunity.assert_called_once_with(token_symbol)

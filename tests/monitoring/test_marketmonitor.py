"""
Extended tests for the MarketMonitor class focusing on improving test coverage
"""
# Make sure to import pytest before other imports


import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
import json
import asyncio

from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.config.config import Configuration


@pytest.fixture
def configuration():
    config = Configuration()
    config.WALLET_KEY = "test_wallet_key"
    config.BASE_PATH = "test_base_path"
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"
    config.MARKET_CACHE_TTL = 60  # 60 seconds cache TTL
    return config


@pytest.fixture
def api_config(configuration):
    from on1builder.config.config import APIConfig
    api_config = AsyncMock()
    api_config.get_token_symbol.side_effect = lambda addr: f"TOKEN_{addr[-4:]}"
    api_config.get_token_address.side_effect = lambda symbol: f"0x{symbol.lower()}_address"
    api_config.get_price.side_effect = lambda token, vs_currency="usd": {"price": 100.0, "change_24h": 5.0}
    api_config.get_real_time_price.side_effect = lambda token, vs_currency="USD": 100.0
    return api_config


@pytest.fixture
def market_monitor(configuration, api_config):
    return MarketMonitor(configuration, api_config)


@pytest.mark.asyncio
async def test_get_token_price(market_monitor):
    """Test getting a token price with caching."""
    # Setup
    token_address = "0xToken123"
    expected_price = 100.0
    
    with patch.object(market_monitor.api_config, 'get_real_time_price', new_callable=AsyncMock) as mock_get_price:
        mock_get_price.return_value = expected_price
        
        # First call should hit the API
        price = await market_monitor.get_token_price(token_address)
        assert price == expected_price
        mock_get_price.assert_called_once_with(token_address, "USD")
        
        # Reset mock to verify second call uses cache
        mock_get_price.reset_mock()
        
        # Second call should use cache
        price = await market_monitor.get_token_price(token_address)
        assert price == expected_price
        mock_get_price.assert_not_called()


@pytest.mark.asyncio
async def test_get_token_price_cache_expiration(market_monitor):
    """Test that price cache expires after TTL."""
    # Setup with a very short TTL for testing
    market_monitor._cache_ttl = 0.1  # 100ms TTL for quick testing
    token_address = "0xToken456"
    expected_price = 200.0
    
    with patch.object(market_monitor.api_config, 'get_real_time_price', new_callable=AsyncMock) as mock_get_price:
        mock_get_price.return_value = expected_price
        
        # First call should hit the API
        price = await market_monitor.get_token_price(token_address)
        assert price == expected_price
        mock_get_price.assert_called_once()
        
        # Wait for cache to expire
        await asyncio.sleep(0.2)
        
        # Reset mock to verify next call hits API again
        mock_get_price.reset_mock()
        
        # Call after cache expiration should hit API again
        price = await market_monitor.get_token_price(token_address)
        assert price == expected_price
        mock_get_price.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_cache(market_monitor):
    """Test the cache cleanup mechanism."""
    # Setup with short TTL
    market_monitor._cache_ttl = 0.1
    market_monitor._last_cache_cleanup = time.time() - 1  # Force cleanup on next access
    
    # Populate cache with dummy data
    token1 = "0xToken1"
    token2 = "0xToken2"
    async with market_monitor._cache_lock:
        market_monitor._price_cache[token1] = {
            "timestamp": time.time() - 0.2,  # Expired
            "price": 100.0,
            "change_24h": 1.0
        }
        market_monitor._price_cache[token2] = {
            "timestamp": time.time(),  # Not expired
            "price": 200.0,
            "change_24h": 2.0
        }
    
    # Force cleanup by accessing a token price
    with patch.object(market_monitor.api_config, 'get_price', new_callable=AsyncMock) as mock_get_price:
        mock_get_price.return_value = {"price": 300.0, "change_24h": 3.0}
        await market_monitor.get_token_price("0xToken3")
    
    # Check that expired entry was removed but non-expired remains
    assert token1 not in market_monitor._price_cache
    assert token2 in market_monitor._price_cache


@pytest.mark.asyncio
async def test_get_price_data(market_monitor):
    """Test retrieving detailed price data for a token."""
    token_symbol = "ETH"
    mock_price_data = {
        "price": 3000.0,
        "volume_24h": 1000000.0,
        "market_cap": 360000000000.0,
        "change_24h": 2.5
    }
    
    with patch.object(market_monitor, '_get_token_price_data', new_callable=AsyncMock) as mock_get_price_data:
        mock_get_price_data.return_value = mock_price_data
        
        result = await market_monitor.get_price_data(token_symbol)
        
        assert result == mock_price_data
        mock_get_price_data.assert_called_once_with(token_symbol)


@pytest.mark.asyncio
async def test_get_token_volume(market_monitor):
    """Test retrieving token trading volume."""
    token_address = "0xTokenVolume"
    expected_volume = 500000.0
    
    with patch.object(market_monitor, '_get_token_volume', new_callable=AsyncMock) as mock_get_volume:
        mock_get_volume.return_value = expected_volume
        
        volume = await market_monitor.get_token_volume(token_address)
        
        assert volume == expected_volume
        mock_get_volume.assert_called_once_with(token_address)


@pytest.mark.asyncio
async def test_is_arbitrage_opportunity(market_monitor):
    """Test arbitrage opportunity detection."""
    token_address = "0xArb123"
    price1 = 100.0
    price2 = 105.0
    min_spread = 3.0  # 3% min spread
    
    # Patch the get_token_prices_across_venues method
    with patch.object(market_monitor, 'get_token_prices_across_venues', new_callable=AsyncMock) as mock_get_prices:
        mock_get_prices.return_value = {"dex1": price1, "dex2": price2}
        
        # Should be an opportunity (5% spread > 3% min)
        is_opportunity = await market_monitor.is_arbitrage_opportunity(token_address, min_spread)
        assert is_opportunity is True
        
        # Update mock for a scenario with insufficient spread
        mock_get_prices.return_value = {"dex1": 100.0, "dex2": 102.0}  # 2% spread
        is_opportunity = await market_monitor.is_arbitrage_opportunity(token_address, min_spread)
        assert is_opportunity is False


@pytest.mark.asyncio
async def test_stop(market_monitor):
    """Test the stop method closes resources properly."""
    # Create a mock session to test proper cleanup
    mock_session = AsyncMock()
    market_monitor.session = mock_session
    
    # Test stopping the market monitor
    await market_monitor.stop()
    
    # Verify session was closed
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_market_features(market_monitor):
    """Test collecting market features for a token."""
    token_address = "0xMarketFeatures"
    
    # Patch the necessary methods
    with patch.object(market_monitor, 'get_token_price', new_callable=AsyncMock) as mock_get_price, \
         patch.object(market_monitor, 'get_token_volume', new_callable=AsyncMock) as mock_get_volume, \
         patch.object(market_monitor, '_get_token_liquidity', new_callable=AsyncMock) as mock_get_liquidity, \
         patch.object(market_monitor, '_get_price_volatility', new_callable=AsyncMock) as mock_get_volatility:
        
        mock_get_price.return_value = 150.0
        mock_get_volume.return_value = 500000.0
        mock_get_liquidity.return_value = 2000000.0
        mock_get_volatility.return_value = 0.05  # 5% volatility
        
        features = await market_monitor.get_market_features(token_address)
        
        assert features["price"] == 150.0
        assert features["volume"] == 500000.0
        assert features["liquidity"] == 2000000.0
        assert features["volatility"] == 0.05

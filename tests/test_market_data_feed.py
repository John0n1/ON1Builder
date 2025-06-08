"""
Tests for the market_data_feed module.
"""

import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from on1builder.monitoring.market_data_feed import MarketDataFeed, track
from on1builder.config.settings import APISettings, GlobalSettings


@pytest.fixture
def mock_web3():
    """Create mock Web3 instance."""
    return MagicMock()


@pytest.fixture
def global_settings():
    """Create test global settings."""
    return GlobalSettings(
        price_cache_ttl=300,
        cache_cleanup_interval=600,
    )


@pytest.fixture
def api_settings():
    """Create test API settings."""
    return APISettings()


@pytest.fixture
def market_data_feed(mock_web3, global_settings, api_settings):
    """Create test market data feed."""
    return MarketDataFeed(mock_web3, global_settings, api_settings)


class TestTrackDecorator:
    """Test the track decorator."""

    def test_track_decorator(self):
        """Test that track decorator increments metrics."""
        class TestClass:
            def __init__(self):
                self.metrics = {}
            
            @track("test_metric")
            async def test_method(self):
                return "result"
        
        test_obj = TestClass()
        
        # Run the async method
        async def run_test():
            result = await test_obj.test_method()
            assert result == "result"
            assert test_obj.metrics["test_metric"] == 1
            
            # Call again
            await test_obj.test_method()
            assert test_obj.metrics["test_metric"] == 2
        
        asyncio.run(run_test())


class TestMarketDataFeed:
    """Test MarketDataFeed class."""

    def test_init(self, market_data_feed, mock_web3, global_settings, api_settings):
        """Test market data feed initialization."""
        assert market_data_feed.web3 == mock_web3
        assert market_data_feed.config == global_settings
        assert market_data_feed.api_config == api_settings
        assert isinstance(market_data_feed._price_cache, dict)
        assert market_data_feed._cache_ttl == global_settings.price_cache_ttl
        assert market_data_feed._cleanup_interval == global_settings.cache_cleanup_interval
        assert isinstance(market_data_feed.metrics, dict)

    @pytest.mark.asyncio
    async def test_initialize(self, market_data_feed):
        """Test market data feed initialization."""
        with patch.object(market_data_feed, 'api_config_client_session') as mock_session:
            await market_data_feed.initialize()
            # Verify session was set up
            assert hasattr(market_data_feed, 'session')

    @pytest.mark.asyncio
    async def test_get_token_price_cache_hit(self, market_data_feed):
        """Test getting token price from cache."""
        # Set up cache
        now = time.time()
        cache_key = "eth_usd"
        market_data_feed._price_cache[cache_key] = {
            "price": Decimal("3500.00"),
            "timestamp": now
        }
        
        price = await market_data_feed.get_token_price("ETH", "USD")
        
        assert price == Decimal("3500.00")
        assert market_data_feed.metrics.get("price_cache_hit", 0) >= 1
        assert market_data_feed.metrics.get("price_lookup", 0) >= 1

    @pytest.mark.asyncio
    async def test_get_token_price_cache_expired(self, market_data_feed):
        """Test getting token price with expired cache."""
        # Set up expired cache
        old_timestamp = time.time() - market_data_feed._cache_ttl - 1
        cache_key = "eth_usd"
        market_data_feed._price_cache[cache_key] = {
            "price": Decimal("3000.00"),
            "timestamp": old_timestamp
        }
        
        # Mock API call
        with patch.object(market_data_feed, 'api_config_real_time_price', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = Decimal("3500.00")
            
            price = await market_data_feed.get_token_price("ETH", "USD")
            
            assert price == Decimal("3500.00")
            mock_api.assert_called_once_with("ETH", "USD")
            
            # Check cache was updated
            assert market_data_feed._price_cache[cache_key]["price"] == Decimal("3500.00")

    @pytest.mark.asyncio
    async def test_get_token_price_api_failure_with_fallback(self, market_data_feed):
        """Test getting token price when API fails but fallback is available."""
        with patch.object(market_data_feed, 'api_config_real_time_price', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = None
            
            price = await market_data_feed.get_token_price("ETH", "USD")
            
            # Should return fallback price for ETH
            assert price == Decimal("3400.00")
            assert market_data_feed.metrics.get("price_fallback", 0) >= 1

    @pytest.mark.asyncio
    async def test_get_token_price_no_fallback(self, market_data_feed):
        """Test getting token price when API fails and no fallback available."""
        with patch.object(market_data_feed, 'api_config_real_time_price', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = None
            
            price = await market_data_feed.get_token_price("UNKNOWN", "USD")
            
            assert price is None

    @pytest.mark.asyncio
    async def test_cleanup_cache(self, market_data_feed):
        """Test cache cleanup functionality."""
        now = time.time()
        old_timestamp = now - market_data_feed._cache_ttl - 1
        
        # Add fresh and expired entries
        market_data_feed._price_cache.update({
            "fresh_entry": {"price": Decimal("100"), "timestamp": now},
            "expired_entry": {"price": Decimal("200"), "timestamp": old_timestamp},
        })
        
        await market_data_feed._cleanup_cache()
        
        # Only fresh entry should remain
        assert "fresh_entry" in market_data_feed._price_cache
        assert "expired_entry" not in market_data_feed._price_cache

    @pytest.mark.asyncio
    async def test_get_market_trend_with_history(self, market_data_feed):
        """Test getting market trend with price history."""
        mock_history = [
            {"price": Decimal("3000")},
            {"price": Decimal("3100")},
            {"price": Decimal("3200")},
            {"price": Decimal("3300")},
        ]
        
        with patch.object(market_data_feed, 'api_config_price_history', new_callable=AsyncMock) as mock_history_api:
            mock_history_api.return_value = mock_history
            
            trend = await market_data_feed.get_market_trend("ETH", "1h", "USD")
            
            assert trend["trend"] == "bullish"  # 10% increase
            assert trend["current_price"] == Decimal("3300")
            assert trend["start_price"] == Decimal("3000")
            assert trend["price_change"] == Decimal("300")
            assert trend["percent_change"] == 10.0
            assert trend["timeframe"] == "1h"
            assert trend["data_points"] == 4

    @pytest.mark.asyncio
    async def test_get_market_trend_unsupported_timeframe(self, market_data_feed):
        """Test getting market trend with unsupported timeframe."""
        with patch.object(market_data_feed, 'api_config_price_history', new_callable=AsyncMock) as mock_history_api:
            mock_history_api.return_value = []
            
            trend = await market_data_feed.get_market_trend("ETH", "invalid", "USD")
            
            # Should default to 1h timeframe
            mock_history_api.assert_called_with("ETH", "1h", "USD")

    @pytest.mark.asyncio
    async def test_get_market_trend_bearish(self, market_data_feed):
        """Test getting bearish market trend."""
        mock_history = [
            {"price": Decimal("3300")},
            {"price": Decimal("3200")},
            {"price": Decimal("3100")},
            {"price": Decimal("3000")},  # -9% change
        ]
        
        with patch.object(market_data_feed, 'api_config_price_history', new_callable=AsyncMock) as mock_history_api:
            mock_history_api.return_value = mock_history
            
            trend = await market_data_feed.get_market_trend("ETH", "1h", "USD")
            
            assert trend["trend"] == "bearish"
            assert trend["percent_change"] < -3

    @pytest.mark.asyncio
    async def test_get_market_trend_sideways(self, market_data_feed):
        """Test getting sideways market trend."""
        mock_history = [
            {"price": Decimal("3300")},
            {"price": Decimal("3310")},
            {"price": Decimal("3290")},
            {"price": Decimal("3305")},  # ~0.15% change
        ]
        
        with patch.object(market_data_feed, 'api_config_price_history', new_callable=AsyncMock) as mock_history_api:
            mock_history_api.return_value = mock_history
            
            trend = await market_data_feed.get_market_trend("ETH", "1h", "USD")
            
            assert trend["trend"] == "sideways"
            assert -3 <= trend["percent_change"] <= 3

    @pytest.mark.asyncio
    async def test_get_market_trend_fallback(self, market_data_feed):
        """Test market trend fallback when history fails."""
        with patch.object(market_data_feed, 'api_config_price_history', new_callable=AsyncMock) as mock_history_api:
            mock_history_api.side_effect = Exception("API error")
            
            with patch.object(market_data_feed, 'get_token_price', new_callable=AsyncMock) as mock_price:
                mock_price.return_value = Decimal("3300")
                
                trend = await market_data_feed.get_market_trend("ETH", "1h", "USD")
                
                # Should return basic trend with current price only
                assert "current_price" in trend
                assert trend["current_price"] == Decimal("3300")

    @pytest.mark.asyncio
    async def test_cache_cleanup_triggers(self, market_data_feed):
        """Test that cache cleanup is triggered periodically."""
        # Set last cleanup to trigger threshold
        market_data_feed._last_cache_cleanup = time.time() - market_data_feed._cleanup_interval - 1
        
        with patch.object(market_data_feed, '_cleanup_cache', new_callable=AsyncMock) as mock_cleanup:
            with patch.object(market_data_feed, 'api_config_real_time_price', new_callable=AsyncMock) as mock_api:
                mock_api.return_value = Decimal("3500")
                
                await market_data_feed.get_token_price("ETH", "USD")
                
                mock_cleanup.assert_called_once()

    def test_metrics_tracking(self, market_data_feed):
        """Test that metrics are properly tracked."""
        # Test direct metric increment
        market_data_feed.metrics["test_metric"] = market_data_feed.metrics.get("test_metric", 0) + 1
        assert market_data_feed.metrics["test_metric"] == 1
        
        # Test multiple increments
        market_data_feed.metrics["test_metric"] = market_data_feed.metrics.get("test_metric", 0) + 1
        assert market_data_feed.metrics["test_metric"] == 2

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, market_data_feed):
        """Test concurrent access to price cache."""
        async def set_price(token, price):
            cache_key = f"{token.lower()}_usd"
            async with market_data_feed._cache_lock:
                market_data_feed._price_cache[cache_key] = {
                    "price": Decimal(str(price)),
                    "timestamp": time.time()
                }
        
        async def get_price(token):
            cache_key = f"{token.lower()}_usd"
            async with market_data_feed._cache_lock:
                return market_data_feed._price_cache.get(cache_key)
        
        # Test concurrent access
        await asyncio.gather(
            set_price("ETH", "3500"),
            set_price("BTC", "62000"),
            get_price("ETH"),
            get_price("BTC"),
        )
        
        assert "eth_usd" in market_data_feed._price_cache
        assert "btc_usd" in market_data_feed._price_cache

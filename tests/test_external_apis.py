"""
Tests for the external_apis module.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

from on1builder.integrations.external_apis import ExternalAPIManager, Provider
from on1builder.config.settings import APISettings


@pytest.fixture
def api_settings():
    """Create test API settings."""
    return APISettings(
        coingecko_api_key="test_cg_key",
        coinmarketcap_api_key="test_cmc_key",
        cryptocompare_api_key="test_cc_key",
    )


@pytest.fixture
def api_manager(api_settings):
    """Create test API manager."""
    manager = ExternalAPIManager(api_settings)
    # Clear caches to ensure clean test state
    manager.price_cache.clear()
    manager.volume_cache.clear()
    return manager


class TestProvider:
    """Test Provider dataclass."""

    def test_provider_creation(self):
        """Test creating a provider."""
        provider = Provider(
            name="test",
            base_url="https://api.test.com",
            price_url="/price",
            rate_limit=100,
        )
        
        assert provider.name == "test"
        assert provider.base_url == "https://api.test.com"
        assert provider.price_url == "/price"
        assert provider.rate_limit == 100
        assert provider.weight == 1.0
        assert provider.success_rate == 1.0
        assert isinstance(provider.limiter, asyncio.Semaphore)

    def test_provider_post_init(self):
        """Test provider post-init creates semaphore."""
        provider = Provider(
            name="test",
            base_url="https://api.test.com",
            rate_limit=50,
        )
        
        assert provider.limiter._value == 50


class TestExternalAPIManager:
    """Test ExternalAPIManager class."""

    def test_init(self, api_manager, api_settings):
        """Test API manager initialization."""
        assert api_manager.api_settings == api_settings
        assert isinstance(api_manager.providers, dict)
        assert "binance" in api_manager.providers
        assert "coingecko" in api_manager.providers
        assert "coinmarketcap" in api_manager.providers
        assert "cryptocompare" in api_manager.providers
        assert "coinpaprika" in api_manager.providers
        
        # Check cache initialization
        assert api_manager.price_cache.maxsize == 2_000
        assert api_manager.volume_cache.maxsize == 1_000

    def test_build_providers(self, api_manager):
        """Test provider building with API keys."""
        providers = api_manager.providers
        
        # Check binance provider
        binance = providers["binance"]
        assert binance.name == "binance"
        assert binance.rate_limit == 1200
        assert binance.weight == 1.0
        
        # Check coingecko provider with API key
        coingecko = providers["coingecko"]
        assert coingecko.api_key == "test_cg_key"
        assert coingecko.rate_limit == 50  # With API key
        assert coingecko.weight == 0.8

    @pytest.mark.asyncio
    async def test_session_management(self, api_manager):
        """Test HTTP session management."""
        # Initially no session
        assert api_manager._session is None
        assert api_manager._session_users == 0
        
        # Acquire session
        await api_manager._acquire_session()
        assert api_manager._session is not None
        assert api_manager._session_users == 1
        
        # Acquire again (reuse)
        await api_manager._acquire_session()
        assert api_manager._session_users == 2
        
        # Release session
        await api_manager._release_session()
        assert api_manager._session_users == 1
        
        # Release again (close)
        await api_manager._release_session()
        assert api_manager._session_users == 0

    @pytest.mark.asyncio
    async def test_initialize(self, api_manager):
        """Test API manager initialization."""
        with patch.object(api_manager, '_load_token_mappings', new_callable=AsyncMock):
            await api_manager.initialize()
            
            assert api_manager._session is not None
            assert api_manager._session_users == 1

    @pytest.mark.asyncio
    async def test_close(self, api_manager):
        """Test API manager cleanup."""
        # Initialize first
        await api_manager.initialize()
        api_manager.price_cache["test"] = "value"
        api_manager.volume_cache["test"] = "value"
        
        # Close
        await api_manager.close()
        
        assert len(api_manager.price_cache) == 0
        assert len(api_manager.volume_cache) == 0

    @pytest.mark.asyncio
    async def test_context_manager(self, api_manager):
        """Test async context manager."""
        with patch.object(api_manager, 'initialize', new_callable=AsyncMock) as mock_init:
            with patch.object(api_manager, 'close', new_callable=AsyncMock) as mock_close:
                async with api_manager:
                    pass
                
                mock_init.assert_called_once()
                mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_token_mappings_success(self, api_manager):
        """Test successful token mappings loading."""
        mock_mappings = {
            "symbol_to_address": {"ETH": "0x123"},
            "address_to_symbol": {"0x123": "ETH"},
            "symbol_to_api_id": {"ETH": "ethereum"},
        }
        
        with patch('json.load', return_value=mock_mappings):
            with patch('on1builder.utils.path_helpers.get_resource_path') as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = True
                mock_path.return_value = mock_file
                
                with patch('builtins.open', mock_open=True):
                    await api_manager._load_token_mappings()
                
                assert api_manager.token_symbol_to_address["ETH"] == "0x123"
                assert api_manager.token_address_to_symbol["0x123"] == "ETH"
                assert api_manager.symbol_to_api_id["ETH"] == "ethereum"

    @pytest.mark.asyncio
    async def test_load_token_mappings_fallback(self, api_manager):
        """Test token mappings fallback to defaults."""
        with patch('on1builder.utils.path_helpers.get_resource_path') as mock_path:
            mock_path.return_value = None
            
            await api_manager._load_token_mappings()
            
            # Should have default mappings
            assert "ETH" in api_manager.symbol_to_api_id
            assert api_manager.symbol_to_api_id["ETH"] == "ethereum"

    def test_add_default_mappings(self, api_manager):
        """Test adding default token mappings."""
        api_manager._add_default_mappings()
        
        expected_tokens = ["ETH", "BTC", "USDT", "USDC", "BNB"]
        for token in expected_tokens:
            assert token in api_manager.symbol_to_api_id

    @pytest.mark.asyncio
    async def test_get_token_price_cached(self, api_manager):
        """Test getting cached token price."""
        # Set cache value with uppercase symbol (as implementation uses)
        api_manager.price_cache["price_ETH"] = 3500.0

        # Mock API calls to prevent actual network requests
        with patch.object(api_manager, '_fetch_price_from_provider', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None  # Shouldn't be called due to cache
            
            price = await api_manager.get_token_price("ETH")
            assert price == 3500.0
            
            # Verify no API call was made
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_token_price_provider_success(self, api_manager):
        """Test successful price fetch from provider."""
        with patch.object(api_manager, '_fetch_price_from_provider', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = 3500.0

            price = await api_manager.get_token_price("ETH")

            assert price == 3500.0
            assert "price_ETH" in api_manager.price_cache
            mock_fetch.assert_called()

    @pytest.mark.asyncio
    async def test_get_token_price_all_providers_fail(self, api_manager):
        """Test when all providers fail."""
        with patch.object(api_manager, '_fetch_price_from_provider', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            
            price = await api_manager.get_token_price("ETH")
            
            assert price is None

    @pytest.mark.asyncio
    async def test_fetch_price_from_provider_binance(self, api_manager):
        """Test fetching price from Binance."""
        mock_response_data = {"price": "3500.0"}
        
        # Mock the entire aiohttp ClientSession.get call
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            
            # Set up the async context manager
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
            
            provider = api_manager.providers["binance"]
            price = await api_manager._fetch_price_from_provider(provider, "ETH")
            
            assert price == 3500.0

    @pytest.mark.asyncio
    async def test_fetch_price_from_provider_coingecko(self, api_manager):
        """Test fetching price from CoinGecko."""
        # Set up API ID mapping
        api_manager.symbol_to_api_id["ETH"] = "ethereum"
        
        mock_response_data = {"ethereum": {"usd": 3500.0}}
        
        # Mock the entire aiohttp ClientSession.get call
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            
            # Set up the async context manager
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
            
            provider = api_manager.providers["coingecko"]
            price = await api_manager._fetch_price_from_provider(provider, "ETH")
            
            assert price == 3500.0

    @pytest.mark.asyncio
    async def test_fetch_price_from_provider_coinmarketcap(self, api_manager):
        """Test fetching price from CoinMarketCap."""
        mock_response_data = {
            "data": {
                "ETH": {
                    "quote": {
                        "USD": {"price": 3500.0}
                    }
                }
            }
        }
        
        # Mock the entire aiohttp ClientSession.get call
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            
            # Set up the async context manager
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
            
            provider = api_manager.providers["coinmarketcap"]
            price = await api_manager._fetch_price_from_provider(provider, "ETH")
            
            assert price == 3500.0

    @pytest.mark.asyncio
    async def test_fetch_price_error_handling(self, api_manager):
        """Test error handling in price fetching."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = Exception("Network error")
        
        with patch.object(api_manager, 'get_client_session', return_value=mock_session):
            provider = api_manager.providers["binance"]
            price = await api_manager._fetch_price_from_provider(provider, "ETH")
            
            assert price is None

    def test_extract_price_from_response_binance(self, api_manager):
        """Test extracting price from Binance response."""
        data = {"price": "3500.0"}
        price = api_manager._extract_price_from_response("binance", data, "ETH")
        assert price == 3500.0

    def test_extract_price_from_response_coingecko(self, api_manager):
        """Test extracting price from CoinGecko response."""
        api_manager.symbol_to_api_id["ETH"] = "ethereum"
        data = {"ethereum": {"usd": 3500.0}}
        price = api_manager._extract_price_from_response("coingecko", data, "ETH")
        assert price == 3500.0

    def test_extract_price_from_response_coinmarketcap(self, api_manager):
        """Test extracting price from CoinMarketCap response."""
        data = {
            "data": {
                "ETH": {
                    "quote": {
                        "USD": {"price": 3500.0}
                    }
                }
            }
        }
        price = api_manager._extract_price_from_response("coinmarketcap", data, "ETH")
        assert price == 3500.0

    def test_extract_price_from_response_error(self, api_manager):
        """Test error handling in price extraction."""
        data = {"invalid": "data"}
        price = api_manager._extract_price_from_response("binance", data, "ETH")
        assert price == 0.0  # Missing price key returns 0.0    @pytest.mark.asyncio
    async def test_get_token_volume_cached(self, api_manager):
        """Test getting cached token volume."""
        api_manager.volume_cache["volume_ETH"] = 1000000.0

        # Mock API calls to prevent actual network requests
        with patch.object(api_manager, '_fetch_volume_from_provider', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None  # Shouldn't be called due to cache
            
            volume = await api_manager.get_token_volume("ETH")
            assert volume == 1000000.0
            
            # Verify no API call was made
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_token_volume_provider_success(self, api_manager):
        """Test successful volume fetch from provider."""
        with patch.object(api_manager, '_fetch_volume_from_provider', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = 1000000.0
            
            volume = await api_manager.get_token_volume("ETH")
            
            assert volume == 1000000.0
            assert "volume_ETH" in api_manager.volume_cache

    @pytest.mark.asyncio
    async def test_fetch_volume_from_provider_binance(self, api_manager):
        """Test fetching volume from Binance."""
        mock_response_data = {"volume": "1000000.0"}
        
        # Mock the entire aiohttp ClientSession.get call
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            
            # Set up the async context manager
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
            
            provider = api_manager.providers["binance"]
            volume = await api_manager._fetch_volume_from_provider(provider, "ETH")
            
            assert volume == 1000000.0

    def test_extract_volume_from_response_binance(self, api_manager):
        """Test extracting volume from Binance response."""
        data = {"volume": "1000000.0"}
        volume = api_manager._extract_volume_from_response("binance", data, "ETH")
        assert volume == 1000000.0

    def test_extract_volume_from_response_coingecko(self, api_manager):
        """Test extracting volume from CoinGecko response."""
        data = {
            "market_data": {
                "total_volume": {"usd": 1000000.0}
            }
        }
        volume = api_manager._extract_volume_from_response("coingecko", data, "ETH")
        assert volume == 1000000.0

    def test_extract_volume_from_response_coinmarketcap(self, api_manager):
        """Test extracting volume from CoinMarketCap response."""
        data = {
            "data": {
                "ETH": {
                    "quote": {
                        "USD": {"volume_24h": 1000000.0}
                    }
                }
            }
        }
        volume = api_manager._extract_volume_from_response("coinmarketcap", data, "ETH")
        assert volume == 1000000.0

    @pytest.mark.asyncio
    async def test_shutdown(self, api_manager):
        """Test shutdown method."""
        with patch.object(api_manager, 'close', new_callable=AsyncMock) as mock_close:
            await api_manager.shutdown()
            mock_close.assert_called_once()

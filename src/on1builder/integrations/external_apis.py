"""
External API management for ON1Builder.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional

import aiohttp
from cachetools import TTLCache

from ..config.settings import APISettings
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class Provider:
    name: str
    base_url: str
    price_url: str | None = None
    volume_url: str | None = None
    historical_url: str | None = None
    api_key: str | None = None
    rate_limit: int = 10
    weight: float = 1.0
    success_rate: float = 1.0
    limiter: asyncio.Semaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.limiter = asyncio.Semaphore(self.rate_limit)


class ExternalAPIManager:
    """Manages external API interactions for price and market data."""

    _session: Optional[aiohttp.ClientSession] = None
    _session_users = 0
    _session_lock = asyncio.Lock()
    _MAX_REQUEST_ATTEMPTS = 4
    _BACKOFF_BASE = 1.7

    def __init__(self, api_settings: APISettings):
        self.api_settings = api_settings
        self.providers = self._build_providers()

        self.price_cache = TTLCache(maxsize=2_000, ttl=300)
        self.volume_cache = TTLCache(maxsize=1_000, ttl=900)

        self.token_address_to_symbol: Dict[str, str] = {}
        self.token_symbol_to_address: Dict[str, str] = {}
        self.symbol_to_api_id: Dict[str, str] = {}
        self.symbol_to_token_name: Dict[str, str] = {}
        self.token_name_to_symbol: Dict[str, str] = {}

    async def initialize(self) -> None:
        """Initialize the API manager and load token mappings."""
        await self._acquire_session()
        await self._load_token_mappings()
        logger.info(
            f"ExternalAPIManager initialized with {len(self.providers)} providers"
        )

    async def close(self) -> None:
        """Clean up resources."""
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
        await self._release_session()
        self.price_cache.clear()
        self.volume_cache.clear()

    async def __aenter__(self) -> "ExternalAPIManager":
        await self.initialize()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    def _build_providers(self) -> Dict[str, Provider]:
        """Build provider configurations."""
        return {
            "binance": Provider(
                name="binance",
                base_url="https://api.binance.com/api/v3",
                price_url="/ticker/price",
                volume_url="/ticker/24hr",
                rate_limit=1200,
                weight=1.0,
            ),
            "coingecko": Provider(
                name="coingecko",
                base_url="https://api.coingecko.com/api/v3",
                price_url="/simple/price",
                historical_url="/coins/{id}/market_chart",
                volume_url="/coins/{id}/market_chart",
                api_key=self.api_settings.coingecko_api_key,
                rate_limit=50 if self.api_settings.coingecko_api_key else 10,
                weight=0.8 if self.api_settings.coingecko_api_key else 0.5,
            ),
            "coinmarketcap": Provider(
                name="coinmarketcap",
                base_url="https://pro-api.coinmarketcap.com/v1",
                price_url="/cryptocurrency/quotes/latest",
                historical_url="/cryptocurrency/quotes/historical",
                volume_url="/cryptocurrency/quotes/latest",
                api_key=self.api_settings.coinmarketcap_api_key,
                rate_limit=333 if self.api_settings.coinmarketcap_api_key else 10,
                weight=0.6,
            ),
            "cryptocompare": Provider(
                name="cryptocompare",
                base_url="https://min-api.cryptocompare.com/data",
                price_url="/price",
                historical_url="/v2/histoday",
                volume_url="/top/totalvolfull",
                api_key=self.api_settings.cryptocompare_api_key,
                rate_limit=300 if self.api_settings.cryptocompare_api_key else 100,
                weight=0.4,
            ),
            "coinpaprika": Provider(
                name="coinpaprika",
                base_url="https://api.coinpaprika.com/v1",
                price_url="/tickers/{id}",
                historical_url="/coins/{id}/ohlcv/historical",
                volume_url="/tickers/{id}",
                weight=0.3,
            ),
        }

    async def _acquire_session(self) -> None:
        """Acquire or create a shared HTTP session."""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30),
                    connector=aiohttp.TCPConnector(limit=100),
                )
            self._session_users += 1

    async def _release_session(self) -> None:
        """Release the shared HTTP session."""
        async with self._session_lock:
            self._session_users -= 1
            if self._session_users <= 0 and self._session:
                await self._session.close()
                self._session = None

    async def get_client_session(self) -> aiohttp.ClientSession:
        """Get the shared HTTP session."""
        if self._session is None or self._session.closed:
            await self._acquire_session()
        return self._session

    async def _load_token_mappings(self) -> None:
        """Load token mappings from consolidated token files."""
        try:
            # Load from the consolidated resource files
            from ..utils.path_helpers import get_resource_path
            
            # Try to load symbol mappings
            symbols_file = get_resource_path("tokens", "symbol_mappings.json")
            if symbols_file and symbols_file.exists():
                import json
                with open(symbols_file) as f:
                    mappings = json.load(f)
                    self.token_symbol_to_address.update(mappings.get("symbol_to_address", {}))
                    self.token_address_to_symbol.update(mappings.get("address_to_symbol", {}))
                    self.symbol_to_api_id.update(mappings.get("symbol_to_api_id", {}))
                    logger.info(f"Loaded {len(self.token_symbol_to_address)} token mappings")
            else:
                logger.warning("Token mappings file not found, using defaults")
                # Add some common mappings
                self._add_default_mappings()
        except Exception as e:
            logger.error(f"Failed to load token mappings: {e}")
            self._add_default_mappings()

    def _add_default_mappings(self) -> None:
        """Add default token mappings for common tokens."""
        defaults = {
            "ETH": {"coingecko_id": "ethereum", "cmc_id": "1027"},
            "BTC": {"coingecko_id": "bitcoin", "cmc_id": "1"},
            "USDT": {"coingecko_id": "tether", "cmc_id": "825"},
            "USDC": {"coingecko_id": "usd-coin", "cmc_id": "3408"},
            "BNB": {"coingecko_id": "binancecoin", "cmc_id": "1839"},
        }
        
        for symbol, mapping in defaults.items():
            self.symbol_to_api_id[symbol] = mapping["coingecko_id"]
            
    async def get_token_price(self, symbol: str) -> Optional[float]:
        """Get current price for a token symbol."""
        cache_key = f"price_{symbol.upper()}"
        
        # Check cache first
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
            
        # Try each provider in order of preference
        for provider_name in ["binance", "coingecko", "coinmarketcap"]:
            try:
                provider = self.providers.get(provider_name)
                if not provider:
                    continue
                    
                async with provider.limiter:
                    price = await self._fetch_price_from_provider(provider, symbol)
                    if price is not None:
                        self.price_cache[cache_key] = price
                        provider.success_rate = min(1.0, provider.success_rate + 0.01)
                        return price
            except Exception as e:
                logger.warning(f"Failed to get price from {provider_name}: {e}")
                if provider_name in self.providers:
                    self.providers[provider_name].success_rate *= 0.95
                continue
                
        logger.error(f"Failed to get price for {symbol} from all providers")
        return None

    async def _fetch_price_from_provider(self, provider: Provider, symbol: str) -> Optional[float]:
        """Fetch price from a specific provider."""
        session = await self.get_client_session()
        
        try:
            if provider.name == "binance":
                url = f"{provider.base_url}{provider.price_url}"
                params = {"symbol": f"{symbol.upper()}USDT"}
                
            elif provider.name == "coingecko":
                api_id = self.symbol_to_api_id.get(symbol.upper())
                if not api_id:
                    return None
                url = f"{provider.base_url}{provider.price_url}"
                params = {"ids": api_id, "vs_currencies": "usd"}
                
            elif provider.name == "coinmarketcap":
                url = f"{provider.base_url}{provider.price_url}"
                params = {"symbol": symbol.upper(), "convert": "USD"}
                headers = {"X-CMC_PRO_API_KEY": provider.api_key} if provider.api_key else {}
                
            else:
                return None
                
            # Make the API request
            timeout = aiohttp.ClientTimeout(total=10)
            kwargs = {"params": params, "timeout": timeout}
            if "headers" in locals():
                kwargs["headers"] = headers
                
            async with session.get(url, **kwargs) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._extract_price_from_response(provider.name, data, symbol)
                else:
                    logger.warning(f"{provider.name} API returned status {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching price from {provider.name}: {e}")
            return None

    def _extract_price_from_response(self, provider_name: str, data: dict, symbol: str) -> Optional[float]:
        """Extract price from provider response."""
        try:
            if provider_name == "binance":
                return float(data.get("price", 0))
                
            elif provider_name == "coingecko":
                api_id = self.symbol_to_api_id.get(symbol.upper())
                if api_id and api_id in data:
                    return float(data[api_id].get("usd", 0))
                    
            elif provider_name == "coinmarketcap":
                quote = data.get("data", {}).get(symbol.upper(), {}).get("quote", {}).get("USD", {})
                return float(quote.get("price", 0))
                
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing {provider_name} response: {e}")
            
        return None

    async def get_token_volume(self, symbol: str) -> Optional[float]:
        """Get 24h volume for a token symbol."""
        cache_key = f"volume_{symbol.upper()}"
        
        # Check cache first
        if cache_key in self.volume_cache:
            return self.volume_cache[cache_key]
            
        # Try each provider in order of preference
        for provider_name in ["binance", "coingecko", "coinmarketcap"]:
            try:
                provider = self.providers.get(provider_name)
                if not provider or not provider.volume_url:
                    continue
                    
                async with provider.limiter:
                    volume = await self._fetch_volume_from_provider(provider, symbol)
                    if volume is not None:
                        self.volume_cache[cache_key] = volume
                        return volume
            except Exception as e:
                logger.warning(f"Failed to get volume from {provider_name}: {e}")
                continue
                
        logger.error(f"Failed to get volume for {symbol} from all providers")
        return None

    async def _fetch_volume_from_provider(self, provider: Provider, symbol: str) -> Optional[float]:
        """Fetch volume from a specific provider."""
        session = await self.get_client_session()
        
        try:
            if provider.name == "binance":
                url = f"{provider.base_url}{provider.volume_url}"
                params = {"symbol": f"{symbol.upper()}USDT"}
                
            elif provider.name == "coingecko":
                api_id = self.symbol_to_api_id.get(symbol.upper())
                if not api_id:
                    return None
                url = f"{provider.base_url}/coins/{api_id}"
                params = {"localization": "false", "tickers": "false", "market_data": "true"}
                
            elif provider.name == "coinmarketcap":
                url = f"{provider.base_url}{provider.volume_url}"
                params = {"symbol": symbol.upper(), "convert": "USD"}
                headers = {"X-CMC_PRO_API_KEY": provider.api_key} if provider.api_key else {}
                
            else:
                return None
                
            # Make the API request
            timeout = aiohttp.ClientTimeout(total=10)
            kwargs = {"params": params, "timeout": timeout}
            if "headers" in locals():
                kwargs["headers"] = headers
                
            async with session.get(url, **kwargs) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._extract_volume_from_response(provider.name, data, symbol)
                else:
                    logger.warning(f"{provider.name} API returned status {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching volume from {provider.name}: {e}")
            return None

    def _extract_volume_from_response(self, provider_name: str, data: dict, symbol: str) -> Optional[float]:
        """Extract volume from provider response."""
        try:
            if provider_name == "binance":
                return float(data.get("volume", 0))
                
            elif provider_name == "coingecko":
                market_data = data.get("market_data", {})
                return float(market_data.get("total_volume", {}).get("usd", 0))
                
            elif provider_name == "coinmarketcap":
                quote = data.get("data", {}).get(symbol.upper(), {}).get("quote", {}).get("USD", {})
                return float(quote.get("volume_24h", 0))
                
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing {provider_name} volume response: {e}")
            
        return None

    async def shutdown(self) -> None:
        """Shutdown the API manager and clean up resources."""
        await self.close()

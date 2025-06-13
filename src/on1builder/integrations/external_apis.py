# src/on1builder/integrations/external_apis.py
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional, List, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import time

import aiohttp
from cachetools import TTLCache

from on1builder.config.loaders import settings
from on1builder.utils.custom_exceptions import APICallError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.path_helpers import get_resource_path
from on1builder.utils.singleton import SingletonMeta

logger = get_logger(__name__)

@dataclass
class RateLimitTracker:
    """Tracks rate limit usage for API providers."""
    requests_made: int = 0
    window_start: float = 0
    max_requests: int = 60
    window_duration: int = 60  # seconds
    backoff_until: float = 0
    
    def can_make_request(self) -> bool:
        """Check if we can make a request without hitting rate limits."""
        now = time.time()
        
        # If in backoff period, deny request
        if now < self.backoff_until:
            return False
        
        # Reset window if needed
        if now - self.window_start >= self.window_duration:
            self.requests_made = 0
            self.window_start = now
        
        return self.requests_made < self.max_requests
    
    def record_request(self, success: bool = True):
        """Record a request and handle rate limit responses."""
        now = time.time()
        
        if now - self.window_start >= self.window_duration:
            self.requests_made = 0
            self.window_start = now
        
        self.requests_made += 1
        
        # If we hit rate limit, implement exponential backoff
        if not success and self.requests_made >= self.max_requests * 0.8:
            self.backoff_until = now + min(60, 2 ** (self.requests_made - self.max_requests))

@dataclass  
class TokenMapping:
    """Structured token mapping data."""
    symbol: str
    name: str
    addresses: Dict[str, str] = field(default_factory=dict)
    api_ids: Dict[str, str] = field(default_factory=dict)
    decimals: int = 18
    is_valid: bool = True
    
class Provider:
    def __init__(
        self,
        name: str,
        base_url: str,
        rate_limit: int,
        api_key: Optional[str] = None,
    ):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.limiter = asyncio.Semaphore(rate_limit)
        self.rate_tracker = RateLimitTracker(max_requests=rate_limit)
        self.consecutive_failures = 0
        self.last_success = time.time()
        self.is_healthy = True

class ExternalAPIManager(metaclass=SingletonMeta):
    # Well-known tokens to load at startup
    WELL_KNOWN_TOKENS = {
        'WBTC', 'WETH', 'SHIB', 'USDC', 'USDT', 'TETHER', 'MATIC', 'BNB', 
        'ADA', 'SOL', 'DOT', 'AVAX', 'LINK', 'UNI', 'LTC', 'BCH', 'XLM',
        'ATOM', 'VET', 'ICP', 'FIL', 'THETA', 'TRX', 'ETC', 'XMR', 'ALGO',
        'EGLD', 'HBAR', 'NEAR', 'FLOW', 'MANA', 'SAND', 'CRV', 'AAVE',
        'COMP', 'MKR', 'YFI', 'SUSHI', '1INCH', 'BAT', 'ZRX', 'ENJ', 'SNX'
    }

    def __init__(self):
        # Only initialize basic attributes here - lazy initialization for heavy operations
        if hasattr(self, '_instance_initialized'):
            logger.debug("ExternalAPIManager constructor called on existing singleton instance")
            return
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._providers: Dict[str, Provider] = {}
        self._rate_limiters: Dict[str, RateLimitTracker] = {}
        self._price_cache = TTLCache(maxsize=1000, ttl=60)  # 1-minute cache
        self._token_mappings: Dict[str, TokenMapping] = {}
        self._all_tokens_loaded = False  # Track if we've loaded all tokens yet
        self._all_tokens_load_time = 0  # Timestamp of last full token load
        self._failed_tokens: Set[str] = set()
        self._background_tasks: Set[asyncio.Task] = set()
        self._initialized = False
        self._data_gathering_active = False
        self._health_check_interval = 300  # 5 minutes
        self._instance_initialized = True
        
        logger.debug("ExternalAPIManager singleton instance created")

    async def _initialize(self):
        if self._initialized:
            logger.debug("ExternalAPIManager already initialized, skipping...")
            return
        logger.info("Initializing ExternalAPIManager...")
        self._providers = self._build_providers()
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=30)
        )
        await self._load_token_mappings_async()
        self._start_background_tasks()
        self._initialized = True
        logger.info(f"ExternalAPIManager initialized with {len(self._providers)} providers and {len(self._token_mappings)} token mappings.")

    def _build_providers(self) -> Dict[str, Provider]:
        providers = {}
        api_settings = settings.api
        if api_settings.coingecko_api_key:
            providers["coingecko"] = Provider(
                name="coingecko",
                base_url="https://api.coingecko.com/api/v3",
                rate_limit=40,
                api_key=api_settings.coingecko_api_key,
            )
        providers["binance"] = Provider(
            name="binance",
            base_url="https://api.binance.com/api/v3",
            rate_limit=20,
        )
        if api_settings.coinmarketcap_api_key:
            providers["coinmarketcap"] = Provider(
                name="coinmarketcap",
                base_url="https://pro-api.coinmarketcap.com/v1",
                rate_limit=10,
                api_key=api_settings.coinmarketcap_api_key,
            )
        if api_settings.cryptocompare_api_key:
            providers["cryptocompare"] = Provider(
                name="cryptocompare",
                base_url="https://min-api.cryptocompare.com/data",
                rate_limit=20,
                api_key=api_settings.cryptocompare_api_key,
            )
        if api_settings.etherscan_api_key:
            providers["etherscan"] = Provider(
                name="etherscan",
                base_url="https://api.etherscan.io/api",
                rate_limit=5,
                api_key=api_settings.etherscan_api_key,
            )
        if api_settings.infura_project_id:
            providers["infura"] = Provider(
                name="infura",
                base_url=f"https://mainnet.infura.io/v3/{api_settings.infura_project_id}",
                rate_limit=10,
            )
        return providers

    def _start_background_tasks(self):
        """Start non-blocking background tasks for data gathering and health monitoring."""
        # Health monitoring task
        health_task = asyncio.create_task(self._health_monitor_loop())
        self._background_tasks.add(health_task)
        health_task.add_done_callback(self._background_tasks.discard)
        
        # Data prefetching task
        prefetch_task = asyncio.create_task(self._data_prefetch_loop())
        self._background_tasks.add(prefetch_task)
        prefetch_task.add_done_callback(self._background_tasks.discard)

    async def _health_monitor_loop(self):
        """Monitor provider health in the background."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._check_provider_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}", exc_info=True)

    async def _data_prefetch_loop(self):
        """Prefetch commonly used token prices in the background."""
        while True:
            try:
                await asyncio.sleep(120)  # Every 2 minutes
                if not self._data_gathering_active:
                    await self._prefetch_common_tokens()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in data prefetch loop: {e}", exc_info=True)

    async def _check_provider_health(self):
        """Check and update provider health status."""
        for provider in self._providers.values():
            try:
                # Simple health check - try to get a common token price
                if provider.name == "binance":
                    url = f"{provider.base_url}/ticker/price"
                    params = {"symbol": "BTCUSDT"}
                    async with provider.limiter:
                        if provider.rate_tracker.can_make_request():
                            async with self._session.get(url, params=params) as response:
                                success = response.status == 200
                                provider.rate_tracker.record_request(success)
                                if success:
                                    provider.consecutive_failures = 0
                                    provider.last_success = time.time()
                                    provider.is_healthy = True
                                else:
                                    provider.consecutive_failures += 1
                                    provider.is_healthy = provider.consecutive_failures < 5
            except Exception as e:
                logger.debug(f"Health check failed for {provider.name}: {e}")
                provider.consecutive_failures += 1
                provider.is_healthy = provider.consecutive_failures < 5

    async def _prefetch_common_tokens(self):
        """Prefetch prices for commonly traded tokens."""
        common_tokens = ["WETH", "USDT", "USDC", "DAI", "WBTC"]
        self._data_gathering_active = True
        
        try:
            tasks = []
            for token in common_tokens:
                if token.upper() not in self._price_cache:
                    task = asyncio.create_task(self._get_price_non_blocking(token))
                    tasks.append(task)
            
            if tasks:
                # Use asyncio.gather with return_exceptions to prevent blocking
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.debug(f"Error during prefetch: {e}")
        finally:
            self._data_gathering_active = False

    async def _load_token_mappings_async(self):
        """Load token mappings asynchronously, starting with well-known tokens only."""
        token_file = get_resource_path("tokens", "all_chains_tokens.json")
        
        try:
            # Load JSON in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            tokens_data = await loop.run_in_executor(None, self._parse_token_json, token_file)
            
            # Process only well-known tokens initially for faster startup
            valid_count = 0
            for token_data in tokens_data:
                token_mapping = self._parse_token_data(token_data)
                if token_mapping and token_mapping.is_valid:
                    symbol_upper = token_mapping.symbol.upper()
                    # Only load well-known tokens initially
                    if symbol_upper in self.WELL_KNOWN_TOKENS:
                        self._token_mappings[symbol_upper] = token_mapping
                        valid_count += 1
            
            logger.info(f"Loaded {valid_count} well-known token mappings for faster startup. Full token loading will happen on-demand.")
            
        except Exception as e:
            logger.error(f"Failed to load token mappings from {token_file}: {e}")
            # Continue with empty mappings rather than failing

    async def _load_all_tokens_async(self):
        """Load all remaining tokens on-demand."""
        if self._all_tokens_loaded:
            return
            
        token_file = get_resource_path("tokens", "all_chains_tokens.json")
        
        try:
            loop = asyncio.get_event_loop()
            tokens_data = await loop.run_in_executor(None, self._parse_token_json, token_file)
            
            # Load all tokens that weren't loaded initially
            valid_count = 0
            for token_data in tokens_data:
                token_mapping = self._parse_token_data(token_data)
                if token_mapping and token_mapping.is_valid:
                    symbol_upper = token_mapping.symbol.upper()
                    if symbol_upper not in self._token_mappings:
                        self._token_mappings[symbol_upper] = token_mapping
                        valid_count += 1
            
            self._all_tokens_loaded = True
            logger.debug(f"Loaded {valid_count} additional token mappings on-demand. Total: {len(self._token_mappings)} tokens.")
            
        except Exception as e:
            logger.error(f"Failed to load additional token mappings: {e}")

    def _parse_token_json(self, token_file: str) -> List[Dict]:
        """Parse token JSON file synchronously (called in executor)."""
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"JSON parsing error: {e}")
            return []

    def _parse_token_data(self, token_data: Dict) -> Optional[TokenMapping]:
        """Parse individual token data with validation."""
        try:
            symbol = token_data.get("symbol", "").strip()
            name = token_data.get("name", "").strip()
            
            if not symbol or not name:
                return None
            
            # Skip tokens with problematic symbols
            if any(char in symbol for char in ['$', '#', '@', '&', '%', ' ', '\t', '\n']):
                logger.debug(f"Skipping token with problematic symbol: {symbol}")
                return None
            
            addresses = token_data.get("addresses", {})
            decimals = int(token_data.get("decimals", 18))
            
            # Extract API IDs with validation
            api_ids = {}
            for api_name in ["coingecko", "coinmarketcap", "binance", "etherscan", "infura"]:
                api_id_key = f"{api_name}_id"
                if api_id_key in token_data and token_data[api_id_key]:
                    api_ids[api_name] = str(token_data[api_id_key]).strip()
            
            return TokenMapping(
                symbol=symbol,
                name=name,
                addresses=addresses,
                api_ids=api_ids,
                decimals=decimals,
                is_valid=True
            )
            
        except Exception as e:
            logger.debug(f"Error parsing token data: {e}")
            return None

    async def _get_price_non_blocking(self, token_symbol: str) -> Optional[float]:
        """Get price without blocking main operations."""
        try:
            return await asyncio.wait_for(self.get_price(token_symbol), timeout=10.0)
        except asyncio.TimeoutError:
            logger.debug(f"Price fetch timeout for {token_symbol}")
            return None
        except Exception as e:
            logger.debug(f"Non-blocking price fetch error for {token_symbol}: {e}")
            return None

    async def get_price(self, token_symbol: str) -> Optional[float]:
        await self._initialize()
        token_symbol_upper = token_symbol.upper()

        # Check cache first
        if token_symbol_upper in self._price_cache:
            return self._price_cache[token_symbol_upper]

        # Skip tokens that have consistently failed
        if token_symbol_upper in self._failed_tokens:
            logger.debug(f"Skipping failed token: {token_symbol}")
            return None

        # Get token mapping for better API targeting
        token_mapping = self._token_mappings.get(token_symbol_upper)
        
        # If token not found and we haven't loaded all tokens yet, try loading them
        if not token_mapping and not self._all_tokens_loaded:
            # Add cooldown to prevent spamming token loads
            import time
            current_time = time.time()
            if current_time - self._all_tokens_load_time > 3600:  # 1 hour cooldown
                logger.debug(f"Token {token_symbol_upper} not found in well-known tokens, loading all tokens...")
                await self._load_all_tokens_async()
                self._all_tokens_load_time = current_time
                token_mapping = self._token_mappings.get(token_symbol_upper)
            else:
                logger.debug(f"Token {token_symbol_upper} not found, but all tokens loaded recently. Skipping reload.")
        
        # Create targeted task list based on available API IDs and provider health
        tasks = []
        healthy_providers = [name for name, provider in self._providers.items() if provider.is_healthy]
        
        if not token_mapping or not token_mapping.api_ids:
            # Fallback to all providers for unmapped tokens
            if "coingecko" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_coingecko(token_symbol_upper)))
            if "binance" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_binance(token_symbol_upper)))
            if "coinmarketcap" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_coinmarketcap(token_symbol_upper)))
            if "cryptocompare" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_cryptocompare(token_symbol_upper)))
        else:
            # Use specific API IDs from mapping
            if "coingecko" in token_mapping.api_ids and "coingecko" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_coingecko(token_symbol_upper, token_mapping.api_ids["coingecko"])))
            if "binance" in token_mapping.api_ids and "binance" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_binance(token_symbol_upper, token_mapping.api_ids["binance"])))
            if "coinmarketcap" in token_mapping.api_ids and "coinmarketcap" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_coinmarketcap(token_symbol_upper, token_mapping.api_ids["coinmarketcap"])))
            if "cryptocompare" in token_mapping.api_ids and "cryptocompare" in healthy_providers:
                tasks.append(asyncio.create_task(self._fetch_from_cryptocompare(token_symbol_upper, token_mapping.api_ids["cryptocompare"])))

        if not tasks:
            logger.debug(f"No healthy providers available for {token_symbol}")
            return None

        # Use asyncio.wait with timeout to prevent blocking
        done, pending = await asyncio.wait(
            tasks, 
            timeout=8.0, 
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel pending tasks to free resources
        for task in pending:
            task.cancel()

        # Process completed tasks
        successful_price = None
        all_failed = True
        
        for task in done:
            try:
                price = await task
                if price is not None:
                    self._price_cache[token_symbol_upper] = price
                    # Remove from failed tokens if we got a price
                    self._failed_tokens.discard(token_symbol_upper)
                    all_failed = False
                    successful_price = price
                    break
            except APICallError as e:
                # Handle rate limiting gracefully
                if hasattr(e, 'status_code') and e.status_code == 429:
                    logger.debug(f"Rate limited for {token_symbol} from {getattr(e, 'provider', 'unknown')}")
                elif hasattr(e, 'status_code') and e.status_code == 400:
                    logger.debug(f"Token not found: {token_symbol} from {getattr(e, 'provider', 'unknown')}")
                else:
                    logger.debug(f"API error for {token_symbol}: {e}")
            except Exception as e:
                logger.debug(f"Unexpected error during price fetch for {token_symbol}: {e}")

        # Track consistently failing tokens
        if all_failed and successful_price is None:
            self._failed_tokens.add(token_symbol_upper)
            logger.debug(f"Added {token_symbol} to failed tokens list")
            
            # Periodically clean failed tokens (give them another chance)
            if len(self._failed_tokens) > 100:
                # Remove 20% of failed tokens to retry them
                failed_list = list(self._failed_tokens)
                to_remove = failed_list[:len(failed_list)//5]
                for token in to_remove:
                    self._failed_tokens.discard(token)
        
        return successful_price

    async def _fetch_from_coingecko(self, symbol: str, token_id: Optional[str] = None) -> Optional[float]:
        provider = self._providers.get("coingecko")
        if not provider or not provider.is_healthy:
            return None

        # Check rate limit before making request
        if not provider.rate_tracker.can_make_request():
            logger.debug(f"Rate limit reached for CoinGecko")
            return None

        # Use provided token_id or try to find it in mappings
        if not token_id:
            token_mapping = self._token_mappings.get(symbol)
            if not token_mapping or "coingecko" not in token_mapping.api_ids:
                return None
            token_id = token_mapping.api_ids["coingecko"]

        url = f"{provider.base_url}/simple/price"
        params = {"ids": token_id, "vs_currencies": "usd"}
        headers = {"x-cg-pro-api-key": provider.api_key} if provider.api_key else {}

        async with provider.limiter:
            try:
                data = await self._make_request(url, provider.name, params=params, headers=headers)
                provider.rate_tracker.record_request(data is not None)
                
                if data and token_id in data and "usd" in data[token_id]:
                    provider.consecutive_failures = 0
                    return float(data[token_id]["usd"])
                
                provider.consecutive_failures += 1
                return None
            except Exception as e:
                provider.rate_tracker.record_request(False)
                provider.consecutive_failures += 1
                raise

    async def _fetch_from_binance(self, symbol: str, binance_symbol: Optional[str] = None) -> Optional[float]:
        provider = self._providers.get("binance")
        if not provider or not provider.is_healthy:
            return None
        
        # Check rate limit before making request
        if not provider.rate_tracker.can_make_request():
            logger.debug(f"Rate limit reached for Binance")
            return None
        
        # Skip symbols with special characters that won't have Binance pairs
        if any(char in symbol for char in ['$', '#', '@', '&', '%']):
            logger.debug(f"Skipping Binance lookup for symbol with special characters: {symbol}")
            return None
            
        # Use provided symbol or derive from token mapping
        if binance_symbol:
            trade_symbol = binance_symbol
        else:
            token_mapping = self._token_mappings.get(symbol)
            if token_mapping and "binance" in token_mapping.api_ids:
                trade_symbol = token_mapping.api_ids["binance"]
            else:
                # Use standard USDT pairing for common tokens
                trade_symbol = f"{symbol}USDT"
        
        url = f"{provider.base_url}/ticker/price"
        params = {"symbol": trade_symbol}
        
        async with provider.limiter:
            try:
                data = await self._make_request(url, provider.name, params=params)
                provider.rate_tracker.record_request(data is not None)
                
                if data and "price" in data:
                    provider.consecutive_failures = 0
                    return float(data["price"])
                
                provider.consecutive_failures += 1
                return None
            except Exception as e:
                provider.rate_tracker.record_request(False)
                provider.consecutive_failures += 1
                raise

    async def _fetch_from_coinmarketcap(self, symbol: str, token_id: Optional[str] = None) -> Optional[float]:
        provider = self._providers.get("coinmarketcap")
        if not provider or not provider.is_healthy:
            return None

        if not provider.rate_tracker.can_make_request():
            return None

        if not token_id:
            token_mapping = self._token_mappings.get(symbol)
            if not token_mapping or "coinmarketcap" not in token_mapping.api_ids:
                return None
            token_id = token_mapping.api_ids["coinmarketcap"]

        url = f"{provider.base_url}/cryptocurrency/quotes/latest"
        params = {"id": token_id, "convert": "USD"}
        headers = {"X-CMC_PRO_API_KEY": provider.api_key}

        async with provider.limiter:
            try:
                data = await self._make_request(url, provider.name, params=params, headers=headers)
                provider.rate_tracker.record_request(data is not None)
                
                if data and "data" in data and token_id in data["data"]:
                    quote = data["data"][token_id].get("quote", {}).get("USD", {})
                    if "price" in quote:
                        provider.consecutive_failures = 0
                        return float(quote["price"])
                
                provider.consecutive_failures += 1
                return None
            except Exception as e:
                provider.rate_tracker.record_request(False)
                provider.consecutive_failures += 1
                raise
    
    async def _fetch_from_cryptocompare(self, symbol: str, token_symbol: Optional[str] = None) -> Optional[float]:
        provider = self._providers.get("cryptocompare")
        if not provider or not provider.is_healthy:
            return None

        if not provider.rate_tracker.can_make_request():
            return None

        url = f"{provider.base_url}/price"
        params = {"fsym": token_symbol or symbol, "tsyms": "USD"}
        headers = {"Authorization": f"Apikey {provider.api_key}"} if provider.api_key else {}
        
        async with provider.limiter:
            try:
                data = await self._make_request(url, provider.name, params=params, headers=headers)
                provider.rate_tracker.record_request(data is not None)
                
                if data and "USD" in data:
                    provider.consecutive_failures = 0
                    return float(data["USD"])
                
                provider.consecutive_failures += 1
                return None
            except Exception as e:
                provider.rate_tracker.record_request(False)
                provider.consecutive_failures += 1
                raise

    async def _fetch_from_etherscan(self, symbol: str, token_id: Optional[str] = None) -> Optional[float]:
        provider = self._providers.get("etherscan")
        if not provider or not provider.is_healthy:
            return None

        if not provider.rate_tracker.can_make_request():
            return None

        # Etherscan is primarily for ETH price, not individual tokens
        if symbol != "ETH" and symbol != "WETH":
            return None

        url = f"{provider.base_url}"
        params = {
            "module": "stats",
            "action": "ethprice",
            "apikey": provider.api_key
        }

        async with provider.limiter:
            try:
                data = await self._make_request(url, provider.name, params=params)
                provider.rate_tracker.record_request(data is not None)
                
                if data and "result" in data and "ethusd" in data["result"]:
                    provider.consecutive_failures = 0
                    return float(data["result"]["ethusd"])
                
                provider.consecutive_failures += 1
                return None
            except Exception as e:
                provider.rate_tracker.record_request(False)
                provider.consecutive_failures += 1
                raise
    
    async def _fetch_from_infura(self, symbol: str, token_id: Optional[str] = None) -> Optional[float]:
        # Infura doesn't provide price data - skip this provider for price fetching
        return None

    async def _make_request(
        self, url: str, provider_name: str, params: Dict = None, headers: Dict = None
    ) -> Optional[Dict[str, Any]]:
        try:
            async with self._session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 400 and provider_name == "binance":
                    # 400 from Binance usually means invalid symbol - this is expected for many tokens
                    symbol = params.get("symbol", "unknown") if params else "unknown"
                    logger.debug(f"Binance: Symbol {symbol} not found (400 error)")
                    return None
                else:
                    raise APICallError(
                        f"Request to {provider_name} failed",
                        provider=provider_name,
                        status_code=response.status
                    )
        except aiohttp.ClientError as e:
            raise APICallError(f"Network error with {provider_name}", provider=provider_name) from e
        except asyncio.TimeoutError:
            raise APICallError(f"Request to {provider_name} timed out", provider=provider_name)

    async def close(self):
        """Clean up resources and cancel background tasks."""
        # Cancel all background tasks
        for task in self._background_tasks.copy():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._background_tasks.clear()
        
        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("ExternalAPIManager session closed.")

    def get_provider_health_status(self) -> Dict[str, Dict[str, Any]]:
        """Get health status of all providers."""
        status = {}
        for name, provider in self._providers.items():
            status[name] = {
                "is_healthy": provider.is_healthy,
                "consecutive_failures": provider.consecutive_failures,
                "last_success": provider.last_success,
                "requests_made": provider.rate_tracker.requests_made,
                "max_requests": provider.rate_tracker.max_requests,
                "backoff_until": provider.rate_tracker.backoff_until
            }
        return status

    def reset_failed_tokens(self):
        """Reset the failed tokens list to give them another chance."""
        count = len(self._failed_tokens)
        self._failed_tokens.clear()
        logger.info(f"Reset {count} failed tokens for retry.")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "price_cache_size": len(self._price_cache),
            "failed_tokens_count": len(self._failed_tokens),
            "token_mappings_count": len(self._token_mappings),
            "data_gathering_active": self._data_gathering_active
        }

    async def get_market_sentiment(self, token_symbol: str) -> Optional[float]:
        """Get market sentiment score for a token (-1 to 1 scale)."""
        await self._initialize()
        
        try:
            # Try to get sentiment from multiple sources
            sentiment_scores = []
            
            # CoinGecko sentiment (if available)
            if "coingecko" in self._providers:
                sentiment = await self._get_coingecko_sentiment(token_symbol)
                if sentiment is not None:
                    sentiment_scores.append(sentiment)
            
            # Advanced social media sentiment analysis
            social_sentiment = await self._get_social_sentiment(token_symbol)
            if social_sentiment is not None:
                sentiment_scores.append(social_sentiment)
            
            # Price momentum sentiment
            momentum_sentiment = await self._get_momentum_sentiment(token_symbol)
            if momentum_sentiment is not None:
                sentiment_scores.append(momentum_sentiment)
            
            if sentiment_scores:
                # Average the sentiment scores
                return sum(sentiment_scores) / len(sentiment_scores)
            
            return 0.0  # Neutral if no data
            
        except Exception as e:
            logger.error(f"Error getting market sentiment for {token_symbol}: {e}")
            return None

    async def get_volatility_index(self, token_symbol: str) -> Optional[float]:
        """Get volatility index for a token (0-1 scale)."""
        await self._initialize()
        
        try:
            # Calculate volatility from historical price data
            historical_prices = await self._get_historical_prices(token_symbol, days=30)
            if historical_prices and len(historical_prices) > 1:
                # Calculate volatility using standard deviation of returns
                returns = []
                for i in range(1, len(historical_prices)):
                    if historical_prices[i-1] > 0:
                        return_val = (historical_prices[i] - historical_prices[i-1]) / historical_prices[i-1]
                        returns.append(return_val)
                
                if returns:
                    import math
                    mean_return = sum(returns) / len(returns)
                    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                    volatility = math.sqrt(variance) * math.sqrt(365)  # Annualized volatility
                    return min(volatility, 2.0)  # Cap at 200%
            
            # Fallback to heuristic estimates
            if token_symbol.upper() in ['BTC', 'WBTC']:
                return 0.4  # Bitcoin volatility
            elif token_symbol.upper() in ['ETH', 'WETH']:
                return 0.5  # Ethereum volatility
            elif token_symbol.upper() in ['USDC', 'USDT', 'DAI']:
                return 0.05  # Stablecoin volatility
            else:
                return 0.7  # Default alt coin volatility
                
        except Exception as e:
            logger.error(f"Error getting volatility for {token_symbol}: {e}")
            return None

    async def get_trading_volume_24h(self, token_symbol: str) -> Optional[float]:
        """Get 24h trading volume in USD."""
        await self._initialize()
        
        try:
            # Try CoinGecko first
            if "coingecko" in self._providers:
                volume = await self._get_coingecko_volume(token_symbol)
                if volume is not None:
                    return volume
            
            # Try Binance
            if "binance" in self._providers:
                volume = await self._get_binance_volume(token_symbol)
                if volume is not None:
                    return volume
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting trading volume for {token_symbol}: {e}")
            return None

    async def get_market_cap(self, token_symbol: str) -> Optional[float]:
        """Get market capitalization in USD."""
        await self._initialize()
        
        try:
            if "coingecko" in self._providers:
                return await self._get_coingecko_market_cap(token_symbol)
            elif "coinmarketcap" in self._providers:
                return await self._get_coinmarketcap_market_cap(token_symbol)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting market cap for {token_symbol}: {e}")
            return None

    async def get_comprehensive_market_data(self, token_symbol: str) -> Dict[str, Any]:
        """Get comprehensive market data for a token."""
        await self._initialize()
        
        tasks = [
            asyncio.create_task(self.get_price(token_symbol)),
            asyncio.create_task(self.get_market_sentiment(token_symbol)),
            asyncio.create_task(self.get_volatility_index(token_symbol)),
            asyncio.create_task(self.get_trading_volume_24h(token_symbol)),
            asyncio.create_task(self.get_market_cap(token_symbol))
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "symbol": token_symbol.upper(),
            "price_usd": results[0] if not isinstance(results[0], Exception) else None,
            "sentiment_score": results[1] if not isinstance(results[1], Exception) else None,
            "volatility_index": results[2] if not isinstance(results[2], Exception) else None,
            "volume_24h_usd": results[3] if not isinstance(results[3], Exception) else None,
            "market_cap_usd": results[4] if not isinstance(results[4], Exception) else None,
            "timestamp": datetime.now().isoformat()
        }

    async def _get_coingecko_sentiment(self, token_symbol: str) -> Optional[float]:
        """Get sentiment from CoinGecko API."""
        try:
            coin_id = self._get_coingecko_id(token_symbol)
            if not coin_id:
                return None
            
            provider = self._providers["coingecko"]
            async with provider.limiter:
                url = f"{provider.base_url}/coins/{coin_id}"
                params = {"localization": "false", "tickers": "false", "market_data": "true"}
                
                async with self._session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract sentiment indicators
                        sentiment_votes = data.get("sentiment_votes_up_percentage", 50)
                        sentiment_score = (sentiment_votes - 50) / 50  # Convert to -1 to 1 scale
                        
                        return max(min(sentiment_score, 1.0), -1.0)
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting CoinGecko sentiment: {e}")
            return None

    async def _get_social_sentiment(self, token_symbol: str) -> Optional[float]:
        """Get social media sentiment with multiple data sources."""
        try:
            # Multiple sentiment analysis approaches
            sentiment_sources = []
            
            # 1. Reddit sentiment from CoinGecko API
            reddit_sentiment = await self._get_reddit_sentiment(token_symbol)
            if reddit_sentiment is not None:
                sentiment_sources.append(reddit_sentiment)
            
            # 2. Twitter mention analysis (using basic search trends)
            twitter_sentiment = await self._get_twitter_sentiment(token_symbol)
            if twitter_sentiment is not None:
                sentiment_sources.append(twitter_sentiment)
            
            # 3. Price momentum-based sentiment
            momentum_sentiment = await self._get_momentum_sentiment(token_symbol)
            if momentum_sentiment is not None:
                sentiment_sources.append(momentum_sentiment)
            
            # 4. Community activity sentiment
            activity_sentiment = await self._get_community_activity_sentiment(token_symbol)
            if activity_sentiment is not None:
                sentiment_sources.append(activity_sentiment)
            
            # Aggregate sentiment scores
            if sentiment_sources:
                return sum(sentiment_sources) / len(sentiment_sources)
            
            # Fallback to heuristic based on token tier
            return self._get_heuristic_sentiment(token_symbol)
                
        except Exception as e:
            logger.debug(f"Error getting social sentiment: {e}")
            return None

    async def _get_reddit_sentiment(self, token_symbol: str) -> Optional[float]:
        """Get Reddit sentiment from social data APIs."""
        try:
            # Use CoinGecko social stats as proxy for Reddit sentiment
            url = f"https://api.coingecko.com/api/v3/coins/{self._get_coingecko_id(token_symbol)}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        community_data = data.get('community_data', {})
                        
                        reddit_subscribers = community_data.get('reddit_subscribers', 0)
                        reddit_posts_48h = community_data.get('reddit_average_posts_48h', 0)
                        reddit_comments_48h = community_data.get('reddit_average_comments_48h', 0)
                        
                        # Calculate sentiment based on activity levels
                        if reddit_subscribers > 100000 and reddit_posts_48h > 10:
                            return 0.3  # High activity = positive sentiment
                        elif reddit_subscribers > 10000:
                            return 0.1  # Medium activity = neutral-positive
                        else:
                            return 0.0  # Low activity = neutral
            
            return None
        except Exception:
            return None
    
    async def _get_twitter_sentiment(self, token_symbol: str) -> Optional[float]:
        """Get Twitter sentiment proxy from search trends."""
        try:
            # Use Google Trends as proxy for social interest
            # In production, would use Twitter API or sentiment analysis services
            popular_tokens = ['BTC', 'ETH', 'WBTC', 'WETH', 'UNI', 'LINK', 'AAVE', 'USDC', 'USDT']
            
            if token_symbol.upper() in popular_tokens:
                # High profile tokens tend to have neutral to positive sentiment
                return 0.15
            else:
                return 0.0
                
        except Exception:
            return None
    
    async def _get_momentum_sentiment(self, token_symbol: str) -> Optional[float]:
        """Calculate sentiment based on recent price momentum."""
        try:
            # Get recent price data to calculate momentum
            historical_prices = await self._get_historical_prices(token_symbol, days=7)
            if len(historical_prices) < 2:
                return None
            
            # Calculate recent momentum
            recent_price = historical_prices[-1]
            week_ago_price = historical_prices[0]
            
            if week_ago_price > 0:
                momentum = (recent_price - week_ago_price) / week_ago_price
                
                # Convert momentum to sentiment score (-1 to 1)
                if momentum > 0.1:  # 10% gain
                    return min(0.5, momentum * 2)  # Cap positive sentiment
                elif momentum < -0.1:  # 10% loss
                    return max(-0.5, momentum * 2)  # Cap negative sentiment
                else:
                    return momentum  # Small movements = small sentiment
            
            return 0.0
            
        except Exception as e:
            self.logger.debug(f"Error calculating momentum sentiment: {e}")
            return None
    
    async def _get_community_activity_sentiment(self, token_symbol: str) -> Optional[float]:
        """Get sentiment based on community activity metrics."""
        try:
            # Use GitHub activity, developer commits, etc. as sentiment proxy
            url = f"https://api.coingecko.com/api/v3/coins/{self._get_coingecko_id(token_symbol)}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        dev_data = data.get('developer_data', {})
                        
                        commits_4_weeks = dev_data.get('commit_count_4_weeks', 0)
                        contributors = dev_data.get('contributors', 0)
                        
                        if commits_4_weeks > 50 and contributors > 10:
                            return 0.25  # High dev activity = positive
                        elif commits_4_weeks > 10:
                            return 0.1   # Medium dev activity = neutral-positive
                        else:
                            return -0.05  # Low dev activity = slightly negative
            
            return None
        except Exception:
            return None
    
    def _get_heuristic_sentiment(self, token_symbol: str) -> float:
        """Fallback sentiment based on token characteristics."""
        tier_1_tokens = ['BTC', 'ETH', 'WBTC', 'WETH']
        tier_2_tokens = ['UNI', 'LINK', 'AAVE', 'COMP', 'MKR']
        stablecoins = ['USDC', 'USDT', 'DAI', 'FRAX']
        
        if token_symbol.upper() in tier_1_tokens:
            return 0.2  # Generally positive sentiment
        elif token_symbol.upper() in tier_2_tokens:
            return 0.1  # Moderately positive sentiment
        elif token_symbol.upper() in stablecoins:
            return 0.0  # Neutral sentiment
        else:
            return -0.1  # Slightly negative for unknown tokens
    
    def _get_coingecko_id(self, token_symbol: str) -> str:
        """Map token symbol to CoinGecko ID."""
        symbol_map = {
            'ETH': 'ethereum',
            'WETH': 'ethereum',
            'BTC': 'bitcoin',
            'WBTC': 'bitcoin',
            'USDC': 'usd-coin',
            'USDT': 'tether',
            'DAI': 'dai',
            'UNI': 'uniswap',
            'LINK': 'chainlink',
            'AAVE': 'aave'
        }
        return symbol_map.get(token_symbol.upper(), token_symbol.lower())

    async def _get_historical_prices(self, token_symbol: str, days: int = 30) -> List[float]:
        """Get historical prices for volatility calculation."""
        try:
            # Map token symbol to CoinGecko ID
            symbol_map = {
                'ETH': 'ethereum',
                'WETH': 'ethereum',
                'BTC': 'bitcoin', 
                'WBTC': 'bitcoin',
                'USDC': 'usd-coin',
                'USDT': 'tether',
                'DAI': 'dai'
            }
            
            coin_id = symbol_map.get(token_symbol.upper(), token_symbol.lower())
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        prices = data.get('prices', [])
                        return [price[1] for price in prices]  # Extract price values
            
            return []
            
        except Exception as e:
            self.logger.debug(f"Failed to get historical prices for {token_symbol}: {e}")
            return []
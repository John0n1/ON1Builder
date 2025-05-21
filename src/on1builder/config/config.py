# api_config.py
"""
ON1Builder – APIConfig & Configuration
======================================

Configuration management and API interaction layer.
"""

from __future__ import annotations

import asyncio
import os
import random
import yaml
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import joblib
import pandas as pd
from cachetools import TTLCache
from dotenv import load_dotenv

from on1builder.utils.logger import setup_logging

logger = setup_logging("Config", level="DEBUG")


class Configuration:
    """Base configuration class for ON1Builder."""
    
    # Chains that need the geth/erigon "extraData" PoA middleware
    POA_CHAINS = {99, 100, 77, 7766, 56, 11155111}
    
    # Default configuration values
    _DEFAULTS = {
        # API provider configuration keys
        "GRAPH_API_KEY": "",
        "UNISWAP_V2_SUBGRAPH_ID": "",
        "COINGECKO_API_KEY": "",
        "DEBUG": False,
        "BASE_PATH": str(Path(__file__).parent.parent.parent.parent),
        "HTTP_ENDPOINT": "https://ethereum-rpc.publicnode.com",
        "WEBSOCKET_ENDPOINT": "wss://ethereum-rpc.publicnode.com",
        "IPC_ENDPOINT": None,
        "SAFETYNET_CACHE_TTL": 60,
        "SAFETYNET_GAS_PRICE_TTL": 10,
        "MAX_GAS_PRICE_GWEI": 100,
        "MIN_PROFIT": 0.001,
        "WALLET_KEY": "",
        "TRANSACTION_RETRY_COUNT": 3,
        "TRANSACTION_RETRY_DELAY": 1.0,
        "GAS_MULTIPLIER": 1.1,
        "CONNECTION_RETRY_COUNT": 3,
        "CONNECTION_RETRY_DELAY": 2.0,
        "WEB3_MAX_RETRIES": 3,
        "MEMORY_CHECK_INTERVAL": 300,
        # TTL for market data cache
        "MARKET_CACHE_TTL": 60,
        # Maximum number of parallel tasks for mempool processing
        "MEMPOOL_MAX_PARALLEL_TASKS": 5,
    }
    
    def __init__(self, config_path=None, env_file=None, skip_env=False):
        """Initialize with optional config path and environment file.
        
        Args:
            config_path: Path to YAML configuration file
            env_file: Path to .env file
            skip_env: If True, skip loading environment variables
        """
        logger.debug("Configuration.__init__ called with config_path=%s, env_file=%s, skip_env=%s", 
                     config_path, env_file, skip_env)
        
        self._config = {}
        self._config.update(self._DEFAULTS)
        
        # Store path info
        self.config_path = config_path
        self.BASE_PATH = self._config["BASE_PATH"]
        
        # Set default config path if none provided
        if not config_path:
            self.config_path = os.path.join(self.BASE_PATH, "configs", "chains", "config.yaml")
        
        logger.debug("Using config_path: %s", self.config_path)
        
        # Load environment variables
        if not skip_env:
            if env_file and os.path.exists(env_file):
                logger.debug("Loading dotenv from %s", env_file)
                load_dotenv(env_file)
            else:
                logger.debug("Loading dotenv from default locations")
                load_dotenv()
            
        # Load from config file if exists
        if self.config_path and os.path.exists(self.config_path):
            logger.debug("Loading YAML from %s", self.config_path)
            self._load_yaml(self.config_path)
        else:
            logger.debug("Config path does not exist: %s", self.config_path)
            
        # Override from environment
        if not skip_env:
            self._load_from_env()
        
        # Validate configuration
        self._validate()
        
        logger.debug("Configuration initialized. DEBUG=%s, MIN_PROFIT=%s", 
                     self._config.get("DEBUG"), self._config.get("MIN_PROFIT"))
        
    def __getattr__(self, name):
        """Get configuration attribute with fallback to _config dict."""
        if name in self._config:
            return self._config[name]
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
        
    def __setattr__(self, name, value):
        """Set configuration attribute in _config dict, except private and config_path."""
        if name.startswith("_") or name == "config_path":
            super().__setattr__(name, value)
        else:
            # Store all other attributes, including BASE_PATH, in the config dict
            self._config[name] = value
        
    def get(self, key, default=None):
        """
        Get configuration value with optional default.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self._config.get(key, default)
        
    def set(self, key, value):
        """Set a configuration value.
        
        Args:
            key: Configuration key
            value: Value to set
        """
        self._config[key] = value
        
    def update(self, config_dict):
        """Update configuration from dictionary.
        
        Args:
            config_dict: Dictionary of configuration values
        """
        self._config.update(config_dict)
        
    def as_dict(self):
        """Convert configuration to dictionary.
        
        Returns:
            Dict: Configuration as dictionary
        """
        return self._config.copy()
        
    async def load(self):
        """Load configuration (async compatibility).
        
        Returns:
            self: Configuration instance
        """
        return self
        
    def save(self, path=None):
        """Save configuration to YAML file.
        
        Args:
            path: Path to save configuration (defaults to original config path)
        """
        save_path = path or self.config_path
        if not save_path:
            raise ValueError("No configuration path specified")
            
        with open(save_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)
        
        logger.debug(f"Configuration saved to {save_path}")
        
    def _load_yaml(self, path):
        """Load configuration from YAML file.
        
        Args:
            path: Path to YAML file
        """
        try:
            with open(path, 'r') as f:
                config_data = yaml.safe_load(f)
                if config_data:
                    # Log what we're loading for debugging
                    logger.debug(f"Loaded YAML data: {config_data}")
                    self._config.update(config_data)
                logger.debug(f"Loaded configuration from {path}")
        except Exception as e:
            logger.error(f"Error loading configuration from {path}: {e}")
            
    def _load_from_env(self):
        """Load configuration from environment variables."""
        logger.debug("Before _load_from_env: DEBUG=%s", self._config.get("DEBUG"))
        
        for key in self._config:
            env_value = os.getenv(key)
            if env_value is not None:
                # Convert environment string to appropriate type based on default
                default_value = self._DEFAULTS.get(key)
                if isinstance(default_value, bool):
                    self._config[key] = env_value.lower() in ('true', '1', 'yes')
                elif isinstance(default_value, int):
                    self._config[key] = int(env_value)
                elif isinstance(default_value, float):
                    self._config[key] = float(env_value)
                else:
                    self._config[key] = env_value
                
                logger.debug("Updated from env: %s=%s", key, self._config[key])
        
        logger.debug("After _load_from_env: DEBUG=%s", self._config.get("DEBUG"))
                    
        # Special handling for WALLET_KEY
        if os.getenv("WALLET_KEY"):
            self._config["WALLET_KEY"] = os.getenv("WALLET_KEY")
            
    def _validate(self):
        """Validate configuration values and set defaults if invalid."""
        # Ensure MIN_PROFIT is non-negative
        if self._config.get("MIN_PROFIT", 0) < 0:
            logger.warning("MIN_PROFIT cannot be negative, using default")
            self._config["MIN_PROFIT"] = self._DEFAULTS["MIN_PROFIT"]
            
        # Ensure gas price limits are reasonable
        if self._config.get("MAX_GAS_PRICE_GWEI", 0) <= 0:
            logger.warning("MAX_GAS_PRICE_GWEI must be positive, using default")
            self._config["MAX_GAS_PRICE_GWEI"] = self._DEFAULTS["MAX_GAS_PRICE_GWEI"]
            
    async def _load_json_safe(self, path):
        """Load JSON file with error handling.
        
        Args:
            path: Path to JSON file
            
        Returns:
            Dict or None: Loaded JSON data or None if error
        """
        import json
        if not path or not os.path.exists(path):
            return None
            
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON from {path}: {e}")
            return None


class MultiChainConfiguration(Configuration):
    """Configuration for multi-chain operations."""
    
    def __init__(self, config_path=None):
        """Initialize with optional config path."""
        super().__init__(config_path or os.path.join(Path(__file__).parent.parent.parent.parent, 
                                              "configs", "chains", "config_multi_chain.yaml"))
        self.chains = []
        
    async def load(self):
        """Load multi-chain configuration."""
        await super().load()
        
        # Load chains configuration
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                
                # Load chains
                if 'chains' in config:
                    self.chains = config['chains']
                    
            except Exception as e:
                logger.error(f"Error loading multi-chain configuration: {e}")
                
        return self
        
    def get_chains(self):
        """Get list of configured chains."""
        return self.chains


# --------------------------------------------------------------------------- #
# provider table                                                              #
# --------------------------------------------------------------------------- #


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
    # runtime objects (initialised in __post_init__)
    limiter: asyncio.Semaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.limiter = asyncio.Semaphore(self.rate_limit)


# --------------------------------------------------------------------------- #
# main class                                                                  #
# --------------------------------------------------------------------------- #


class APIConfig:
    """
    Aggregates token price & volume data from multiple public providers.
    """

    _session: Optional[aiohttp.ClientSession] = None
    _session_users = 0
    _session_lock = asyncio.Lock()

    _MAX_REQUEST_ATTEMPTS = 4
    _BACKOFF_BASE = 1.7

    def __init__(self, configuration: Configuration) -> None:
        self.cfg = configuration
        self.providers: Dict[str, Provider] = self._build_providers()

        self.price_cache = TTLCache(maxsize=2_000, ttl=300)
        self.volume_cache = TTLCache(maxsize=1_000, ttl=900)

        # symbol / address maps
        self.token_address_to_symbol: Dict[str, str] = {}
        self.token_symbol_to_address: Dict[str, str] = {}
        self.symbol_to_api_id: Dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # life-cycle                                                         #
    # ------------------------------------------------------------------ #

    async def initialize(self) -> None:
        await self._populate_token_maps()
        await self._acquire_session()
        logger.info("APIConfig initialised with %d providers", len(self.providers))

    async def close(self) -> None:
        # Close instance session if one was patched
        if '_session' in self.__dict__ and self._session:
            try:
                await self._session.close()
            except Exception:
                pass
        # Release shared session
        await self._release_session()
        self.price_cache.clear()
        self.volume_cache.clear()
        logger.debug("APIConfig closed gracefully")

    async def __aenter__(self) -> "APIConfig":
        await self.initialize()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    async def is_healthy(self) -> bool:  # noqa: D401
        """Cheap health probe used by MainCore watchdog."""
        return bool(self.providers)

    # ------------------------------------------------------------------ #
    # internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _build_providers(self) -> Dict[str, Provider]:
        g_api = self.cfg.get("GRAPH_API_KEY", "")
        uni_id = self.cfg.get("UNISWAP_V2_SUBGRAPH_ID", "")

        provs = {
            "binance": Provider(
                "binance",
                "https://api.binance.com/api/v3",
                price_url="/ticker/price",
                volume_url="/ticker/24hr",
                rate_limit=1_200,
                weight=1.0,
            ),
            "coingecko": Provider(
                "coingecko",
                "https://api.coingecko.com/api/v3",
                price_url="/simple/price",
                historical_url="/coins/{id}/market_chart",
                volume_url="/coins/{id}/market_chart",
                api_key=self.cfg.COINGECKO_API_KEY,
                rate_limit=50 if self.cfg.COINGECKO_API_KEY else 10,
                weight=0.8 if self.cfg.COINGECKO_API_KEY else 0.5,
            ),
            "uniswap_subgraph": Provider(
                "uniswap_subgraph",
                f"https://gateway.thegraph.com/api/{g_api}/subgraphs/id/{uni_id}",
                rate_limit=5,
                weight=0.3,
            ),
            "dexscreener": Provider(
                "dexscreener",
                "https://api.dexscreener.com/latest/dex",
                rate_limit=10,
                weight=0.3,
            ),
            "coinpaprika": Provider(
                "coinpaprika",
                "https://api.coinpaprika.com/v1",
                price_url="/tickers/{id}",
                historical_url="/coins/{id}/ohlcv/historical",
                volume_url="/tickers/{id}",
                weight=0.3,
            ),
        }
        return provs

    async def _populate_token_maps(self) -> None:
        addresses = await self.cfg._load_json_safe(self.cfg.TOKEN_ADDRESSES) or {}
        symbols = await self.cfg._load_json_safe(self.cfg.TOKEN_SYMBOLS) or {}
        for sym, addr in addresses.items():
            sym_u = sym.upper()
            addr_l = addr.lower()
            self.token_address_to_symbol[addr_l] = sym_u
            self.token_symbol_to_address[sym_u] = addr_l
            self.symbol_to_api_id[sym_u] = symbols.get(sym_u, sym_u.lower())

    # session management (shared across all APIConfig instances) ----------

    @classmethod
    async def _acquire_session(cls) -> None:
        async with cls._session_lock:
            cls._session_users += 1
            if cls._session is None or cls._session.closed:
                timeout = aiohttp.ClientTimeout(total=30)
                cls._session = aiohttp.ClientSession(timeout=timeout)

    @classmethod
    async def _release_session(cls) -> None:
        async with cls._session_lock:
            cls._session_users -= 1
            if cls._session_users <= 0 and cls._session:
                await cls._session.close()
                cls._session = None
                cls._session_users = 0

    # ------------------------------------------------------------------ #
    # low-level request helper                                           #
    # ------------------------------------------------------------------ #

    async def _request(
        self, provider: Provider, endpoint: str, *, params: Dict[str, Any] | None = None
    ) -> Any | None:
        url = provider.base_url + endpoint
        for attempt in range(self._MAX_REQUEST_ATTEMPTS):
            delay = self._BACKOFF_BASE ** attempt + random.random()
            async with provider.limiter:
                if self._session is None:
                    await self._acquire_session()
                try:
                    async with self._session.get(url, params=params, headers=self._headers(provider)) as r:
                        if r.status == 429:
                            await asyncio.sleep(delay)
                            continue
                        if r.status >= 400:
                            logger.debug("%s HTTP %s – %s", provider.name, r.status, url)
                            return None
                        return await r.json()
                except aiohttp.ClientError:
                    await asyncio.sleep(delay)
                except Exception as exc:
                    logger.error("HTTP error (%s): %s", provider.name, exc)
                    await asyncio.sleep(delay)
        return None

    @staticmethod
    def _headers(provider: Provider) -> Dict[str, str]:
        if provider.name in ("coingecko",):
            return {"x-cg-pro-api-key": provider.api_key} if provider.api_key else {}
        if provider.name == "coinmarketcap":
            return {"X-CMC_PRO_API_KEY": provider.api_key or ""}
        return {}

    # ------------------------------------------------------------------ #
    # symbol helpers                                                     #
    # ------------------------------------------------------------------ #

    def _norm(self, sym_or_addr: str) -> str:
        if (sym_or_addr.startswith("0x")):
            sym = self.token_address_to_symbol.get(sym_or_addr.lower())
            return sym or sym_or_addr.lower()
        return sym_or_addr.upper()

    # ------------------------------------------------------------------ #
    # price & volume public API                                          #
    # ------------------------------------------------------------------ #

    async def get_real_time_price(self, token_or_addr: str, vs: str = "usd") -> Optional[Decimal]:
        t_norm = self._norm(token_or_addr)
        key = f"p:{t_norm}:{vs}"
        if key in self.price_cache:
            return self.price_cache[key]

        prices, weights = [], []
        for prov in self.providers.values():
            p = await self._price_from_provider(prov, t_norm, vs)
            if p is not None:
                prices.append(p)
                weights.append(prov.weight * prov.success_rate)

        if not prices:
            return None
        wavg = sum(p * w for p, w in zip(prices, weights)) / sum(weights)
        val = Decimal(str(wavg))
        self.price_cache[key] = val
        return val

    async def _price_from_provider(self, prov: Provider, token: str, vs: str) -> Optional[Decimal]:
        if prov.name == "binance":
            data = await self._request(prov, prov.price_url, params={"symbol": token + vs.upper()})
            return Decimal(data["price"]) if data else None

        if prov.name == "coingecko":
            token_id = self.symbol_to_api_id.get(token, token.lower())
            params = {"ids": token_id, "vs_currencies": vs}
            data = await self._request(prov, prov.price_url, params=params)
            try:
                return Decimal(str(data[token_id][vs]))
            except Exception:
                return None

        if prov.name == "dexscreener" and token.startswith("0x"):
            endpoint = f"/pairs/ethereum/{token}"
            data = await self._request(prov, endpoint)
            price = data.get("pair", {}).get("priceUsd") if data else None
            return Decimal(str(price)) if price else None

        if prov.name == "coinpaprika":
            token_id = self.symbol_to_api_id.get(token, token)
            endpoint = prov.price_url.format(id=token_id)
            data = await self._request(prov, endpoint)
            price = data.get("quotes", {}).get(vs.upper(), {}).get("price") if data else None
            return Decimal(str(price)) if price else None

        return None  # fallback

    async def get_token_volume(self, token_or_addr: str) -> float:
        t_norm = self._norm(token_or_addr)
        key = f"v:{t_norm}"
        if key in self.volume_cache:
            return self.volume_cache[key]

        for prov in self.providers.values():
            v = await self._volume_from_provider(prov, t_norm)
            if v is not None:
                self.volume_cache[key] = v
                return v
        return 0.0

    async def _volume_from_provider(self, prov: Provider, token: str) -> Optional[float]:
        if prov.name == "binance":
            endpoint = prov.volume_url
            data = await self._request(prov, endpoint, params={"symbol": token + "USDT"})
            return float(data["quoteVolume"]) if data else None
        if prov.name == "coingecko":
            token_id = self.symbol_to_api_id.get(token, token)
            endpoint = prov.volume_url
            params = {"vs_currency": "usd", "days": 1}
            data = await self._request(prov, endpoint.format(id=token_id), params=params)
            vols = data.get("total_volumes") if data else []
            return float(vols[-1][1]) if vols else None
        return None

    # ------------------------------------------------------------------ #
    # prediction helper (unchanged API)                                  #
    # ------------------------------------------------------------------ #

    async def predict_price(self, token: str) -> float:
        lr_path = Path(self.cfg.MODEL_PATH)
        hist = await self._hist_prices(token, days=7)
        if not hist:
            return 0.0
        if (lr_path.exists()):
            try:
                mdl = joblib.load(lr_path)
                df = pd.DataFrame(
                    [{
                        "price_usd": sum(hist) / len(hist),
                        "volume_24h": await self.get_token_volume(token),
                        "market_cap": 0,
                        "volatility": float(pd.Series(hist).pct_change().std()),
                        "liquidity_ratio": 0,
                        "price_momentum": (hist[-1] - hist[0]) / hist[0],
                    }]
                )
                return float(mdl.predict(df)[0])
            except Exception:
                pass
        # naive fallback
        return float(sum(hist) / len(hist))

    async def _hist_prices(self, token: str, *, days: int) -> List[float]:
        key = f"h:{token}:{days}"
        if key in self.price_cache:
            return self.price_cache[key]
        for prov in self.providers.values():
            if not prov.historical_url:
                continue
            series = await self._hist_from_provider(prov, token, days)
            if series:
                self.price_cache[key] = series
                return series
        return []

    async def _hist_from_provider(self, prov: Provider, token: str, days: int) -> List[float]:
        if prov.name == "coingecko":
            token_id = self.symbol_to_api_id.get(token, token.lower())
            data = await self._request(
                prov,
                prov.historical_url.format(id=token_id),
                params={"vs_currency": "usd", "days": days},
            )
            return [float(p[1]) for p in (data or {}).get("prices", [])][-days:]
        return []

    # ------------------------------------------------------------------ #
    # utility                                                            #
    # ------------------------------------------------------------------ #

    def get_token_symbol(self, address: str) -> Optional[str]:
        return self.token_address_to_symbol.get(address.lower())

    def get_token_address(self, symbol: str) -> Optional[str]:
        return self.token_symbol_to_address.get(symbol.upper())

    # nice for debug
    def __repr__(self) -> str:  # noqa: D401
        provs = ", ".join(self.providers)
        return f"<APIConfig providers=[{provs}]>"

    async def get_price_history(
        self, 
        token_or_addr: str, 
        timeframe: str = "1h", 
        vs: str = "usd"
    ) -> List[Dict[str, Any]]:
        """Get token price history for a specific time frame.
        
        Args:
            token_or_addr: Token symbol or address
            timeframe: Time frame for history (e.g., "1h", "24h", "7d")
            vs: Quote currency
            
        Returns:
            List of price data points with timestamps
        """
        t_norm = self._norm(token_or_addr)
        key = f"h:{t_norm}:{timeframe}:{vs}"
        
        if key in self.price_cache:
            return self.price_cache[key]
            
        # Map timeframe to days for providers
        timeframe_days = {
            "5m": 0.0035,  # ~5 minutes
            "15m": 0.01,   # ~15 minutes
            "1h": 0.05,    # ~1 hour
            "4h": 0.17,    # ~4 hours
            "12h": 0.5,    # 12 hours
            "24h": 1,      # 1 day
            "7d": 7,       # 7 days
            "30d": 30      # 30 days
        }
        
        days = timeframe_days.get(timeframe, 1)
        
        # Try to get historical data from providers
        result = []
        
        for prov in self.providers.values():
            if not prov.historical_url:
                continue
                
            data = await self._hist_from_provider(prov, t_norm, days)
            if data:
                # Format data into a standard structure
                formatted_data = []
                for item in data:
                    if isinstance(item, list) and len(item) >= 2:
                        # Most APIs return [timestamp, price] format
                        formatted_data.append({
                            "timestamp": item[0],
                            "price": item[1],
                        })
                    elif isinstance(item, dict):
                        # Some APIs might return dictionary format
                        formatted_data.append(item)
                        
                if formatted_data:
                    # Add provider name for debugging
                    for entry in formatted_data:
                        entry["provider"] = prov.name
                        
                    self.price_cache[key] = formatted_data
                    logger.debug(f"Loaded historical price data for {t_norm} from {prov.name}: {len(formatted_data)} points")
                    return formatted_data
                 # Try to get data from another provider - Dexscreener
            if token_or_addr.startswith("0x") and "dexscreener" in self.providers:
                try:
                    prov = self.providers["dexscreener"]
                    endpoint = f"/pairs/ethereum/{token_or_addr.lower()}"
                    data = await self._request(prov, endpoint)
                    
                    if data and "pair" in data and "priceUsd" in data["pair"]:
                        pair_data = data["pair"]
                        price_data = []
                        
                        # Use price change data to estimate historical prices
                        current_price = float(pair_data.get("priceUsd", 0))
                        price_change = float(pair_data.get("priceChange", {}).get("h24", 0)) / 100
                        
                        if current_price > 0:
                            from datetime import datetime, timedelta
                            now = datetime.now()
                            
                            # Generate points based on timeframe
                            points = 24 if "h" in timeframe else 7 if "d" in timeframe else 12
                            
                            # Generate synthetic price history based on current price and change percentage
                            previous_price = current_price / (1 + price_change)
                            price_step = (current_price - previous_price) / points
                            
                            for i in range(points + 1):
                                point_time = now - timedelta(hours=24 * (1 - i/points))
                                point_price = previous_price + (price_step * i)
                                
                                price_data.append({
                                    "timestamp": int(point_time.timestamp() * 1000),
                                    "price": point_price,
                                    "provider": "dexscreener",
                                    "synthetic": True
                                })
                            
                            self.price_cache[key] = price_data
                            logger.debug(f"Generated synthetic price history for {t_norm} from Dexscreener data")
                            return price_data
                except Exception as e:
                    logger.debug(f"Error getting data from Dexscreener: {e}")
            
            # Last fallback - generate simple history based on current price
            current_price = await self.get_real_time_price(token_or_addr, vs)
            if current_price:
                # Generate synthetic historical data for UI/testing purposes
                import random
                from datetime import datetime, timedelta
                
                now = datetime.now()
                points = 24 if "h" in timeframe else 7 if "d" in timeframe else 12
                
                volatility = 0.02  # 2% typical volatility
                result = []
                
                base_price = float(current_price)
                
                for i in range(points):
                    time_offset = timedelta(hours=-i if "h" in timeframe else -i*24 if "d" in timeframe else -i*0.5)
                    timestamp = int((now + time_offset).timestamp() * 1000)
                    
                    # Random walk price model with slight trend bias
                    random_change = (random.random() - 0.45) * volatility * base_price  # Slight upward bias
                    point_price = base_price + random_change
                    
                    result.append({
                        "timestamp": timestamp,
                        "price": point_price,
                        "provider": "synthetic",
                        "synthetic": True
                    })
                    
                    # Update base for next point
                    base_price = point_price
                
                # Sort by timestamp ascending
                result.sort(key=lambda x: x["timestamp"])
                self.price_cache[key] = result
                return result
            
        return []

    async def get_price(
        self,
        token: str,
        quote_currency: str = "USD",
    ) -> Any:
        """
        Alias for get_real_time_price for compatibility with existing tests.
        """
        return await self.get_real_time_price(token, quote_currency)

# Expose DEFAULTS for testing and external usage
_DEFAULTS = Configuration._DEFAULTS

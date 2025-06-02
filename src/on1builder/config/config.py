#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – APIConfig & Configuration
======================================

Configuration management and API interaction layer.
This module provides a unified configuration system for ON1Builder,
including support for environment variables, YAML configuration files, and default values.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import yaml
from cachetools import TTLCache
from dotenv import load_dotenv

from on1builder.utils.logger import get_logger

logger = get_logger(__name__)


class Configuration:
    """Base configuration class for ON1Builder."""

    POA_CHAINS = {99, 100, 77, 7766, 56, 11155111}

    _DEFAULTS = {
        "GRAPH_API_KEY": "",
        "UNISWAP_V2_SUBGRAPH_ID": "",
        "COINGECKO_API_KEY": "",
        "MONITORED_TOKENS": [],
        "DEBUG": False,
        "BASE_PATH": str(Path(__file__).resolve().parent.parent.parent.parent),
        "HTTP_ENDPOINT": "https://ethereum-rpc.publicnode.com",
        "WEBSOCKET_ENDPOINT": "wss://ethereum-rpc.publicnode.com",
        "IPC_ENDPOINT": None,
        "SAFETYNET_CACHE_TTL": 60,
        "SAFETYNET_GAS_PRICE_TTL": 10,
        "MAX_GAS_PRICE_GWEI": 100,
        "MIN_PROFIT": 0.001,
        "MEMPOOL_RETRY_DELAY": 0.5,
        "MEMPOOL_MAX_RETRIES": 3,
        "MARKET_CACHE_TTL": 60,
        "MEMPOOL_MAX_PARALLEL_TASKS": 10,
        "WALLET_KEY": "<WALLET_KEY>",
        "TRANSACTION_RETRY_COUNT": 3,
        "TRANSACTION_RETRY_DELAY": 1.0,
        "GAS_MULTIPLIER": 1.1,
        "CONNECTION_RETRY_COUNT": 3,
        "CONNECTION_RETRY_DELAY": 2.0,
        "WEB3_MAX_RETRIES": 3,
        "MEMORY_CHECK_INTERVAL": 300,
    }

    def __init__(self, config_path=None, env_file=None, skip_env=False):
        self._config = dict(self._DEFAULTS)
        self.config_path = config_path
        self.BASE_PATH = self._config["BASE_PATH"]
        self._api_config: Optional[APIConfig] = None

        if not config_path:
            self.config_path = os.path.join(
                self.BASE_PATH, "configs", "chains", "config.yaml"
            )

        if not skip_env:
            if env_file and os.path.exists(env_file):
                load_dotenv(env_file)
            else:
                load_dotenv()

        if self.config_path and os.path.exists(self.config_path):
            self._load_yaml(self.config_path)

        if not skip_env:
            self._load_from_env()

        self._validate()

    def __getattr__(self, name):
        # Allow properties to be accessed normally
        if name == 'api_config':
            if not self._api_config:
                self._api_config = APIConfig(self)
            return self._api_config
        if name in self._config:
            return self._config[name]
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'. Did you mean: '{name}'?")

    def __setattr__(self, name, value):
        if name.startswith("_") or name == "config_path":
            super().__setattr__(name, value)
        else:
            self._config[name] = value

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value

    def update(self, config_dict):
        self._config.update(config_dict)

    def as_dict(self):
        return self._config.copy()

    async def load(self):
        return self

    def save(self, path=None):
        save_path = path or self.config_path
        if not save_path:
            raise ValueError("No configuration path specified")
        with open(save_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)
        logger.debug(f"Configuration saved to {save_path}")

    def _load_yaml(self, path):
        try:
            with open(path, "r") as f:
                config_data = yaml.safe_load(f)
                if config_data:
                    self._config.update(config_data)
                    logger.debug(f"Loaded YAML config from {path}")
        except Exception as e:
            logger.error(f"Failed to load config YAML from {path}: {e}")

    def _load_from_env(self):
        # Load known config keys
        for key in self._config:
            env_val = os.getenv(key)
            if env_val:
                default = self._DEFAULTS.get(key)
                try:
                    if isinstance(default, bool):
                        self._config[key] = env_val.lower() in ("true", "1", "yes")
                    elif isinstance(default, int):
                        self._config[key] = int(env_val)
                    elif isinstance(default, float):
                        self._config[key] = float(env_val)
                    else:
                        self._config[key] = env_val
                except ValueError:
                    logger.warning(f"Invalid env var format for {key}={env_val}")

                if key.lower() == "wallet_key":
                    logger.debug(f"Loaded {key}=<REDACTED>")
                else:
                    logger.debug(f"Loaded {key}={self._config[key]}")

        # Load API keys that might not be in defaults
        api_keys = [
            "COINGECKO_API_KEY", "COINMARKETCAP_API_KEY", "CRYPTOCOMPARE_API_KEY",
            "ETHERSCAN_API_KEY", "INFURA_PROJECT_ID", "INFURA_API_KEY"
        ]
        for key in api_keys:
            env_val = os.getenv(key)
            if env_val:
                self._config[key] = env_val
                logger.debug(f"Loaded API key {key}=<REDACTED>")

        # WALLET_KEY (hardcode mask)
        if os.getenv("WALLET_KEY"):
            self._config["WALLET_KEY"] = os.getenv("WALLET_KEY")

    def _validate(self):
        if self._config.get("MIN_PROFIT", 0) < 0:
            logger.warning("MIN_PROFIT cannot be negative, resetting to default")
            self._config["MIN_PROFIT"] = self._DEFAULTS["MIN_PROFIT"]

        if self._config.get("MAX_GAS_PRICE_GWEI", 0) <= 0:
            logger.warning("MAX_GAS_PRICE_GWEI must be positive, resetting to default")
            self._config["MAX_GAS_PRICE_GWEI"] = self._DEFAULTS["MAX_GAS_PRICE_GWEI"]

    async def _load_json_safe(self, path, description=None):
        import json
        if not path or not os.path.exists(path):
            logger.warning(f"File not found for {description or 'JSON'}: {path}")
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
                logger.debug(f"Loaded {description or 'JSON'} from {path}")
                return data
        except Exception as e:
            logger.error(f"Failed to load {description or 'JSON'} from {path}: {e}")
            return None

    def get_chain_config(self, chain_name: str) -> Dict[str, Any]:
        return self._config.get("chains", {}).get(chain_name, {})

    @property
    def api_config(self) -> APIConfig:
        if not self._api_config:
            self._api_config = APIConfig(self)
        return self._api_config


class MultiChainConfiguration(Configuration):
    def __init__(self, config_path=None, env_file=None, skip_env=False):
        default_path = os.path.join(
            Path(__file__).resolve().parent.parent.parent.parent,
            "configs",
            "chains",
            "config_multi_chain.yaml",
        )
        super().__init__(config_path or default_path, env_file=env_file, skip_env=skip_env)
        self.chains = []

    async def load(self):
        await super().load()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    config = yaml.safe_load(f)
                    if "chains" in config:
                        self.chains = config["chains"]
            except Exception as e:
                logger.error(f"Failed loading multi-chain config: {e}")
        return self

    def get_chains(self):
        return self.chains



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


class APIConfig:
    """Aggregates token price & volume data from multiple public providers."""

    _session: Optional[aiohttp.ClientSession] = None
    _session_users = 0
    _session_lock = asyncio.Lock()
    _MAX_REQUEST_ATTEMPTS = 4
    _BACKOFF_BASE = 1.7

    def __init__(self, config: Configuration):
        self.cfg = config
        self.providers = self._build_providers()

        self.price_cache = TTLCache(maxsize=2_000, ttl=300)
        self.volume_cache = TTLCache(maxsize=1_000, ttl=900)

        self.token_address_to_symbol: Dict[str, str] = {}
        self.token_symbol_to_address: Dict[str, str] = {}
        self.symbol_to_api_id: Dict[str, str] = {}
        self.symbol_to_token_name: Dict[str, str] = {}
        self.token_name_to_symbol: Dict[str, str] = {}
        
        # Load token mappings synchronously on initialization
        self._load_token_mappings_sync()
        
    async def get_client_session(self) -> aiohttp.ClientSession:
        """Returns the existing client session or creates a new one if needed.
        
        This method ensures a shared ClientSession is available for making HTTP requests.
        It also increments the session user count to track active users.
        
        Returns:
            aiohttp.ClientSession: A shared aiohttp client session
        """
        # Ensure we have a session available
        if self._session is None or self._session.closed:
            await self._acquire_session()
        return self._session

    async def initialize(self) -> None:
        for var, attr, default in [
            ("TOKEN_ADDRESSES", "TOKEN_ADDRESSES", "resources/tokens/chainid-1/address2token.json"),
            ("TOKEN_SYMBOLS", "TOKEN_SYMBOLS", "resources/tokens/chainid-1/symbol2address.json"),
            ("ADDRESS_TO_SYMBOL", "ADDRESS_TO_SYMBOL", "resources/tokens/chainid-1/address2symbol.json"),
        ]:
            path = os.getenv(var)
            setattr(self.cfg, attr, path or os.path.join(self.cfg.BASE_PATH, default))

        await self._populate_token_maps()
        await self._acquire_session()
        logger.info(f"APIConfig initialized with {len(self.providers)} providers")

    async def close(self) -> None:
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
        await self._release_session()
        self.price_cache.clear()
        self.volume_cache.clear()

    async def __aenter__(self) -> "APIConfig":
        await self.initialize()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    async def is_healthy(self) -> bool:
        return bool(self.providers)

    def _build_providers(self) -> Dict[str, Provider]:
        g_api = self.cfg.get("GRAPH_API_KEY", "")
        uni_id = self.cfg.get("UNISWAP_V2_SUBGRAPH_ID", "")

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
                api_key=self.cfg.get("COINGECKO_API_KEY", ""),
                rate_limit=50 if self.cfg.get("COINGECKO_API_KEY") else 10,
                weight=0.8 if self.cfg.get("COINGECKO_API_KEY") else 0.5,
            ),
            "coinmarketcap": Provider(
                name="coinmarketcap",
                base_url="https://pro-api.coinmarketcap.com/v1",
                price_url="/cryptocurrency/quotes/latest",
                historical_url="/cryptocurrency/quotes/historical",
                volume_url="/cryptocurrency/quotes/latest",
                api_key=self.cfg.get("COINMARKETCAP_API_KEY", ""),
                rate_limit=333 if self.cfg.get("COINMARKETCAP_API_KEY") else 10,
                weight=0.6,
            ),
            "cryptocompare": Provider(
                name="cryptocompare",
                base_url="https://min-api.cryptocompare.com/data",
                price_url="/price",
                historical_url="/v2/histoday",
                volume_url="/top/totalvolfull",
                api_key=self.cfg.get("CRYPTOCOMPARE_API_KEY", ""),
                rate_limit=300 if self.cfg.get("CRYPTOCOMPARE_API_KEY") else 100,
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

    def _create_api_id_mappings(self) -> None:
        """Create API-specific token ID mappings for different providers using loaded token data."""
        
        # Initialize provider mappings
        coingecko_mappings = {}
        coinpaprika_mappings = {}
        cryptocompare_mappings = {}
        coinmarketcap_mappings = {}
        binance_mappings = {}
        
        # Use symbol to token name mapping to create provider-specific IDs
        if hasattr(self, 'symbol_to_token_name') and self.symbol_to_token_name:
            for symbol, token_name in self.symbol_to_token_name.items():
                if token_name is None:  # Skip None entries
                    continue
                    
                symbol_upper = symbol.upper()
                token_lower = token_name.lower()
                
                # CoinGecko uses specific API IDs (lowercase, hyphenated)
                if symbol_upper == 'ETH':
                    coingecko_id = 'ethereum'
                elif symbol_upper == 'BTC':
                    coingecko_id = 'bitcoin'
                elif symbol_upper == 'USDT':
                    coingecko_id = 'tether'
                elif symbol_upper == 'USDC':
                    coingecko_id = 'usd-coin'
                elif symbol_upper == 'WETH':
                    coingecko_id = 'weth'
                elif symbol_upper == 'WBTC':
                    coingecko_id = 'wrapped-bitcoin'
                elif symbol_upper == 'LINK':
                    coingecko_id = 'chainlink'
                elif symbol_upper == 'UNI':
                    coingecko_id = 'uniswap'
                elif symbol_upper == 'AAVE':
                    coingecko_id = 'aave'
                elif symbol_upper == 'DAI':
                    coingecko_id = 'dai'
                elif symbol_upper == 'MATIC':
                    coingecko_id = 'matic-network'
                elif symbol_upper == 'SHIB':
                    coingecko_id = 'shiba-inu'
                elif symbol_upper == 'PEPE':
                    coingecko_id = 'pepe'
                elif symbol_upper == 'ARB':
                    coingecko_id = 'arbitrum'
                elif symbol_upper == 'stETH':
                    coingecko_id = 'staked-ether'
                elif symbol_upper == 'wstETH':
                    coingecko_id = 'wrapped-steth'
                else:
                    # For unknown tokens, try to make a reasonable ID
                    coingecko_id = token_lower.replace(' ', '-').replace('(', '').replace(')', '')
                    
                coingecko_mappings[symbol_upper] = coingecko_id
                
                # CoinPaprika uses symbol-name format, but needs correct format
                if symbol_upper == 'ETH':
                    paprika_id = 'eth-ethereum'
                elif symbol_upper == 'BTC':
                    paprika_id = 'btc-bitcoin'
                elif symbol_upper == 'USDT':
                    paprika_id = 'usdt-tether'
                elif symbol_upper == 'USDC':
                    paprika_id = 'usdc-usd-coin'
                elif symbol_upper == 'DAI':
                    paprika_id = 'dai-dai'
                elif symbol_upper == 'WETH':
                    paprika_id = 'weth-weth'
                elif symbol_upper == 'LINK':
                    paprika_id = 'link-chainlink'
                elif symbol_upper == 'UNI':
                    paprika_id = 'uni-uniswap'
                elif symbol_upper == 'AAVE':
                    paprika_id = 'aave-aave'
                else:
                    # Fallback to a reasonable format
                    paprika_id = f"{symbol.lower()}-{token_lower.replace(' ', '-')}"
                coinpaprika_mappings[symbol_upper] = paprika_id
                
                # CryptoCompare uses simple symbols (uppercase)
                cryptocompare_mappings[symbol_upper] = symbol_upper
                
                # CoinMarketCap uses symbol mapping (they have internal IDs, but symbols work for many)
                coinmarketcap_mappings[symbol_upper] = symbol_upper
                
                # Binance uses symbol pairs (most against USDT)
                if symbol_upper not in ['USDT', 'USDC', 'DAI', 'BUSD']:
                    binance_mappings[symbol_upper] = f"{symbol_upper}USDT"
        
        # Fallback to minimal hardcoded mappings if JSON data not available
        if not coingecko_mappings:
            coingecko_mappings = {
                'ETH': 'ethereum', 'BTC': 'bitcoin', 'USDT': 'tether', 
                'USDC': 'usd-coin', 'DAI': 'dai', 'WETH': 'weth',
                'LINK': 'chainlink', 'UNI': 'uniswap', 'AAVE': 'aave'
            }
            coinpaprika_mappings = {
                'ETH': 'eth-ethereum', 'BTC': 'btc-bitcoin', 'USDT': 'usdt-tether',
                'USDC': 'usdc-usd-coin', 'DAI': 'dai-dai', 'LINK': 'link-chainlink'
            }
            cryptocompare_mappings = {
                'ETH': 'ETH', 'BTC': 'BTC', 'USDT': 'USDT', 'USDC': 'USDC', 'DAI': 'DAI'
            }
            coinmarketcap_mappings = {
                'ETH': 'ETH', 'BTC': 'BTC', 'USDT': 'USDT', 'USDC': 'USDC', 'DAI': 'DAI'
            }
            binance_mappings = {
                'ETH': 'ETHUSDT', 'BTC': 'BTCUSDT', 'LINK': 'LINKUSDT', 'UNI': 'UNIUSDT'
            }
        
        # Always ensure we have the essential tokens, even if missing from JSON
        essential_tokens = {
            'ETH': ('ethereum', 'eth-ethereum', 'ETH', 'ETH', 'ETHUSDT'),
            'BTC': ('bitcoin', 'btc-bitcoin', 'BTC', 'BTC', 'BTCUSDT'),
        }
        
        for symbol, (gecko_id, paprika_id, crypto_id, cmc_id, binance_id) in essential_tokens.items():
            if symbol not in coingecko_mappings:
                coingecko_mappings[symbol] = gecko_id
            if symbol not in coinpaprika_mappings:
                coinpaprika_mappings[symbol] = paprika_id
            if symbol not in cryptocompare_mappings:
                cryptocompare_mappings[symbol] = crypto_id
            if symbol not in coinmarketcap_mappings:
                coinmarketcap_mappings[symbol] = cmc_id
            if symbol not in binance_mappings:
                binance_mappings[symbol] = binance_id
        
        # Store provider-specific mappings
        self.symbol_to_api_id = {
            'coingecko': coingecko_mappings,
            'coinpaprika': coinpaprika_mappings,
            'cryptocompare': cryptocompare_mappings,
            'coinmarketcap': coinmarketcap_mappings,
            'binance': binance_mappings,
        }
        
        logger.debug(f"Created dynamic API ID mappings: CoinGecko({len(coingecko_mappings)}), "
                    f"CoinPaprika({len(coinpaprika_mappings)}), CryptoCompare({len(cryptocompare_mappings)}), "
                    f"CoinMarketCap({len(coinmarketcap_mappings)}), Binance({len(binance_mappings)})")

    def _load_token_mappings_sync(self) -> None:
        """Load token mappings from JSON files synchronously."""
        import json
        
        base_path = os.path.join(self.cfg.BASE_PATH, "resources", "tokens", f"chainid-{getattr(self.cfg, 'chain_id', 1)}")
        
        try:
            # Load address to symbol mapping
            address_to_symbol_path = os.path.join(base_path, "address2symbol.json")
            if os.path.exists(address_to_symbol_path):
                with open(address_to_symbol_path, 'r') as f:
                    self.token_address_to_symbol = json.load(f)
                logger.debug(f"Loaded {len(self.token_address_to_symbol)} address->symbol mappings")
            
            # Load symbol to address mapping
            symbol_to_address_path = os.path.join(base_path, "symbol2address.json")
            if os.path.exists(symbol_to_address_path):
                with open(symbol_to_address_path, 'r') as f:
                    self.token_symbol_to_address = json.load(f)
                logger.debug(f"Loaded {len(self.token_symbol_to_address)} symbol->address mappings")
            
            # Load symbol to token name mapping
            symbol_to_token_path = os.path.join(base_path, "symbol2token.json")
            if os.path.exists(symbol_to_token_path):
                with open(symbol_to_token_path, 'r') as f:
                    self.symbol_to_token_name = json.load(f)
                logger.debug(f"Loaded {len(self.symbol_to_token_name)} symbol->token mappings")
            
            # Load token name to symbol mapping
            token_to_symbol_path = os.path.join(base_path, "token2symbol.json")
            if os.path.exists(token_to_symbol_path):
                with open(token_to_symbol_path, 'r') as f:
                    self.token_name_to_symbol = json.load(f)
                logger.debug(f"Loaded {len(self.token_name_to_symbol)} token->symbol mappings")
            
            # Create API ID mappings for different providers
            self._create_api_id_mappings()
            
        except Exception as e:
            logger.error(f"Failed to load token mappings: {e}")

    async def _populate_token_maps(self) -> None:
        addresses = await self.cfg._load_json_safe(self.cfg.TOKEN_ADDRESSES, "TOKEN_ADDRESSES") or {}
        symbols = await self.cfg._load_json_safe(self.cfg.TOKEN_SYMBOLS, "TOKEN_SYMBOLS") or {}
        addr_to_sym = await self.cfg._load_json_safe(self.cfg.ADDRESS_TO_SYMBOL, "ADDRESS_TO_SYMBOL") or {}

        for addr, sym in addr_to_sym.items():
            addr_l, sym_u = addr.lower(), sym.upper()
            self.token_address_to_symbol[addr_l] = sym_u
            self.token_symbol_to_address[sym_u] = addr_l

        for sym, addr in addresses.items():
            sym_u, addr_l = sym.upper(), addr.lower()
            self.token_address_to_symbol[addr_l] = sym_u
            self.token_symbol_to_address[sym_u] = addr_l
            self.symbol_to_api_id[sym_u] = symbols.get(sym_u, sym_u.lower())

        logger.debug(f"Token maps loaded: {len(self.token_address_to_symbol)} tokens")

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

    async def get_real_time_price(self, token: str, vs: str = "usd") -> Optional[Decimal]:
        t_norm = self._norm(token)
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
            fallback = self._get_fallback_price(t_norm, vs)
            if fallback:
                logger.warning(f"Using fallback price for {t_norm}: {fallback}")
                self.price_cache[key] = fallback
                return fallback
            return None

        weighted = sum(p * Decimal(str(w)) for p, w in zip(prices, weights)) / Decimal(str(sum(weights)))
        val = Decimal(str(weighted))
        self.price_cache[key] = val
        return val

    def _get_fallback_price(self, token: str, vs: str = "usd") -> Optional[Decimal]:
        if vs.lower() != "usd":
            return None
        fallbacks = {
            "ETH": Decimal("3400"),
            "BTC": Decimal("62000"),
            "USDT": Decimal("1"),
            "USDC": Decimal("1"),
            "DAI": Decimal("1"),
        }
        return fallbacks.get(token.upper())

    def _norm(self, symbol_or_address: str) -> str:
        return (
            self.token_address_to_symbol.get(symbol_or_address.lower(), symbol_or_address.lower())
            if symbol_or_address.startswith("0x")
            else symbol_or_address.upper()
        )

    async def _price_from_provider(
        self, prov: Provider, token: str, vs: str
    ) -> Optional[Decimal]:
        try:
            if prov.name == "binance":
                # Use API mapping for Binance
                binance_mappings = self.symbol_to_api_id.get('binance', {})
                symbol = binance_mappings.get(token, f"{token}USDT")
                data = await self._request(prov, prov.price_url, params={"symbol": symbol})
                return Decimal(data["price"]) if data and "price" in data else None

            if prov.name == "coingecko":
                # Use proper CoinGecko API IDs
                coingecko_mappings = self.symbol_to_api_id.get('coingecko', {})
                token_id = coingecko_mappings.get(token, token.lower())
                params = {"ids": token_id, "vs_currencies": vs}
                data = await self._request(prov, prov.price_url, params=params)
                return Decimal(str(data[token_id][vs])) if data and token_id in data else None

            if prov.name == "coinpaprika":
                # Use proper CoinPaprika ticker IDs
                coinpaprika_mappings = self.symbol_to_api_id.get('coinpaprika', {})
                token_id = coinpaprika_mappings.get(token, f"{token.lower()}-{token.lower()}")
                endpoint = prov.price_url.format(id=token_id)
                data = await self._request(prov, endpoint)
                return Decimal(str(data["quotes"][vs.upper()]["price"])) if data and "quotes" in data and vs.upper() in data["quotes"] else None

            if prov.name == "cryptocompare":
                # CryptoCompare uses simple symbol mapping
                cryptocompare_mappings = self.symbol_to_api_id.get('cryptocompare', {})
                from_symbol = cryptocompare_mappings.get(token, token)
                params = {"fsym": from_symbol, "tsyms": vs.upper()}
                data = await self._request(prov, prov.price_url, params=params)
                return Decimal(str(data[vs.upper()])) if data and vs.upper() in data else None

            if prov.name == "coinmarketcap":
                # CoinMarketCap uses symbol mapping
                coinmarketcap_mappings = self.symbol_to_api_id.get('coinmarketcap', {})
                symbol = coinmarketcap_mappings.get(token, token)
                params = {"symbol": symbol, "convert": vs.upper()}
                data = await self._request(prov, prov.price_url, params=params)
                if data and "data" in data and symbol in data["data"]:
                    quote_data = data["data"][symbol]["quote"].get(vs.upper())
                    if quote_data:
                        return Decimal(str(quote_data["price"]))
                return None

            return None
        except Exception as e:
            logger.debug(f"Error from provider {prov.name}: {e}")
            return None

    async def _request(
        self, prov: Provider, endpoint: str, *, params: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        url = prov.base_url + endpoint
        for attempt in range(self._MAX_REQUEST_ATTEMPTS):
            delay = self._BACKOFF_BASE**attempt + random.random()
            async with prov.limiter:
                if self._session is None:
                    await self._acquire_session()
                try:
                    async with self._session.get(
                        url, params=params, headers=self._headers(prov)
                    ) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(delay)
                            continue
                        if resp.status >= 400:
                            logger.warning(f"{prov.name} HTTP {resp.status}: {url}")
                            return None
                        return await resp.json()
                except aiohttp.ClientError:
                    await asyncio.sleep(delay)
                except Exception as e:
                    logger.debug(f"HTTP error from {prov.name}: {e}")
                    await asyncio.sleep(delay)
        return None

    async def get_price_history(
        self, token: str, vs: str = "usd", days: int = 30
    ) -> Optional[List[Dict[str, Any]]]:
        """Fetch historical price data for a token."""
        t_norm = self._norm(token)
        key = f"ph:{t_norm}:{vs}:{days}"
        if key in self.price_cache:
            return self.price_cache[key]

        prices = []
        for prov in self.providers.values():
            if not prov.historical_url:
                continue
            try:
                # Get the appropriate API ID for the provider
                if prov.name == "coingecko":
                    coingecko_mappings = self.symbol_to_api_id.get('coingecko', {})
                    api_id = coingecko_mappings.get(t_norm, t_norm.lower())
                elif prov.name == "coinpaprika":
                    coinpaprika_mappings = self.symbol_to_api_id.get('coinpaprika', {})
                    api_id = coinpaprika_mappings.get(t_norm, f"{t_norm.lower()}-{t_norm.lower()}")
                else:
                    api_id = t_norm.lower()
                
                data = await self._request(
                    prov,
                    prov.historical_url.format(id=api_id),
                    params={"vs_currency": vs, "days": days}
                )
                if data and "prices" in data:
                    prices.extend(data["prices"])
            except Exception as e:
                logger.debug(f"Error fetching historical data from {prov.name}: {e}")

        if not prices:
            return None

        self.price_cache[key] = prices
        return prices
    
    @staticmethod
    def _headers(prov: Provider) -> Dict[str, str]:
        if prov.name == "coingecko" and prov.api_key:
            return {"x-cg-pro-api-key": prov.api_key}
        if prov.name == "coinmarketcap" and prov.api_key:
            return {"X-CMC_PRO_API_KEY": prov.api_key}
        if prov.name == "cryptocompare" and prov.api_key:
            return {"authorization": f"Apikey {prov.api_key}"}
        return {}

    def get_token_symbol(self, address: str) -> Optional[str]:
        return self.token_address_to_symbol.get(address.lower())

    def get_token_address(self, symbol: str) -> Optional[str]:
        return self.token_symbol_to_address.get(symbol.upper())

    async def get_market_volatility(self, token: str, hours: int = 24) -> Optional[float]:
        """Calculate price volatility for a token over the specified time period."""
        try:
            # Get recent price history
            history = await self.get_price_history(token, days=max(1, hours // 24))
            if not history or len(history) < 2:
                return None
            
            # Extract prices and calculate volatility
            prices = [float(price[1]) for price in history[-min(hours, len(history)):]]
            if len(prices) < 2:
                return None
            
            # Calculate standard deviation of price changes
            price_changes = [
                (prices[i] - prices[i-1]) / prices[i-1] 
                for i in range(1, len(prices))
            ]
            
            if not price_changes:
                return 0.0
            
            mean_change = sum(price_changes) / len(price_changes)
            variance = sum((change - mean_change) ** 2 for change in price_changes) / len(price_changes)
            volatility = variance ** 0.5
            
            logger.debug(f"Calculated volatility for {token}: {volatility:.4f}")
            return volatility
            
        except Exception as e:
            logger.debug(f"Error calculating volatility for {token}: {e}")
            return None

    async def get_volume_trend(self, token: str, vs: str = "usd") -> Optional[Dict[str, float]]:
        """Get volume trend information for a token."""
        cache_key = f"vol_trend:{self._norm(token)}:{vs}"
        if cache_key in self.volume_cache:
            return self.volume_cache[cache_key]
        
        try:
            volumes = []
            for prov in self.providers.values():
                if not prov.volume_url:
                    continue
                
                vol_data = await self._get_volume_from_provider(prov, token, vs)
                if vol_data:
                    volumes.append(vol_data)
            
            if not volumes:
                return None
            
            # Calculate weighted average
            total_weight = sum(prov.weight for prov in self.providers.values() if prov.volume_url)
            if total_weight == 0:
                return None
            
            avg_volume = sum(vol * prov.weight for vol, prov in zip(volumes, self.providers.values()) if prov.volume_url) / total_weight
            
            trend_data = {
                "current_volume": avg_volume,
                "volume_24h": avg_volume,  # Simplified - could be enhanced with historical comparison
                "trend": 0.0  # Neutral trend, could be enhanced with trend calculation
            }
            
            self.volume_cache[cache_key] = trend_data
            return trend_data
            
        except Exception as e:
            logger.debug(f"Error getting volume trend for {token}: {e}")
            return None

    async def _get_volume_from_provider(self, prov: Provider, token: str, vs: str) -> Optional[float]:
        """Get volume data from a specific provider."""
        try:
            if prov.name == "binance":
                binance_mappings = self.symbol_to_api_id.get('binance', {})
                symbol = binance_mappings.get(token, f"{token}USDT")
                data = await self._request(prov, prov.volume_url, params={"symbol": symbol})
                return float(data["volume"]) if data and "volume" in data else None
                
            elif prov.name == "coingecko":
                coingecko_mappings = self.symbol_to_api_id.get('coingecko', {})
                token_id = coingecko_mappings.get(token, token.lower())
                params = {"ids": token_id, "vs_currencies": vs}
                data = await self._request(prov, "/simple/price", params=params)
                return float(data[token_id][f"{vs}_24h_vol"]) if data and token_id in data and f"{vs}_24h_vol" in data[token_id] else None
                
            elif prov.name == "cryptocompare":
                # CryptoCompare volume data
                cryptocompare_mappings = self.symbol_to_api_id.get('cryptocompare', {})
                from_symbol = cryptocompare_mappings.get(token, token)
                params = {"fsym": from_symbol, "tsym": vs.upper(), "limit": 1}
                data = await self._request(prov, "/v2/histoday", params=params)
                if data and "Data" in data and "Data" in data["Data"] and len(data["Data"]["Data"]) > 0:
                    return float(data["Data"]["Data"][0]["volumeto"])
                return None
                
            elif prov.name == "coinmarketcap":
                # CoinMarketCap volume data
                coinmarketcap_mappings = self.symbol_to_api_id.get('coinmarketcap', {})
                symbol = coinmarketcap_mappings.get(token, token)
                params = {"symbol": symbol, "convert": vs.upper()}
                data = await self._request(prov, prov.volume_url, params=params)
                if data and "data" in data and symbol in data["data"]:
                    quote_data = data["data"][symbol]["quote"].get(vs.upper())
                    if quote_data and "volume_24h" in quote_data:
                        return float(quote_data["volume_24h"])
                return None
                
            # Binance, CoinGecko, CryptoCompare, and CoinMarketCap provide reliable volume data
            # CoinPaprika doesn't have direct volume endpoints in their free tier
            
            return None
        except Exception as e:
            logger.debug(f"Error getting volume from {prov.name}: {e}")
            return None

    async def get_market_summary(self, tokens: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive market summary for multiple tokens."""
        summary = {}
        
        for token in tokens:
            try:
                price = await self.get_real_time_price(token)
                volatility = await self.get_market_volatility(token)
                volume_data = await self.get_volume_trend(token)
                
                summary[token] = {
                    "price": float(price) if price else None,
                    "volatility": volatility,
                    "volume_24h": volume_data.get("volume_24h") if volume_data else None,
                    "last_updated": time.time()
                }
            except Exception as e:
                logger.debug(f"Error getting market summary for {token}: {e}")
                summary[token] = {"error": str(e)}
        
        return summary


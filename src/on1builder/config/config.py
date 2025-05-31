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
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import joblib
import pandas as pd
import yaml
from cachetools import TTLCache
from dotenv import load_dotenv

from on1builder.utils.logger import setup_logging

logger = setup_logging("Config", level="DEBUG")


class Configuration:
    """Base configuration class for ON1Builder."""

    POA_CHAINS = {99, 100, 77, 7766, 56, 11155111}

    _DEFAULTS = {
        "GRAPH_API_KEY": "",
        "UNISWAP_V2_SUBGRAPH_ID": "",
        "COINGECKO_API_KEY": "",
        "DEBUG": False,
        "BASE_PATH": str(Path(__file__).resolve().parent.parent.parent.parent),
        "HTTP_ENDPOINT": "https://ethereum-rpc.publicnode.com",
        "WEBSOCKET_ENDPOINT": "wss://ethereum-rpc.publicnode.com",
        "IPC_ENDPOINT": None,
        "C-CHAIN_HTTP_ENDPOINT": "",
        "C-CHAIN_WEBSOCKET_ENDPOINT": "",
        "P-CHAIN_HTTP_ENDPOINT": "",
        "X-CHAIN_HTTP_ENDPOINT": "",
        "SUI_HTTP_ENDPOINT": "",
        "SUI_WEBSOCKET_ENDPOINT": "",
        "SOLANA_HTTP_ENDPOINT": "",
        "SOLANA_WEBSOCKET_ENDPOINT": "",
        "SOLANA_YELLOWSTONE_GRPC_ENDPOINT": "",
        "SAFETYNET_CACHE_TTL": 60,
        "SAFETYNET_GAS_PRICE_TTL": 10,
        "MAX_GAS_PRICE_GWEI": 100,
        "MIN_PROFIT": 0.001,
        "MEMPOOL_RETRY_DELAY": 0.5,
        "MEMPOOL_MAX_RETRIES": 3,
        "MARKET_CACHE_TTL": 60,  # <- Fixed: no duplicates
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
        if name in self._config:
            return self._config[name]
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")

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
            "uniswap_subgraph": Provider(
                name="uniswap_subgraph",
                base_url=f"https://gateway.thegraph.com/api/{g_api}/subgraphs/id/{uni_id}",
                rate_limit=5,
                weight=0.3,
            ),
            "dexscreener": Provider(
                name="dexscreener",
                base_url="https://api.dexscreener.com/latest/dex",
                rate_limit=10,
                weight=0.3,
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

        weighted = sum(p * w for p, w in zip(prices, weights)) / sum(weights)
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
                symbol = f"{token.replace('W', '')}USDT"
                data = await self._request(prov, prov.price_url, params={"symbol": symbol})
                return Decimal(data["price"]) if data and "price" in data else None

            if prov.name == "coingecko":
                token_id = self.symbol_to_api_id.get(token, token.lower())
                params = {"ids": token_id, "vs_currencies": vs}
                data = await self._request(prov, prov.price_url, params=params)
                return Decimal(str(data[token_id][vs])) if data and token_id in data else None

            if prov.name == "coinpaprika":
                token_id = self.symbol_to_api_id.get(token, token)
                endpoint = prov.price_url.format(id=token_id)
                data = await self._request(prov, endpoint)
                return Decimal(str(data["quotes"][vs.upper()]["price"])) if data else None

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

    @staticmethod
    def _headers(prov: Provider) -> Dict[str, str]:
        if prov.name == "coingecko" and prov.api_key:
            return {"x-cg-pro-api-key": prov.api_key}
        if prov.name == "coinmarketcap" and prov.api_key:
            return {"X-CMC_PRO_API_KEY": prov.api_key}
        return {}

    def get_token_symbol(self, address: str) -> Optional[str]:
        return self.token_address_to_symbol.get(address.lower())

    def get_token_address(self, symbol: str) -> Optional[str]:
        return self.token_symbol_to_address.get(symbol.upper())

    def __repr__(self) -> str:
        return f"<APIConfig providers=[{', '.join(self.providers)}]>"

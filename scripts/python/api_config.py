# api_config.py
"""
ON1Builder – APIConfig
======================

Thin aggregation layer over various public price/volume APIs.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import joblib
import pandas as pd
from cachetools import TTLCache

from configuration import Configuration
from logger_on1 import setup_logging

logger = setup_logging("APIConfig", level="DEBUG")


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
        g_api = self.cfg.get_config_value("GRAPH_API_KEY", "")
        uni_id = self.cfg.get_config_value("UNISWAP_V2_SUBGRAPH_ID", "")

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
        if sym_or_addr.startswith("0x"):
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
        if lr_path.exists():
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

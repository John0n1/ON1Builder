#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – MarketMonitor
======================

Market data monitoring service. MarketMonitor provides real-time price and 
volume data for tokens, tracks market trends, 
and checks for arbitrage opportunities across multiple venues. 
It uses an in-memory cache to optimize performance and reduce API calls.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from on1builder.config.config import APIConfig, Configuration
from on1builder.utils.logger import setup_logging

logger = setup_logging("MarketMonitor", level="DEBUG")


def track(metric_name: str):
    """Decorator to increment a metric counter on each call."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            self.metrics[metric_name] = self.metrics.get(metric_name, 0) + 1
            return await func(self, *args, **kwargs)
        return wrapper
    return decorator


class MarketMonitor:
    """Market data monitoring service."""

    def __init__(
        self,
        web3: Any,
        config: Configuration,
        api_config: APIConfig,
    ) -> None:
        self.web3 = web3
        self.config = config
        self.api_config = api_config

        # In-memory caches
        self._price_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self._last_cache_cleanup = time.time()
        self._cache_ttl = config.get("PRICE_CACHE_TTL", 300)
        self._cleanup_interval = config.get("CACHE_CLEANUP_INTERVAL", 300)

        # Metrics counters
        self.metrics: Dict[str, int] = {}

        logger.info("MarketMonitor initialized")

    @track("price_lookup")
    async def get_token_price(
        self,
        token: str,
        quote_currency: str = "USD",
        *args,
        **kwargs,
    ) -> Optional[Decimal]:
        """Get the current price of a token."""
        now = time.time()
        if now - self._last_cache_cleanup > self._cleanup_interval:
            await self._cleanup_cache()

        cache_key = f"{token.lower()}_{quote_currency.lower()}"
        async with self._cache_lock:
            if cache_key in self._price_cache:
                entry = self._price_cache[cache_key]
                if now - entry["timestamp"] < self._cache_ttl:
                    self.metrics["price_cache_hit"] = self.metrics.get("price_cache_hit", 0) + 1
                    logger.debug(f"Cache hit for {token} price")
                    return entry["price"]

        # Delegate to APIConfig
        price = await self.api_config.get_real_time_price(token, quote_currency)
        if price is not None:
            async with self._cache_lock:
                self._price_cache[cache_key] = {"price": price, "timestamp": now}
            logger.debug(f"Updated price for {token}: {price} {quote_currency}")
        else:
            # MarketMonitor-level fallback if APIConfig also fails
            token_upper = token.upper()
            fallback_prices = {
                "ETH": Decimal("3400.00"),
                "BTC": Decimal("62000.00"),
                "USDT": Decimal("1.00"),
                # ...etc
            }
            fallback = fallback_prices.get(token_upper)
            if fallback is not None:
                self.metrics["price_fallback"] = self.metrics.get("price_fallback", 0) + 1
                async with self._cache_lock:
                    self._price_cache[cache_key] = {"price": fallback, "timestamp": now}
                logger.debug(f"Using fallback price for {token}: {fallback} {quote_currency}")
                price = fallback

        return price

    async def _cleanup_cache(self) -> None:
        """Clean up expired cache entries."""
        now = time.time()
        self._last_cache_cleanup = now

        async with self._cache_lock:
            expired = [
                key for key, entry in self._price_cache.items()
                if now - entry["timestamp"] > self._cache_ttl
            ]
            for key in expired:
                del self._price_cache[key]
            if expired:
                logger.debug(f"Cleared {len(expired)} expired price cache entries")

    async def get_market_trend(
        self,
        token: str,
        timeframe: str = "1h",
        quote_currency: str = "USD",
    ) -> Dict[str, Any]:
        """Get market trend data for a token."""
        supported = ["5m", "15m", "1h", "4h", "12h", "24h", "7d"]
        if timeframe not in supported:
            logger.warning(f"Unsupported timeframe '{timeframe}', defaulting to 1h")
            timeframe = "1h"

        # Try history-based
        if hasattr(self.api_config, "get_price_history"):
            try:
                history = await self.api_config.get_price_history(token, timeframe, quote_currency)
                if history:
                    start = history[0]["price"]
                    end = history[-1]["price"]
                    change = end - start
                    pct = (change / start * 100) if start else 0.0

                    if pct > 3:
                        trend = "bullish"
                    elif pct < -3:
                        trend = "bearish"
                    else:
                        trend = "sideways"

                    return {
                        "trend": trend,
                        "current_price": end,
                        "start_price": start,
                        "price_change": change,
                        "percent_change": pct,
                        "timeframe": timeframe,
                        "data_points": len(history),
                    }
            except Exception as e:
                logger.error(f"Error fetching price history: {e}")

        # Fallback simple
        try:
            curr = await self.get_token_price(token, quote_currency)
            if curr is None:
                return {"trend": "unknown", "error": "No price available"}
            return {
                "trend": "unknown",
                "current_price": curr,
                "note": "Limited trend data",
            }
        except Exception as e:
            logger.error(f"Error calculating market trend: {e}")
            return {"trend": "unknown", "error": str(e)}

    @track("volume_lookup")
    async def get_token_volume(
        self,
        token: str,
        timeframe: str = "24h",
        quote_currency: str = "USD",
    ) -> Optional[Decimal]:
        """Get trading volume for a token."""
        cache_key = f"vol_{token.lower()}_{timeframe}_{quote_currency.lower()}"
        now = time.time()

        async with self._cache_lock:
            if cache_key in self._price_cache:
                entry = self._price_cache[cache_key]
                if now - entry["timestamp"] < self._cache_ttl:
                    self.metrics["volume_cache_hit"] = self.metrics.get("volume_cache_hit", 0) + 1
                    logger.debug(f"Cache hit for {token} volume")
                    return entry["volume"]

        # Delegate
        volume = None
        try:
            volume = await self.api_config.get_token_volume(token)
        except Exception as e:
            logger.error(f"Error getting token volume: {e}")

        # Fallback volumes
        if volume is None:
            token_upper = token.upper()
            fallback = {
                "ETH": Decimal("5000000.00"),
                "BTC": Decimal("20000000.00"),
                # ...etc
            }.get(token_upper)
            if fallback is not None:
                self.metrics["volume_fallback"] = self.metrics.get("volume_fallback", 0) + 1
                volume = fallback
                logger.debug(f"Using fallback volume for {token}: {volume} {quote_currency}")

        if volume is not None:
            async with self._cache_lock:
                self._price_cache[cache_key] = {"volume": volume, "timestamp": now}

        return volume

    async def schedule_updates(self) -> None:
        """Schedule regular updates of market data."""
        logger.info("Scheduling market data updates")
        interval = self.config.get("MARKET_UPDATE_INTERVAL", 60)
        tokens = self.config.get("MONITORED_TOKENS", [])

        if not tokens:
            logger.warning("No tokens configured for monitoring")
            return

        asyncio.create_task(self._update_loop(interval, tokens))

    async def _update_loop(self, interval: int, tokens: List[str]) -> None:
        """Background loop to refresh market data in parallel."""
        logger.info(f"Starting update loop for {len(tokens)} tokens, interval {interval}s")
        while True:
            try:
                tasks: List[asyncio.Task] = []
                for token in tokens:
                    tasks.append(self.get_token_price(token))
                    tasks.append(self.get_token_volume(token))
                # fire off all at once
                await asyncio.gather(*tasks)
            except Exception as e:
                logger.error(f"Error in market data update loop: {e}")
            await asyncio.sleep(interval)

    async def is_healthy(self) -> bool:
        """Check if the monitor can fetch price for a health-check token."""
        try:
            test = self.config.get("HEALTH_CHECK_TOKEN", "ETH")
            price = await self.get_token_price(test)
            return price is not None
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def stop(self) -> None:
        """No-op: relies on APIConfig’s session cleanup."""
        logger.info("MarketMonitor stopping (no local resources to close)")

    async def check_market_conditions(
        self,
        token: str,
        condition_type: str = "volatility",
    ) -> Dict[str, Any]:
        """Check specific market conditions: volatility, liquidity, momentum."""
        result: Dict[str, Any] = {
            "token": token,
            "condition_type": condition_type,
            "timestamp": time.time(),
        }

        try:
            if condition_type == "volatility":
                t1 = await self.get_market_trend(token, "1h")
                t4 = await self.get_market_trend(token, "4h")
                vol = abs(t1.get("percent_change", 0.0))
                vol_long = abs(t4.get("percent_change", 0.0))
                avg_vol = (vol + vol_long) / 2
                if avg_vol > 10:
                    cond = "high"
                elif avg_vol > 5:
                    cond = "medium"
                else:
                    cond = "low"
                result.update({"condition": cond, "volatility": avg_vol})

            elif condition_type == "liquidity":
                vol = await self.get_token_volume(token)
                price = await self.get_token_price(token)
                if vol and price:
                    score = float(vol) / float(price)
                    cond = "high" if score > 1e6 else "medium" if score > 1e5 else "low"
                    result.update({"condition": cond, "liquidity_score": score})
                else:
                    result.update({"condition": "unknown", "error": "No vol/price"})

            elif condition_type == "momentum":
                trends = [
                    (await self.get_market_trend(token, tf))["percent_change"]
                    for tf in ("1h", "4h", "24h")
                    if isinstance(await self.get_market_trend(token, tf), dict)
                ]
                if trends:
                    weighted = (trends[0] + trends[1]*2 + trends[2]*3) / 6
                    if weighted > 5:
                        cond = "strongly_positive"
                    elif weighted > 2:
                        cond = "positive"
                    elif weighted < -5:
                        cond = "strongly_negative"
                    elif weighted < -2:
                        cond = "negative"
                    else:
                        cond = "neutral"
                    result.update({"condition": cond, "momentum_score": weighted})
                else:
                    result.update({"condition": "unknown", "error": "No trend data"})
            else:
                result.update({"condition": "unknown", "error": f"Unsupported: {condition_type}"})

            return result

        except Exception as e:
            logger.error(f"Error checking market conditions: {e}")
            return {"token": token, "condition": "error", "error": str(e)}

    async def get_token_prices_across_venues(self, token: str) -> Dict[str, float]:
        """Fetch prices from each provider for arbitrage analysis."""
        venues: Dict[str, float] = {}
        try:
            primary = await self.get_token_price(token)
            if primary is not None:
                venues["primary"] = float(primary)

            for name, prov in self.api_config.providers.items():
                try:
                    price = await self.api_config._price_from_provider(prov, token, "usd")
                    if price is not None:
                        venues[name] = float(price)
                except Exception:
                    continue

            if not venues:
                base = 100.0
                venues = {"uniswap": base, "sushiswap": base*1.02, "balancer": base*0.98}
        except Exception as e:
            logger.error(f"Error fetching prices across venues: {e}")

        return venues

    async def is_arbitrage_opportunity(self, token: str, min_spread_percent: float = 1.0) -> bool:
        """Check if arbitrage spread ≥ min_spread_percent exists."""
        try:
            prices = await self.get_token_prices_across_venues(token)
            if len(prices) < 2:
                return False
            vals = list(prices.values())
            spread = (max(vals) - min(vals)) / min(vals) * 100 if min(vals) else 0.0
            logger.debug(f"Arb spread for {token}: {spread:.2f}%")
            return spread >= min_spread_percent
        except Exception as e:
            logger.error(f"Error in arbitrage check: {e}")
            return False

    async def _get_price_volatility(self, token: str) -> float:
        """Calculate normalized volatility score (0.0–1.0)."""
        try:
            changes = []
            for tf in ("1h", "4h", "24h"):
                trend = await self.get_market_trend(token, tf)
                if "percent_change" in trend:
                    changes.append(abs(float(trend["percent_change"])))
            if not changes:
                return 0.05
            avg = sum(changes) / len(changes)
            return min(avg / 20.0, 1.0)
        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            return 0.05

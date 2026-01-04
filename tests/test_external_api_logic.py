"""Focused logic tests for ExternalAPIManager without hitting real networks."""
import asyncio
import time
from cachetools import TTLCache
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.integrations.external_apis import ExternalAPIManager, RateLimitTracker


def reset_manager_state(manager: ExternalAPIManager):
    """Ensure singleton state is clean for each test."""
    manager._initialized = True  # skip real initialization
    manager._providers = {}
    manager._session = None
    manager._background_tasks = set()
    manager._price_cache = TTLCache(maxsize=10, ttl=60)
    manager._failed_tokens = set()
    manager._token_mappings = {}
    manager._all_tokens_loaded = True
    manager._all_tokens_load_time = 0


def test_rate_limit_tracker_backoff_when_near_limit(monkeypatch):
    tracker = RateLimitTracker(max_requests=5, window_duration=60)
    tracker.requests_made = 4
    tracker.window_start = time.time()

    tracker.record_request(success=False)
    assert tracker.requests_made == 5
    assert tracker.backoff_until > 0
    assert tracker.can_make_request() is False


@pytest.mark.asyncio
async def test_get_price_returns_cache_and_skips_failed_tokens(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager_state(manager)
    manager._initialize = AsyncMock()

    manager._price_cache["ETH"] = 123.45
    manager._failed_tokens.add("BAD")

    cached = await manager.get_price("eth")
    assert cached == 123.45

    skipped = await manager.get_price("BAD")
    assert skipped is None


@pytest.mark.asyncio
async def test_comprehensive_market_data_handles_errors_gracefully(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager_state(manager)
    manager._initialize = AsyncMock()

    manager.get_price = AsyncMock(side_effect=Exception("price failure"))
    manager.get_market_sentiment = AsyncMock(return_value=0.2)
    manager.get_volatility_index = AsyncMock(side_effect=Exception("vol failure"))
    manager.get_trading_volume_24h = AsyncMock(return_value=1111.1)
    manager.get_market_cap = AsyncMock(return_value=None)

    data = await manager.get_comprehensive_market_data("eth")

    assert data["symbol"] == "ETH"
    assert data["price_usd"] is None  # exception converted to None
    assert data["sentiment_score"] == 0.2
    assert data["volatility_index"] is None  # exception converted to None
    assert data["volume_24h_usd"] == 1111.1
    assert data["market_cap_usd"] is None


def test_parse_token_data_rejects_problematic_symbols():
    manager = ExternalAPIManager()
    reset_manager_state(manager)

    good = manager._parse_token_data(
        {"symbol": "GOOD", "name": "Good Token", "addresses": {}, "decimals": 18}
    )
    bad = manager._parse_token_data({"symbol": "BA D", "name": "Bad Token"})

    assert good is not None and good.symbol == "GOOD"
    assert bad is None


@pytest.mark.asyncio
async def test_get_price_skips_unhealthy_providers(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager_state(manager)
    # Restore original coroutine method in case earlier tests patched it
    manager.get_price = ExternalAPIManager.get_price.__get__(manager, ExternalAPIManager)  # type: ignore[attr-defined]
    manager._initialize = AsyncMock()
    # Simulate only one provider and mark unhealthy
    manager._providers = {"coingecko": SimpleNamespace(is_healthy=False)}
    manager._failed_tokens = set()

    price = await manager.get_price("ETH")
    assert price is None

"""Behavior-first tests for MarketDataFeed without touching real networks."""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.monitoring.market_data_feed import MarketDataFeed


class DummyWeb3:
    def __init__(self):
        self.eth = SimpleNamespace()


class DummyWeb3AsyncChain:
    def __init__(self):
        self.eth = SimpleNamespace()

        async def chain_id():
            return 137

        self.eth.chain_id = chain_id


@pytest.fixture(autouse=True)
def stub_settings(monkeypatch):
    stub = SimpleNamespace(
        heartbeat_interval=10,
        chains=[1],
        market_price_persist_interval=0,
    )
    monkeypatch.setattr("on1builder.monitoring.market_data_feed.settings", stub)
    yield


@pytest.mark.asyncio
async def test_price_cache_and_blacklist(monkeypatch):
    feed = MarketDataFeed(DummyWeb3())
    feed._db_ready = True
    feed._db_interface.save_market_price = AsyncMock()
    feed._api_manager.get_price = AsyncMock(
        side_effect=[1.0, None, None, None, None, None]
    )

    # First call caches the price
    price1 = await feed.get_price("ETH")
    assert price1 == Decimal("1.0")
    # Subsequent call hits cache
    price2 = await feed.get_price("ETH")
    assert price2 == Decimal("1.0")

    # Trigger failures and ensure blacklist after 5 consecutive failures
    for _ in range(5):
        await feed.get_price("FAIL")
    assert "FAIL" in feed.get_failed_tokens()
    # Blacklisted tokens short-circuit
    assert await feed.get_price("FAIL") is None


@pytest.mark.asyncio
async def test_price_persistence(monkeypatch):
    feed = MarketDataFeed(DummyWeb3())
    feed._persist_interval = 1
    feed._db_ready = True
    feed._db_interface.save_market_price = AsyncMock()
    feed._api_manager.get_price = AsyncMock(return_value=123.45)

    price = await feed.get_price("ETH")
    assert price == Decimal("123.45")
    feed._db_interface.save_market_price.assert_called_once()


@pytest.mark.asyncio
async def test_volatility_and_trend_detection(monkeypatch):
    feed = MarketDataFeed(DummyWeb3())
    now = datetime.now()
    # Build a gently increasing price series over the last hour
    history = [
        (now - timedelta(minutes=60 - i * 5), Decimal("90") + Decimal(i))
        for i in range(12)
    ]
    feed._price_history["ETH"] = history  # oldest first

    vol = await feed.get_volatility("ETH", timeframe_minutes=60)
    assert vol is not None and vol >= 0

    trend = await feed.get_price_trend("ETH", timeframe_minutes=60)
    assert trend == "bullish"


@pytest.mark.asyncio
async def test_should_avoid_trading_based_on_volatility(monkeypatch):
    feed = MarketDataFeed(DummyWeb3())
    feed._volatility_cache["ETH_60m"] = 0.2  # high volatility
    feed._market_sentiment["ETH"] = 0.0
    assert await feed.should_avoid_trading("ETH") is True


@pytest.mark.asyncio
async def test_resolve_chain_id_awaits_async_property():
    feed = MarketDataFeed(DummyWeb3AsyncChain())
    resolved = await feed._resolve_chain_id()
    assert resolved == 137

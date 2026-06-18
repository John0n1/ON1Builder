from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.monitoring import market_data_feed as market_module
from on1builder.monitoring.market_data_feed import MarketDataFeed


class AwaitableValue:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        async def _coro():
            return self.value

        return _coro().__await__()


@pytest.fixture
def stub_settings(monkeypatch):
    settings = SimpleNamespace(
        heartbeat_interval=10, chains=[1], market_price_persist_interval=1
    )
    monkeypatch.setattr(market_module, "settings", settings)
    return settings


@pytest.fixture
def feed(stub_settings):
    web3 = MagicMock()
    web3.eth = SimpleNamespace(chain_id=AwaitableValue(1))
    feed = MarketDataFeed(web3)
    feed._api_manager = MagicMock()
    feed._api_manager.close = AsyncMock()
    feed._api_manager.reset_failed_tokens = MagicMock()
    feed._db_interface = MagicMock(
        initialize_db=AsyncMock(), save_market_price=AsyncMock()
    )
    return feed


@pytest.mark.asyncio
async def test_start_stop_get_price_and_persistence(feed, monkeypatch):
    class FakeTask:
        def __init__(self, coro):
            self.coro = coro
            self.cancel = MagicMock()

        def __await__(self):
            self.coro.close()
            if False:
                yield None
            return None

    monkeypatch.setattr(
        market_module.asyncio, "create_task", lambda coro: FakeTask(coro)
    )
    await feed.start()
    assert feed._is_running is True

    feed._api_manager.get_price = AsyncMock(return_value=Decimal("12.5"))
    price = await feed.get_price("ETH")
    assert price == Decimal("12.5")
    assert await feed.get_price("ETH") == Decimal("12.5")

    assert await feed.get_price("ß") is None
    assert await feed.get_price("UNKNOWN") is None

    await feed.stop()
    feed._api_manager.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_price_handles_db_failures(feed):
    feed._persist_interval = 1
    feed._db_ready = False
    feed._db_interface.initialize_db = AsyncMock(side_effect=RuntimeError("db down"))
    await feed._persist_price("ETH", Decimal("1"))

    feed._last_persisted.clear()
    feed._db_interface.initialize_db = AsyncMock(return_value=None)
    await feed._persist_price("ETH", Decimal("1"))
    feed._db_interface.save_market_price.assert_awaited_once()


@pytest.mark.asyncio
async def test_volatility_trend_sentiment_slippage_and_avoid_trading(feed):
    now = datetime.now()
    feed._price_history["ETH"] = [
        (now - timedelta(minutes=60 - i * 5), Decimal("100") + Decimal(i * 2))
        for i in range(12)
    ]
    vol = await feed.get_volatility("ETH", 60)
    assert vol is not None
    assert await feed.get_price_trend("ETH", 60) == "bullish"

    feed._api_manager.get_market_sentiment = AsyncMock(
        side_effect=[0.7, RuntimeError("fallback")]
    )
    assert await feed.get_market_sentiment("ETH") == 0.7
    feed._market_sentiment["ETH"] = -0.9
    assert await feed.get_market_sentiment("ETH") == -0.9

    slippage = await feed.get_optimal_slippage("ETH", Decimal("20000"))
    assert Decimal("0.001") <= slippage <= Decimal("0.05")
    assert await feed.should_avoid_trading("ETH") is True


@pytest.mark.asyncio
async def test_get_prices_background_loops_and_analysis(feed, monkeypatch):
    feed.get_price = AsyncMock(side_effect=[Decimal("1"), Decimal("2")])
    assert await feed.get_prices(["ETH", "WETH"]) == {
        "ETH": Decimal("1"),
        "WETH": Decimal("2"),
    }

    feed._is_running = True
    feed.get_prices = AsyncMock(
        side_effect=lambda symbols: setattr(feed, "_is_running", False) or {}
    )
    monkeypatch.setattr(
        "on1builder.integrations.abi_registry.ABIRegistry",
        lambda: SimpleNamespace(
            get_monitored_tokens=lambda chain_id: {
                "ETH": "0x1",
                "WETH": "0x2",
                "BAD": "0x3",
            }
        ),
    )
    monkeypatch.setattr(market_module.asyncio, "sleep", AsyncMock())
    await feed._update_loop()
    feed.get_prices.assert_awaited_once()

    feed._is_running = True
    feed._calculate_market_sentiment = AsyncMock(
        side_effect=lambda: setattr(feed, "_is_running", False)
    )
    feed._detect_market_anomalies = AsyncMock()
    await feed._analysis_loop()
    feed._calculate_market_sentiment.assert_awaited_once()


@pytest.mark.asyncio
async def test_sentiment_anomaly_and_summary_helpers(feed):
    now = datetime.now()
    feed._price_history = {
        "ETH": [
            (now - timedelta(minutes=5 * (20 - i)), Decimal("100") + Decimal(i * 3))
            for i in range(20)
        ],
        "USDC": [
            (now - timedelta(minutes=5 * (20 - i)), Decimal("1")) for i in range(20)
        ],
    }
    await feed._calculate_market_sentiment()
    assert "ETH" in feed._market_sentiment

    feed.get_volatility = AsyncMock(side_effect=[0.09, 0.01])
    await feed._detect_market_anomalies()

    summary = feed.get_market_data_summary()
    assert summary["total_tracked_symbols"] == 2
    feed.reset_failed_tokens()
    assert feed.get_failed_tokens() == set()

    feed._record_failed_token("ETH")
    feed._reset_failed_token("ETH")
    assert "ETH" not in feed.get_failed_tokens()

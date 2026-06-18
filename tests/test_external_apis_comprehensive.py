import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from cachetools import TTLCache

from on1builder.integrations import external_apis as api_module
from on1builder.integrations.external_apis import (
    ExternalAPIManager,
    Provider,
    TokenMapping,
)
from on1builder.utils.custom_exceptions import APICallError


class DummyResponse:
    def __init__(self, status=200, data=None):
        self.status = status
        self._data = data or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._data


class DummySession:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.closed = False
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return DummyResponse()

    async def close(self):
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True
        return False


class DummyTask:
    def __init__(self, result=None):
        self.result = result
        self.cancelled = False
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)

    def cancel(self):
        self.cancelled = True

    def done(self):
        return False

    def __await__(self):
        async def _inner():
            if self.cancelled:
                raise asyncio.CancelledError
            return self.result

        return _inner().__await__()


class FakeLoop:
    async def run_in_executor(self, executor, func, *args):
        return func(*args)


class AwaitableCall:
    def __init__(self, value):
        self.value = value

    async def call(self):
        return self.value


class FakePairFunctions:
    def __init__(self, token0="0xtoken", token1="0xstable"):
        self._token0 = token0
        self._token1 = token1

    def getReserves(self):
        return AwaitableCall((200, 1000, 0))

    def token0(self):
        return AwaitableCall(self._token0)

    def token1(self):
        return AwaitableCall(self._token1)


class FakeFactoryFunctions:
    def getPair(self, token_a, token_b):
        return AwaitableCall("0x0000000000000000000000000000000000000001")


class FakeOracleFunctions:
    def decimals(self):
        return AwaitableCall(8)

    def latestRoundData(self):
        return AwaitableCall((1, 2500_00000000, 0, int(time.time()), 1))


class FakeSupplyFunctions:
    def totalSupply(self):
        return AwaitableCall(5_000_000)

    def decimals(self):
        return AwaitableCall(6)


class FakeWeb3:
    def __init__(self):
        self.eth = SimpleNamespace(contract=self._contract)

    def to_checksum_address(self, address):
        return address

    def _contract(self, address=None, abi=None):
        names = {item.get("name") for item in (abi or [])}
        if "latestRoundData" in names:
            return SimpleNamespace(functions=FakeOracleFunctions())
        if "totalSupply" in names:
            return SimpleNamespace(functions=FakeSupplyFunctions())
        if "getPair" in names:
            return SimpleNamespace(functions=FakeFactoryFunctions())
        return SimpleNamespace(functions=FakePairFunctions())


def reset_manager(manager: ExternalAPIManager):
    for name in [
        "_initialize",
        "get_price",
        "get_market_sentiment",
        "get_volatility_index",
        "get_trading_volume_24h",
        "get_market_cap",
        "get_comprehensive_market_data",
        "_load_configured_oracle_feeds",
        "_start_background_tasks",
        "_load_token_mappings_async",
        "_parse_token_json",
        "_make_request",
        "_fetch_from_coingecko",
        "_fetch_from_binance",
        "_get_historical_prices",
        "_get_coingecko_sentiment",
        "_get_social_sentiment",
        "_get_momentum_sentiment",
        "_get_coingecko_volume",
        "_get_binance_volume",
        "_get_coingecko_market_cap",
        "_get_onchain_supply",
        "_get_onchain_price",
        "_get_oracle_price",
        "_get_reddit_sentiment",
        "_get_twitter_sentiment",
        "_get_community_activity_sentiment",
        "_load_all_tokens_async",
    ]:
        setattr(
            manager,
            name,
            getattr(ExternalAPIManager, name).__get__(manager, ExternalAPIManager),
        )
    manager._initialized = True
    manager._closed = False
    manager._session = None
    manager._providers = {}
    manager._rate_limiters = {}
    manager._background_tasks = set()
    manager._price_cache = TTLCache(maxsize=20, ttl=60)
    manager._failed_tokens = set()
    manager._provider_backoff = {}
    manager._token_mappings = {}
    manager._all_tokens_loaded = True
    manager._all_tokens_load_time = 0
    manager._onchain_web3 = None
    manager._primary_chain_id = 1
    manager._oracle_feeds_by_chain = {1: {"ETH": "0xfeed", "BTC": "0xbtc"}}
    manager._oracle_feeds = manager._oracle_feeds_by_chain[1]
    manager._data_gathering_active = False


def provider(name, base_url="https://example.com", rate_limit=5):
    return Provider(name=name, base_url=base_url, rate_limit=rate_limit)


@pytest.mark.asyncio
async def test_initialize_builds_providers_and_marks_initialized(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    manager._initialized = False
    manager._load_token_mappings_async = AsyncMock()
    called = {"oracle": 0, "tasks": 0}

    built = {"coingecko": provider("coingecko")}
    monkeypatch.setattr(manager, "_build_providers", lambda: built)
    monkeypatch.setattr(
        manager,
        "_load_configured_oracle_feeds",
        lambda: called.__setitem__("oracle", called["oracle"] + 1),
    )
    monkeypatch.setattr(
        manager,
        "_start_background_tasks",
        lambda: called.__setitem__("tasks", called["tasks"] + 1),
    )
    monkeypatch.setattr(
        api_module.aiohttp, "ClientSession", lambda **kwargs: DummySession()
    )

    await ExternalAPIManager._initialize(manager)

    assert manager._providers == built
    assert manager._initialized is True
    manager._load_token_mappings_async.assert_awaited_once()
    assert called == {"oracle": 1, "tasks": 1}


def test_build_providers_and_oracle_config(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    monkeypatch.setattr(
        api_module,
        "settings",
        SimpleNamespace(
            api=SimpleNamespace(etherscan_api_key="secret"),
            oracle_feeds={"1": {"ETH": "0xabc"}, "56": {"BNB": "0xdef"}, "bad": {}},
        ),
    )

    providers = manager._build_providers()
    manager._providers = providers
    manager._load_configured_oracle_feeds()

    assert set(providers) == {"coingecko", "binance", "etherscan"}
    assert manager._oracle_feeds_by_chain[1]["ETH"] == "0xabc"
    assert manager._oracle_feeds_by_chain[56]["BNB"] == "0xdef"


def test_start_background_tasks_registers_tasks(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    created = []

    def fake_create_task(coro):
        coro.close()
        task = DummyTask()
        created.append(task)
        return task

    monkeypatch.setattr(api_module.asyncio, "create_task", fake_create_task)

    manager._start_background_tasks()

    assert len(created) == 2
    assert manager._background_tasks == set(created)
    assert all(task.callbacks for task in created)


@pytest.mark.asyncio
async def test_check_provider_health_and_prefetch(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    good = provider("binance", base_url="https://binance")
    bad = provider("binance", base_url="https://binance")
    bad.rate_tracker.can_make_request = lambda: True
    good.rate_tracker.can_make_request = lambda: True
    manager._providers = {"good": good, "bad": bad}
    manager._session = DummySession([DummyResponse(200, {}), RuntimeError("boom")])
    manager._providers["good"].name = "binance"
    manager._providers["bad"].name = "binance"

    await manager._check_provider_health()

    assert good.is_healthy is True
    assert bad.consecutive_failures >= 1

    manager._get_price_non_blocking = AsyncMock(return_value=1.0)
    manager._price_cache["WETH"] = 10.0
    await manager._prefetch_common_tokens()
    assert manager._data_gathering_active is False
    assert manager._get_price_non_blocking.await_count == 4


@pytest.mark.asyncio
async def test_token_loading_and_parsing(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    tokens = [
        {"symbol": "ETH", "name": "Ether", "coingecko_id": "ethereum"},
        {"symbol": "UNI", "name": "Uniswap", "binance_id": "UNIUSDT"},
        {"symbol": "BAD TOKEN", "name": "Bad"},
        {"symbol": "XYZ", "name": "Other"},
    ]
    monkeypatch.setattr(api_module, "get_resource_path", lambda *parts: "ignored.json")
    monkeypatch.setattr(api_module.asyncio, "get_event_loop", lambda: FakeLoop())
    monkeypatch.setattr(manager, "_parse_token_json", lambda path: tokens)

    await manager._load_token_mappings_async()
    assert set(manager._token_mappings) == {"UNI"}

    manager._all_tokens_loaded = False
    await manager._load_all_tokens_async()
    assert {"ETH", "UNI", "XYZ"}.issubset(set(manager._token_mappings))
    assert manager._all_tokens_loaded is True

    good = manager._parse_token_data(
        {"symbol": "AAVE", "name": "Aave", "decimals": "6", "coingecko_id": "aave"}
    )
    assert good == TokenMapping(
        symbol="AAVE",
        name="Aave",
        addresses={},
        api_ids={"coingecko": "aave"},
        decimals=6,
        is_valid=True,
    )
    assert manager._parse_token_data({"symbol": "Å", "name": "Bad"}) is None
    assert manager._parse_token_data({"symbol": "", "name": "Bad"}) is None

    import builtins

    manager._parse_token_json = ExternalAPIManager._parse_token_json.__get__(
        manager, ExternalAPIManager
    )
    monkeypatch.setattr(
        builtins, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("nope"))
    )
    assert manager._parse_token_json("missing.json") == []


@pytest.mark.asyncio
async def test_get_price_paths_and_failed_token_cleanup(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    manager._initialize = AsyncMock()

    assert await manager.get_price("notascii£") is None
    assert await manager.get_price("unknown-token") is None

    manager._get_onchain_price = AsyncMock(return_value=123.0)
    assert await manager.get_price("ETH") == 123.0
    assert manager._price_cache["ETH"] == 123.0

    manager._price_cache.clear()
    manager._get_onchain_price = AsyncMock(return_value=None)
    manager._get_oracle_price = AsyncMock(return_value=222.0)
    manager._providers = {}
    assert await manager.get_price("ETH") == 222.0

    manager._price_cache.clear()
    manager._get_oracle_price = AsyncMock(return_value=None)
    manager._providers = {"coingecko": provider("coingecko")}
    rate_error = APICallError("rate", api_name="coingecko", status_code=429)
    rate_error.status_code = 429
    rate_error.provider = "coingecko"
    manager._fetch_from_coingecko = AsyncMock(side_effect=rate_error)
    manager._failed_tokens = {f"OLD{i}" for i in range(101)}
    price = await manager.get_price("ETH")
    assert price is None
    assert len(manager._failed_tokens) < 103
    assert any(token.startswith("OLD") for token in manager._failed_tokens)


@pytest.mark.asyncio
async def test_get_price_uses_provider_tasks_and_reloads_tokens(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    manager._initialize = AsyncMock()
    manager._all_tokens_loaded = False
    manager._all_tokens_load_time = 0
    manager._get_onchain_price = AsyncMock(return_value=None)
    manager._get_oracle_price = AsyncMock(return_value=None)
    manager._load_all_tokens_async = AsyncMock(
        side_effect=lambda: manager._token_mappings.update(
            {
                "ETH": TokenMapping(
                    symbol="ETH",
                    name="Ether",
                    api_ids={"coingecko": "ethereum", "binance": "ETHUSDT"},
                )
            }
        )
    )
    manager._providers = {
        "coingecko": provider("coingecko"),
        "binance": provider("binance"),
    }
    manager._fetch_from_coingecko = AsyncMock(return_value=321.0)
    manager._fetch_from_binance = AsyncMock(return_value=111.0)

    price = await manager.get_price("ETH")

    assert price in {321.0, 111.0}
    manager._load_all_tokens_async.assert_awaited_once()
    assert (
        manager._fetch_from_coingecko.await_count
        + manager._fetch_from_binance.await_count
        >= 1
    )


@pytest.mark.asyncio
async def test_provider_fetchers_and_make_request(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    cg = provider("coingecko", base_url="https://cg")
    bn = provider("binance", base_url="https://bn")
    es = provider("etherscan", base_url="https://es")
    es.api_key = "k"
    manager._providers = {"coingecko": cg, "binance": bn, "etherscan": es}
    manager._token_mappings = {
        "ETH": TokenMapping(
            symbol="ETH",
            name="Ether",
            api_ids={"coingecko": "ethereum", "binance": "ETHUSDT"},
        )
    }

    manager._make_request = AsyncMock(return_value={"ethereum": {"usd": 2000}})
    assert await manager._fetch_from_coingecko("ETH") == 2000.0

    manager._make_request = AsyncMock(side_effect=RuntimeError("429 rate limit"))
    with pytest.raises(RuntimeError):
        await manager._fetch_from_coingecko("ETH", "ethereum")
    assert manager._is_provider_backed_off("coingecko") is True

    manager._make_request = AsyncMock(return_value={"price": "3000.5"})
    assert await manager._fetch_from_binance("ETH") == 3000.5
    assert await manager._fetch_from_binance("BAD$") is None

    manager._make_request = AsyncMock(side_effect=RuntimeError("429 rate limit"))
    with pytest.raises(RuntimeError):
        await manager._fetch_from_binance("ETH", "ETHUSDT")
    assert manager._is_provider_backed_off("binance") is True

    manager._make_request = AsyncMock(return_value={"result": {"ethusd": "2500"}})
    assert await manager._fetch_from_etherscan("ETH") == 2500.0
    assert await manager._fetch_from_etherscan("UNI") is None

    manager._session = DummySession(
        [
            DummyResponse(200, {"ok": True}),
            DummyResponse(400, {}),
            DummyResponse(500, {}),
        ]
    )
    assert await ExternalAPIManager._make_request(manager, "u", "coingecko") == {
        "ok": True
    }
    assert (
        await ExternalAPIManager._make_request(
            manager, "u", "binance", params={"symbol": "BAD"}
        )
        is None
    )
    with pytest.raises(TypeError):
        await ExternalAPIManager._make_request(manager, "u", "coingecko")

    class ErrorSession:
        def get(self, *args, **kwargs):
            raise aiohttp.ClientError("net")

    manager._session = ErrorSession()
    with pytest.raises(TypeError):
        await ExternalAPIManager._make_request(manager, "u", "coingecko")


@pytest.mark.asyncio
async def test_close_health_cache_and_backoff_helpers():
    manager = ExternalAPIManager()
    reset_manager(manager)
    task = DummyTask()
    manager._background_tasks = {task}
    manager._session = DummySession()
    p = provider("binance")
    p.rate_tracker.record_request(False)
    manager._providers = {"binance": p}
    manager._failed_tokens = {"A", "B"}
    manager._provider_backoff = {"binance": time.time() + 30, "old": time.time() - 1}
    manager._price_cache["ETH"] = 1.0
    manager._token_mappings["ETH"] = TokenMapping(symbol="ETH", name="Ether")

    status = manager.get_provider_health_status()
    stats = manager.get_cache_stats()
    assert status["binance"]["requests_made"] >= 1
    assert stats["price_cache_size"] == 1
    assert "binance" in stats["provider_backoff"]
    assert manager._is_provider_backed_off("binance") is True

    manager.reset_failed_tokens()
    assert manager._failed_tokens == set()
    assert manager._provider_backoff == {}

    await manager.close()
    assert manager._background_tasks == set()
    assert manager._session is None


@pytest.mark.asyncio
async def test_oracle_and_onchain_helpers(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    web3 = FakeWeb3()
    monkeypatch.setattr(
        api_module.Web3ConnectionFactory,
        "create_connection",
        AsyncMock(return_value=web3),
    )

    oracle_price = await manager._get_oracle_price("WETH")
    assert oracle_price == 2500.0
    assert manager._normalize_oracle_symbol("weth") == "ETH"

    class FakeRegistry:
        def get_token_address(self, symbol, chain_id):
            mapping = {"WETH": "0xtoken", "USDC": "0xstable", "ETH": "0xtoken"}
            return mapping.get(symbol)

    monkeypatch.setitem(
        __import__("sys").modules,
        "on1builder.integrations.abi_registry",
        SimpleNamespace(ABIRegistry=lambda: FakeRegistry()),
    )

    onchain_price = await manager._get_onchain_price("ETH")
    assert onchain_price == 5.0

    supply = await manager._get_onchain_supply("ETH")
    assert supply == 5.0

    pair = await manager._get_uniswap_v2_pair(web3, "0xa", "0xb")
    reserves = await manager._get_pair_reserves(
        web3, "0x0000000000000000000000000000000000000001"
    )
    token0 = await manager._get_pair_token(
        web3, "0x0000000000000000000000000000000000000001", 0
    )
    assert pair == "0x0000000000000000000000000000000000000001"
    assert reserves == (200, 1000)
    assert token0 == "0xtoken"


@pytest.mark.asyncio
async def test_market_sentiment_volatility_volume_cap_and_metadata(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    manager._initialize = AsyncMock()
    manager._providers = {
        "coingecko": provider("coingecko"),
        "binance": provider("binance"),
    }

    manager._get_coingecko_sentiment = AsyncMock(return_value=0.2)
    manager._get_social_sentiment = AsyncMock(return_value=0.4)
    manager._get_momentum_sentiment = AsyncMock(return_value=0.6)
    assert await manager.get_market_sentiment("ETH") == pytest.approx(0.4)

    manager._get_historical_prices = AsyncMock(return_value=[100, 110, 121])
    assert await manager.get_volatility_index("ETH") is not None
    manager._get_historical_prices = AsyncMock(side_effect=RuntimeError("no data"))
    assert await manager.get_volatility_index("USDC") is None

    manager._get_coingecko_volume = AsyncMock(return_value=1000.0)
    manager._get_binance_volume = AsyncMock(return_value=2000.0)
    assert await manager.get_trading_volume_24h("ETH") == 1000.0
    manager._get_coingecko_volume = AsyncMock(return_value=None)
    assert await manager.get_trading_volume_24h("ETH") == 2000.0

    manager.get_price = AsyncMock(return_value=2.5)
    manager._get_onchain_supply = AsyncMock(return_value=100)
    assert await manager.get_market_cap("ETH") == 250.0
    manager._get_onchain_supply = AsyncMock(return_value=None)
    manager._get_coingecko_market_cap = AsyncMock(return_value=999.0)
    assert await manager.get_market_cap("ETH") == 999.0

    data = await manager.get_comprehensive_market_data("eth")
    assert data["symbol"] == "ETH"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_coingecko_helpers_social_sentiment_and_history(monkeypatch):
    manager = ExternalAPIManager()
    reset_manager(manager)
    manager._providers = {
        "coingecko": provider("coingecko", base_url="https://cg"),
        "binance": provider("binance", base_url="https://bn"),
    }
    manager._session = DummySession(
        [
            DummyResponse(200, {"sentiment_votes_up_percentage": 75}),
            DummyResponse(
                200,
                {
                    "market_data": {
                        "total_volume": {"usd": 1234},
                        "market_cap": {"usd": 5678},
                        "circulating_supply": 42,
                    }
                },
            ),
            DummyResponse(200, {"market_data": {"market_cap": {"usd": 5678}}}),
            DummyResponse(200, {"market_data": {"circulating_supply": 42}}),
            DummyResponse(200, {"quoteVolume": "7654"}),
        ]
    )

    assert await manager._get_coingecko_sentiment("ETH") == 0.5
    assert await manager._get_coingecko_volume("ETH") == 1234.0
    assert await manager._get_coingecko_market_cap("ETH") == 5678.0
    assert await manager._get_coingecko_supply("ETH") == 42.0
    assert await manager._get_binance_volume("ETH") == 7654.0

    manager._get_reddit_sentiment = AsyncMock(return_value=0.3)
    manager._get_twitter_sentiment = AsyncMock(return_value=0.1)
    manager._get_momentum_sentiment = AsyncMock(return_value=0.2)
    manager._get_community_activity_sentiment = AsyncMock(return_value=0.0)
    assert await manager._get_social_sentiment("ETH") == pytest.approx(0.15)
    assert manager._get_heuristic_sentiment("BTC") == 0.2
    assert manager._get_heuristic_sentiment("UNI") == 0.1
    assert manager._get_heuristic_sentiment("USDC") == 0.0
    assert manager._get_heuristic_sentiment("XYZ") == -0.1
    assert manager._get_coingecko_id("WETH") == "ethereum"

    manager._get_historical_prices = ExternalAPIManager._get_historical_prices.__get__(
        manager, ExternalAPIManager
    )
    manager._get_reddit_sentiment = ExternalAPIManager._get_reddit_sentiment.__get__(
        manager, ExternalAPIManager
    )
    manager._get_twitter_sentiment = ExternalAPIManager._get_twitter_sentiment.__get__(
        manager, ExternalAPIManager
    )
    manager._get_momentum_sentiment = (
        ExternalAPIManager._get_momentum_sentiment.__get__(manager, ExternalAPIManager)
    )
    manager._get_community_activity_sentiment = (
        ExternalAPIManager._get_community_activity_sentiment.__get__(
            manager, ExternalAPIManager
        )
    )
    monkeypatch.setattr(
        api_module.aiohttp,
        "ClientSession",
        lambda: DummySession([DummyResponse(200, {"prices": [[1, 100], [2, 110]]})]),
    )
    assert await manager._get_historical_prices("ETH", days=2) == [100, 110]
    monkeypatch.setattr(
        api_module.aiohttp,
        "ClientSession",
        lambda: DummySession(
            [
                DummyResponse(
                    200,
                    {
                        "community_data": {
                            "reddit_subscribers": 200000,
                            "reddit_average_posts_48h": 20,
                        }
                    },
                )
            ]
        ),
    )
    assert await manager._get_reddit_sentiment("ETH") == 0.3
    monkeypatch.setattr(
        api_module.aiohttp,
        "ClientSession",
        lambda: DummySession(
            [
                DummyResponse(
                    200,
                    {
                        "developer_data": {
                            "commit_count_4_weeks": 60,
                            "contributors": 20,
                        }
                    },
                )
            ]
        ),
    )
    assert await manager._get_community_activity_sentiment("ETH") == 0.25
    assert await manager._get_twitter_sentiment("ETH") == 0.15
    manager._get_historical_prices = AsyncMock(return_value=[100, 130])
    assert await manager._get_momentum_sentiment("ETH") == 0.5
    manager._get_historical_prices = AsyncMock(side_effect=RuntimeError("boom"))
    assert await manager._get_momentum_sentiment("ETH") is None

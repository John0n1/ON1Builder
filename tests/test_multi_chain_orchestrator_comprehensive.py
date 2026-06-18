from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.core import multi_chain_orchestrator as orch_module
from on1builder.core.multi_chain_orchestrator import MultiChainOrchestrator


class AwaitableValue:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        async def _coro():
            return self.value

        return _coro().__await__()


class Worker:
    def __init__(self, chain_id, price):
        self.chain_id = chain_id
        self.web3 = SimpleNamespace(
            eth=SimpleNamespace(
                chain_id=AwaitableValue(chain_id), gas_price=AwaitableValue(30 * 10**9)
            ),
            to_wei=lambda amount, unit: int(Decimal(amount) * Decimal(10**18)),
        )
        self.market_feed = SimpleNamespace(
            get_price=AsyncMock(return_value=Decimal(price))
        )
        self.tx_scanner = SimpleNamespace(monitored_tokens=["ETH", "USDC"])
        self.tx_manager = SimpleNamespace(
            execute_swap=AsyncMock(
                return_value={
                    "success": True,
                    "amount_out_usd": 105,
                    "tx_hash": "0xabc",
                }
            )
        )


class BalanceManager:
    def __init__(self, balances):
        self.balances = balances

    async def get_balance(self, token):
        return self.balances.get(token, Decimal("0"))

    def get_balance_aware_investment_limit(self):
        return Decimal("500")

    def get_total_balance_usd(self):
        return sum(self.balances.values())

    async def update_balance(self):
        return None


@pytest.fixture(autouse=True)
def stub_settings(monkeypatch):
    monkeypatch.setattr(
        orch_module,
        "settings",
        SimpleNamespace(
            wallet_address="0xabc",
            wallet_addresses={1: "0xabc", 137: "0xabc"},
            min_profit_percentage=Decimal("0.1"),
            arbitrage_scan_interval=1,
        ),
    )


@pytest.mark.asyncio
async def test_start_stop_and_find_cross_chain_arbitrage(monkeypatch):
    workers = [Worker(1, "2000"), Worker(137, "2100")]
    orch = MultiChainOrchestrator(workers)
    monkeypatch.setattr(
        orch_module, "create_web3_instance", AsyncMock(return_value="web3")
    )
    monkeypatch.setattr(
        orch_module,
        "BalanceManager",
        lambda web3, address: BalanceManager(
            {"USDC": Decimal("1000"), "ETH": Decimal("2")}
        ),
    )

    class FakeTask:
        def __init__(self, coro):
            self.coro = coro

        def cancel(self):
            self.coro.close()

        def done(self):
            return False

        def __await__(self):
            self.coro.close()
            if False:
                yield None
            return None

    monkeypatch.setattr(orch_module.asyncio, "create_task", lambda coro: FakeTask(coro))
    monkeypatch.setattr(orch_module.asyncio, "gather", AsyncMock(return_value=[]))
    await orch.start()
    assert orch.is_running is True
    assert len(orch.balance_managers) == 2

    opportunities = await orch._find_cross_chain_arbitrage()
    assert opportunities

    await orch.stop()
    assert orch.is_running is False


def test_cooldown_and_spread_scoring_helpers(monkeypatch):
    orch = MultiChainOrchestrator([Worker(1, "2000"), Worker(137, "2100")])
    monkeypatch.setattr(
        orch_module.asyncio,
        "get_running_loop",
        lambda: SimpleNamespace(time=lambda: 10),
    )
    orch._set_cooldown("ETH")
    assert orch._is_on_cooldown("ETH") is True

    opps = orch._analyze_price_spreads(
        "ETH",
        {
            1: {
                "price": Decimal("2000"),
                "gas_cost_usd": Decimal("1"),
                "liquidity_score": Decimal("0.8"),
            },
            137: {
                "price": Decimal("2100"),
                "gas_cost_usd": Decimal("1"),
                "liquidity_score": Decimal("0.7"),
            },
        },
    )
    assert opps


@pytest.mark.asyncio
async def test_execute_cross_chain_arbitrage_and_profit_helpers():
    orch = MultiChainOrchestrator([Worker(1, "2000"), Worker(137, "2100")])
    orch.balance_managers = {
        1: BalanceManager({"USDC": Decimal("1000")}),
        137: BalanceManager({"ETH": Decimal("2")}),
    }
    orch._notification_service = SimpleNamespace(send_alert=AsyncMock())
    orch._calculate_optimal_trade_size = AsyncMock(return_value=Decimal("100"))
    orch._get_optimal_gas_price = AsyncMock(side_effect=[1, 1])
    orch._calculate_actual_profit = AsyncMock(return_value=Decimal("5"))

    opportunity = {
        "token_symbol": "ETH",
        "buy_on_chain": 1,
        "sell_on_chain": 137,
        "buy_price": Decimal("2000"),
        "sell_price": Decimal("2100"),
        "expected_profit_usd": Decimal("5"),
        "estimated_gas_cost": Decimal("1"),
    }
    await orch.execute_cross_chain_arbitrage(opportunity)
    orch._notification_service.send_alert.assert_awaited_once()

    assert await MultiChainOrchestrator._calculate_actual_profit(
        orch,
        {"success": True, "amount_out_usd": 105},
        {"success": True, "amount_out_usd": 110},
        Decimal("100"),
        {"estimated_gas_cost": 1, "expected_profit_usd": 12},
    ) == Decimal("9")
    assert await MultiChainOrchestrator._calculate_actual_profit(
        orch,
        Exception("x"),
        {"success": True},
        Decimal("100"),
        {"estimated_gas_cost": 4},
    ) == Decimal("-2.0")
    assert await MultiChainOrchestrator._calculate_actual_profit(
        orch, Exception("x"), Exception("y"), Decimal("100"), {"estimated_gas_cost": 4}
    ) == Decimal("-4")
    assert orch._extract_amount_from_result({"amount_out_usd": 3}) == Decimal("3")
    assert (
        orch._extract_amount_from_result(
            {
                "receipt": {
                    "logs": [
                        {
                            "topics": [
                                SimpleNamespace(
                                    hex=lambda: "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
                                )
                            ],
                            "data": "0x" + "0" * 63 + "a",
                        }
                    ]
                }
            }
        )
        is not None
    )


@pytest.mark.asyncio
async def test_liquidity_gas_balance_analysis_and_reporting(monkeypatch):
    orch = MultiChainOrchestrator([Worker(1, "2000"), Worker(137, "2100")])
    worker = orch.workers[1]
    orch._get_token_address = AsyncMock(side_effect=["token", "WETH", "USDC"])
    orch._query_pool_liquidity = AsyncMock(
        side_effect=[Decimal("500000"), Decimal("0")]
    )
    assert await orch._estimate_liquidity(worker, "ETH") > 0
    original_web3 = worker.web3
    worker.web3 = None
    assert await orch._estimate_liquidity(worker, "ETH") == 0.3
    worker.web3 = original_web3

    orch._get_current_eth_price = AsyncMock(return_value=Decimal("3000"))
    assert await orch._estimate_arbitrage_gas_cost(10**9) > 0
    orch._gas_tracker = {
        1: [
            Decimal("10"),
            Decimal("20"),
            Decimal("30"),
            Decimal("40"),
            Decimal("50"),
            Decimal("60"),
        ]
    }
    assert await orch._get_optimal_gas_price(worker) > 0

    orch.balance_managers = {
        1: BalanceManager({"USDC": Decimal("900")}),
        137: BalanceManager({"ETH": Decimal("100")}),
    }
    orch._notification_service = SimpleNamespace(send_alert=AsyncMock())
    await orch._analyze_balance_distribution()
    orch._notification_service.send_alert.assert_awaited_once()

    orch._opportunity_history = [
        {
            "timestamp": datetime.now(),
            "token": "ETH",
            "actual_profit": 1,
            "execution_time": 1.5,
        }
        for _ in range(10)
    ]
    await orch._generate_opportunity_analysis()
    assert orch._notification_service.send_alert.await_count >= 2

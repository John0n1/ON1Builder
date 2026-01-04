"""Behavior-heavy tests that assert end-to-end intentions rather than syntax."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.engines.strategy_executor import StrategyExecutor
from on1builder.monitoring.txpool_scanner import TxPoolScanner
from on1builder.utils.profit_calculator import ProfitCalculator


class DummyBalanceManager:
    def __init__(self, summary):
        self._summary = summary
        self.recorded = []

    async def get_balance_summary(self):
        return self._summary

    async def calculate_optimal_gas_price(self, _expected_profit):
        return 7, True

    async def record_profit(self, profit_amount, strategy_name, *_, **__):
        self.recorded.append((profit_amount, strategy_name))


class DummyTxManager:
    async def execute_arbitrage(self, opportunity):
        return {"success": True, "profit_eth": opportunity.get("expected_profit_eth", 0), "gas_used": 120_000}

    async def execute_front_run(self, opportunity):
        return {"success": True, "profit_eth": opportunity.get("estimated_profit_eth", 0.0), "gas_used": 150_000}

    async def execute_back_run(self, opportunity):
        return {"success": True, "profit_eth": 0.05, "gas_used": 90_000}

    async def execute_sandwich(self, opportunity):
        return {"success": False, "profit_eth": 0.0, "gas_used": 200_000}

    async def execute_flashloan_arbitrage(self, opportunity):
        return {"success": True, "profit_eth": 0.2, "gas_used": 180_000}


class DummyWeb3:
    def __init__(self):
        self.eth = SimpleNamespace(chain_id=1)

    def from_wei(self, value, unit):
        if unit == "ether":
            return Decimal(value) / Decimal(10**18)
        return value


class DummyExecutor:
    def __init__(self):
        self.executed = []

    async def execute_opportunity(self, opportunity):
        self.executed.append(opportunity)
        return {"success": True, "handled": True}


class DummyContracts:
    def __init__(self):
        self.uniswap_v2_router = {"1": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"}
        self.uniswap_v3_router = {}
        self.sushiswap_router = {}
        self.aave_v3_pool = {}
        self.simple_flashloan_contract = {}


@pytest.mark.asyncio
async def test_profit_calculator_tracks_net_profit_and_strategy_intent(monkeypatch):
    """Ensure profit analysis reflects inflow/outflow, gas, and strategy signals."""
    calculator = ProfitCalculator(AsyncMock(), SimpleNamespace(wallet_address="0xabc"))
    # Avoid hitting live pricing
    monkeypatch.setattr(calculator, "_convert_eth_to_usd", AsyncMock(return_value=Decimal("20")))
    movements = [
        {
            "type": "transfer",
            "token_symbol": "ETH",
            "amount": 0.3,
            "amount_usd": 60.0,
            "to_address": "0xabc",
            "from_address": "0x123",
        },
        {
            "type": "transfer",
            "token_symbol": "ETH",
            "amount": 0.1,
            "amount_usd": 20.0,
            "to_address": "0x999",
            "from_address": "0xabc",
        },
        {"type": "flash_loan", "protocol_address": "0xflash"},
    ]

    analysis = await calculator._analyze_profit_by_strategy(
        movements, gas_cost=Decimal("0.01"), strategy_type="flash_loan"
    )

    assert analysis["total_inflow_usd"] == 60.0
    assert analysis["total_outflow_usd"] == 20.0
    assert analysis["gross_profit_usd"] == 40.0
    # gas_cost_usd mocked to 20, so net profit should reflect business intent (cover gas)
    assert analysis["net_profit_usd"] == 20.0
    assert analysis["net_token_changes"]["ETH"] == pytest.approx(0.2)
    assert analysis["strategy_analysis"]["flash_loan_detected"] is True


@pytest.mark.asyncio
async def test_strategy_executor_respects_balance_tiers_and_enhances_opportunities(monkeypatch, tmp_path):
    """Validate strategy selection honors balance tiers and enhances opportunities with limits."""
    balance_summary = {
        "balance": 2.0,
        "balance_tier": "medium",
        "wallet_address": "0xabc",
        "max_investment": 1.0,
        "profit_threshold": 0.05,
        "flashloan_recommended": False,
        "emergency_mode": False,
    }
    balance_manager = DummyBalanceManager(balance_summary)
    tx_manager = DummyTxManager()
    executor = StrategyExecutor(tx_manager, balance_manager)
    # Make selection deterministic
    executor._exploration_rate = 0.0
    executor._weights["front_run"] = [3.0]
    executor._weights["arbitrage"] = [0.1]

    opportunity = {"expected_profit_eth": 0.4, "investment_amount": 2.0}
    strategy_func, chosen = await executor._select_strategy(opportunity)
    assert chosen == "front_run"
    assert strategy_func is not None

    enhanced = await executor._enhance_opportunity_with_balance(opportunity)
    assert enhanced["investment_amount"] == 1.0  # capped to max_investment
    assert enhanced["amount_limited"] is True
    assert enhanced["min_profit_threshold"] == balance_summary["profit_threshold"]
    assert "optimal_gas_price" in enhanced and enhanced["gas_viable"] is True


def test_strategy_executor_updates_weights_with_context():
    """Weight updates should reward profitable executions with contextual signals."""
    balance_manager = DummyBalanceManager(
        {
            "balance": 5.0,
            "balance_tier": "medium",
            "wallet_address": "0xabc",
            "max_investment": 2.0,
            "profit_threshold": 0.01,
            "flashloan_recommended": False,
            "emergency_mode": False,
        }
    )
    executor = StrategyExecutor(DummyTxManager(), balance_manager)
    executor._weights["arbitrage"] = [1.0]

    opportunity = {"expected_profit_eth": 0.2, "balance_tier": "medium", "gas_used": 110_000}
    executor._update_weights_ml("arbitrage", success=True, profit=0.3, opportunity=opportunity)

    assert executor._weights["arbitrage"][0] > 1.0


@pytest.mark.asyncio
async def test_txpool_scanner_identifies_mev_relevance_and_opportunities(monkeypatch):
    """End-to-end transaction analysis should flag MEV relevance and produce opportunities."""
    stub_settings = SimpleNamespace(
        contracts=DummyContracts(),
        chains=[1],
        websocket_urls={1: "ws://dummy"},
        connection_retry_delay=0.1,
        heartbeat_interval=1,
    )
    monkeypatch.setattr("on1builder.monitoring.txpool_scanner.settings", stub_settings)
    monkeypatch.setattr(
        "on1builder.monitoring.txpool_scanner.ABIRegistry",
        lambda: SimpleNamespace(get_monitored_tokens=lambda chain_id: {"ETH": "0xtoken"}),
    )

    scanner = TxPoolScanner(DummyWeb3(), DummyExecutor(), chain_id=1)
    tx = {
        "hash": bytes.fromhex("11" * 32),
        "from": "0xdead",
        "to": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
        "value": 6 * 10**18,
        "gasPrice": 60 * 10**9,
        "gas": 21000,
        "input": bytes.fromhex("38ed1739"),
    }

    analysis = scanner._analyze_transaction_comprehensive(tx)
    assert analysis["target_dex"] == "uniswap_v2"
    assert scanner._is_relevant_for_mev(analysis) is True
    # Priority should include value, gas, and dex bonuses
    assert analysis["priority_score"] == pytest.approx(0.65, rel=0.05)

    opportunities = await scanner._analyze_for_opportunities(analysis)
    # With a sizable trade into a DEX, we should surface at least front/back run opportunities
    assert any(o["strategy_type"] == "front_run" for o in opportunities)
    assert any(o["strategy_type"] == "back_run" for o in opportunities)

"""Logic-focused tests for MultiChainOrchestrator without network side effects."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from on1builder.core.multi_chain_orchestrator import MultiChainOrchestrator


class DummyWeb3:
    def __init__(self, chain_id, gas_price=30 * 10**9):
        self._chain_id = chain_id
        self.eth = SimpleNamespace(chain_id=chain_id, gas_price=gas_price)

    async def to_wei(self, amount, unit):
        return int(Decimal(amount) * (10**18))


class DummyTxScanner:
    def __init__(self, tokens):
        self.monitored_tokens = tokens


class DummyMarketFeed:
    def __init__(self, price_map):
        self.price_map = price_map

    async def get_price(self, symbol):
        return self.price_map.get(symbol)


class DummyTxManager:
    async def execute_swap(self, *_, **__):
        return {"success": True, "amount_out_usd": 105}


class DummyWorker:
    def __init__(self, chain_id, price_map):
        self.chain_id = chain_id
        self.web3 = DummyWeb3(chain_id)
        self.tx_scanner = DummyTxScanner(tokens=["ETH", "USDC"])
        self.market_feed = DummyMarketFeed(price_map)
        self.tx_manager = DummyTxManager()


class DummyBalanceManager:
    def __init__(self, balance_map):
        self.balance_map = balance_map

    async def get_balance(self, token):
        return self.balance_map.get(token, Decimal("0"))

    def get_balance_aware_investment_limit(self):
        return Decimal("500")

    def get_total_balance_usd(self):
        return sum(self.balance_map.values())

    async def update_balance(self):
        return None


@pytest.fixture(autouse=True)
def stub_settings(monkeypatch):
    stub = SimpleNamespace(
        wallet_address="0xabc",
        min_profit_percentage=Decimal("0.5"),
        arbitrage_scan_interval=1,
    )
    monkeypatch.setattr("on1builder.core.multi_chain_orchestrator.settings", stub)
    return stub


def test_common_tokens_detected_across_workers():
    workers = [
        DummyWorker(1, {"ETH": Decimal("2000")}),
        DummyWorker(137, {"ETH": Decimal("2100")}),
    ]
    orch = MultiChainOrchestrator(workers)
    common = orch._get_common_tokens()
    assert "ETH" in common


@pytest.mark.asyncio
async def test_analyze_price_spreads_filters_by_profit(monkeypatch):
    workers = [
        DummyWorker(1, {"ETH": Decimal("2000")}),
        DummyWorker(137, {"ETH": Decimal("2100")}),
    ]
    orch = MultiChainOrchestrator(workers)
    price_data = {
        1: {"price": Decimal("2000"), "gas_cost_usd": Decimal("1"), "liquidity_score": Decimal("0.8")},
        137: {"price": Decimal("2100"), "gas_cost_usd": Decimal("1"), "liquidity_score": Decimal("0.8")},
    }
    opps = orch._analyze_price_spreads("ETH", price_data)
    assert opps, "Should surface arbitrage when spread exceeds gas + min profit"
    assert all(o["estimated_gas_cost"] > 0 for o in opps)


@pytest.mark.asyncio
async def test_optimal_trade_size_respects_limits(monkeypatch):
    workers = [
        DummyWorker(1, {"ETH": Decimal("2000")}),
        DummyWorker(137, {"ETH": Decimal("2100")}),
    ]
    orch = MultiChainOrchestrator(workers)
    buy_bm = DummyBalanceManager({"USDC": Decimal("800")})
    sell_bm = DummyBalanceManager({"ETH": Decimal("2")})
    opportunity = {"liquidity_score": Decimal("0.5"), "score": 0.6, "token_symbol": "ETH"}
    size = await orch._calculate_optimal_trade_size(opportunity, buy_bm, sell_bm)
    # Should not exceed 80% of buy balance and should scale by risk factor
    assert size <= Decimal("800") * Decimal("0.8")
    assert size >= Decimal("10")  # minimum trade size enforced

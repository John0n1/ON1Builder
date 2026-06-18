from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.engines import safety_guard as safety_module
from on1builder.engines.safety_guard import SafetyGuard


class AwaitableValue:
    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc

    def __await__(self):
        async def _coro():
            if self.exc:
                raise self.exc
            return self.value

        return _coro().__await__()


@pytest.fixture
def stub_settings(monkeypatch):
    settings = SimpleNamespace(
        allow_insufficient_funds_tests=False,
        default_gas_limit=21000,
        emergency_balance_threshold=0.01,
        low_balance_threshold=0.05,
        min_wallet_balance=0.1,
        max_gas_price_gwei=100,
    )
    monkeypatch.setattr(safety_module, "settings", settings)
    return settings


@pytest.fixture
def guard(stub_settings):
    web3 = MagicMock()
    web3.eth.gas_price = AwaitableValue(30 * 10**9)
    web3.eth.get_balance = AsyncMock(return_value=2 * 10**18)
    web3.from_wei = lambda value, unit: value / (10**18 if unit == "ether" else 10**9)
    notification = MagicMock(send_alert=AsyncMock(), send_message=MagicMock())
    balance_manager = MagicMock()
    balance_manager.get_balance = AsyncMock(return_value=Decimal("1.5"))
    return SafetyGuard(
        web3,
        balance_manager=balance_manager,
        chain_id=1,
        notification_service=notification,
    )


@pytest.mark.asyncio
async def test_check_transaction_short_circuits_when_circuit_broken(guard):
    guard._circuit_broken = True
    guard._circuit_break_reason = "too many failures"
    guard._circuit_break_time = time.time()
    ok, reason = await guard.check_transaction({})
    assert ok is False
    assert "too many failures" in reason


@pytest.mark.asyncio
async def test_balance_checks_cover_bypass_and_failure_paths(stub_settings, guard):
    stub_settings.allow_insufficient_funds_tests = True
    assert await guard._check_balance({}) == (
        True,
        "Balance check bypassed for testing.",
    )

    stub_settings.allow_insufficient_funds_tests = False
    guard._balance_manager = None
    ok, reason = await guard._check_balance({})
    assert ok is False and "missing" in reason.lower()

    guard._balance_manager = MagicMock(
        get_balance=AsyncMock(return_value=Decimal("0.005"))
    )
    ok, reason = await guard._check_balance(
        {"from": "0x1", "gasPrice": 50 * 10**9, "gas": 21_000, "value": 0}
    )
    assert ok is False and "Insufficient balance" in reason

    guard._balance_manager.get_balance = AsyncMock(return_value=Decimal("1.2"))
    ok, reason = await guard._check_balance(
        {"from": "0x1", "gasPrice": 50 * 10**9, "gas": 21_000_000, "value": 0}
    )
    assert ok is False and "Transaction too large" in reason

    guard._balance_manager.get_balance = AsyncMock(return_value=Decimal("2.0"))
    assert await guard._check_balance(
        {"from": "0x1", "gasPrice": 1, "gas": 21_000, "value": 0}
    ) == (True, "Sufficient balance with appropriate reserves.")
    assert guard._get_dynamic_reserve(0.001) == 0.005
    assert guard._get_dynamic_reserve(0.02) == 0.01
    assert guard._get_dynamic_reserve(1.0) == 0.1


@pytest.mark.asyncio
async def test_gas_price_limit_checks_cover_dynamic_static_and_eip1559(
    guard, stub_settings
):
    assert await guard._check_gas_price({}) == (
        True,
        "Gas price not specified, will be set by web3.",
    )

    ok, reason = await guard._check_gas_price({"gasPrice": 200 * 10**9})
    assert ok is False and "dynamic limit" in reason

    guard._web3.eth.gas_price = AwaitableValue(exc=RuntimeError("lookup failed"))
    ok, reason = await guard._check_gas_price(
        {"gasPrice": 50 * 10**9, "maxFeePerGas": 200 * 10**9}
    )
    assert ok is False and "maxFeePerGas" in reason

    ok, reason = await guard._check_gas_price({"gasPrice": 50 * 10**9})
    assert ok is True and "accepted limits" in reason


@pytest.mark.asyncio
async def test_gas_limit_duplicate_rate_profit_and_market_checks(guard):
    assert await guard._check_gas_limit({}) == (
        True,
        "Gas limit not specified, will be estimated.",
    )
    assert (await guard._check_gas_limit({"gas": 200_000, "data": "0x"}))[0] is False
    assert (await guard._check_gas_limit({"gas": 2_500_000, "data": "0x1234567890ab"}))[
        0
    ] is False
    assert (await guard._check_gas_limit({"gas": 10_000, "data": "0x1234567890ab"}))[
        0
    ] is False
    assert await guard._check_gas_limit({"gas": 50_000, "data": "0x1234567890ab"}) == (
        True,
        "Gas limit is reasonable for transaction type.",
    )

    tx = {"to": "0x1", "value": 0, "data": "0x", "gasPrice": 1}
    for _ in range(guard._duplicate_threshold):
        assert (await guard._check_duplicate_tx(tx))[0] is True
    assert (await guard._check_duplicate_tx(tx))[0] is False

    guard._gas_spent_last_hour = 0.04
    guard._hourly_gas_limit = 0.05
    ok, reason = await guard._check_rate_limits({"gasPrice": 10**14, "gas": 200000})
    assert ok is False and "Hourly gas limit exceeded" in reason

    guard._gas_spent_last_hour = 0
    guard._failed_tx_count = guard._failed_tx_threshold
    guard.trip_circuit_breaker = AsyncMock()
    ok, reason = await guard._check_rate_limits({"gasPrice": 1, "gas": 1})
    assert ok is False and "Circuit breaker tripped" in reason
    guard.trip_circuit_breaker.assert_awaited_once()

    ok, reason = await guard._check_profit_viability(
        {"gasPrice": 10**9, "gas": 100000, "expected_profit_eth": 0.00001}
    )
    assert ok is False and "too low" in reason
    assert await guard._check_profit_viability(
        {"gasPrice": 1, "gas": 1, "expected_profit_eth": 1}
    ) == (True, "Profit viability check passed.")

    guard._web3.eth.gas_price = AwaitableValue(400 * 10**9)
    ok, reason = await guard._check_market_conditions({"expected_profit_eth": 0.001})
    assert ok is False and "volatile" in reason
    guard._web3.eth.gas_price = AwaitableValue(exc=RuntimeError("bad market"))
    ok, reason = await guard._check_market_conditions({})
    assert ok is True and "skipped" in reason.lower()


def test_record_and_reset_helpers_and_stats(guard, monkeypatch):
    guard._record_failed_check("balance")
    guard.record_gas_spent(0.2)
    guard.record_transaction_result(False)
    guard.record_transaction_result(True)
    guard._last_gas_reset = time.time() - 4000
    guard._reset_hourly_gas_if_needed()
    assert guard._gas_spent_last_hour == 0.0

    guard._recent_tx_signatures = set(range(1002))
    guard._circuit_broken = True
    guard._circuit_break_reason = "x"
    guard._failed_tx_count = 3
    guard._auto_reset_circuit_breaker()
    assert guard._circuit_broken is False
    assert guard._failed_tx_count == 0

    guard._circuit_broken = True
    guard.reset_circuit_breaker()
    assert guard._circuit_broken is False

    stats = guard.get_safety_stats()
    perf = guard.get_performance_stats()
    assert "success_rate_percentage" in stats
    assert "check_distribution" in perf


@pytest.mark.asyncio
async def test_trip_circuit_breaker_and_auto_reset_property(guard, monkeypatch):
    await guard.trip_circuit_breaker("danger")
    assert guard._circuit_broken is True
    guard._notification_service.send_alert.assert_awaited_once()

    guard._circuit_break_time = time.time() - guard._auto_reset_delay - 1
    assert guard.is_circuit_broken is False


@pytest.mark.asyncio
async def test_check_transaction_runs_checks_and_handles_exceptions(guard):
    guard._reset_hourly_gas_if_needed = MagicMock()
    guard._check_balance = AsyncMock(return_value=(True, "ok"))
    guard._check_gas_price = AsyncMock(return_value=(True, "ok"))
    guard._check_gas_limit = AsyncMock(return_value=(True, "ok"))
    guard._check_duplicate_tx = AsyncMock(return_value=(True, "ok"))
    guard._check_rate_limits = AsyncMock(return_value=(True, "ok"))
    guard._check_profit_viability = AsyncMock(return_value=(True, "ok"))
    guard._check_market_conditions = AsyncMock(return_value=(True, "ok"))

    ok, reason = await guard.check_transaction({"gas": 1})
    assert ok is True and "passed" in reason

    guard._check_gas_limit = AsyncMock(side_effect=RuntimeError("boom"))
    ok, reason = await guard.check_transaction({"gas": 1})
    assert ok is False and "Safety check error" in reason

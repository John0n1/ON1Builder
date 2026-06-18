from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.utils.gas_optimizer import GasOptimizer


class AwaitableValue:
    def __init__(self, value=None, exc: Exception | None = None):
        self.value = value
        self.exc = exc

    def __await__(self):
        async def _coro():
            if self.exc:
                raise self.exc
            return self.value

        return _coro().__await__()


class SequenceAwaitable:
    def __init__(self, values):
        self.values = list(values)

    def __await__(self):
        async def _coro():
            value = self.values.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        return _coro().__await__()


class FakeWeb3:
    def __init__(self):
        self.eth = SimpleNamespace()
        self.eth.get_block = AsyncMock(
            return_value={"baseFeePerGas": 100, "transactions": []}
        )
        self.eth.get_transaction = AsyncMock(return_value={})
        self.eth.gas_price = AwaitableValue(200)

    def to_wei(self, value, unit):
        assert unit == "gwei"
        return int(value * 10**9)

    def from_wei(self, value, unit):
        assert unit == "gwei"
        return value / 10**9


@pytest.mark.asyncio
async def test_initialize_sets_eip1559_and_handles_failure(monkeypatch):
    web3 = FakeWeb3()
    optimizer = GasOptimizer(web3)
    optimizer._update_gas_metrics = AsyncMock()

    await optimizer.initialize()
    assert optimizer._is_eip1559_supported is True
    optimizer._update_gas_metrics.assert_awaited_once()

    broken = FakeWeb3()
    broken.eth.get_block = AsyncMock(side_effect=RuntimeError("boom"))
    failed_optimizer = GasOptimizer(broken)
    await failed_optimizer.initialize()
    assert failed_optimizer._is_eip1559_supported is False


@pytest.mark.asyncio
async def test_get_optimal_gas_params_selects_eip1559_or_legacy(monkeypatch):
    web3 = FakeWeb3()
    optimizer = GasOptimizer(web3)
    optimizer._last_update = datetime.now() - timedelta(seconds=31)
    optimizer._update_gas_metrics = AsyncMock()
    optimizer._get_eip1559_params = AsyncMock(return_value={"type": 2})
    optimizer._get_legacy_gas_params = AsyncMock(return_value={"type": 0})

    optimizer._is_eip1559_supported = True
    assert await optimizer.get_optimal_gas_params("high", 2) == {"type": 2}
    optimizer._update_gas_metrics.assert_awaited_once()

    optimizer._is_eip1559_supported = False
    assert await optimizer.get_optimal_gas_params("low", 1) == {"type": 0}


@pytest.mark.asyncio
async def test_get_eip1559_params_and_fallback(monkeypatch):
    web3 = FakeWeb3()
    optimizer = GasOptimizer(web3)
    optimizer._priority_fee_history = [
        (datetime.now(), 2_000_000_000),
        (datetime.now(), 4_000_000_000),
    ]
    optimizer._base_fee_history = [
        (datetime.now(), 100_000_000_000),
        (datetime.now(), 120_000_000_000),
    ]

    params = await optimizer._get_eip1559_params("high", 2)
    assert params["type"] == 2
    assert params["maxPriorityFeePerGas"] == 4_500_000_000
    assert params["maxFeePerGas"] > params["maxPriorityFeePerGas"]

    optimizer._get_legacy_gas_params = AsyncMock(
        return_value={"gasPrice": 123, "type": 0}
    )
    web3.eth.get_block = AsyncMock(side_effect=RuntimeError("bad block"))
    assert await optimizer._get_eip1559_params("normal", 1) == {
        "gasPrice": 123,
        "type": 0,
    }


@pytest.mark.asyncio
async def test_get_legacy_gas_params_and_fallback():
    web3 = FakeWeb3()
    web3.eth.gas_price = AwaitableValue(100)
    optimizer = GasOptimizer(web3)
    optimizer._gas_history = [(datetime.now(), value) for value in range(100, 200)]

    params = await optimizer._get_legacy_gas_params("urgent", 2)
    assert params["type"] == 0
    assert params["gasPrice"] >= 100

    web3.eth.gas_price = SequenceAwaitable([RuntimeError("fail"), 777])
    assert await optimizer._get_legacy_gas_params("normal", 1) == {
        "gasPrice": 777,
        "type": 0,
    }


def test_predict_base_fee_with_various_histories():
    optimizer = GasOptimizer(FakeWeb3())
    assert optimizer._predict_base_fee(1) == 0

    now = datetime.now()
    optimizer._base_fee_history = [(now, 100)]
    assert optimizer._predict_base_fee(2) == 100

    optimizer._base_fee_history = [
        (now - timedelta(minutes=i), 100 + i * 10) for i in range(10)
    ]
    prediction = optimizer._predict_base_fee(3)
    assert prediction >= 0
    assert prediction <= int(
        optimizer._base_fee_history[-1][1] * (optimizer.EIP1559_MAX_INCREASE_FACTOR**3)
    )


@pytest.mark.asyncio
async def test_update_gas_metrics_calculates_priority_and_trims_old_data(monkeypatch):
    web3 = FakeWeb3()
    web3.eth.gas_price = AwaitableValue(200)
    web3.eth.get_block = AsyncMock(
        return_value={"baseFeePerGas": 120, "transactions": ["a"]}
    )
    optimizer = GasOptimizer(web3)
    optimizer._is_eip1559_supported = True
    optimizer._calculate_priority_fee_estimate = AsyncMock(return_value=50)
    old_time = datetime.now() - timedelta(hours=3)
    optimizer._gas_history = [(old_time, 1)]
    optimizer._base_fee_history = [(old_time, 2)]
    optimizer._priority_fee_history = [(old_time, 3)]

    await optimizer._update_gas_metrics()

    assert len(optimizer._gas_history) == 1
    assert optimizer._gas_history[-1][1] == 200
    assert optimizer._base_fee_history[-1][1] == 120
    assert optimizer._priority_fee_history[-1][1] == 50


@pytest.mark.asyncio
async def test_calculate_priority_fee_estimate_paths():
    web3 = FakeWeb3()
    web3.eth.get_transaction = AsyncMock(
        side_effect=[
            {"maxPriorityFeePerGas": 3},
            {"gasPrice": 120},
            RuntimeError("skip"),
        ]
    )
    optimizer = GasOptimizer(web3)
    latest_block = {"transactions": ["a", "b", "c"]}

    fee = await optimizer._calculate_priority_fee_estimate(latest_block, 100, 150)
    assert fee == 11.5

    web3.eth.get_transaction = AsyncMock(side_effect=RuntimeError("boom"))
    assert (
        await optimizer._calculate_priority_fee_estimate(latest_block, 100, 150) == 50
    )


@pytest.mark.asyncio
async def test_estimate_transaction_cost_for_eip_and_legacy():
    optimizer = GasOptimizer(FakeWeb3())
    optimizer.get_optimal_gas_params = AsyncMock(
        side_effect=[{"type": 2, "maxFeePerGas": 100}, {"type": 0, "gasPrice": 50}]
    )

    assert await optimizer.estimate_transaction_cost(21_000) == Decimal(
        21_000 * 100
    ) / Decimal(10**18)
    assert await optimizer.estimate_transaction_cost(10, "low") == Decimal(
        500
    ) / Decimal(10**18)


@pytest.mark.asyncio
async def test_should_delay_transaction_and_error_path():
    optimizer = GasOptimizer(FakeWeb3())
    assert await optimizer.should_delay_transaction() == (False, None)

    now = datetime.now()
    optimizer._gas_history = [(now - timedelta(minutes=i), 100) for i in range(19)] + [
        (now, 220)
    ]
    optimizer._base_fee_history = [
        (now - timedelta(minutes=9 - i), fee)
        for i, fee in enumerate([200, 180, 160, 150, 140, 130, 120, 110, 100, 90])
    ]
    should_delay, wait_time = await optimizer.should_delay_transaction("normal")
    assert should_delay is True
    assert wait_time is not None and wait_time >= 300

    optimizer._gas_history = object()  # type: ignore[assignment]
    assert await optimizer.should_delay_transaction() == (False, None)


def test_get_gas_analytics_with_and_without_history():
    web3 = FakeWeb3()
    optimizer = GasOptimizer(web3)
    empty = optimizer.get_gas_analytics()
    assert empty["error"] == "No gas history available"

    now = datetime.now()
    optimizer._is_eip1559_supported = True
    optimizer._gas_history = [
        (now - timedelta(minutes=i), value * 10**9)
        for i, value in enumerate(range(10, 20), start=1)
    ]
    optimizer._base_fee_history = [(now, 12 * 10**9), (now, 14 * 10**9)]
    optimizer._priority_fee_history = [(now, 2 * 10**9), (now, 4 * 10**9)]
    analytics = optimizer.get_gas_analytics()

    assert analytics["gas_history_count"] == 10
    assert analytics["current_gas_price_gwei"] > 0
    assert analytics["avg_gas_price_gwei"] >= analytics["min_gas_price_gwei"]
    assert analytics["current_base_fee_gwei"] == 14.0
    assert analytics["avg_priority_fee_gwei"] == 3.0

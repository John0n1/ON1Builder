from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.utils import error_recovery as error_recovery_module
from on1builder.utils.custom_exceptions import (
    ConnectionError,
    InsufficientFundsError,
    StrategyExecutionError,
    TransactionError,
)
from on1builder.utils.error_recovery import (
    CircuitBreaker,
    ErrorRecoveryManager,
    RetryManager,
    get_error_recovery_manager,
    with_circuit_breaker,
    with_error_recovery,
    with_retry,
)


@pytest.mark.asyncio
async def test_circuit_breaker_opens_then_half_opens_and_closes():
    breaker = CircuitBreaker(
        failure_threshold=2, recovery_timeout=1, expected_exception=ValueError
    )
    attempts = {"count": 0}

    @breaker
    async def flaky():
        attempts["count"] += 1
        if attempts["count"] <= 2:
            raise ValueError("boom")
        return "ok"

    with pytest.raises(ValueError):
        await flaky()
    assert breaker.state == "CLOSED"
    with pytest.raises(ValueError):
        await flaky()
    assert breaker.state == "OPEN"

    with pytest.raises(StrategyExecutionError):
        await flaky()

    breaker.last_failure_time = datetime.now() - timedelta(seconds=2)
    result = await flaky()
    assert result == "ok"
    assert breaker.state == "CLOSED"
    assert breaker.failure_count == 0


def test_circuit_breaker_reset_timing_helpers():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
    assert breaker._should_attempt_reset() is True
    assert breaker._time_until_reset() == 0.0

    breaker.last_failure_time = datetime.now() - timedelta(seconds=3)
    assert breaker._should_attempt_reset() is False
    assert 0 < breaker._time_until_reset() <= 10


@pytest.mark.asyncio
async def test_retry_manager_retries_and_uses_backoff(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(
        error_recovery_module.asyncio,
        "sleep",
        AsyncMock(side_effect=lambda delay: sleeps.append(delay)),
    )

    retry = RetryManager(
        max_attempts=3, base_delay=2, max_delay=10, exponential_base=2, jitter=False
    )
    attempts = {"count": 0}

    @retry
    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("nope")
        return "done"

    assert await flaky() == "done"
    assert attempts["count"] == 3
    assert sleeps == [2, 4]
    assert retry._calculate_delay(3) == 10


@pytest.mark.asyncio
async def test_retry_manager_applies_jitter_and_raises_after_all_failures(monkeypatch):
    monkeypatch.setattr(error_recovery_module.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr("random.uniform", lambda a, b: 1.25)

    retry = RetryManager(
        max_attempts=3, base_delay=4, max_delay=20, exponential_base=2, jitter=True
    )

    @retry
    async def always_fails():
        raise TransactionError("bad tx")

    with pytest.raises(StrategyExecutionError) as exc:
        await always_fails()

    assert isinstance(exc.value.cause, TransactionError)
    assert retry._calculate_delay(0) == pytest.approx(5.0)
    assert retry._calculate_delay(1) == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_error_recovery_manager_handle_error_and_statistics(monkeypatch):
    manager = ErrorRecoveryManager()
    context = {"chain_id": 1}

    failing_strategy = AsyncMock(side_effect=RuntimeError("fail"))
    success_strategy = AsyncMock(return_value=True)
    manager.recovery_strategies[ConnectionError] = [failing_strategy, success_strategy]

    handled = await manager.handle_error(ConnectionError("rpc"), context, "worker")
    assert handled is True
    stats = manager.get_error_statistics()
    assert stats["error_counts"]["worker:ConnectionError"] == 1
    assert stats["total_errors"] == 1
    assert "worker:ConnectionError" in stats["last_errors"]

    manager.error_counts["worker:ConnectionError"] = 11
    manager.last_errors["worker:ConnectionError"] = datetime.now()
    assert manager._is_error_frequency_too_high("worker:ConnectionError") is True


@pytest.mark.asyncio
async def test_error_recovery_manager_connection_and_transaction_strategies(
    monkeypatch,
):
    manager = ErrorRecoveryManager()
    nonce_manager = MagicMock()
    nonce_manager.resync_nonce = AsyncMock()
    tx_manager = SimpleNamespace(
        _address="0xabc",
        _nonce_manager=nonce_manager,
        _gas_optimizer=SimpleNamespace(_web3="old"),
        _safety_guard=SimpleNamespace(_web3="old"),
        _web3="old",
    )
    new_web3 = object()

    monkeypatch.setattr(
        "on1builder.utils.web3_factory.Web3ConnectionFactory.create_connection",
        AsyncMock(return_value=new_web3),
    )
    monkeypatch.setattr(
        "on1builder.core.nonce_manager.NonceManager",
        lambda web3, address: ("nonce", web3, address),
    )

    context = {"chain_id": 5, "transaction_manager": tx_manager}
    assert await manager._reconnect_web3(ConnectionError("rpc"), context) is True
    assert tx_manager._web3 is new_web3
    assert tx_manager._gas_optimizer._web3 is new_web3
    assert tx_manager._safety_guard._web3 is new_web3
    assert tx_manager._nonce_manager == ("nonce", new_web3, "0xabc")
    assert context["retry"] is True

    tx_context = {"transaction_manager": SimpleNamespace(_nonce_manager=nonce_manager)}
    assert await manager._resync_nonce(TransactionError("tx"), tx_context) is True
    nonce_manager.resync_nonce.assert_awaited_once()

    gas_context = {"tx_params": {"gasPrice": 100, "gas": 200000}}
    assert (
        await manager._increase_gas_price(TransactionError("tx"), gas_context) is True
    )
    assert gas_context["retry_tx_params"]["gasPrice"] == 120
    assert await manager._reduce_gas_limit(TransactionError("tx"), gas_context) is True
    assert gas_context["retry_tx_params"]["gas"] == 180000


@pytest.mark.asyncio
async def test_error_recovery_manager_funds_strategies_and_missing_context():
    manager = ErrorRecoveryManager()
    context: dict[str, object] = {}

    assert await manager._switch_rpc_endpoint(ConnectionError("x"), context) is True
    assert await manager._reduce_connection_pool(ConnectionError("x"), context) is True

    assert (
        await manager._wait_for_funds(InsufficientFundsError("funds"), context) is False
    )
    assert context["trading_paused"] is True
    assert "pause_until" in context

    position_context = {"position_size_multiplier": 0.8}
    assert (
        await manager._reduce_position_size(
            InsufficientFundsError("funds"), position_context
        )
        is True
    )
    assert position_context["position_size_multiplier"] == 0.4

    pause_context: dict[str, object] = {}
    assert (
        await manager._pause_trading(InsufficientFundsError("funds"), pause_context)
        is True
    )
    assert pause_context["trading_paused"] is True

    assert await manager._resync_nonce(TransactionError("tx"), {}) is False
    assert await manager._increase_gas_price(TransactionError("tx"), {}) is False
    assert await manager._reduce_gas_limit(TransactionError("tx"), {}) is False


@pytest.mark.asyncio
async def test_with_error_recovery_decorator_retries_after_recovery(monkeypatch):
    manager = MagicMock()
    manager.handle_error = AsyncMock(return_value=True)
    monkeypatch.setattr(
        error_recovery_module, "get_error_recovery_manager", lambda: manager
    )

    attempts = {"count": 0}

    @with_error_recovery("engine")
    async def flaky(value):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("first")
        return value * 2

    assert await flaky(3) == 6
    manager.handle_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_with_error_recovery_reraises_when_unrecovered_or_retry_fails(
    monkeypatch,
):
    manager = MagicMock()
    manager.handle_error = AsyncMock(return_value=False)
    monkeypatch.setattr(
        error_recovery_module, "get_error_recovery_manager", lambda: manager
    )

    @with_error_recovery("engine")
    async def broken():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        await broken()

    manager.handle_error = AsyncMock(return_value=True)
    calls = {"count": 0}

    @with_error_recovery("engine")
    async def retry_fails():
        calls["count"] += 1
        raise RuntimeError(f"fail-{calls['count']}")

    with pytest.raises(RuntimeError, match="fail-2"):
        await retry_fails()


@pytest.mark.asyncio
async def test_convenience_decorators_and_singleton_getter(monkeypatch):
    assert isinstance(with_circuit_breaker(), CircuitBreaker)
    assert isinstance(with_retry(), RetryManager)
    assert get_error_recovery_manager() is error_recovery_module._error_recovery_manager

    manager = MagicMock()
    manager.handle_error = AsyncMock(return_value=True)
    monkeypatch.setattr(
        error_recovery_module, "get_error_recovery_manager", lambda: manager
    )

    @with_circuit_breaker(failure_threshold=1, expected_exception=ValueError)
    @with_retry(max_attempts=1)
    async def wrapped():
        return "ok"

    assert await wrapped() == "ok"

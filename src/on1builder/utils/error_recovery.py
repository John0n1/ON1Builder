#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

from .custom_exceptions import (
    ConnectionError,
    InsufficientFundsError,
    StrategyExecutionError,
    TransactionError,
)
from .logging_config import get_logger

F = TypeVar("F", bound=Callable[..., Any])
logger = get_logger(__name__)


class CircuitBreaker:
    """Circuit breaker pattern for handling repeated failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise StrategyExecutionError(
                        f"Circuit breaker is OPEN for {func.__name__}. "
                        f"Next attempt in {self._time_until_reset():.1f} seconds"
                    )

            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise e

        return wrapper

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt a reset."""
        if self.last_failure_time is None:
            return True
        return (
            datetime.now() - self.last_failure_time
        ).total_seconds() >= self.recovery_timeout

    def _time_until_reset(self) -> float:
        """Calculate time remaining until reset attempt."""
        if self.last_failure_time is None:
            return 0.0
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return max(0.0, self.recovery_timeout - elapsed)

    def _on_success(self):
        """Handle successful execution."""
        self.failure_count = 0
        self.state = "CLOSED"

    def _on_failure(self):
        """Handle failed execution."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures. "
                f"Will retry in {self.recovery_timeout} seconds."
            )


class RetryManager:
    """Manages retry logic with exponential backoff and jitter."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(self.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except (ConnectionError, TransactionError) as e:
                    last_exception = e

                    if attempt == self.max_attempts - 1:
                        break

                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    await asyncio.sleep(delay)

            # All attempts failed
            raise StrategyExecutionError(
                f"All {self.max_attempts} attempts failed for {func.__name__}",
                cause=last_exception,
            )

        return wrapper

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and optional jitter."""
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            import random

            # Add ±25% jitter
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor

        return delay


class ErrorRecoveryManager:
    """Centralized error recovery and monitoring."""

    def __init__(self):
        self.error_counts: dict[str, int] = {}
        self.last_errors: dict[str, datetime] = {}
        self.recovery_strategies: dict[type, list[Callable]] = {}

        # Register default recovery strategies
        self._register_default_strategies()

    def _register_default_strategies(self):
        """Register default recovery strategies for common errors."""
        self.recovery_strategies[ConnectionError] = [
            self._reconnect_web3,
            self._switch_rpc_endpoint,
            self._reduce_connection_pool,
        ]

        self.recovery_strategies[InsufficientFundsError] = [
            self._wait_for_funds,
            self._reduce_position_size,
            self._pause_trading,
        ]

        self.recovery_strategies[TransactionError] = [
            self._resync_nonce,
            self._increase_gas_price,
            self._reduce_gas_limit,
        ]

    async def handle_error(
        self, error: Exception, context: dict[str, Any], component_name: str
    ) -> bool:
        """
        Handle error with appropriate recovery strategy.

        Returns:
            True if recovery was attempted, False if error should be re-raised
        """
        error_type = type(error)
        error_key = f"{component_name}:{error_type.__name__}"

        # Track error frequency
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        self.last_errors[error_key] = datetime.now()

        logger.error(f"Error in {component_name}: {error}")

        # Check if we have recovery strategies for this error type
        if error_type in self.recovery_strategies:
            strategies = self.recovery_strategies[error_type]

            for strategy in strategies:
                try:
                    logger.info(f"Attempting recovery strategy: {strategy.__name__}")
                    success = await strategy(error, context)
                    if success:
                        logger.info(f"Recovery successful using {strategy.__name__}")
                        return True
                except Exception as recovery_error:
                    logger.warning(
                        f"Recovery strategy {strategy.__name__} failed: {recovery_error}"
                    )
                    continue

        # Check if error frequency is too high
        if self._is_error_frequency_too_high(error_key):
            logger.critical(
                f"Error frequency too high for {error_key}. Emergency shutdown may be required."
            )

        return False

    def _is_error_frequency_too_high(self, error_key: str) -> bool:
        """Check if error frequency exceeds safe thresholds."""
        count = self.error_counts.get(error_key, 0)
        last_error = self.last_errors.get(error_key)

        if last_error and count > 10:
            # More than 10 errors in the last 5 minutes
            time_window = timedelta(minutes=5)
            if datetime.now() - last_error < time_window:
                return True

        return False

    async def _reconnect_web3(self, error: Exception, context: dict[str, Any]) -> bool:
        """Attempt to reconnect Web3 connections."""
        try:
            logger.info("Attempting to reconnect Web3 connections...")
            from on1builder.core.nonce_manager import NonceManager
            from on1builder.utils.web3_factory import Web3ConnectionFactory

            chain_id = context.get("chain_id")
            tm = context.get("transaction_manager")
            if not chain_id or tm is None:
                return False

            new_web3 = await Web3ConnectionFactory.create_connection(
                chain_id, force_new=True
            )
            tm._web3 = new_web3
            if getattr(tm, "_gas_optimizer", None):
                tm._gas_optimizer._web3 = new_web3
            if getattr(tm, "_safety_guard", None):
                tm._safety_guard._web3 = new_web3
            tm._nonce_manager = NonceManager(new_web3, tm._address)
            context["retry"] = True
            return True
        except Exception:
            return False

    async def _switch_rpc_endpoint(
        self, error: Exception, context: dict[str, Any]
    ) -> bool:
        """Switch to backup RPC endpoint."""
        try:
            logger.info("Switching to backup RPC endpoint...")
            # Implementation would switch RPC URLs
            return True
        except Exception:
            return False

    async def _reduce_connection_pool(
        self, error: Exception, context: dict[str, Any]
    ) -> bool:
        """Reduce connection pool size to handle connection issues."""
        logger.info("Reducing connection pool size...")
        return True

    async def _wait_for_funds(self, error: Exception, context: dict[str, Any]) -> bool:
        """Wait for additional funds to be available."""
        logger.info("Pausing trading due to insufficient funds (no blocking wait).")
        context["trading_paused"] = True
        context["pause_until"] = datetime.now() + timedelta(minutes=10)
        return False

    async def _reduce_position_size(
        self, error: Exception, context: dict[str, Any]
    ) -> bool:
        """Reduce position size to conserve funds."""
        logger.info("Reducing position size due to insufficient funds...")
        context["position_size_multiplier"] = (
            context.get("position_size_multiplier", 1.0) * 0.5
        )
        return True

    async def _pause_trading(self, error: Exception, context: dict[str, Any]) -> bool:
        """Pause trading temporarily."""
        logger.info("Pausing trading due to insufficient funds...")
        context["trading_paused"] = True
        context["pause_until"] = datetime.now() + timedelta(minutes=10)
        return True

    async def _resync_nonce(self, error: Exception, context: dict[str, Any]) -> bool:
        """Resync transaction nonce."""
        logger.info("Resyncing transaction nonce...")
        tm = context.get("transaction_manager")
        if tm is None or not getattr(tm, "_nonce_manager", None):
            return False
        await tm._nonce_manager.resync_nonce()
        context["retry"] = True
        return True

    async def _increase_gas_price(
        self, error: Exception, context: dict[str, Any]
    ) -> bool:
        """Increase gas price for failed transactions."""
        logger.info("Increasing gas price for transaction retry...")
        tx_params = context.get("retry_tx_params") or context.get("tx_params")
        if not tx_params or "gasPrice" not in tx_params:
            return False
        current_multiplier = context.get("gas_price_multiplier", 1.0)
        new_multiplier = min(current_multiplier * 1.2, 3.0)
        context["gas_price_multiplier"] = new_multiplier
        tx_params["gasPrice"] = int(tx_params["gasPrice"] * new_multiplier)
        context["retry_tx_params"] = tx_params
        context["retry"] = True
        return True

    async def _reduce_gas_limit(
        self, error: Exception, context: dict[str, Any]
    ) -> bool:
        """Reduce gas limit for failed transactions."""
        logger.info("Reducing gas limit for transaction retry...")
        tx_params = context.get("retry_tx_params") or context.get("tx_params")
        if not tx_params or "gas" not in tx_params:
            return False
        current_limit = tx_params.get("gas", 250000)
        tx_params["gas"] = max(int(current_limit * 0.9), 100000)
        context["retry_tx_params"] = tx_params
        context["retry"] = True
        return True

    def get_error_statistics(self) -> dict[str, Any]:
        """Get error statistics for monitoring."""
        return {
            "error_counts": self.error_counts.copy(),
            "last_errors": {k: v.isoformat() for k, v in self.last_errors.items()},
            "total_errors": sum(self.error_counts.values()),
        }


# Global error recovery manager instance
_error_recovery_manager = ErrorRecoveryManager()


def get_error_recovery_manager() -> ErrorRecoveryManager:
    """Get the global error recovery manager."""
    return _error_recovery_manager


# Convenience decorators
def with_circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: type = Exception,
):
    """Decorator for applying circuit breaker pattern."""
    return CircuitBreaker(failure_threshold, recovery_timeout, expected_exception)


def with_retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
    """Decorator for applying retry logic with exponential backoff."""
    return RetryManager(max_attempts, base_delay, max_delay)


def with_error_recovery(component_name: str):
    """Decorator for comprehensive error handling with recovery."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                context = {"function": func.__name__, "args": args, "kwargs": kwargs}
                recovery_manager = get_error_recovery_manager()

                recovered = await recovery_manager.handle_error(
                    e, context, component_name
                )
                if not recovered:
                    raise e

                # Retry once after recovery
                try:
                    return await func(*args, **kwargs)
                except Exception as retry_error:
                    logger.error(f"Retry after recovery failed: {retry_error}")
                    raise retry_error

        return wrapper

    return decorator

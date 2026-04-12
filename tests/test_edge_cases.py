#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander
"""
Edge case tests for critical paths: balance management, validation,
transaction handling, and error recovery.
"""

import pytest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

from on1builder.core.balance_manager import BalanceManager
from on1builder.config.validation import ConfigValidator
from on1builder.utils.custom_exceptions import (
    InsufficientFundsError,
    ValidationError,
    ConfigurationError,
)
from on1builder.utils.constants import BALANCE_TIER_THRESHOLDS

# ---------------------------------------------------------------------------
# Balance Manager edge cases
# ---------------------------------------------------------------------------


class TestBalanceManagerEdgeCases:
    """Edge case tests for BalanceManager."""

    @pytest.fixture
    def mock_web3(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=0)
        web3.from_wei = Mock(
            side_effect=lambda wei, unit: Decimal(str(wei)) / Decimal("1e18")
        )
        return web3

    @pytest.fixture
    def manager(self, mock_web3):
        return BalanceManager(mock_web3, "0x1234567890123456789012345678901234567890")

    def test_zero_balance_tier(self, manager):
        """Zero balance should be classified as 'emergency'."""
        assert manager._determine_balance_tier(Decimal("0")) == "emergency"

    def test_negative_balance_tier(self, manager):
        """Negative balance should be classified as 'emergency'."""
        assert manager._determine_balance_tier(Decimal("-1")) == "emergency"
        assert manager._determine_balance_tier(Decimal("-0.001")) == "emergency"

    def test_very_small_positive_balance(self, manager):
        """Extremely small positive balance should be 'dust'."""
        assert manager._determine_balance_tier(Decimal("0.000001")) == "dust"

    def test_exact_threshold_values(self, manager):
        """Balance at exact tier thresholds should return that tier."""
        for tier, threshold in BALANCE_TIER_THRESHOLDS.items():
            result = manager._determine_balance_tier(threshold)
            assert (
                result == tier
            ), f"Balance {threshold} should be '{tier}', got '{result}'"

    def test_very_large_balance(self, manager):
        """Very large balance should be classified as 'whale'."""
        assert manager._determine_balance_tier(Decimal("10000")) == "whale"
        assert manager._determine_balance_tier(Decimal("999999")) == "whale"

    @pytest.mark.asyncio
    async def test_zero_balance_update(self, manager, mock_web3):
        """Updating balance when wallet has zero ETH should return zero."""
        mock_web3.eth.get_balance.return_value = 0
        balance = await manager.update_balance(force=True)
        assert balance == Decimal("0")

    @pytest.mark.asyncio
    async def test_profit_tracking_negative_value(self, manager):
        """Recording a negative profit (loss) should not be tracked (below threshold)."""
        await manager.record_profit(Decimal("-0.01"), "arbitrage")
        stats = manager.get_profit_stats()
        # Negative profit is below MIN_PROFIT_THRESHOLD so it's not tracked
        assert stats["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_profit_tracking_zero_value(self, manager):
        """Recording zero profit should not be tracked (below threshold)."""
        await manager.record_profit(Decimal("0"), "arbitrage")
        stats = manager.get_profit_stats()
        assert stats["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_profit_tracking_above_threshold(self, manager):
        """Recording profit above threshold should be tracked."""
        await manager.record_profit(Decimal("0.01"), "arbitrage")
        stats = manager.get_profit_stats()
        assert stats["total_trades"] == 1
        assert stats["total_profit_eth"] == Decimal("0.01")

    @pytest.mark.asyncio
    async def test_max_investment_zero_balance(self, manager):
        """Max investment with zero balance should be zero or very small."""
        manager.current_balance = Decimal("0")
        max_inv = await manager.get_max_investment_amount()
        assert max_inv >= Decimal("0")

    @pytest.mark.asyncio
    async def test_max_investment_dust_balance(self, manager):
        """Max investment with dust balance should be conservative."""
        manager.current_balance = Decimal("0.005")
        max_inv = await manager.get_max_investment_amount()
        assert max_inv <= manager.current_balance


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


class TestValidationEdgeCases:
    """Edge case tests for config validation."""

    def test_zero_address_is_valid_hex(self):
        """Zero address (0x000...0) is valid hex and passes format validation."""
        result = ConfigValidator.validate_wallet_address(
            "0x0000000000000000000000000000000000000000"
        )
        assert result == "0x0000000000000000000000000000000000000000"

    def test_address_with_leading_whitespace(self):
        """Addresses with leading/trailing whitespace should be handled."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_wallet_address(
                " 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7"
            )

    def test_address_too_long(self):
        """Address longer than 42 chars should be rejected."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_wallet_address("0x" + "a" * 41)

    def test_address_too_short(self):
        """Address shorter than 42 chars should be rejected."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_wallet_address("0x" + "a" * 39)

    def test_address_non_hex_chars(self):
        """Address with non-hex characters should be rejected."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_wallet_address(
                "0xGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG"
            )

    def test_valid_chain_ids(self):
        """Valid chain IDs should pass validation."""
        result = ConfigValidator.validate_chain_ids([1])
        assert 1 in result

    def test_chain_id_zero(self):
        """Chain ID zero should be rejected (not in valid list)."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_chain_ids([0])

    def test_chain_id_negative(self):
        """Negative chain ID should be rejected."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_chain_ids([-1])

    def test_empty_chain_ids(self):
        """Empty chain ID list should be rejected."""
        with pytest.raises(ValidationError, match="At least one chain ID"):
            ConfigValidator.validate_chain_ids([])

    def test_rpc_url_valid_https(self):
        """Valid HTTPS RPC URL should pass."""
        result = ConfigValidator.validate_rpc_urls(
            {1: "https://mainnet.infura.io/v3/abc123"}, [1]
        )
        assert result[1] == "https://mainnet.infura.io/v3/abc123"

    def test_rpc_url_valid_http_localhost(self):
        """HTTP localhost should pass (development use)."""
        result = ConfigValidator.validate_rpc_urls({1: "http://localhost:8545"}, [1])
        assert result[1] == "http://localhost:8545"

    def test_rpc_url_missing_for_chain(self):
        """Missing RPC URL for a required chain should raise."""
        with pytest.raises(ConfigurationError):
            ConfigValidator.validate_rpc_urls({}, [1])


# ---------------------------------------------------------------------------
# Custom exceptions edge cases
# ---------------------------------------------------------------------------


class TestCustomExceptionEdgeCases:
    """Edge case tests for custom exception classes."""

    def test_exception_chain_propagation(self):
        """Exceptions should properly chain causes."""
        from on1builder.utils.custom_exceptions import (
            TransactionError,
            ConnectionError,
        )

        original = ValueError("original error")
        try:
            try:
                raise original
            except ValueError as e:
                raise ConnectionError("connection lost") from e
        except ConnectionError as e:
            assert e.__cause__ is original
            assert "connection lost" in str(e)

    def test_exception_with_empty_message(self):
        """Exceptions with empty message should still work."""
        from on1builder.utils.custom_exceptions import ON1BuilderError

        err = ON1BuilderError("")
        assert str(err) == ""
        assert isinstance(err, Exception)

    def test_all_exceptions_are_subclass(self):
        """All custom exceptions should inherit from ON1BuilderError."""
        from on1builder.utils.custom_exceptions import (
            ON1BuilderError,
            ConfigurationError,
            ConnectionError,
            TransactionError,
            InsufficientFundsError,
            StrategyExecutionError,
            InitializationError,
        )

        for exc_class in [
            ConfigurationError,
            ConnectionError,
            TransactionError,
            InsufficientFundsError,
            StrategyExecutionError,
            InitializationError,
        ]:
            assert issubclass(
                exc_class, ON1BuilderError
            ), f"{exc_class.__name__} should inherit from ON1BuilderError"


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


class TestConstantsSanity:
    """Verify constants are logically consistent."""

    def test_balance_tiers_increasing(self):
        """Balance tier thresholds should be in increasing order."""
        thresholds = list(BALANCE_TIER_THRESHOLDS.values())
        for i in range(1, len(thresholds)):
            assert (
                thresholds[i] > thresholds[i - 1]
            ), f"Tier thresholds not increasing: {thresholds[i-1]} >= {thresholds[i]}"

    def test_gas_limits_sane(self):
        """Gas limits should be within reasonable bounds."""
        from on1builder.utils.constants import DEFAULT_GAS_LIMIT, MAX_GAS_LIMIT

        assert DEFAULT_GAS_LIMIT > 0
        assert MAX_GAS_LIMIT > DEFAULT_GAS_LIMIT
        assert MAX_GAS_LIMIT <= 30_000_000  # Ethereum block gas limit

    def test_retry_settings_sane(self):
        """Retry settings should be positive and reasonable."""
        from on1builder.utils.constants import (
            DEFAULT_TRANSACTION_RETRY_COUNT,
            DEFAULT_TRANSACTION_RETRY_DELAY,
            TRANSACTION_TIMEOUT,
        )

        assert DEFAULT_TRANSACTION_RETRY_COUNT > 0
        assert DEFAULT_TRANSACTION_RETRY_COUNT <= 10
        assert DEFAULT_TRANSACTION_RETRY_DELAY > 0
        assert TRANSACTION_TIMEOUT > 0

    def test_cache_durations_positive(self):
        """All cache durations should be positive."""
        from on1builder.utils.constants import (
            BALANCE_CACHE_DURATION,
            TOKEN_PRICE_CACHE_DURATION,
            GAS_PRICE_CACHE_DURATION,
            MARKET_DATA_CACHE_DURATION,
            ABI_CACHE_DURATION,
        )

        for duration in [
            BALANCE_CACHE_DURATION,
            TOKEN_PRICE_CACHE_DURATION,
            GAS_PRICE_CACHE_DURATION,
            MARKET_DATA_CACHE_DURATION,
            ABI_CACHE_DURATION,
        ]:
            assert duration > 0

    def test_regex_patterns_valid(self):
        """Regex patterns should be compilable."""
        import re
        from on1builder.utils.constants import (
            ETHEREUM_ADDRESS_PATTERN,
            TRANSACTION_HASH_PATTERN,
            PRIVATE_KEY_PATTERN,
        )

        for pattern in [
            ETHEREUM_ADDRESS_PATTERN,
            TRANSACTION_HASH_PATTERN,
            PRIVATE_KEY_PATTERN,
        ]:
            compiled = re.compile(pattern)
            assert compiled is not None

    def test_address_pattern_matches(self):
        """Address pattern should match valid Ethereum addresses."""
        import re
        from on1builder.utils.constants import ETHEREUM_ADDRESS_PATTERN

        pattern = re.compile(ETHEREUM_ADDRESS_PATTERN)
        # Valid address
        assert pattern.match("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")
        # Invalid
        assert not pattern.match("invalid")
        assert not pattern.match("0x123")  # too short


# ---------------------------------------------------------------------------
# Error recovery edge cases
# ---------------------------------------------------------------------------


class TestCircuitBreakerEdgeCases:
    """Edge case tests for circuit breaker pattern."""

    def test_circuit_breaker_initial_state(self):
        """Circuit breaker should start in CLOSED state."""
        from on1builder.utils.error_recovery import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0

    def test_circuit_breaker_threshold_config(self):
        """Circuit breaker should accept custom thresholds."""
        from on1builder.utils.error_recovery import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=10, recovery_timeout=120.0)
        assert cb.failure_threshold == 10
        assert cb.recovery_timeout == 120.0


# ---------------------------------------------------------------------------
# Memory optimizer edge cases
# ---------------------------------------------------------------------------


class TestMemoryOptimizerEdgeCases:
    """Edge case tests for memory optimizer."""

    def test_memory_optimizer_initialization(self):
        """MemoryOptimizer should initialize with correct defaults."""
        from on1builder.utils.memory_optimizer import MemoryOptimizer

        optimizer = MemoryOptimizer(gc_threshold_mb=256.0, cleanup_interval_seconds=120)
        assert optimizer._gc_threshold_mb == 256.0
        assert optimizer._cleanup_interval == 120
        assert optimizer._is_running is False
        assert optimizer._metrics_history == []

    def test_memory_optimizer_custom_warning_threshold(self):
        """MemoryOptimizer should accept custom warning threshold."""
        from on1builder.utils.memory_optimizer import MemoryOptimizer

        optimizer = MemoryOptimizer(memory_warning_threshold=90.0)
        assert optimizer._memory_warning_threshold == 90.0


if __name__ == "__main__":
    pytest.main([__file__])

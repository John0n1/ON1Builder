#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander
"""
Tests for utility modules.
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal


def test_gas_optimizer_initialization():
    """Test GasOptimizer initializes with correct defaults."""
    from on1builder.utils.gas_optimizer import GasOptimizer

    mock_web3 = MagicMock()
    optimizer = GasOptimizer(mock_web3)

    assert optimizer is not None
    assert hasattr(optimizer, "get_gas_analytics")
    assert optimizer._is_eip1559_supported is None
    assert optimizer._gas_history == []
    assert optimizer._base_fee_history == []
    assert optimizer._priority_fee_history == []


def test_gas_optimizer_priority_levels():
    """Test GasOptimizer defines valid priority levels with increasing multipliers."""
    from on1builder.utils.gas_optimizer import GasOptimizer

    mock_web3 = MagicMock()
    optimizer = GasOptimizer(mock_web3)

    assert "low" in optimizer.PRIORITY_LEVELS
    assert "normal" in optimizer.PRIORITY_LEVELS
    assert "high" in optimizer.PRIORITY_LEVELS
    assert "urgent" in optimizer.PRIORITY_LEVELS
    assert (
        optimizer.PRIORITY_LEVELS["low"]["multiplier"]
        < optimizer.PRIORITY_LEVELS["urgent"]["multiplier"]
    )


def test_profit_calculator_initialization():
    """Test ProfitCalculator initializes with event signatures and empty caches."""
    from on1builder.utils.profit_calculator import ProfitCalculator

    mock_web3 = MagicMock()
    mock_settings = MagicMock()
    calculator = ProfitCalculator(mock_web3, mock_settings)

    assert calculator is not None
    assert "Transfer" in calculator._event_signatures
    assert "Swap" in calculator._event_signatures
    assert "FlashLoan" in calculator._event_signatures
    assert calculator._token_decimals_cache == {}
    assert calculator._price_cache == {}


def test_logging_config():
    """Test that logging configuration produces functional loggers."""
    from on1builder.utils.logging_config import get_logger

    logger = get_logger("test_utils_module")
    assert logger is not None
    assert "test_utils_module" in logger.name
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")
    assert hasattr(logger, "warning")
    assert hasattr(logger, "debug")
    assert hasattr(logger, "critical")


def test_logging_config_returns_same_logger():
    """Test that get_logger returns the same logger instance for the same name."""
    from on1builder.utils.logging_config import get_logger

    logger1 = get_logger("test_same_name")
    logger2 = get_logger("test_same_name")
    assert logger1 is logger2


def test_notification_service_basic():
    """Test NotificationService initializes with no active session."""
    from on1builder.utils.notification_service import NotificationService

    NotificationService.reset_instance()
    try:
        mock_settings = MagicMock()
        mock_settings.notification = MagicMock()
        mock_settings.notification.email_enabled = False
        mock_settings.notification.discord_enabled = False

        service = NotificationService(mock_settings)
        assert service is not None
        assert service._session is None
    finally:
        NotificationService.reset_instance()


def test_container_register_and_get():
    """Test Container register_instance and get."""
    from on1builder.utils.container import Container

    container = Container()
    container.register_instance("test_key", "test_value")
    result = container.get("test_key")
    assert result == "test_value"


def test_container_provider_lazy_instantiation():
    """Test Container register_provider lazily creates instances."""
    from on1builder.utils.container import Container

    container = Container()
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return {"created": True}

    container.register_provider("lazy_key", factory)
    assert call_count == 0  # Not yet called
    result = container.get("lazy_key")
    assert call_count == 1
    assert result == {"created": True}


def test_container_singleton_registration():
    """Test Container singleton registration returns the same instance."""
    from on1builder.utils.container import Container

    container = Container()
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return {"instance": call_count}

    container.register_singleton("singleton_key", factory)
    first = container.get("singleton_key")
    second = container.get("singleton_key")
    assert first is second
    assert call_count == 1


def test_container_missing_key_raises():
    """Test Container raises KeyError for unregistered keys."""
    from on1builder.utils.container import Container

    container = Container()
    with pytest.raises(KeyError, match="No provider registered"):
        container.get("missing_key")


def test_container_get_or_none():
    """Test Container get_or_none returns None for missing keys."""
    from on1builder.utils.container import Container

    container = Container()
    result = container.get_or_none("nonexistent")
    assert result is None


def test_config_redactor_masks_sensitive():
    """Test that ConfigRedactor masks sensitive values in configuration."""
    from on1builder.utils.config_redactor import ConfigRedactor

    config = {
        "wallet_key": "0x1234567890abcdef",
        "api_key": "secret-key-123",
        "chain_id": 1,
        "debug": True,
    }
    redacted = ConfigRedactor.redact_config(config)
    assert redacted["wallet_key"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["chain_id"] == 1
    assert redacted["debug"] is True


def test_config_redactor_preserves_with_flag():
    """Test that ConfigRedactor preserves sensitive values when show_sensitive=True."""
    from on1builder.utils.config_redactor import ConfigRedactor

    config = {"wallet_key": "0xabc123"}
    result = ConfigRedactor.redact_config(config, show_sensitive=True)
    assert result["wallet_key"] == "0xabc123"


def test_config_redactor_nested():
    """Test that ConfigRedactor handles nested dictionaries."""
    from on1builder.utils.config_redactor import ConfigRedactor

    config = {
        "api": {"etherscan_api_key": "key123", "rate_limit": 100},
        "chain_id": 1,
    }
    redacted = ConfigRedactor.redact_config(config)
    assert redacted["api"]["etherscan_api_key"] == "[REDACTED]"
    assert redacted["api"]["rate_limit"] == 100
    assert redacted["chain_id"] == 1


if __name__ == "__main__":
    pytest.main([__file__])

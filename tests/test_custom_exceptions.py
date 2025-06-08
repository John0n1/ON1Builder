#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for ON1Builder utils.custom_exceptions module.
Tests for 100% coverage of all exception classes and methods.
"""

import json
import time
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from unittest.mock import Mock, patch

from on1builder.utils.custom_exceptions import (
    StrategyExecutionError,
    ConfigurationError,
    ChainConnectionError,
    TransactionError,
)


class TestStrategyExecutionError:
    """Test suite for StrategyExecutionError class."""

    def test_init_minimal(self):
        """Test StrategyExecutionError with minimal parameters."""
        error = StrategyExecutionError()
        
        assert error.message == "Strategy execution failed"
        assert error.strategy_name is None
        assert error.chain_id is None
        assert error.tx_hash is None
        assert error.details == {}
        assert error.original_exception is None
        assert error.traceback is None
        assert isinstance(error.timestamp, float)
        assert error.timestamp <= time.time()

    def test_init_full_parameters(self):
        """Test StrategyExecutionError with all parameters."""
        original_exc = ValueError("Original error")
        details = {"gas_used": 21000, "slippage": 0.5}
        
        error = StrategyExecutionError(
            message="Custom message",
            strategy_name="arbitrage_v1",
            chain_id=1,
            tx_hash="0x123abc",
            details=details,
            original_exception=original_exc,
        )
        
        assert error.message == "Custom message"
        assert error.strategy_name == "arbitrage_v1"
        assert error.chain_id == 1
        assert error.tx_hash == "0x123abc"
        assert error.details == details
        assert error.original_exception == original_exc
        assert error.traceback is not None
        assert "ValueError: Original error" in error.traceback

    def test_traceback_generation(self):
        """Test that traceback is properly generated from original exception."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error = StrategyExecutionError(original_exception=e)
            
        assert error.traceback is not None
        assert "ValueError: Test error" in error.traceback

    def test_str_representation(self):
        """Test string representation of StrategyExecutionError."""
        error = StrategyExecutionError(
            message="Test error",
            strategy_name="test_strategy",
            chain_id=1,
        )
        
        str_repr = str(error)
        assert "Test error" in str_repr
        assert "test_strategy" in str_repr
        assert "Chain ID: 1" in str_repr

    def test_str_representation_minimal(self):
        """Test string representation with minimal data."""
        error = StrategyExecutionError()
        str_repr = str(error)
        assert "Strategy execution failed" in str_repr

    def test_str_representation_with_all_fields(self):
        """Test string representation with all fields populated."""
        original_exc = RuntimeError("Original error")
        details = {"key": "value"}
        
        error = StrategyExecutionError(
            message="Full test",
            strategy_name="full_strategy",
            chain_id=42,
            tx_hash="0xfull123",
            details=details,
            original_exception=original_exc,
        )
        
        str_repr = str(error)
        assert "Full test" in str_repr
        assert "Strategy: full_strategy" in str_repr
        assert "Chain ID: 42" in str_repr
        assert "TX Hash: 0xfull123" in str_repr
        assert "Details: {'key': 'value'}" in str_repr
        assert "Caused by: Original error" in str_repr

    def test_to_dict(self):
        """Test conversion to dictionary."""
        original_exc = ValueError("Original error")
        details = {"key": "value"}
        
        error = StrategyExecutionError(
            message="Test message",
            strategy_name="test_strategy",
            chain_id=42,
            tx_hash="0xabc123",
            details=details,
            original_exception=original_exc,
        )
        
        result = error.to_dict()
        
        assert result["message"] == "Test message"
        assert result["strategy_name"] == "test_strategy"
        assert result["chain_id"] == 42
        assert result["tx_hash"] == "0xabc123"
        assert result["details"] == details
        assert result["timestamp"] == error.timestamp
        assert result["original_exception"] == "Original error"
        assert result["traceback"] is not None

    def test_to_dict_minimal(self):
        """Test to_dict with minimal data."""
        error = StrategyExecutionError()
        result = error.to_dict()
        
        assert result["message"] == "Strategy execution failed"
        assert result["strategy_name"] is None
        assert result["chain_id"] is None
        assert result["tx_hash"] is None
        assert result["details"] == {}
        assert result["original_exception"] is None
        assert result["traceback"] is None

    def test_to_json(self):
        """Test JSON serialization."""
        error = StrategyExecutionError(
            message="JSON test",
            strategy_name="json_strategy",
            chain_id=1,
        )
        
        json_str = error.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["message"] == "JSON test"
        assert parsed["strategy_name"] == "json_strategy"
        assert parsed["chain_id"] == 1

    def test_to_json_with_complex_data(self):
        """Test JSON serialization with complex data types."""
        from datetime import datetime
        details = {"timestamp": datetime.now(), "data": [1, 2, 3]}
        
        error = StrategyExecutionError(details=details)
        json_str = error.to_json()
        
        # Should not raise an exception due to default=str
        parsed = json.loads(json_str)
        assert "details" in parsed

    def test_exception_inheritance(self):
        """Test that StrategyExecutionError properly inherits from Exception."""
        error = StrategyExecutionError("test")
        assert isinstance(error, Exception)
        assert isinstance(error, StrategyExecutionError)

    def test_exception_can_be_raised_and_caught(self):
        """Test that exception can be properly raised and caught."""
        with pytest.raises(StrategyExecutionError) as exc_info:
            raise StrategyExecutionError("test error")
        
        assert str(exc_info.value) == "test error"

    def test_timestamp_is_current(self):
        """Test that timestamp is set to current time."""
        before_time = time.time()
        error = StrategyExecutionError()
        after_time = time.time()
        
        assert before_time <= error.timestamp <= after_time

    def test_details_dict_mutability(self):
        """Test that details dict can be modified after creation."""
        error = StrategyExecutionError()
        assert error.details == {}
        
        error.details["new_key"] = "new_value"
        assert error.details["new_key"] == "new_value"

    def test_no_traceback_without_original_exception(self):
        """Test that traceback is None when no original exception is provided."""
        error = StrategyExecutionError(message="No original exception")
        assert error.traceback is None


class TestSimpleExceptions:
    """Test suite for simple exception classes (ConfigurationError, etc.)."""

    def test_configuration_error_basic(self):
        """Test ConfigurationError basic functionality."""
        error = ConfigurationError("Config error message")
        assert str(error) == "Config error message"
        assert isinstance(error, Exception)
        assert isinstance(error, ConfigurationError)

    def test_configuration_error_no_message(self):
        """Test ConfigurationError with no message."""
        error = ConfigurationError()
        assert str(error) == ""

    def test_configuration_error_can_be_raised(self):
        """Test ConfigurationError can be raised and caught."""
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError("Test config error")
        
        assert str(exc_info.value) == "Test config error"

    def test_chain_connection_error_basic(self):
        """Test ChainConnectionError basic functionality."""
        error = ChainConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, Exception)
        assert isinstance(error, ChainConnectionError)

    def test_chain_connection_error_no_message(self):
        """Test ChainConnectionError with no message."""
        error = ChainConnectionError()
        assert str(error) == ""

    def test_chain_connection_error_can_be_raised(self):
        """Test ChainConnectionError can be raised and caught."""
        with pytest.raises(ChainConnectionError) as exc_info:
            raise ChainConnectionError("RPC connection failed")
        
        assert str(exc_info.value) == "RPC connection failed"

    def test_transaction_error_basic(self):
        """Test TransactionError basic functionality."""
        error = TransactionError("Transaction failed")
        assert str(error) == "Transaction failed"
        assert isinstance(error, Exception)
        assert isinstance(error, TransactionError)

    def test_transaction_error_no_message(self):
        """Test TransactionError with no message."""
        error = TransactionError()
        assert str(error) == ""

    def test_transaction_error_can_be_raised(self):
        """Test TransactionError can be raised and caught."""
        with pytest.raises(TransactionError) as exc_info:
            raise TransactionError("Gas estimation failed")
        
        assert str(exc_info.value) == "Gas estimation failed"


class TestExceptionInheritance:
    """Test that all custom exceptions properly inherit from Exception."""

    def test_all_exceptions_inherit_from_exception(self):
        """Test all custom exceptions inherit from Exception."""
        exceptions_to_test = [
            (StrategyExecutionError, "strategy error"),
            (ConfigurationError, "config error"),
            (ChainConnectionError, "connection error"),
            (TransactionError, "transaction error"),
        ]
        
        for exc_class, message in exceptions_to_test:
            error = exc_class(message)
            assert isinstance(error, Exception)
            assert isinstance(error, exc_class)

    def test_exception_hierarchy(self):
        """Test that exceptions can be caught as base Exception."""
        exceptions_to_test = [
            StrategyExecutionError("test"),
            ConfigurationError("test"),
            ChainConnectionError("test"),
            TransactionError("test"),
        ]
        
        for error in exceptions_to_test:
            with pytest.raises(Exception):
                raise error


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_details_dict(self):
        """Test that empty details dict is handled properly."""
        error = StrategyExecutionError(details={})
        assert error.details == {}
        assert error.to_dict()["details"] == {}

    def test_none_values_in_to_dict(self):
        """Test to_dict handles None values correctly."""
        error = StrategyExecutionError()
        result = error.to_dict()
        
        # Should contain None values, not exclude them
        assert "strategy_name" in result
        assert result["strategy_name"] is None

    def test_json_serialization_with_none_values(self):
        """Test JSON serialization includes None values."""
        error = StrategyExecutionError()
        json_str = error.to_json()
        parsed = json.loads(json_str)
        
        assert "strategy_name" in parsed
        assert parsed["strategy_name"] is None

    def test_large_details_dict(self):
        """Test handling of large details dictionary."""
        large_details = {f"key_{i}": f"value_{i}" for i in range(1000)}
        
        error = StrategyExecutionError(details=large_details)
        assert len(error.details) == 1000
        
        # Should be able to serialize to JSON
        json_str = error.to_json()
        parsed = json.loads(json_str)
        assert len(parsed["details"]) == 1000

    def test_special_characters_in_strings(self):
        """Test handling of special characters in string fields."""
        special_chars = "Test with 🚀 émojis and ñ spëcial chars"
        
        error = StrategyExecutionError(message=special_chars)
        assert error.message == special_chars
        
        # Should serialize to JSON properly
        json_str = error.to_json()
        parsed = json.loads(json_str)
        assert parsed["message"] == special_chars

    def test_very_long_message(self):
        """Test handling of very long error messages."""
        long_message = "x" * 10000
        error = StrategyExecutionError(message=long_message)
        
        assert error.message == long_message
        assert len(str(error)) >= 10000

    def test_nested_exception_traceback(self):
        """Test traceback generation with nested exceptions."""
        try:
            try:
                raise ValueError("Inner error")
            except ValueError as inner:
                raise RuntimeError("Outer error") from inner
        except RuntimeError as e:
            error = StrategyExecutionError(original_exception=e)
            
        assert error.traceback is not None
        assert "RuntimeError: Outer error" in error.traceback

    def test_circular_reference_in_details(self):
        """Test that circular references in details break JSON serialization."""
        details = {}
        details["self"] = details  # Circular reference
        
        error = StrategyExecutionError(details=details)
        
        # Should raise ValueError due to circular reference
        with pytest.raises(ValueError, match="Circular reference detected"):
            error.to_json()

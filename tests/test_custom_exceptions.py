#!/usr/bin/env python3
"""
Tests for custom exception classes.
"""

import pytest

def test_custom_exceptions_exist():
    """Test that custom exception classes exist and are properly defined."""
    from on1builder.utils.custom_exceptions import (
        ConnectionError,
        ConfigurationError,
        StrategyExecutionError,
        TransactionError,
    )
    
    # Test that all exceptions inherit from the correct base classes
    assert issubclass(ConnectionError, Exception)
    assert issubclass(ConfigurationError, Exception)
    assert issubclass(StrategyExecutionError, Exception)
    assert issubclass(TransactionError, Exception)

def test_exception_instantiation():
    """Test that exceptions can be instantiated with messages."""
    from on1builder.utils.custom_exceptions import (
        ConnectionError,
        ConfigurationError,
        StrategyExecutionError,
        TransactionError,
    )
    
    # Test creating exceptions with messages
    conn_error = ConnectionError("Connection failed")
    assert "Connection failed" in str(conn_error)
    
    config_error = ConfigurationError("Invalid config")
    assert "Invalid config" in str(config_error)
    
    strategy_error = StrategyExecutionError("Strategy failed")
    assert "Strategy failed" in str(strategy_error)
    
    tx_error = TransactionError("Transaction failed")
    assert "Transaction failed" in str(tx_error)

def test_exception_raising():
    """Test that exceptions can be raised and caught properly."""
    from on1builder.utils.custom_exceptions import ConfigurationError
    
    with pytest.raises(ConfigurationError) as exc_info:
        raise ConfigurationError("Test error message")
    
    assert "Test error message" in str(exc_info.value)

if __name__ == "__main__":
    pytest.main([__file__])
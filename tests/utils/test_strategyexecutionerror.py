# LICENSE: MIT // github.com/John0n1/ON1Builder

"""
Tests for the StrategyExecutionError class in utils/strategyexecutionerror.py
"""

import pytest
from on1builder.utils.strategyexecutionerror import StrategyExecutionError


def test_strategy_execution_error_init():
    """Test the initialization of StrategyExecutionError with default message."""
    error = StrategyExecutionError()
    
    # Check that the error has the default message
    assert error.message == "Strategy execution failed"
    assert str(error) == "Strategy execution failed"


def test_strategy_execution_error_custom_message():
    """Test the initialization of StrategyExecutionError with a custom message."""
    error_message = "Custom strategy error message"
    error = StrategyExecutionError(error_message)
    
    # Check that the error has the custom message
    assert error.message == error_message
    assert str(error) == error_message


def test_strategy_execution_error_inheritance():
    """Test that StrategyExecutionError inherits from Exception."""
    error = StrategyExecutionError()
    
    # Check that the error is an instance of Exception
    assert isinstance(error, Exception)
    
    # Check that it can be caught as an Exception
    try:
        raise StrategyExecutionError("Test exception")
        assert False, "Exception was not raised"
    except Exception as e:
        assert str(e) == "Test exception"


def test_strategy_execution_error_in_exception_hierarchy():
    """Test that StrategyExecutionError fits in the exception hierarchy."""
    try:
        raise StrategyExecutionError("Strategy failed due to invalid parameters")
    except StrategyExecutionError as e:
        # Should be caught here
        assert str(e) == "Strategy failed due to invalid parameters"
        # Check that it's also an Exception
        assert isinstance(e, Exception)
    except Exception:
        pytest.fail("Should have been caught as StrategyExecutionError")

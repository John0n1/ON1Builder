# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from scripts.python.pyutils.strategyexecutionerror import StrategyExecutionError

def test_strategy_execution_error():
    error_message = "Test error message"
    error = StrategyExecutionError(error_message)
    
    assert str(error) == error_message
    assert isinstance(error, Exception)

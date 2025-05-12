# ========================================================================================================================
# https://github.com/John0n1/ON1Builder

# This file contains the StrategyExecutionError class, which is a custom exception for strategy execution failures.
# ========================================================================================================================


class StrategyExecutionError(Exception):
    """Custom exception for strategy execution failures."""

    def __init__(self, message: str = "Strategy execution failed") -> None:
        self.message: str = message
        super().__init__(self.message)

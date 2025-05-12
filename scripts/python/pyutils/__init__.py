# LICENSE: MIT // github.com/John0n1/ON1Builder

"""
ON1Builder package initialization.
"""
# ./ON1Builder/utils/Python/__init__.py

from strategyexecutionerror import StrategyExecutionError

__all__: list[str] = ["StrategyExecutionError"]


def initialize_package() -> None:
    """
    Initialize the ON1Builder package.
    """
    try:
        # Add any package initialization logic here
        pass
    except Exception as e:
        raise RuntimeError(f"Failed to initialize ON1Builder package: {e}")


def cleanup_package() -> None:
    """
    Clean up resources used by the ON1Builder package.
    """
    try:
        # Add any package cleanup logic here
        pass
    except Exception as e:
        raise RuntimeError(f"Failed to clean up ON1Builder package: {e}")

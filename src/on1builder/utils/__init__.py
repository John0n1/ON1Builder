"""
Common utilities for ON1Builder.
"""

from .container import Container
from .custom_exceptions import (
    ConnectionError,
    ConfigurationError,
    StrategyExecutionError,
    TransactionError,
)
from .logging_config import get_logger
# NotificationService import disabled due to aiohttp dependency
# from .notification_service import NotificationService
from .path_helpers import (
    ensure_dir_exists,
    get_abi_path,
    get_base_dir,
    get_chain_config_path,
    get_config_dir,
    get_resource_dir,
    get_resource_path,
    get_strategy_weights_path,
    get_token_data_path,
)
# Gas optimizer and profit calculator imports disabled due to web3/aiohttp dependencies
# from .gas_optimizer import GasOptimizer
# from .profit_calculator import ProfitCalculator

__all__ = [
    "Container",
    "get_logger", 
    # "NotificationService",  # Disabled due to dependencies
    "StrategyExecutionError",
    "ConfigurationError",
    "ConnectionError",  # Note: fixed name from ChainConnectionError
    "TransactionError",
    "get_base_dir",
    "get_config_dir",
    "get_resource_dir",
    "get_resource_path",
    "get_abi_path",
    "get_token_data_path",
    "get_strategy_weights_path",
    "get_chain_config_path",
    "ensure_dir_exists",
    # "GasOptimizer",      # Disabled due to dependencies
    # "ProfitCalculator",  # Disabled due to dependencies
]

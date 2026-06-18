"""
Common utilities for ON1Builder.
"""

from .cli_helpers import (
    confirm_action,
    error_message,
    handle_cli_errors,
    info_message,
    success_message,
    warning_message,
)
from .config_redactor import ConfigRedactor
from .constants import *  # noqa: F401,F403
from .container import Container
from .custom_exceptions import (
    APICallError,
    ConfigurationError,
    ConnectionError,
    InitializationError,
    InsufficientFundsError,
    ON1BuilderError,
    SafetyCheckError,
    StrategyExecutionError,
    TransactionError,
    ValidationError,
)
from .error_recovery import (
    get_error_recovery_manager,
    with_circuit_breaker,
    with_error_recovery,
    with_retry,
)
from .logging_config import get_logger, reset_logging, setup_logging
from .memory_optimizer import (
    cleanup_memory_optimization,
    get_memory_optimizer,
    initialize_memory_optimization,
)

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
    # Core utilities
    "Container",
    "get_logger",
    "setup_logging",
    "reset_logging",
    # Memory optimization
    "get_memory_optimizer",
    "initialize_memory_optimization",
    "cleanup_memory_optimization",
    # CLI helpers
    "handle_cli_errors",
    "success_message",
    "info_message",
    "warning_message",
    "error_message",
    "confirm_action",
    # Config and recovery helpers
    "ConfigRedactor",
    "get_error_recovery_manager",
    "with_circuit_breaker",
    "with_retry",
    "with_error_recovery",
    # Exceptions
    "ON1BuilderError",
    "StrategyExecutionError",
    "ConfigurationError",
    "ConnectionError",
    "TransactionError",
    "InitializationError",
    "InsufficientFundsError",
    "APICallError",
    "ValidationError",
    "SafetyCheckError",
    # Path helpers
    "get_base_dir",
    "get_config_dir",
    "get_resource_dir",
    "get_resource_path",
    "get_abi_path",
    "get_token_data_path",
    "get_strategy_weights_path",
    "get_chain_config_path",
    "ensure_dir_exists",
    # Disabled due to dependencies
    # "NotificationService",
    # "GasOptimizer",
    # "ProfitCalculator",
]

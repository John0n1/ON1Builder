# src/on1builder/utils/custom_exceptions.py
from typing import Optional, Dict, Any

class ON1BuilderError(Exception):
    """Base exception for all custom errors in the ON1Builder application."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message

class ConfigurationError(ON1BuilderError):
    """Raised for errors related to application configuration."""
    def __init__(self, message: str = "Configuration error", key: Optional[str] = None):
        details = {"key": key} if key else {}
        super().__init__(message, details)

class InitializationError(ON1BuilderError):
    """Raised when a critical component fails to initialize."""
    def __init__(self, message: str = "Component initialization failed", component: Optional[str] = None):
        details = {"component": component} if component else {}
        super().__init__(message, details)

class ConnectionError(ON1BuilderError):
    """Raised for errors related to network or RPC connections."""
    def __init__(self, message: str = "Connection failed", endpoint: Optional[str] = None):
        details = {"endpoint": endpoint} if endpoint else {}
        super().__init__(message, details)

class TransactionError(ON1BuilderError):
    """Raised for errors during transaction building, signing, or sending."""
    def __init__(self, message: str = "Transaction failed", tx_hash: Optional[str] = None, reason: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        if details:
            # If details are provided directly, use them
            final_details = details.copy()
            if tx_hash:
                final_details["tx_hash"] = tx_hash
            if reason:
                final_details["reason"] = reason
        else:
            # Build details from individual parameters
            final_details = {
                "tx_hash": tx_hash,
                "reason": reason
            }
        super().__init__(message, details=final_details)

class StrategyExecutionError(ON1BuilderError):
    """Raised for errors during the execution of a trading strategy."""
    def __init__(self, message: str = "Strategy execution failed", strategy_name: Optional[str] = None):
        details = {"strategy": strategy_name} if strategy_name else {}
        super().__init__(message, details)

class InsufficientFundsError(TransactionError):
    """Raised when an operation fails due to insufficient wallet balance."""
    def __init__(self, message: str = "Insufficient funds for transaction", required: float = 0, available: float = 0):
        details = {
            "required_eth": required,
            "available_eth": available,
            "reason": "Insufficient wallet balance"
        }
        super().__init__(message, details=details)

class APICallError(ON1BuilderError):
    """Raised when an external API call fails."""
    def __init__(self, message: str = "External API call failed", provider: Optional[str] = None, status_code: Optional[int] = None):
        details = {
            "provider": provider,
            "status_code": status_code
        }
        super().__init__(message, details)
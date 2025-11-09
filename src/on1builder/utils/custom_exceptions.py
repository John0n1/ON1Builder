# src/on1builder/utils/custom_exceptions.py
# flake8: noqa E501
from __future__ import annotations

from typing import Optional, Dict, Any, Union


class ON1BuilderError(Exception):
    """Base exception for all custom errors in the ON1Builder application."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        self.cause = cause
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


class ConfigurationError(ON1BuilderError):
    """Raised for errors related to application configuration."""

    def __init__(
        self,
        message: str = "Configuration error",
        key: Optional[str] = None,
        value: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        detail_payload: Dict[str, Any] = dict(details or {})
        if key:
            detail_payload.setdefault("key", key)
        if value is not None:
            detail_payload.setdefault("value", value)
        super().__init__(message, detail_payload, cause)


class InitializationError(ON1BuilderError):
    """Raised when a critical component fails to initialize."""

    def __init__(
        self,
        message: str = "Component initialization failed",
        component: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {"component": component} if component else {}
        super().__init__(message, details, cause)


class ConnectionError(ON1BuilderError):
    """Raised for errors related to network or RPC connections."""

    def __init__(
        self,
        message: str = "Connection failed",
        endpoint: Optional[str] = None,
        chain_id: Optional[int] = None,
        retry_count: Optional[int] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {}
        if endpoint:
            details["endpoint"] = endpoint
        if chain_id is not None:
            details["chain_id"] = chain_id
        if retry_count is not None:
            details["retry_count"] = retry_count
        super().__init__(message, details, cause)


class TransactionError(ON1BuilderError):
    """Raised for errors during transaction building, signing, or sending."""

    def __init__(
        self,
        message: str = "Transaction failed",
        tx_hash: Optional[str] = None,
        reason: Optional[str] = None,
        gas_used: Optional[int] = None,
        gas_price: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        final_details = details.copy() if details else {}

        if tx_hash:
            final_details["tx_hash"] = tx_hash
        if reason:
            final_details["reason"] = reason
        if gas_used is not None:
            final_details["gas_used"] = gas_used
        if gas_price is not None:
            final_details["gas_price"] = gas_price

        super().__init__(message, final_details, cause)


class StrategyExecutionError(ON1BuilderError):
    """Raised for errors during the execution of a trading strategy."""

    def __init__(
        self,
        message: str = "Strategy execution failed",
        strategy: Optional[str] = None,
        opportunity: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {}
        if strategy:
            details["strategy"] = strategy
        if opportunity:
            # Only include safe fields from opportunity
            safe_opportunity = {
                k: v
                for k, v in opportunity.items()
                if k in ["type", "token_pair", "profit_estimate", "chain_id"]
            }
            details["opportunity"] = safe_opportunity
        super().__init__(message, details, cause)


class InsufficientFundsError(TransactionError):
    """Raised when an operation fails due to insufficient wallet balance."""

    def __init__(
        self,
        message: str = "Insufficient funds",
        required_amount: Optional[Union[int, float]] = None,
        available_amount: Optional[Union[int, float]] = None,
        token: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {}
        if required_amount is not None:
            details["required_amount"] = required_amount
        if available_amount is not None:
            details["available_amount"] = available_amount
        if token:
            details["token"] = token
        super().__init__(message, details=details, cause=cause)


class APICallError(ON1BuilderError):
    """Raised when an external API call fails."""

    def __init__(
        self,
        message: str = "API call failed",
        api_name: Optional[str] = None,
        endpoint: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {}
        if api_name:
            details["api_name"] = api_name
        if endpoint:
            details["endpoint"] = endpoint
        if status_code is not None:
            details["status_code"] = status_code
        if response_body:
            details["response_body"] = response_body[:500]  # Limit response size
        super().__init__(message, details, cause)


class ValidationError(ON1BuilderError):
    """Raised when data validation fails."""

    def __init__(
        self,
        message: str = "Validation failed",
        field: Optional[str] = None,
        value: Optional[Any] = None,
        expected_type: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        if expected_type:
            details["expected_type"] = expected_type
        super().__init__(message, details, cause)


class SafetyCheckError(ON1BuilderError):
    """Raised when a safety check fails."""

    def __init__(
        self,
        message: str = "Safety check failed",
        check_name: Optional[str] = None,
        threshold: Optional[Union[int, float]] = None,
        actual_value: Optional[Union[int, float]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {}
        if check_name:
            details["check_name"] = check_name
        if threshold is not None:
            details["threshold"] = threshold
        if actual_value is not None:
            details["actual_value"] = actual_value
        super().__init__(message, details, cause)

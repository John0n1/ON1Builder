"""Comprehensive tests for custom_exceptions module."""
import pytest
from on1builder.utils.custom_exceptions import (
    ON1BuilderError,
    ConfigurationError,
    InitializationError,
    ConnectionError,
    TransactionError,
    StrategyExecutionError,
    InsufficientFundsError,
    APICallError,
    ValidationError,
    SafetyCheckError,
)


class TestON1BuilderError:
    """Test base exception class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = ON1BuilderError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details == {}
        assert error.cause is None

    def test_error_with_details(self):
        """Test error with details."""
        details = {"key": "value", "count": 42}
        error = ON1BuilderError("Error with details", details=details)
        assert error.details == details
        assert "Details:" in str(error)
        assert "key" in str(error)

    def test_error_with_cause(self):
        """Test error with cause exception."""
        cause = ValueError("Original error")
        error = ON1BuilderError("Wrapped error", cause=cause)
        assert error.cause == cause
        assert isinstance(error.cause, ValueError)

    def test_to_dict(self):
        """Test converting error to dictionary."""
        details = {"field": "test"}
        cause = RuntimeError("root cause")
        error = ON1BuilderError("Test", details=details, cause=cause)
        
        result = error.to_dict()
        
        assert result["error_type"] == "ON1BuilderError"
        assert result["message"] == "Test"
        assert result["details"] == details
        assert "root cause" in result["cause"]


class TestConfigurationError:
    """Test ConfigurationError."""

    def test_basic_config_error(self):
        """Test basic configuration error."""
        error = ConfigurationError()
        assert "Configuration error" in str(error)

    def test_config_error_with_key(self):
        """Test configuration error with key."""
        error = ConfigurationError("Invalid value", key="wallet_address")
        assert error.details["key"] == "wallet_address"

    def test_config_error_with_value(self):
        """Test configuration error with value."""
        error = ConfigurationError("Bad value", value=12345)
        assert error.details["value"] == 12345

    def test_config_error_full(self):
        """Test configuration error with all parameters."""
        cause = KeyError("missing")
        error = ConfigurationError(
            "Config failed",
            key="api_key",
            value="invalid",
            details={"extra": "info"},
            cause=cause
        )
        assert error.details["key"] == "api_key"
        assert error.details["value"] == "invalid"
        assert error.details["extra"] == "info"
        assert error.cause == cause


class TestInitializationError:
    """Test InitializationError."""

    def test_basic_init_error(self):
        """Test basic initialization error."""
        error = InitializationError()
        assert "initialization failed" in str(error).lower()

    def test_init_error_with_component(self):
        """Test initialization error with component name."""
        error = InitializationError("Failed to start", component="DatabaseInterface")
        assert error.details["component"] == "DatabaseInterface"

    def test_init_error_with_cause(self):
        """Test initialization error with cause."""
        cause = ConnectionError("DB unreachable")
        error = InitializationError("Init failed", component="DB", cause=cause)
        assert error.cause == cause


class TestConnectionError:
    """Test ConnectionError."""

    def test_basic_connection_error(self):
        """Test basic connection error."""
        error = ConnectionError()
        assert "Connection failed" in str(error)

    def test_connection_error_with_endpoint(self):
        """Test connection error with endpoint."""
        error = ConnectionError("Timeout", endpoint="https://rpc.example.com")
        assert error.details["endpoint"] == "https://rpc.example.com"

    def test_connection_error_with_chain(self):
        """Test connection error with chain ID."""
        error = ConnectionError("RPC down", chain_id=1, endpoint="https://eth.com")
        assert error.details["chain_id"] == 1
        assert error.details["endpoint"] == "https://eth.com"

    def test_connection_error_with_retries(self):
        """Test connection error with retry count."""
        error = ConnectionError("Max retries", retry_count=3, endpoint="wss://node.com")
        assert error.details["retry_count"] == 3

    def test_connection_error_full(self):
        """Test connection error with all parameters."""
        cause = TimeoutError("timeout")
        error = ConnectionError(
            "Connection lost",
            endpoint="https://test.com",
            chain_id=137,
            retry_count=5,
            cause=cause
        )
        assert error.details["endpoint"] == "https://test.com"
        assert error.details["chain_id"] == 137
        assert error.details["retry_count"] == 5
        assert error.cause == cause


class TestTransactionError:
    """Test TransactionError."""

    def test_basic_transaction_error(self):
        """Test basic transaction error."""
        error = TransactionError()
        assert "Transaction failed" in str(error)

    def test_transaction_error_with_hash(self):
        """Test transaction error with hash."""
        tx_hash = "0xabc123"
        error = TransactionError("Reverted", tx_hash=tx_hash)
        assert error.details["tx_hash"] == tx_hash

    def test_transaction_error_with_gas(self):
        """Test transaction error with gas details."""
        error = TransactionError("Out of gas", gas_used=21000, gas_price=50)
        assert error.details["gas_used"] == 21000
        assert error.details["gas_price"] == 50

    def test_transaction_error_with_reason(self):
        """Test transaction error with reason."""
        error = TransactionError("Failed", reason="Slippage too high")
        assert error.details["reason"] == "Slippage too high"

    def test_transaction_error_full(self):
        """Test transaction error with all parameters."""
        error = TransactionError(
            "TX failed",
            tx_hash="0x123",
            reason="insufficient funds",
            gas_used=50000,
            gas_price=100,
            details={"nonce": 42}
        )
        assert error.details["tx_hash"] == "0x123"
        assert error.details["reason"] == "insufficient funds"
        assert error.details["gas_used"] == 50000
        assert error.details["gas_price"] == 100
        assert error.details["nonce"] == 42


class TestStrategyExecutionError:
    """Test StrategyExecutionError."""

    def test_basic_strategy_error(self):
        """Test basic strategy error."""
        error = StrategyExecutionError()
        assert "Strategy execution failed" in str(error)

    def test_strategy_error_with_name(self):
        """Test strategy error with strategy name."""
        error = StrategyExecutionError("Failed", strategy="arbitrage")
        assert error.details["strategy"] == "arbitrage"

    def test_strategy_error_with_opportunity(self):
        """Test strategy error with opportunity details."""
        opportunity = {
            "type": "arbitrage",
            "token_pair": "ETH/USDC",
            "profit_estimate": 0.05,
            "chain_id": 1,
            "sensitive_data": "should not appear"
        }
        error = StrategyExecutionError("Failed", opportunity=opportunity)
        
        # Should include safe fields only
        assert error.details["opportunity"]["type"] == "arbitrage"
        assert error.details["opportunity"]["token_pair"] == "ETH/USDC"
        assert "sensitive_data" not in error.details["opportunity"]

    def test_strategy_error_full(self):
        """Test strategy error with all parameters."""
        cause = ValueError("Invalid route")
        opportunity = {"type": "flashloan", "profit_estimate": 0.1}
        error = StrategyExecutionError(
            "Execution failed",
            strategy="flashloan_arb",
            opportunity=opportunity,
            cause=cause
        )
        assert error.details["strategy"] == "flashloan_arb"
        assert error.cause == cause


class TestInsufficientFundsError:
    """Test InsufficientFundsError."""

    def test_basic_insufficient_funds(self):
        """Test basic insufficient funds error."""
        error = InsufficientFundsError()
        assert "Insufficient funds" in str(error)

    def test_insufficient_funds_with_amounts(self):
        """Test insufficient funds with amounts."""
        error = InsufficientFundsError(
            "Not enough ETH",
            required_amount=1.5,
            available_amount=0.8
        )
        assert error.details["required_amount"] == 1.5
        assert error.details["available_amount"] == 0.8

    def test_insufficient_funds_with_token(self):
        """Test insufficient funds with token."""
        error = InsufficientFundsError(
            "Not enough tokens",
            required_amount=1000,
            available_amount=500,
            token="USDC"
        )
        assert error.details["token"] == "USDC"

    def test_insufficient_funds_full(self):
        """Test insufficient funds with all parameters."""
        cause = ValueError("Balance check failed")
        error = InsufficientFundsError(
            "Cannot execute",
            required_amount=100.0,
            available_amount=50.0,
            token="DAI",
            cause=cause
        )
        assert error.details["required_amount"] == 100.0
        assert error.details["available_amount"] == 50.0
        assert error.details["token"] == "DAI"
        assert error.cause == cause


class TestAPICallError:
    """Test APICallError."""

    def test_basic_api_error(self):
        """Test basic API error."""
        error = APICallError()
        assert "API call failed" in str(error)

    def test_api_error_with_name(self):
        """Test API error with API name."""
        error = APICallError("Request failed", api_name="CoinGecko")
        assert error.details["api_name"] == "CoinGecko"

    def test_api_error_with_status(self):
        """Test API error with status code."""
        error = APICallError("HTTP error", status_code=429)
        assert error.details["status_code"] == 429

    def test_api_error_with_response_truncation(self):
        """Test API error truncates long responses."""
        long_response = "x" * 1000
        error = APICallError("Error", response_body=long_response)
        assert len(error.details["response_body"]) == 500

    def test_api_error_full(self):
        """Test API error with all parameters."""
        error = APICallError(
            "Request timeout",
            api_name="Etherscan",
            endpoint="/api/v1/tx",
            status_code=504,
            response_body="Gateway timeout",
            cause=TimeoutError()
        )
        assert error.details["api_name"] == "Etherscan"
        assert error.details["endpoint"] == "/api/v1/tx"
        assert error.details["status_code"] == 504
        assert error.details["response_body"] == "Gateway timeout"


class TestValidationError:
    """Test ValidationError."""

    def test_basic_validation_error(self):
        """Test basic validation error."""
        error = ValidationError()
        assert "Validation failed" in str(error)

    def test_validation_error_with_field(self):
        """Test validation error with field name."""
        error = ValidationError("Invalid input", field="email")
        assert error.details["field"] == "email"

    def test_validation_error_with_value(self):
        """Test validation error with value."""
        error = ValidationError("Bad value", field="age", value="-5")
        assert error.details["field"] == "age"
        assert error.details["value"] == "-5"

    def test_validation_error_with_type(self):
        """Test validation error with expected type."""
        error = ValidationError(
            "Type mismatch",
            field="count",
            value="abc",
            expected_type="integer"
        )
        assert error.details["expected_type"] == "integer"

    def test_validation_error_full(self):
        """Test validation error with all parameters."""
        cause = TypeError("Cannot convert")
        error = ValidationError(
            "Validation failed",
            field="price",
            value="invalid",
            expected_type="float",
            cause=cause
        )
        assert error.details["field"] == "price"
        assert error.details["value"] == "invalid"
        assert error.details["expected_type"] == "float"
        assert error.cause == cause


class TestSafetyCheckError:
    """Test SafetyCheckError."""

    def test_basic_safety_check_error(self):
        """Test basic safety check error."""
        error = SafetyCheckError()
        assert "Safety check failed" in str(error)

    def test_safety_check_with_name(self):
        """Test safety check error with check name."""
        error = SafetyCheckError("Check failed", check_name="gas_price_limit")
        assert error.details["check_name"] == "gas_price_limit"

    def test_safety_check_with_threshold(self):
        """Test safety check error with threshold."""
        error = SafetyCheckError(
            "Exceeded limit",
            check_name="max_slippage",
            threshold=5.0,
            actual_value=8.5
        )
        assert error.details["threshold"] == 5.0
        assert error.details["actual_value"] == 8.5

    def test_safety_check_full(self):
        """Test safety check error with all parameters."""
        cause = ValueError("Out of range")
        error = SafetyCheckError(
            "Safety violation",
            check_name="balance_check",
            threshold=100,
            actual_value=50,
            cause=cause
        )
        assert error.details["check_name"] == "balance_check"
        assert error.details["threshold"] == 100
        assert error.details["actual_value"] == 50
        assert error.cause == cause


class TestErrorInheritance:
    """Test exception inheritance chain."""

    def test_all_inherit_from_base(self):
        """Test all custom exceptions inherit from ON1BuilderError."""
        exceptions = [
            ConfigurationError,
            InitializationError,
            ConnectionError,
            TransactionError,
            StrategyExecutionError,
            InsufficientFundsError,
            APICallError,
            ValidationError,
            SafetyCheckError,
        ]
        
        for exc_class in exceptions:
            error = exc_class()
            assert isinstance(error, ON1BuilderError)
            assert isinstance(error, Exception)

    def test_insufficient_funds_inherits_transaction(self):
        """Test InsufficientFundsError inherits from TransactionError."""
        error = InsufficientFundsError()
        assert isinstance(error, TransactionError)
        assert isinstance(error, ON1BuilderError)

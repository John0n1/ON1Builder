"""Comprehensive tests for config/validation module."""
import pytest
from pathlib import Path
from unittest.mock import patch, Mock
from on1builder.config.validation import (
    ConfigValidator,
    validate_complete_config,
)
from on1builder.utils.custom_exceptions import ConfigurationError, ValidationError


class TestValidateWalletAddress:
    """Test wallet address validation."""

    def test_valid_address(self):
        """Test valid Ethereum address."""
        address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7"
        result = ConfigValidator.validate_wallet_address(address)
        assert result == address.lower()

    def test_valid_address_lowercase(self):
        """Test valid lowercase address."""
        address = "0x742d35cc6634c0532925a3b844bc9e7595f0beb7"
        result = ConfigValidator.validate_wallet_address(address)
        assert result == address

    def test_empty_address(self):
        """Test empty address raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_wallet_address("")
        assert "cannot be empty" in str(exc_info.value)

    def test_invalid_format(self):
        """Test invalid address format."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_wallet_address("invalid")
        assert "Invalid wallet address format" in str(exc_info.value)

    def test_missing_0x_prefix(self):
        """Test address without 0x prefix."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_wallet_address("742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    def test_wrong_length(self):
        """Test address with wrong length."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_wallet_address("0x742d35Cc")


class TestValidatePrivateKey:
    """Test private key validation."""

    def test_valid_key_with_prefix(self):
        """Test valid private key with 0x prefix."""
        key = "0x" + "a" * 64
        result = ConfigValidator.validate_private_key(key)
        assert result == "a" * 64
        assert not result.startswith("0x")

    def test_valid_key_without_prefix(self):
        """Test valid private key without prefix."""
        key = "b" * 64
        result = ConfigValidator.validate_private_key(key)
        assert result == key

    def test_empty_key(self):
        """Test empty private key."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_private_key("")
        assert "cannot be empty" in str(exc_info.value)

    def test_invalid_length(self):
        """Test private key with invalid length."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_private_key("0x123")

    def test_invalid_characters(self):
        """Test private key with invalid characters."""
        key = "0x" + "g" * 64  # 'g' is not a hex character
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_private_key(key)
        assert "Invalid private key format" in str(exc_info.value)


class TestValidateChainIds:
    """Test chain ID validation."""

    def test_valid_single_chain(self):
        """Test valid single chain ID."""
        result = ConfigValidator.validate_chain_ids([1])
        assert result == [1]

    def test_valid_multiple_chains(self):
        """Test valid multiple chain IDs."""
        result = ConfigValidator.validate_chain_ids([1, 137, 42161])
        assert set(result) == {1, 137, 42161}

    def test_removes_duplicates(self):
        """Test duplicate chain IDs are removed."""
        result = ConfigValidator.validate_chain_ids([1, 1, 137, 137])
        assert result == [1, 137] or result == [137, 1]
        assert len(result) == 2

    def test_empty_list(self):
        """Test empty chain list raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_chain_ids([])
        assert "At least one chain ID" in str(exc_info.value)

    def test_invalid_chain_id(self):
        """Test invalid chain ID raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_chain_ids([1, 999999])
        assert "Invalid chain IDs" in str(exc_info.value)
        assert "999999" in str(exc_info.value)

    def test_testnet_chains(self):
        """Test testnet chain IDs are valid."""
        result = ConfigValidator.validate_chain_ids([5, 80001])
        assert set(result) == {5, 80001}


class TestValidateRpcUrls:
    """Test RPC URL validation."""

    def test_valid_rpc_urls(self):
        """Test valid RPC URLs."""
        rpc_urls = {
            1: "https://mainnet.infura.io",
            137: "https://polygon-rpc.com"
        }
        result = ConfigValidator.validate_rpc_urls(rpc_urls, [1, 137])
        assert result == rpc_urls

    def test_missing_rpc_for_chain(self):
        """Test missing RPC URL raises error."""
        rpc_urls = {1: "https://mainnet.infura.io"}
        
        with pytest.raises(ConfigurationError) as exc_info:
            ConfigValidator.validate_rpc_urls(rpc_urls, [1, 137])
        
        assert "Missing RPC URLs" in str(exc_info.value)
        assert "137" in str(exc_info.value)

    def test_invalid_url_format_no_protocol(self):
        """Test URL without protocol raises error."""
        rpc_urls = {1: "mainnet.infura.io"}
        
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_rpc_urls(rpc_urls, [1])
        
        assert "must start with http" in str(exc_info.value)

    def test_empty_url(self):
        """Test empty URL raises error."""
        rpc_urls = {1: ""}
        
        with pytest.raises(ValidationError):
            ConfigValidator.validate_rpc_urls(rpc_urls, [1])

    def test_http_and_https_urls(self):
        """Test both HTTP and HTTPS URLs are valid."""
        rpc_urls = {
            1: "https://mainnet.infura.io",
            137: "http://localhost:8545"
        }
        result = ConfigValidator.validate_rpc_urls(rpc_urls, [1, 137])
        assert result == rpc_urls


class TestValidateBalanceThresholds:
    """Test balance threshold validation."""

    def test_valid_thresholds(self):
        """Test valid balance thresholds."""
        # Should not raise
        ConfigValidator.validate_balance_thresholds(0.1, 1.0, 10.0)

    def test_negative_emergency_threshold(self):
        """Test negative emergency threshold raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_balance_thresholds(-1.0, 1.0, 10.0)
        assert "cannot be negative" in str(exc_info.value)

    def test_low_less_than_emergency(self):
        """Test low threshold less than emergency raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_balance_thresholds(2.0, 1.0, 10.0)
        assert "must be greater than emergency" in str(exc_info.value)

    def test_high_less_than_low(self):
        """Test high threshold less than low raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_balance_thresholds(0.1, 10.0, 5.0)
        assert "must be greater than low" in str(exc_info.value)

    def test_equal_thresholds(self):
        """Test equal thresholds raise error."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_balance_thresholds(1.0, 1.0, 10.0)


class TestValidateGasSettings:
    """Test gas settings validation."""

    def test_valid_gas_settings(self):
        """Test valid gas settings."""
        # Should not raise
        ConfigValidator.validate_gas_settings(100, 1.5, 21000)

    def test_zero_max_gas_price(self):
        """Test zero max gas price raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_gas_settings(0, 1.5, 21000)
        assert "must be positive" in str(exc_info.value)

    def test_negative_gas_price(self):
        """Test negative gas price raises error."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_gas_settings(-10, 1.5, 21000)

    def test_very_high_gas_price_warning(self, caplog):
        """Test very high gas price logs warning."""
        ConfigValidator.validate_gas_settings(1500, 1.5, 21000)
        assert "Very high max gas price" in caplog.text

    def test_zero_multiplier(self):
        """Test zero multiplier raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_gas_settings(100, 0, 21000)
        assert "multiplier must be positive" in str(exc_info.value)

    def test_high_multiplier_warning(self, caplog):
        """Test high multiplier logs warning."""
        ConfigValidator.validate_gas_settings(100, 15.0, 21000)
        assert "Very high gas price multiplier" in caplog.text

    def test_zero_gas_limit(self):
        """Test zero gas limit raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_gas_settings(100, 1.5, 0)
        assert "gas limit must be positive" in str(exc_info.value)


class TestValidateProfitSettings:
    """Test profit settings validation."""

    def test_valid_profit_settings(self):
        """Test valid profit settings."""
        # Should not raise
        ConfigValidator.validate_profit_settings(0.01, 5.0, 1.0)

    def test_negative_min_profit(self):
        """Test negative min profit raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_profit_settings(-0.01, 5.0, 1.0)
        assert "cannot be negative" in str(exc_info.value)

    def test_negative_profit_percentage(self):
        """Test negative profit percentage raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_profit_settings(0.01, -5.0, 1.0)
        assert "cannot be negative" in str(exc_info.value)

    def test_invalid_slippage_over_100(self):
        """Test slippage over 100% raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_profit_settings(0.01, 5.0, 150.0)
        assert "between 0 and 100" in str(exc_info.value)

    def test_invalid_slippage_negative(self):
        """Test negative slippage raises error."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_profit_settings(0.01, 5.0, -1.0)

    def test_zero_values_allowed(self):
        """Test zero values are allowed."""
        # Should not raise
        ConfigValidator.validate_profit_settings(0.0, 0.0, 0.0)


class TestValidateMlSettings:
    """Test ML settings validation."""

    def test_valid_ml_settings(self):
        """Test valid ML settings."""
        # Should not raise
        ConfigValidator.validate_ml_settings(0.001, 0.1, 0.95)

    def test_zero_learning_rate(self):
        """Test zero learning rate raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_ml_settings(0, 0.1, 0.95)
        assert "must be between 0 and 1" in str(exc_info.value)

    def test_learning_rate_over_1(self):
        """Test learning rate over 1 raises error."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_ml_settings(1.5, 0.1, 0.95)

    def test_negative_exploration_rate(self):
        """Test negative exploration rate raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_ml_settings(0.001, -0.1, 0.95)
        assert "must be between 0 and 1" in str(exc_info.value)

    def test_exploration_rate_boundaries(self):
        """Test exploration rate boundaries."""
        # 0 and 1 should be valid
        ConfigValidator.validate_ml_settings(0.001, 0.0, 0.95)
        ConfigValidator.validate_ml_settings(0.001, 1.0, 0.95)

    def test_decay_rate_zero(self):
        """Test decay rate of 0 raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_ml_settings(0.001, 0.1, 0)
        assert "must be between 0 and 1" in str(exc_info.value)

    def test_decay_rate_one(self):
        """Test decay rate of 1 raises error."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_ml_settings(0.001, 0.1, 1.0)


class TestValidateNotificationSettings:
    """Test notification settings validation."""

    def test_valid_notification_settings(self):
        """Test valid notification settings."""
        # Should not raise
        ConfigValidator.validate_notification_settings(["slack", "email"], "INFO")

    def test_invalid_level(self):
        """Test invalid notification level raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_notification_settings(["slack"], "INVALID")
        assert "Invalid notification level" in str(exc_info.value)

    def test_case_insensitive_level(self):
        """Test notification level is case insensitive."""
        # Should not raise
        ConfigValidator.validate_notification_settings(["slack"], "info")
        ConfigValidator.validate_notification_settings(["slack"], "WARNING")

    def test_invalid_channel(self):
        """Test invalid notification channel raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_notification_settings(["invalid_channel"], "INFO")
        assert "Invalid notification channels" in str(exc_info.value)

    def test_mixed_valid_invalid_channels(self):
        """Test mix of valid and invalid channels."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_notification_settings(
                ["slack", "invalid", "email"],
                "INFO"
            )
        assert "invalid" in str(exc_info.value)

    def test_all_valid_channels(self):
        """Test all valid channel types."""
        # Should not raise
        ConfigValidator.validate_notification_settings(
            ["slack", "telegram", "discord", "email"],
            "WARNING"
        )


class TestValidateFilePaths:
    """Test file path validation."""

    def test_valid_directory_path(self, tmp_path):
        """Test valid directory path."""
        test_dir = tmp_path / "test_dir"
        paths = {"log_dir": str(test_dir)}
        
        # Should create directory
        ConfigValidator.validate_file_paths(paths)
        assert test_dir.exists()

    def test_existing_directory(self, tmp_path):
        """Test existing directory path."""
        test_dir = tmp_path / "existing"
        test_dir.mkdir()
        
        paths = {"data_directory": str(test_dir)}
        
        # Should not raise
        ConfigValidator.validate_file_paths(paths)

    def test_file_path_creates_parent(self, tmp_path):
        """Test file path creates parent directory."""
        test_file = tmp_path / "subdir" / "file.txt"
        paths = {"config_file": str(test_file)}
        
        # Should create parent directory
        ConfigValidator.validate_file_paths(paths)
        assert test_file.parent.exists()

    def test_invalid_path_creation(self):
        """Test invalid path raises error."""
        paths = {"log_dir": "/invalid/path/that/cannot/be/created"}
        
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_file_paths(paths)
        assert "Cannot create" in str(exc_info.value)

    def test_empty_path_skipped(self):
        """Test empty path is skipped."""
        paths = {"log_dir": ""}
        
        # Should not raise
        ConfigValidator.validate_file_paths(paths)


class TestValidateCompleteConfig:
    """Test complete configuration validation."""

    def test_minimal_valid_config(self):
        """Test minimal valid configuration."""
        config = {
            "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7",
            "wallet_key": "0x" + "a" * 64,
            "chains": [1],
            "rpc_urls": {1: "https://mainnet.infura.io"}
        }
        
        result = validate_complete_config(config)
        assert result["wallet_address"] == config["wallet_address"].lower()
        assert not result["wallet_key"].startswith("0x")

    def test_full_valid_config(self):
        """Test complete valid configuration."""
        config = {
            "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7",
            "wallet_key": "0x" + "a" * 64,
            "chains": [1, 137],
            "rpc_urls": {
                1: "https://mainnet.infura.io",
                137: "https://polygon-rpc.com"
            },
            "emergency_balance_threshold": 0.1,
            "low_balance_threshold": 1.0,
            "high_balance_threshold": 10.0,
            "max_gas_price_gwei": 100,
            "gas_price_multiplier": 1.2,
            "default_gas_limit": 21000,
            "min_profit_eth": 0.01,
            "min_profit_percentage": 5.0,
            "slippage_tolerance": 1.0,
            "ml_learning_rate": 0.001,
            "ml_exploration_rate": 0.1,
            "ml_decay_rate": 0.95
        }
        
        result = validate_complete_config(config)
        assert "wallet_address" in result
        assert "chains" in result

    def test_config_with_validation_error(self):
        """Test configuration with validation error."""
        config = {
            "wallet_address": "invalid_address"
        }
        
        with pytest.raises(ValidationError):
            validate_complete_config(config)

    def test_config_with_missing_rpc(self):
        """Test configuration with missing RPC."""
        config = {
            "chains": [1, 137],
            "rpc_urls": {1: "https://mainnet.infura.io"}
        }
        
        with pytest.raises(ConfigurationError):
            validate_complete_config(config)

    def test_partial_config_validation(self):
        """Test partial configuration is validated correctly."""
        config = {
            "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7",
            "max_gas_price_gwei": 100
        }
        
        # Should only validate fields that are present
        result = validate_complete_config(config)
        assert "wallet_address" in result

    def test_unexpected_error_handling(self):
        """Test unexpected errors are wrapped properly."""
        config = {"wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7"}
        
        with patch.object(ConfigValidator, "validate_wallet_address", side_effect=RuntimeError("Unexpected")):
            with pytest.raises(ConfigurationError) as exc_info:
                validate_complete_config(config)
            
            assert "unexpected error" in str(exc_info.value).lower()

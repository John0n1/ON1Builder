# src/on1builder/config/validation.py
# flake8: noqa E501
"""Configuration validation utilities for ON1Builder."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from ..utils.custom_exceptions import ConfigurationError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class ConfigValidator:
    """Validates configuration settings for ON1Builder."""

    # Chain ID validation ranges
    VALID_CHAIN_IDS = {
        1: "Ethereum Mainnet",
        137: "Polygon",
        42161: "Arbitrum One",
        10: "Optimism",
        56: "BSC",
        43114: "Avalanche",
        250: "Fantom",
        # Add test networks
        5: "Goerli",
        80001: "Mumbai",
        421613: "Arbitrum Goerli",
    }

    # Ethereum address pattern
    ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")

    # Private key pattern (64 hex chars, optionally prefixed with 0x)
    PRIVATE_KEY_PATTERN = re.compile(r"^(0x)?[a-fA-F0-9]{64}$")

    @classmethod
    def validate_wallet_address(cls, address: str) -> str:
        """Validate Ethereum wallet address format."""
        if not address:
            raise ValidationError("Wallet address cannot be empty", field="wallet_address")

        if not cls.ADDRESS_PATTERN.match(address):
            raise ValidationError(
                "Invalid wallet address format. Must be a valid Ethereum address",
                field="wallet_address",
                value=address,
                expected_type="Ethereum address (0x...)",
            )

        return address.lower()

    @classmethod
    def validate_private_key(cls, private_key: str) -> str:
        """Validate private key format."""
        if not private_key:
            raise ValidationError("Private key cannot be empty", field="wallet_key")

        if not cls.PRIVATE_KEY_PATTERN.match(private_key):
            raise ValidationError(
                "Invalid private key format. Must be 64 hex characters",
                field="wallet_key",
                expected_type="64 hex characters (optionally prefixed with 0x)",
            )

        # Remove 0x prefix if present for consistency
        return private_key.replace("0x", "")

    @classmethod
    def validate_chain_ids(cls, chain_ids: List[int]) -> List[int]:
        """Validate list of chain IDs."""
        if not chain_ids:
            raise ValidationError("At least one chain ID must be specified", field="chains")

        invalid_chains = [cid for cid in chain_ids if cid not in cls.VALID_CHAIN_IDS]
        if invalid_chains:
            raise ValidationError(
                f"Invalid chain IDs: {invalid_chains}. "
                f"Supported chains: {list(cls.VALID_CHAIN_IDS.keys())}",
                field="chains",
                value=invalid_chains,
            )

        return list(set(chain_ids))  # Remove duplicates

    @classmethod
    def validate_rpc_urls(cls, rpc_urls: Dict[int, str], chain_ids: List[int]) -> Dict[int, str]:
        """Validate RPC URLs for specified chains."""
        missing_rpcs = [cid for cid in chain_ids if cid not in rpc_urls]
        if missing_rpcs:
            raise ConfigurationError(
                f"Missing RPC URLs for chains: {missing_rpcs}",
                details={"missing_chains": missing_rpcs},
            )

        # Validate URL format
        for chain_id, url in rpc_urls.items():
            if not url or not isinstance(url, str):
                raise ValidationError(
                    f"Invalid RPC URL for chain {chain_id}", field=f"rpc_url_{chain_id}", value=url
                )

            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValidationError(
                    f"RPC URL for chain {chain_id} must start with http:// or https://",
                    field=f"rpc_url_{chain_id}",
                    value=url,
                )

        return rpc_urls

    @classmethod
    def validate_balance_thresholds(
        cls, emergency_threshold: float, low_threshold: float, high_threshold: float
    ) -> None:
        """Validate balance threshold configuration."""
        if emergency_threshold < 0:
            raise ValidationError(
                "Emergency balance threshold cannot be negative",
                field="emergency_balance_threshold",
                value=emergency_threshold,
            )

        if low_threshold <= emergency_threshold:
            raise ValidationError(
                "Low balance threshold must be greater than emergency threshold",
                field="low_balance_threshold",
                value=low_threshold,
            )

        if high_threshold <= low_threshold:
            raise ValidationError(
                "High balance threshold must be greater than low threshold",
                field="high_balance_threshold",
                value=high_threshold,
            )

    @classmethod
    def validate_gas_settings(
        cls, max_gas_price_gwei: int, gas_price_multiplier: float, default_gas_limit: int
    ) -> None:
        """Validate gas-related settings."""
        if max_gas_price_gwei <= 0:
            raise ValidationError(
                "Maximum gas price must be positive",
                field="max_gas_price_gwei",
                value=max_gas_price_gwei,
            )

        if max_gas_price_gwei > 1000:
            logger.warning(f"Very high max gas price: {max_gas_price_gwei} gwei")

        if gas_price_multiplier <= 0:
            raise ValidationError(
                "Gas price multiplier must be positive",
                field="gas_price_multiplier",
                value=gas_price_multiplier,
            )

        if gas_price_multiplier > 10:
            logger.warning(f"Very high gas price multiplier: {gas_price_multiplier}")

        if default_gas_limit <= 0:
            raise ValidationError(
                "Default gas limit must be positive",
                field="default_gas_limit",
                value=default_gas_limit,
            )

    @classmethod
    def validate_profit_settings(
        cls, min_profit_eth: float, min_profit_percentage: float, slippage_tolerance: float
    ) -> None:
        """Validate profit-related settings."""
        if min_profit_eth < 0:
            raise ValidationError(
                "Minimum profit cannot be negative", field="min_profit_eth", value=min_profit_eth
            )

        if min_profit_percentage < 0:
            raise ValidationError(
                "Minimum profit percentage cannot be negative",
                field="min_profit_percentage",
                value=min_profit_percentage,
            )

        if not 0 <= slippage_tolerance <= 100:
            raise ValidationError(
                "Slippage tolerance must be between 0 and 100",
                field="slippage_tolerance",
                value=slippage_tolerance,
            )

    @classmethod
    def validate_ml_settings(
        cls, learning_rate: float, exploration_rate: float, decay_rate: float
    ) -> None:
        """Validate machine learning settings."""
        if not 0 < learning_rate <= 1:
            raise ValidationError(
                "Learning rate must be between 0 and 1",
                field="ml_learning_rate",
                value=learning_rate,
            )

        if not 0 <= exploration_rate <= 1:
            raise ValidationError(
                "Exploration rate must be between 0 and 1",
                field="ml_exploration_rate",
                value=exploration_rate,
            )

        if not 0 < decay_rate < 1:
            raise ValidationError(
                "Decay rate must be between 0 and 1", field="ml_decay_rate", value=decay_rate
            )

    @classmethod
    def validate_notification_settings(cls, channels: List[str], min_level: str) -> None:
        """Validate notification settings."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if min_level.upper() not in valid_levels:
            raise ValidationError(
                f"Invalid notification level: {min_level}. Must be one of {valid_levels}",
                field="min_notification_level",
                value=min_level,
            )

        valid_channels = ["slack", "telegram", "discord", "email"]
        invalid_channels = [ch for ch in channels if ch.lower() not in valid_channels]
        if invalid_channels:
            raise ValidationError(
                f"Invalid notification channels: {invalid_channels}. "
                f"Valid channels: {valid_channels}",
                field="notification_channels",
                value=invalid_channels,
            )

    @classmethod
    def validate_file_paths(cls, paths: Dict[str, Union[str, Path]]) -> None:
        """Validate file paths exist and are accessible."""
        for path_name, path_value in paths.items():
            if not path_value:
                continue

            path = Path(path_value)

            if path_name.endswith("_dir") or path_name.endswith("_directory"):
                # Directory should exist or be creatable
                if not path.exists():
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        raise ValidationError(
                            f"Cannot create directory: {path}",
                            field=path_name,
                            value=str(path),
                            cause=e,
                        )
            else:
                # File should exist or its parent directory should be writable
                if not path.exists():
                    parent = path.parent
                    if not parent.exists():
                        try:
                            parent.mkdir(parents=True, exist_ok=True)
                        except Exception as e:
                            raise ValidationError(
                                f"Cannot create parent directory for {path}",
                                field=path_name,
                                value=str(path),
                                cause=e,
                            )

    def validate_complete_config(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform complete validation of configuration dictionary.

        Args:
            config_dict: Raw configuration dictionary

        Returns:
            Validated and normalized configuration dictionary

        Raises:
            ValidationError: If any validation fails
            ConfigurationError: If configuration is invalid
        """
        logger.info("Performing complete configuration validation")

        try:
            # Validate wallet settings
            if "wallet_address" in config_dict:
                config_dict["wallet_address"] = self.validate_wallet_address(
                    config_dict["wallet_address"]
                )

            if "wallet_key" in config_dict:
                config_dict["wallet_key"] = self.validate_private_key(config_dict["wallet_key"])

            # Validate chain settings
            if "chains" in config_dict:
                config_dict["chains"] = self.validate_chain_ids(config_dict["chains"])

            # Validate RPC URLs
            if "rpc_urls" in config_dict and "chains" in config_dict:
                config_dict["rpc_urls"] = self.validate_rpc_urls(
                    config_dict["rpc_urls"], config_dict["chains"]
                )

            # Validate balance thresholds
            if all(
                k in config_dict
                for k in [
                    "emergency_balance_threshold",
                    "low_balance_threshold",
                    "high_balance_threshold",
                ]
            ):
                self.validate_balance_thresholds(
                    config_dict["emergency_balance_threshold"],
                    config_dict["low_balance_threshold"],
                    config_dict["high_balance_threshold"],
                )

            # Validate gas settings
            if all(
                k in config_dict
                for k in ["max_gas_price_gwei", "gas_price_multiplier", "default_gas_limit"]
            ):
                self.validate_gas_settings(
                    config_dict["max_gas_price_gwei"],
                    config_dict["gas_price_multiplier"],
                    config_dict["default_gas_limit"],
                )

            # Validate profit settings
            if all(
                k in config_dict
                for k in ["min_profit_eth", "min_profit_percentage", "slippage_tolerance"]
            ):
                self.validate_profit_settings(
                    config_dict["min_profit_eth"],
                    config_dict["min_profit_percentage"],
                    config_dict["slippage_tolerance"],
                )

            # Validate ML settings
            if all(
                k in config_dict for k in ["ml_learning_rate", "ml_exploration_rate", "ml_decay_rate"]
            ):
                self.validate_ml_settings(
                    config_dict["ml_learning_rate"],
                    config_dict["ml_exploration_rate"],
                    config_dict["ml_decay_rate"],
                )

            logger.info("Configuration validation completed successfully")
            return config_dict

        except (ValidationError, ConfigurationError) as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during configuration validation: {e}")
            raise ConfigurationError("Configuration validation failed due to unexpected error", cause=e)

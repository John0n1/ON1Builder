#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Union

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
        8453: "Base",
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
            raise ValidationError(
                "Wallet address cannot be empty", field="wallet_address"
            )

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
    def validate_chain_ids(cls, chain_ids: list[int]) -> list[int]:
        """Validate list of chain IDs."""
        if not chain_ids:
            raise ValidationError(
                "At least one chain ID must be specified", field="chains"
            )

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
    def validate_rpc_urls(
        cls, rpc_urls: dict[int, str], chain_ids: list[int]
    ) -> dict[int, str]:
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
                    f"Invalid RPC URL for chain {chain_id}",
                    field=f"rpc_url_{chain_id}",
                    value=url,
                )

            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValidationError(
                    f"RPC URL for chain {chain_id} must start with http:// or https://",
                    field=f"rpc_url_{chain_id}",
                    value=url,
                )

            # Basic sanity checks to catch obvious misconfigurations
            lower = url.lower()
            if "mainnet" in lower and chain_id not in (1,):
                logger.warning(
                    f"RPC URL for chain {chain_id} looks like mainnet: {url}"
                )
            if "goerli" in lower and chain_id not in (5, 420, 421613):
                logger.warning(f"RPC URL for chain {chain_id} looks like Goerli: {url}")
            if "sepolia" in lower and chain_id not in (11155111,):
                logger.warning(
                    f"RPC URL for chain {chain_id} looks like Sepolia: {url}"
                )
            if "bsc" in lower and chain_id not in (56, 97):
                logger.warning(f"RPC URL for chain {chain_id} looks like BSC: {url}")
            if "bitcoin" in lower or "btc" in lower:
                raise ValidationError(
                    f"RPC URL for chain {chain_id} appears to be a Bitcoin RPC, "
                    "which is not supported",
                    field=f"rpc_url_{chain_id}",
                    value=url,
                )
            if "solana" in lower or "sol" in lower:
                raise ValidationError(
                    f"RPC URL for chain {chain_id} appears to be a Solana RPC, "
                    "which is not supported",
                    field=f"rpc_url_{chain_id}",
                    value=url,
                )
            if "polygon" in lower and chain_id not in (137, 80001):
                logger.warning(
                    f"RPC URL for chain {chain_id} looks like Polygon: {url}"
                )
            if "arbitrum" in lower and chain_id not in (42161, 421613):
                logger.warning(
                    f"RPC URL for chain {chain_id} looks like Arbitrum: {url}"
                )
            if "optimism" in lower and chain_id not in (10, 420):
                logger.warning(
                    f"RPC URL for chain {chain_id} looks like Optimism: {url}"
                )
            if "avalanche" in lower and chain_id not in (43114, 43113):
                logger.warning(
                    f"RPC URL for chain {chain_id} looks like Avalanche: {url}"
                )
            if "fantom" in lower and chain_id not in (250, 4002):
                logger.warning(f"RPC URL for chain {chain_id} looks like Fantom: {url}")
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
        cls,
        max_gas_price_gwei: int,
        gas_price_multiplier: float,
        default_gas_limit: int,
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
        cls,
        min_profit_eth: float,
        min_profit_percentage: float,
        slippage_tolerance: float,
    ) -> None:
        """Validate profit-related settings."""
        if min_profit_eth < 0:
            raise ValidationError(
                "Minimum profit cannot be negative",
                field="min_profit_eth",
                value=min_profit_eth,
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
                "Decay rate must be between 0 and 1",
                field="ml_decay_rate",
                value=decay_rate,
            )

    @classmethod
    def validate_notification_settings(
        cls, channels: list[str], min_level: str
    ) -> None:
        """Validate notification settings."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if min_level.upper() not in valid_levels:
            raise ValidationError(
                f"Invalid notification level: {min_level}. Must be one of {valid_levels}",
                field="min_notification_level",
                value=min_level,
            )

        valid_channels = ["slack", "telegram", "discord", "email"]
        normalized = [
            ch.strip() for ch in channels if isinstance(ch, str) and ch.strip()
        ]
        invalid_channels = [ch for ch in normalized if ch.lower() not in valid_channels]
        if invalid_channels:
            raise ValidationError(
                f"Invalid notification channels: {invalid_channels}. "
                f"Valid channels: {valid_channels}",
                field="notification_channels",
                value=invalid_channels,
            )

    @classmethod
    def validate_file_paths(cls, paths: dict[str, Union[str, Path]]) -> None:
        """Validate file paths exist and are accessible."""
        for path_name, path_value in paths.items():
            if not path_value:
                continue

            path = Path(path_value)
            # Windows-specific guard: POSIX-style absolute paths without a drive
            # (e.g. "/invalid/path") are typically unintended and should be rejected early.
            if (
                os.name == "nt"
                and (path.is_absolute() or str(path).startswith(("/", "\\")))
                and path.drive == ""
                and path.anchor in ("/", "\\")
            ):
                raise ValidationError(
                    f"Cannot create directory: {path}",
                    field=path_name,
                    value=str(path),
                )

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

    def validate_complete_config(self, config_dict: dict[str, Any]) -> dict[str, Any]:
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
        logger.debug("Performing complete configuration validation")

        try:
            # Validate wallet settings
            if "wallet_address" in config_dict:
                config_dict["wallet_address"] = self.validate_wallet_address(
                    config_dict["wallet_address"]
                )

            if "wallet_key" in config_dict:
                config_dict["wallet_key"] = self.validate_private_key(
                    config_dict["wallet_key"]
                )

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
                for k in [
                    "max_gas_price_gwei",
                    "gas_price_multiplier",
                    "default_gas_limit",
                ]
            ):
                self.validate_gas_settings(
                    config_dict["max_gas_price_gwei"],
                    config_dict["gas_price_multiplier"],
                    config_dict["default_gas_limit"],
                )

            # Validate profit settings
            if all(
                k in config_dict
                for k in [
                    "min_profit_eth",
                    "min_profit_percentage",
                    "slippage_tolerance",
                ]
            ):
                self.validate_profit_settings(
                    config_dict["min_profit_eth"],
                    config_dict["min_profit_percentage"],
                    config_dict["slippage_tolerance"],
                )

            # Validate submission mode and simulation backend
            if "submission_mode" in config_dict:
                if config_dict["submission_mode"] not in (
                    "public",
                    "private",
                    "bundle",
                ):
                    raise ValidationError(
                        "submission_mode must be 'public', 'private', or 'bundle'",
                        field="submission_mode",
                        value=config_dict["submission_mode"],
                    )
            if "simulation_backend" in config_dict:
                if config_dict["simulation_backend"] not in (
                    "eth_call",
                    "anvil",
                    "tenderly",
                ):
                    raise ValidationError(
                        "simulation_backend must be one of: eth_call, anvil, tenderly",
                        field="simulation_backend",
                        value=config_dict["simulation_backend"],
                    )
            if (
                "submission_mode" in config_dict
                and config_dict["submission_mode"] == "private"
            ):
                if not config_dict.get("private_rpc_url"):
                    raise ValidationError(
                        "private_rpc_url is required when submission_mode is 'private'",
                        field="private_rpc_url",
                    )
            if (
                "submission_mode" in config_dict
                and config_dict["submission_mode"] == "bundle"
            ):
                missing = [
                    k
                    for k in ("bundle_relay_url", "bundle_relay_auth_token")
                    if not config_dict.get(k)
                ]
                if missing:
                    raise ValidationError(
                        f"bundle submission requires: {missing}",
                        field="bundle_submission",
                    )
                if config_dict.get("bundle_target_block_offset", 0) <= 0:
                    raise ValidationError(
                        "bundle_target_block_offset must be > 0",
                        field="bundle_target_block_offset",
                        value=config_dict.get("bundle_target_block_offset"),
                    )
                if config_dict.get("bundle_timeout_seconds", 0) <= 0:
                    raise ValidationError(
                        "bundle_timeout_seconds must be > 0",
                        field="bundle_timeout_seconds",
                        value=config_dict.get("bundle_timeout_seconds"),
                    )
            if config_dict.get("bundle_signer_key"):
                config_dict["bundle_signer_key"] = self.validate_private_key(
                    config_dict["bundle_signer_key"]
                )
            if (
                "simulation_backend" in config_dict
                and config_dict["simulation_backend"] == "tenderly"
            ):
                missing = [
                    key
                    for key in (
                        "tenderly_account_slug",
                        "tenderly_project_slug",
                        "tenderly_access_token",
                    )
                    if not config_dict.get(key)
                ]
                if missing:
                    raise ValidationError(
                        f"Tenderly simulation requires: {missing}",
                        field="tenderly_credentials",
                    )
            if (
                "simulation_concurrency" in config_dict
                and config_dict["simulation_concurrency"] <= 0
            ):
                raise ValidationError(
                    "simulation_concurrency must be > 0",
                    field="simulation_concurrency",
                    value=config_dict.get("simulation_concurrency"),
                )

            # Validate ML settings
            if all(
                k in config_dict
                for k in ["ml_learning_rate", "ml_exploration_rate", "ml_decay_rate"]
            ):
                self.validate_ml_settings(
                    config_dict["ml_learning_rate"],
                    config_dict["ml_exploration_rate"],
                    config_dict["ml_decay_rate"],
                )

            # Validate notification settings (nested or flattened)
            notifications = config_dict.get("notifications")
            if notifications:
                if isinstance(notifications, dict):
                    channels = notifications.get("channels", [])
                    min_level = notifications.get("min_level", "INFO")
                else:
                    channels = getattr(notifications, "channels", [])
                    min_level = getattr(notifications, "min_level", "INFO")
                self.validate_notification_settings(channels, min_level)

            if (
                "notification_channels" in config_dict
                or "min_notification_level" in config_dict
            ):
                raw_channels = config_dict.get("notification_channels", [])
                if isinstance(raw_channels, str):
                    channels = [
                        item.strip() for item in raw_channels.split(",") if item.strip()
                    ]
                else:
                    channels = raw_channels or []
                min_level = config_dict.get("min_notification_level", "INFO")
                self.validate_notification_settings(channels, min_level)

            logger.debug("Configuration validation completed successfully")
            return config_dict

        except (ValidationError, ConfigurationError) as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during configuration validation: {e}")
            raise ConfigurationError(
                "Configuration validation failed due to unexpected error", cause=e
            )


# Provide a module-level wrapper to keep the public API simple
def validate_complete_config(config_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Convenience helper that mirrors :meth:`ConfigValidator.validate_complete_config`.

    The test suite and the settings model expect this symbol to exist at module scope,
    but the original implementation only lived on the ``ConfigValidator`` class which
    caused ``ImportError`` when importing ``validate_complete_config`` directly.
    """
    validator = ConfigValidator()
    return validator.validate_complete_config(config_dict)

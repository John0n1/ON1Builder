# src/on1builder/utils/config_redactor.py
"""Configuration redaction utilities for ON1Builder."""
# flake8: noqa E501
from __future__ import annotations
from typing import Any, Dict


class ConfigRedactor:
    """Utility class for redacting sensitive configuration values."""

    # Define sensitive keys that should be redacted
    SENSITIVE_KEYS = {
        "wallet_key",
        "private_key",
        "secret_key",
        "api_key",
        "token",
        "password",
        "smtp_password",
        "slack_webhook_url",
        "telegram_bot_token",
        "discord_webhook_url",
        "etherscan_api_key",
        "coingecko_api_key",
        "coinmarketcap_api_key",
        "cryptocompare_api_key",
        "infura_project_id",
    }

    REDACTED_VALUE = "[REDACTED]"

    @classmethod
    def redact_config(
        cls, config_dict: Dict[str, Any], show_sensitive: bool = False
    ) -> Dict[str, Any]:
        """
        Recursively redact sensitive values in a configuration dictionary.

        Args:
            config_dict: The configuration dictionary to redact
            show_sensitive: If True, sensitive values are not redacted

        Returns:
            A new dictionary with sensitive values redacted
        """
        if show_sensitive:
            return config_dict

        return cls._redact_recursive(config_dict.copy())

    @classmethod
    def _redact_recursive(cls, obj: Any) -> Any:
        """Recursively redact sensitive values in nested structures."""
        if isinstance(obj, dict):
            redacted = {}
            for key, value in obj.items():
                if cls._is_sensitive_key(key):
                    redacted[key] = cls.REDACTED_VALUE
                else:
                    redacted[key] = cls._redact_recursive(value)
            return redacted
        elif isinstance(obj, list):
            return [cls._redact_recursive(item) for item in obj]
        else:
            return obj

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        """Check if a key is considered sensitive."""
        key_lower = key.lower()
        return any(sensitive in key_lower for sensitive in cls.SENSITIVE_KEYS)

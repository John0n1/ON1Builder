# configuration.py
"""
ON1Builder – Configuration
==========================

Centralised runtime configuration loader.

"""

from __future__ import annotations
import json
import os
import types
from pathlib import Path
from typing import Any, Dict

import dotenv
import yaml
from eth_utils import is_checksum_address, to_checksum_address

from logger_on1 import setup_logging

logger = setup_logging("Configuration", level="DEBUG")


# --------------------------------------------------------------------------- #
# defaults                                                                    #
# --------------------------------------------------------------------------- #

_DEFAULTS: Dict[str, Any] = {
    # gas / profit
    "MAX_GAS_PRICE_GWEI": 500,
    "MAX_GAS_PRICE": 100_000_000_000,
    "BASE_GAS_LIMIT": 21_000,
    "GAS_LIMIT": 1_000_000,
    "SLIPPAGE_DEFAULT": 0.10,
    "SLIPPAGE_LOW_CONGESTION": 0.20,
    "SLIPPAGE_HIGH_CONGESTION": 0.05,
    "MIN_SLIPPAGE": 0.01,
    "MAX_SLIPPAGE": 0.50,
    "MIN_PROFIT": 0.001,
    "MIN_BALANCE": 1e-6,
    # timing / misc
    "MEMORY_CHECK_INTERVAL": 300,
    "COMPONENT_HEALTH_CHECK_INTERVAL": 60,
    "PROFITABLE_TX_PROCESS_TIMEOUT": 1.0,
    "NONCE_CACHE_TTL": 60,
    "NONCE_RETRY_DELAY": 1,
    "NONCE_MAX_RETRIES": 5,
    "NONCE_TRANSACTION_TIMEOUT": 120,
    "SAFETYNET_CACHE_TTL": 300,
    "SAFETYNET_GAS_PRICE_TTL": 30,
    # Web3
    "WEB3_MAX_RETRIES": 3,
    "WEB3_RETRY_DELAY": 2,
}

_PATH_KEYS = {
    "ERC20_ABI",
    "AAVE_FLASHLOAN_ABI",
    "AAVE_POOL_ABI",
    "UNISWAP_ABI",
    "SUSHISWAP_ABI",
    "ERC20_SIGNATURES",
    "TOKEN_ADDRESSES",
    "TOKEN_SYMBOLS",
    "GAS_PRICE_ORACLE_ABI",
}

_ADDR_KEYS = {
    "WALLET_ADDRESS",
    "UNISWAP_ADDRESS",
    "SUSHISWAP_ADDRESS",
    "AAVE_POOL_ADDRESS",
    "AAVE_FLASHLOAN_ADDRESS",
    "GAS_PRICE_ORACLE_ADDRESS",
    "WETH_ADDRESS",
    "USDC_ADDRESS",
    "USDT_ADDRESS",
}

# --------------------------------------------------------------------------- #
# helper                                                                      #
# --------------------------------------------------------------------------- #


def _checksum(addr: str, key_name: str) -> str:
    if not addr:
        return ""
    if not addr.startswith("0x") or len(addr) != 42:
        raise ValueError(f"{key_name}: invalid address '{addr}'")
    return addr if is_checksum_address(addr) else to_checksum_address(addr)


# --------------------------------------------------------------------------- #
# main class                                                                  #
# --------------------------------------------------------------------------- #


class Configuration(types.SimpleNamespace):  # noqa: D101 – docstring above
    BASE_PATH: Path = Path(__file__).parent.parent.parent  # project root
    ML_PATH: str = "/data/ml/training_data.csv"  # Initialize here

    def __init__(
        self,
        env_path: str | Path = "config/template.env",
        yaml_file: str | Path = "config/config.yaml",
        environment: str = "development",
        **overrides: Any,
    ) -> None:
        super().__init__()
        self._env_path = Path(env_path)
        self._yaml_file = Path(yaml_file)
        self._environment = environment
        self._raw: Dict[str, Any] = {}
        self._load(overrides)

    # ------------------------------------------------------------------ #
    # public API                                                         #
    # ------------------------------------------------------------------ #

    async def load(self) -> None:
        """Legacy coroutine kept for backward-compat; now a no-op."""
        return None

    async def reload(self) -> None:
        """Hot reload from YAml/env; keeps existing object identity."""
        self._load()
        logger.info("Configuration reloaded successfully")

    # ------------------------------------------------------------------ #
    # internals                                                          #
    # ------------------------------------------------------------------ #

    def _load(self, overrides: Dict[str, Any] | None = None) -> None:
        overrides = overrides or {}
        dotenv.load_dotenv(self._env_path, override=False)

        # 1) defaults
        data: Dict[str, Any] = dict(_DEFAULTS)

        # 2) YAml
        if self._yaml_file.exists():
            try:
                yaml_data = yaml.safe_load(self._yaml_file.read_text()) or {}
                data.update(yaml_data.get(self._environment, {}))
            except Exception as exc:
                logger.error("Config YAml parse error: %s", exc)

        # 3) .env
        for k in set(os.environ):  # env vars are *uppercase* already
            if k in data or k in _PATH_KEYS or k in _ADDR_KEYS:
                data[k] = os.environ[k]

        # 4) explicit kwargs
        data.update(overrides)

        # path fix-ups -------------------------------------------------
        for key in _PATH_KEYS:
            if key in data and data[key]:
                path = self.BASE_PATH / str(data[key])
                if not path.exists():
                    logger.warning("%s file missing: %s", key, path)
                data[key] = str(path.resolve())

        # checksum addresses ------------------------------------------
        for key in _ADDR_KEYS:
            if key in data:
                try:
                    data[key] = _checksum(str(data[key]), key)
                except ValueError as exc:
                    logger.warning("%s – set to empty. (%s)", key, exc)
                    data[key] = ""

        # expose as attributes
        self.__dict__.update(data)
        self._raw = data  # keep original mapping for debug

        # make sure linear-regression folder exists
        lr_dir = Path(self.ML_PATH)
        lr_dir.mkdir(parents=True, exist_ok=True)

        logger.debug("Configuration loaded (%d keys)", len(data))

    # ------------------------------------------------------------------ #
    # helpers for JSON resources                                         #
    # ------------------------------------------------------------------ #

    async def _load_json(self, file_path: str | Path) -> Any:
        path = Path(file_path)
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            logger.error("JSON resource missing: %s", path)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error [%s]: %s", path.name, exc)
        return {}

    async def _load_json_safe(self, path: str, name: str = "") -> Dict[str, Any]:
        return await self._load_json(path)

    # ------------------------------------------------------------------ #
    # dunder helpers                                                     #
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:  # noqa: D401
        keys = ("HTTP_ENDPOINT", "WEBSOCKET_ENDPOINT", "INFURA_PROJECT_ID")
        preview = ", ".join(f"{k}={getattr(self, k, '')!s}" for k in keys)
        return f"<Configuration {preview} …>"


# lint-friendly re-export for older code: get_config_value()
def get_config_value(cfg: Configuration, key: str, default: Any | None = None) -> Any:
    return getattr(cfg, key, default)

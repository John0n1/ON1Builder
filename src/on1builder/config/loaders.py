"""
Configuration loaders for YAML files and environment variables.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ..utils.logging_config import get_logger
from .settings import ChainSettings, GlobalSettings, MultiChainSettings

logger = get_logger(__name__)


class ConfigLoader:
    """Loads and manages configuration from various sources."""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = (
            base_path or Path(__file__).resolve().parent.parent.parent.parent
        )
        self.config_dir = self.base_path / "configs"

    def load_global_config(self, config_path: Optional[str] = None) -> GlobalSettings:
        """Load global configuration settings."""

        # Start with defaults
        config_data = {}

        # Load common settings if they exist
        common_path = self.config_dir / "common_settings.yaml"
        if common_path.exists():
            config_data.update(self._load_yaml(common_path))

        # Load specific config file if provided
        if config_path:
            config_path_obj = Path(config_path)
            if not config_path_obj.is_absolute():
                config_path_obj = self.config_dir / config_path

            if config_path_obj.exists():
                config_data.update(self._load_yaml(config_path_obj))

        # Override with environment variables
        config_data.update(self._load_from_env())

        # Set base_path
        config_data["base_path"] = self.base_path

        return GlobalSettings(**config_data)

    def load_multi_chain_config(
        self, config_path: Optional[str] = None
    ) -> MultiChainSettings:
        """Load multi-chain configuration."""

        # Use default multi-chain config if not specified
        if not config_path:
            config_path = "chains/config_multi_chain.yaml"

        config_data = {}

        # Load common settings first
        common_path = self.config_dir / "common_settings.yaml"
        if common_path.exists():
            config_data.update(self._load_yaml(common_path))

        # Load multi-chain specific config
        config_path_obj = Path(config_path)
        if not config_path_obj.is_absolute():
            config_path_obj = self.config_dir / config_path

        if config_path_obj.exists():
            config_data.update(self._load_yaml(config_path_obj))

        # Override with environment variables
        config_data.update(self._load_from_env())

        # Set base_path
        config_data["base_path"] = self.base_path

        return MultiChainSettings(**config_data)

    def load_chain_config(self, chain_name: str) -> ChainSettings:
        """Load configuration for a specific chain."""

        chain_config_path = self.config_dir / "chains" / f"{chain_name}.yaml"

        if not chain_config_path.exists():
            raise FileNotFoundError(
                f"Chain configuration not found: {chain_config_path}"
            )

        config_data = self._load_yaml(chain_config_path)
        config_data["name"] = chain_name

        return ChainSettings(**config_data)

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML configuration file."""
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
                logger.debug(f"Loaded YAML config from {path}")
                return data
        except Exception as e:
            logger.error(f"Failed to load YAML config from {path}: {e}")
            return {}

    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}

        # Known configuration keys that can be loaded from environment
        env_mappings = {
            # Debug
            "DEBUG": ("debug", bool),
            # Trading
            "MIN_PROFIT": ("min_profit", float),
            "WALLET_KEY": ("wallet_key", str),
            # Connection
            "CONNECTION_RETRY_COUNT": ("connection_retry_count", int),
            "CONNECTION_RETRY_DELAY": ("connection_retry_delay", float),
            "WEB3_MAX_RETRIES": ("web3_max_retries", int),
            # Transaction
            "TRANSACTION_RETRY_COUNT": ("transaction_retry_count", int),
            "TRANSACTION_RETRY_DELAY": ("transaction_retry_delay", float),
            # Mempool
            "MEMPOOL_RETRY_DELAY": ("mempool_retry_delay", float),
            "MEMPOOL_MAX_RETRIES": ("mempool_max_retries", int),
            "MEMPOOL_MAX_PARALLEL_TASKS": ("mempool_max_parallel_tasks", int),
            # Safety net
            "SAFETYNET_CACHE_TTL": ("safetynet_cache_ttl", int),
            "SAFETYNET_GAS_PRICE_TTL": ("safetynet_gas_price_ttl", int),
            # System
            "MEMORY_CHECK_INTERVAL": ("memory_check_interval", int),
            "MARKET_CACHE_TTL": ("market_cache_ttl", int),
        }

        # Load API settings into nested structure
        api_config = {}
        api_env_mappings = {
            "COINGECKO_API_KEY": "coingecko_api_key",
            "COINMARKETCAP_API_KEY": "coinmarketcap_api_key",
            "CRYPTOCOMPARE_API_KEY": "cryptocompare_api_key",
            "ETHERSCAN_API_KEY": "etherscan_api_key",
            "INFURA_PROJECT_ID": "infura_project_id",
            "INFURA_API_KEY": "infura_api_key",
            "GRAPH_API_KEY": "graph_api_key",
            "UNISWAP_V2_SUBGRAPH_ID": "uniswap_v2_subgraph_id",
        }

        # Load general config
        for env_key, (config_key, value_type) in env_mappings.items():
            env_val = os.getenv(env_key)
            if env_val is not None:
                try:
                    if value_type == bool:
                        config[config_key] = env_val.lower() in ("true", "1", "yes")
                    elif value_type == int:
                        config[config_key] = int(env_val)
                    elif value_type == float:
                        config[config_key] = float(env_val)
                    else:
                        config[config_key] = env_val

                    # Mask sensitive values in logs
                    if config_key == "wallet_key":
                        logger.debug(f"Loaded {config_key}=<REDACTED>")
                    else:
                        logger.debug(f"Loaded {config_key}={config[config_key]}")

                except ValueError as e:
                    logger.warning(
                        f"Invalid env var format for {env_key}={env_val}: {e}"
                    )

        # Load API config
        for env_key, config_key in api_env_mappings.items():
            env_val = os.getenv(env_key)
            if env_val is not None:
                api_config[config_key] = env_val
                logger.debug(f"Loaded API key {config_key}=<REDACTED>")

        if api_config:
            config["api"] = api_config

        return config


# Global instance of config loader for convenience
_config_loader = None


def get_config_loader() -> ConfigLoader:
    """Get a global instance of the ConfigLoader."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def load_configuration(
    config_path: Optional[str] = None, chain: Optional[str] = None
) -> Dict[str, Any]:
    """
    Load configuration from files and environment variables.

    Args:
        config_path: Path to configuration file (optional)
        chain: Chain name for chain-specific config (optional)

    Returns:
        Dictionary containing merged configuration data
    """
    loader = get_config_loader()

    try:
        # Load global configuration
        global_config = loader.load_global_config(config_path)
        config_dict = global_config.dict()

        # If chain is specified, try to load chain-specific config
        if chain:
            try:
                chain_config = loader.load_chain_config(chain)
                # Merge chain config into global config
                config_dict.update(chain_config.dict())
            except Exception as e:
                logger.warning(f"Failed to load chain config for {chain}: {e}")

        return config_dict

    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        # Return minimal default configuration
        return {
            "debug": False,
            "base_path": Path(__file__).resolve().parent.parent.parent.parent,
        }


def load_global_settings(config_path: Optional[str] = None) -> GlobalSettings:
    """Load global settings from configuration files."""
    loader = get_config_loader()
    return loader.load_global_config(config_path)


def load_multi_chain_settings(config_path: Optional[str] = None) -> MultiChainSettings:
    """Load multi-chain settings from configuration files."""
    loader = get_config_loader()
    return loader.load_multi_chain_config(config_path)


def load_chain_settings(chain_name: str) -> ChainSettings:
    """Load settings for a specific chain."""
    loader = get_config_loader()
    return loader.load_chain_config(chain_name)

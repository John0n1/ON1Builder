#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ON1Builder – Configuration with Multi-Chain Support
=================================================
Loads and manages configuration with support for multiple chains.
"""

import os
import yaml
import dotenv
import logging
import types
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger("Configuration")

# Default values for configuration
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
    # API endpoints and keys
    "HTTP_ENDPOINT": "https://eth-sepolia.g.alchemy.com/v2/demo",  # Sepolia testnet fallback
    "WEBSOCKET_ENDPOINT": "wss://eth-sepolia.g.alchemy.com/v2/demo",  # Sepolia testnet fallback
    "GRAPH_API_KEY": "",
    "ETHERSCAN_API_KEY": "",
    # Execution control
    "DRY_RUN": True,  # Default to dry run mode (no real transactions)
    "GO_LIVE": False,  # Default to not sending real transactions
    # Vault settings
    "VAULT_ADDR": "http://localhost:8200",  # Default Vault address
    "VAULT_TOKEN": "",  # Default empty token
    "VAULT_PATH": "secret/on1builder",  # Default secret path
    # Multi-chain settings
    "CHAINS": "",  # Default to empty string (no chains)
    "CHAIN_ID": "1",  # Default to Ethereum mainnet
    "CHAIN_NAME": "Ethereum",  # Default to Ethereum
}

# Keys that represent file paths
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

# Keys that represent Ethereum addresses
_ADDR_KEYS = {
    "WALLET_ADDRESS",
    "UNISWAP_ADDRESS",
    "SUSHISWAP_ADDRESS",
    "AAVE_POOL_ADDRESS",
    "AAVE_FLASHLOAN_ADDRESS",
    "GAS_PRICE_ORACLE_ADDRESS",
}

# Keys that represent secrets
_SECRET_KEYS = {
    "WALLET_KEY",
    "INFURA_API_KEY",
    "ALCHEMY_API_KEY",
    "ETHERSCAN_API_KEY",
    "GRAPH_API_KEY",
    "COINMARKETCAP_API_KEY",
    "CRYPTOCOMPARE_API_KEY",
    "SLACK_WEBHOOK_URL",
    "SMTP_PASSWORD",
}

# Chain-specific configuration prefixes
_CHAIN_PREFIXES = [
    "CHAIN_1_",  # Ethereum Mainnet
    "CHAIN_5_",  # Goerli Testnet
    "CHAIN_11155111_",  # Sepolia Testnet
    "CHAIN_137_",  # Polygon Mainnet
    "CHAIN_80001_",  # Mumbai Testnet
    "CHAIN_56_",  # Binance Smart Chain Mainnet
    "CHAIN_97_",  # Binance Smart Chain Testnet
    "CHAIN_42161_",  # Arbitrum One
    "CHAIN_421613_",  # Arbitrum Goerli
    "CHAIN_10_",  # Optimism
    "CHAIN_420_",  # Optimism Goerli
    "CHAIN_43114_",  # Avalanche C-Chain
    "CHAIN_43113_",  # Avalanche Fuji Testnet
]

def _get_vault_secret(vault_addr: str, vault_token: str, vault_path: str, key: str) -> Optional[str]:
    """Get a secret from HashiCorp Vault.
    
    Args:
        vault_addr: The Vault server address
        vault_token: The Vault token
        vault_path: The path to the secret in Vault
        key: The key of the secret
        
    Returns:
        The secret value, or None if not found
    """
    try:
        import hvac
        client = hvac.Client(url=vault_addr, token=vault_token)
        if not client.is_authenticated():
            logger.error("Failed to authenticate with Vault")
            return None
        
        secret = client.secrets.kv.v2.read_secret_version(path=vault_path)
        if not secret or "data" not in secret or "data" not in secret["data"]:
            logger.error(f"Secret not found at {vault_path}")
            return None
        
        return secret["data"]["data"].get(key)
    except Exception as e:
        logger.error(f"Error getting secret from Vault: {e}")
        return None

def _checksum(address: str, key: str) -> str:
    """Convert an Ethereum address to checksum format.
    
    Args:
        address: The Ethereum address
        key: The key of the address (for logging)
        
    Returns:
        The checksum address
        
    Raises:
        ValueError: If the address is invalid
    """
    try:
        from web3 import Web3
        if not address or not address.startswith("0x"):
            raise ValueError(f"Invalid Ethereum address: {address}")
        return Web3.to_checksum_address(address)
    except Exception as e:
        raise ValueError(f"Invalid Ethereum address for {key}: {e}")

class MultiChainConfiguration(types.SimpleNamespace):
    """Configuration class with multi-chain support."""

    BASE_PATH: Path = Path(__file__).parent.parent.parent  # project root

    # ML-related settings
    ML_PATH: str = os.path.join(
        str(Path(__file__).parent.parent.parent), "data/ml"
    )  # Relative path to ml directory
    MODEL_PATH: str = os.path.join(
        str(Path(__file__).parent.parent.parent), "data/ml/price_model.joblib"
    )  # Path to the price model
    TRAINING_DATA_PATH: str = os.path.join(
        str(Path(__file__).parent.parent.parent), "data/ml/training_data.csv"
    )  # Path to the training data
    MODEL_RETRAINING_INTERVAL: int = 3600  # 1 hour retraining interval
    MIN_TRAINING_SAMPLES: int = 100  # Minimum 100 training samples
    MODEL_ACCURACY_THRESHOLD: float = 0.7  # 70% accuracy threshold
    PREDICTION_CACHE_TTL: int = 300  # 5 minute cache TTL

    # Mempool-related settings
    MEMPOOL_MAX_PARALLEL_TASKS: int = 5  # Maximum number of parallel tasks
    MEMPOOL_MAX_RETRIES: int = 3  # Maximum number of retries
    MEMPOOL_RETRY_DELAY: int = 1  # Retry delay in seconds

    def __init__(
        self,
        env_path: str | Path = "config/template.env",
        yaml_file: str | Path = "config/config_multi_chain.yaml",
        environment: str = "development",
        **overrides: Any,
    ) -> None:
        super().__init__()
        self._env_path = Path(env_path)
        self._yaml_file = Path(yaml_file)
        self._environment = environment
        self._raw: Dict[str, Any] = {}
        self._chains: List[Dict[str, Any]] = []
        self._load(overrides)
        self._parse_chains()

    # ------------------------------------------------------------------ #
    # public API                                                         #
    # ------------------------------------------------------------------ #

    async def load(self) -> None:
        """Legacy coroutine kept for backward-compat; now a no-op."""
        return None

    async def reload(self) -> None:
        """Hot reload from YAml/env; keeps existing object identity."""
        self._load()
        self._parse_chains()
        logger.info("Configuration reloaded successfully")

    def get_chains(self) -> List[Dict[str, Any]]:
        """Get the list of configured chains.
        
        Returns:
            A list of chain configurations
        """
        return self._chains

    # ------------------------------------------------------------------ #
    # private implementation                                             #
    # ------------------------------------------------------------------ #

    def _load(self, overrides: Dict[str, Any] | None = None) -> None:
        """Load configuration from defaults, YAml, env, and overrides.
        
        Args:
            overrides: Optional dictionary of configuration overrides
        """
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
            if k in data or k in _PATH_KEYS or k in _ADDR_KEYS or k in _SECRET_KEYS:
                data[k] = os.environ[k]
            # Also load chain-specific configuration
            for prefix in _CHAIN_PREFIXES:
                if k.startswith(prefix):
                    data[k] = os.environ[k]

        # 4) explicit kwargs
        data.update(overrides)

        # 5) Load secrets from Vault if GO_LIVE is true
        go_live = data.get("GO_LIVE", False)
        if go_live and isinstance(go_live, str):
            go_live = go_live.lower() == "true"
            
        if go_live:
            logger.info("GO_LIVE is true, loading secrets from Vault")
            vault_addr = data.get("VAULT_ADDR")
            vault_token = data.get("VAULT_TOKEN")
            vault_path = data.get("VAULT_PATH", "secret/on1builder")
            
            if vault_addr and vault_token:
                for key in _SECRET_KEYS:
                    secret_value = _get_vault_secret(vault_addr, vault_token, vault_path, key)
                    if secret_value:
                        logger.info(f"Loaded {key} from Vault")
                        data[key] = secret_value
                
                # Load chain-specific secrets
                chains = data.get("CHAINS", "")
                if chains:
                    chain_ids = [c.strip() for c in chains.split(",")]
                    for chain_id in chain_ids:
                        chain_path = f"{vault_path}/chain_{chain_id}"
                        for key in _SECRET_KEYS:
                            secret_key = f"CHAIN_{chain_id}_{key}"
                            secret_value = _get_vault_secret(vault_addr, vault_token, chain_path, key)
                            if secret_value:
                                logger.info("Loaded a secret for a chain-specific key from Vault")
                                data[secret_key] = secret_value
            else:
                logger.warning("VAULT_ADDR or VAULT_TOKEN not set, skipping Vault secret loading")

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
            
            # Also checksum chain-specific addresses
            for prefix in _CHAIN_PREFIXES:
                chain_key = f"{prefix}{key}"
                if chain_key in data:
                    try:
                        data[chain_key] = _checksum(str(data[chain_key]), chain_key)
                    except ValueError as exc:
                        logger.warning("%s – set to empty. (%s)", chain_key, exc)
                        data[chain_key] = ""

        # store raw data and update self ------------------------------
        self._raw = data
        for k, v in data.items():
            setattr(self, k, v)
    
    def _parse_chains(self) -> None:
        """Parse the chains configuration."""
        chains = []
        
        # Check if CHAINS is defined
        chains_str = getattr(self, "CHAINS", "")
        if chains_str:
            # Parse comma-separated list of chain IDs
            chain_ids = [c.strip() for c in chains_str.split(",")]
            for chain_id in chain_ids:
                # Create chain configuration
                chain_config = {
                    "CHAIN_ID": chain_id,
                    "CHAIN_NAME": getattr(self, f"CHAIN_{chain_id}_CHAIN_NAME", f"Chain {chain_id}"),
                }
                
                # Add chain-specific configuration
                for key in self._raw:
                    prefix = f"CHAIN_{chain_id}_"
                    if key.startswith(prefix):
                        config_key = key[len(prefix):]
                        chain_config[config_key] = getattr(self, key)
                
                # Add global configuration as fallback
                for key in _DEFAULTS:
                    if key not in chain_config and hasattr(self, key):
                        chain_config[key] = getattr(self, key)
                
                chains.append(chain_config)
        
        # If no chains were configured, use global configuration as a single chain
        if not chains:
            chain_config = {
                "CHAIN_ID": getattr(self, "CHAIN_ID", "1"),
                "CHAIN_NAME": getattr(self, "CHAIN_NAME", "Ethereum"),
            }
            
            # Add global configuration
            for key in self._raw:
                if key not in ["CHAINS", "CHAIN_ID", "CHAIN_NAME"] and key not in chain_config:
                    chain_config[key] = getattr(self, key)
            
            chains.append(chain_config)
        
        self._chains = chains
        logger.info(f"Parsed {len(chains)} chains: {', '.join(c.get('CHAIN_NAME', 'Unknown') for c in chains)}")

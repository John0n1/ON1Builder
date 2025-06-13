# src/on1builder/integrations/abi_registry.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from on1builder.utils.logging_config import get_logger
from on1builder.utils.path_helpers import get_resource_dir, get_monitored_tokens_path
from on1builder.utils.singleton import SingletonMeta

logger = get_logger(__name__)

class ABIRegistry(metaclass=SingletonMeta):
    """
    A singleton registry for managing and providing access to contract ABIs and token data.
    It loads all resources on first initialization.
    """

    def __init__(self):
        self._abis: Dict[str, List[Dict[str, Any]]] = {}
        self._tokens: List[Dict[str, Any]] = []
        self._token_map_by_symbol: Dict[int, Dict[str, str]] = {}  # chain_id -> {SYMBOL: address}
        self._token_map_by_address: Dict[int, Dict[str, str]] = {} # chain_id -> {address: SYMBOL}
        self._loaded = False
        self._load_all_resources()

    def _load_all_resources(self) -> None:
        """Loads all ABIs and token data from the resources directory."""
        if self._loaded:
            return
            
        logger.info("Initializing ABIRegistry: Loading all ABIs and token data...")
        
        # Load ABIs
        abi_dir = get_resource_dir() / "abi"
        if not abi_dir.is_dir():
            logger.warning(f"ABI directory not found at: {abi_dir}")
        else:
            for file_path in abi_dir.glob("*.json"):
                try:
                    name = file_path.stem.lower().replace("_abi", "")
                    with open(file_path, "r") as f:
                        abi_data = json.load(f)
                        # ABI can be a list directly or inside an 'abi' key
                        self._abis[name] = abi_data if isinstance(abi_data, list) else abi_data.get("abi", [])
                        if not self._abis[name]:
                             logger.warning(f"No ABI content found for '{name}' in {file_path}")
                except (json.JSONDecodeError, IOError) as e:
                    logger.error(f"Failed to load or parse ABI file {file_path}: {e}")
        
        logger.info(f"Loaded {len(self._abis)} contract ABIs.")

        # Load Tokens
        tokens_file_path = get_monitored_tokens_path()
        if not tokens_file_path.exists():
            logger.warning(f"Monitored tokens file not found at: {tokens_file_path}")
        else:
            try:
                with open(tokens_file_path, "r") as f:
                    self._tokens = json.load(f)
                self._build_token_maps()
                logger.info(f"Loaded and mapped {len(self._tokens)} tokens.")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load or parse tokens file {tokens_file_path}: {e}")

        self._loaded = True

    def _build_token_maps(self):
        """Builds hashmaps for quick token lookups by symbol and address."""
        for token_data in self._tokens:
            symbol = token_data.get("symbol")
            if not symbol:
                continue

            for chain_id_str, address in token_data.get("addresses", {}).items():
                try:
                    chain_id = int(chain_id_str)
                    
                    # Map by symbol
                    if chain_id not in self._token_map_by_symbol:
                        self._token_map_by_symbol[chain_id] = {}
                    self._token_map_by_symbol[chain_id][symbol.upper()] = address.lower()
                    
                    # Map by address
                    if chain_id not in self._token_map_by_address:
                        self._token_map_by_address[chain_id] = {}
                    self._token_map_by_address[chain_id][address.lower()] = symbol.upper()
                except ValueError:
                    logger.warning(f"Invalid chain ID '{chain_id_str}' for token {symbol}")

    def get_abi(self, name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a contract ABI by its common name.
        
        Args:
            name: The name of the contract (e.g., 'uniswap_v2_router', 'erc20').
        
        Returns:
            The contract ABI as a list of dictionaries, or None if not found.
        """
        return self._abis.get(name.lower().replace("_abi", ""))

    def get_token_address(self, symbol: str, chain_id: int) -> Optional[str]:
        """
        Retrieves a token's contract address for a specific chain.
        
        Args:
            symbol: The token's symbol (e.g., 'WETH', 'USDC'). Case-insensitive.
            chain_id: The integer ID of the blockchain.
        
        Returns:
            The token's checksummed address as a string, or None if not found.
        """
        return self._token_map_by_symbol.get(chain_id, {}).get(symbol.upper())

    def get_token_symbol(self, address: str, chain_id: int) -> Optional[str]:
        """
        Retrieves a token's symbol from its contract address for a specific chain.
        
        Args:
            address: The token's contract address. Case-insensitive.
            chain_id: The integer ID of the blockchain.
        
        Returns:
            The token's symbol as a string, or None if not found.
        """
        return self._token_map_by_address.get(chain_id, {}).get(address.lower())

    def get_monitored_tokens(self, chain_id: int) -> Dict[str, str]:
        """
        Returns a dictionary of all monitored tokens (symbol: address) for a given chain.
        
        Args:
            chain_id: The integer ID of the blockchain.
            
        Returns:
            A dictionary mapping uppercase token symbols to lowercase addresses.
        """
        return self._token_map_by_symbol.get(chain_id, {})
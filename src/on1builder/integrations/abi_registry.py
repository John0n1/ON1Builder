#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import json
from typing import Any

from on1builder.utils.logging_config import get_logger
from on1builder.utils.path_helpers import get_monitored_tokens_path, get_resource_dir
from on1builder.utils.singleton import SingletonMeta

logger = get_logger(__name__)


class ABIRegistry(metaclass=SingletonMeta):
    """
    A singleton registry for managing and providing access to contract ABIs and token data.
    It loads all resources on first initialization.
    """

    def __init__(self):
        self._abis: dict[str, list[dict[str, Any]]] = {}
        self._tokens: list[dict[str, Any]] = []
        self._token_map_by_symbol: dict[int, dict[str, str]] = (
            {}
        )  # chain_id -> {SYMBOL: address}
        self._token_map_by_address: dict[int, dict[str, str]] = (
            {}
        )  # chain_id -> {address: SYMBOL}
        self._token_info_by_address: dict[int, dict[str, dict[str, Any]]] = (
            {}
        )  # chain_id -> {address: info}
        self._loaded = False
        self._load_all_resources()

    def _load_all_resources(self) -> None:
        """Loads all ABIs and token data from the resources directory."""
        if self._loaded:
            return

        logger.debug("Initializing ABIRegistry: Loading all ABIs and token data...")

        # Load ABIs
        abi_dir = get_resource_dir() / "abi"
        if not abi_dir.is_dir():
            logger.warning(f"ABI directory not found at: {abi_dir}")
        else:
            for file_path in abi_dir.glob("*.json"):
                try:
                    name = file_path.stem.lower().replace("_abi", "")
                    with open(file_path) as f:
                        abi_data = json.load(f)
                        # ABI can be a list directly or inside an 'abi' key
                        self._abis[name] = (
                            abi_data
                            if isinstance(abi_data, list)
                            else abi_data.get("abi", [])
                        )
                        if not self._abis[name]:
                            logger.warning(
                                f"No ABI content found for '{name}' in {file_path}"
                            )
                except (OSError, json.JSONDecodeError) as e:
                    logger.error(f"Failed to load or parse ABI file {file_path}: {e}")

        logger.debug("Loaded %s contract ABIs.", len(self._abis))

        # Load Tokens
        tokens_file_path = get_monitored_tokens_path()
        if not tokens_file_path.exists():
            logger.warning(f"Monitored tokens file not found at: {tokens_file_path}")
        else:
            try:
                with open(tokens_file_path) as f:
                    self._tokens = json.load(f)
                self._build_token_maps()
                logger.debug("Loaded and mapped %s tokens.", len(self._tokens))
            except (OSError, json.JSONDecodeError) as e:
                logger.error(
                    f"Failed to load or parse tokens file {tokens_file_path}: {e}"
                )

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
                    self._token_map_by_symbol[chain_id][
                        symbol.upper()
                    ] = address.lower()

                    # Map by address
                    if chain_id not in self._token_map_by_address:
                        self._token_map_by_address[chain_id] = {}
                    self._token_map_by_address[chain_id][
                        address.lower()
                    ] = symbol.upper()

                    # Store token info for quick lookup (including decimals/name where available)
                    if chain_id not in self._token_info_by_address:
                        self._token_info_by_address[chain_id] = {}
                    self._token_info_by_address[chain_id][address.lower()] = {
                        "symbol": symbol.upper(),
                        "address": address.lower(),
                        "chain_id": chain_id,
                        "name": token_data.get("name"),
                        "decimals": token_data.get("decimals", 18),
                        "api_ids": token_data.get("api_ids", {}),
                    }
                except ValueError:
                    logger.warning(
                        f"Invalid chain ID '{chain_id_str}' for token {symbol}"
                    )

    def get_abi(self, name: str) -> list[dict[str, Any]] | None:
        """
        Retrieves a contract ABI by its common name.

        Args:
            name: The name of the contract (e.g., 'uniswap_v2_router', 'erc20').

        Returns:
            The contract ABI as a list of dictionaries, or None if not found.
        """
        return self._abis.get(name.lower().replace("_abi", ""))

    def get_token_address(self, symbol: str, chain_id: int) -> str | None:
        """
        Retrieves a token's contract address for a specific chain.

        Args:
            symbol: The token's symbol (e.g., 'WETH', 'USDC'). Case-insensitive.
            chain_id: The integer ID of the blockchain.

        Returns:
            The token's checksummed address as a string, or None if not found.
        """
        return self._token_map_by_symbol.get(chain_id, {}).get(symbol.upper())

    def get_token_symbol(self, address: str, chain_id: int) -> str | None:
        """
        Retrieves a token's symbol from its contract address for a specific chain.

        Args:
            address: The token's contract address. Case-insensitive.
            chain_id: The integer ID of the blockchain.

        Returns:
            The token's symbol as a string, or None if not found.
        """
        return self._token_map_by_address.get(chain_id, {}).get(address.lower())

    def get_monitored_tokens(self, chain_id: int) -> dict[str, str]:
        """
        Returns a dictionary of all monitored tokens (symbol: address) for a given chain.

        Args:
            chain_id: The integer ID of the blockchain.

        Returns:
            A dictionary mapping uppercase token symbols to lowercase addresses.
        """
        return self._token_map_by_symbol.get(chain_id, {})

    # ------------------------------------------------------------------
    # Additional helpers for token metadata
    # ------------------------------------------------------------------
    def get_token_symbol_by_address(
        self, address: str, chain_id: int | None = None
    ) -> str | None:
        """Public-friendly alias that optionally searches across chains when chain_id is unknown."""
        address = address.lower()
        if chain_id is not None:
            return self._token_map_by_address.get(chain_id, {}).get(address)

        for chain_map in self._token_map_by_address.values():
            symbol = chain_map.get(address)
            if symbol:
                return symbol
        return None

    def get_token_info_by_address(
        self, address: str, chain_id: int | None = None
    ) -> dict[str, Any] | None:
        """Return stored token metadata (symbol, name, decimals) for an address."""
        address = address.lower()
        if chain_id is not None:
            return self._token_info_by_address.get(chain_id, {}).get(address)

        for chain_map in self._token_info_by_address.values():
            info = chain_map.get(address)
            if info:
                return info
        return None

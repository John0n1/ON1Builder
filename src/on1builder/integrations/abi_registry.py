#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – ABIRegistry
========================
A lightweight ABI registry for Ethereum        # 4) Fallback to module-relative
        return p1  # Return the expected path even if it doesn't existtracts.
Loads and validates ABI JSON files from a specified directory.
License: MIT
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Required functions per contract type                                        #
# --------------------------------------------------------------------------- #
_REQUIRED: Dict[str, set[str]] = {
    "erc20": {"transfer", "approve", "transferFrom", "balanceOf"},
    "uniswap": {
        "swapExactTokensForTokens",
        "swapTokensForExactTokens",
        "addLiquidity",
        "getAmountsOut",
    },
    "sushiswap": {
        "swapExactTokensForTokens",
        "swapTokensForExactTokens",
        "addLiquidity",
        "getAmountsOut",
    },
    "aave_flashloan": {
        "fn_RequestFlashLoan",
        "executeOperation",
        "ADDRESSES_PROVIDER",
        "POOL",
    },
    "aave": {"admin", "implementation", "upgradeTo", "upgradeToAndCall"},
}


# --------------------------------------------------------------------------- #
# Module‐level singletons                                                     #
# --------------------------------------------------------------------------- #
_registry_instance: Optional[ABIRegistry] = None
_GLOBAL_ABIS: Dict[str, List[Dict[str, Any]]] = {}
_GLOBAL_SIG_MAP: Dict[str, Dict[str, str]] = {}
_GLOBAL_SELECTOR_MAP: Dict[str, List[Tuple[str, str]]] = {}
_FILE_HASH: Dict[str, str] = {}
_initialized = False


async def get_registry(abi_path: Optional[str] = None) -> ABIRegistry:
    """
    Return the global ABIRegistry, creating or re-initializing it if needed.

    Args:
        abi_path: Path to ABI files directory. If provided and differs from
                  the current path, the registry will reload from that directory.

    Returns:
        ABIRegistry: The shared registry instance.
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ABIRegistry(abi_path)
        await _registry_instance.initialize(abi_path)
    elif abi_path is not None and _registry_instance.abi_path != Path(abi_path):
        await _registry_instance.initialize(abi_path)
    return _registry_instance


class ABIRegistry:
    """
    Registry for ABI definitions.

    Loads and validates ABI JSON files from a specified directory.
    """

    def __init__(self, abi_path: Optional[str] = None) -> None:
        """
        Initialize the ABI registry.

        Args:
            abi_path: Optional directory containing ABI JSON files.
        """
        if abi_path:
            self.abi_path: Path = Path(abi_path)
        else:
            self.abi_path = self._find_default_abi_path()

        self.abis = _GLOBAL_ABIS
        self.function_signatures = _GLOBAL_SIG_MAP
        self.reload_count: int = 0

        if not self.abi_path.exists():
            logger.warning(f"ABI path not found: {self.abi_path}")

    async def initialize(self, abi_path: Optional[str] = None) -> bool:
        """
        (Re)initialize the registry, optionally overriding the path.

        Args:
            abi_path: New directory to load ABIs from.

        Returns:
            bool: True if initialization succeeded.
        """
        global _initialized
        try:
            if abi_path:
                new_path = Path(abi_path)
                if new_path.exists():
                    self.abi_path = new_path
                else:
                    logger.warning(
                        f"Provided ABI path not found: {abi_path}, using {self.abi_path}"
                    )

            if not self.abis and self.abi_path.exists():
                self.load_abis()

            _initialized = True
            logger.info(f"ABIRegistry initialized at: {self.abi_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ABIRegistry: {e}")
            return False

    async def is_healthy(self) -> bool:
        """
        Health check for the registry.

        Returns:
            bool: True if at least one ABI has been loaded and the path exists.
        """
        if not _initialized:
            return False
        if not self.abi_path.exists():
            logger.warning(f"ABI path does not exist: {self.abi_path}")
            return False
        if not self.abis:
            logger.warning("No ABIs loaded")
            return False
        return True

    def _find_default_abi_path(self) -> Path:
        """
        Determine the default ABI directory.

        Returns:
            Path: A best-guess path for `resources/abi`.
        """
        module_dir = Path(__file__).parent
        # 1) Module-relative resources/abi (new structure)
        p1 = module_dir.parent / "resources" / "abi"
        if p1.exists():
            return p1
        # 2) Project root / resources/abi (old structure for backward compatibility)
        root = module_dir.parent.parent.parent
        p2 = root / "resources" / "abi"
        if p2.exists():
            return p2
        # 3) BASE_PATH env
        if "BASE_PATH" in os.environ:
            p3 = Path(os.environ["BASE_PATH"]) / "resources" / "abi"
            if p3.exists():
                return p3
        # 4) Fallback to module-relative
        return p1  # Return the expected path even if it doesn't exist

    def load_abis(self) -> None:
        """
        Load all `.json` ABI files from `self.abi_path`, updating global maps.
        """
        if not self.abi_path.exists():
            logger.error(f"ABI directory not found: {self.abi_path}")
            return

        loaded, failed = 0, 0
        logger.info(f"Loading ABIs from {self.abi_path}")

        # Files to exclude from ABI loading (non-ABI JSON files)
        excluded_files = {
            "resources/ml_data/strategy_weights.json",
            "token_list.json",
            "config.json",
            "metadata.json",
        }
        excluded_patterns = ["_config", "_settings", "_cache"]

        for file_path in self.abi_path.glob("*.json"):
            # Skip excluded files
            if file_path.name in excluded_files or any(
                pattern in file_path.name for pattern in excluded_patterns
            ):
                logger.debug(f"Skipping non-ABI file: {file_path.name}")
                continue

            name = file_path.stem
            if name.endswith("_abi"):
                name = name[:-4]

            try:
                raw = file_path.read_text()
                digest = hashlib.md5(raw.encode()).hexdigest()
                if _FILE_HASH.get(name) == digest:
                    loaded += 1
                    continue
                _FILE_HASH[name] = digest

                data = json.loads(raw)
                abi = data["abi"] if isinstance(data, dict) and "abi" in data else data
                if not isinstance(abi, list):
                    logger.warning(
                        f"Skipping {file_path.name}: Invalid ABI format (not a list)"
                    )
                    failed += 1
                    continue

                _GLOBAL_ABIS[name] = abi
                sigs = self._extract_function_signatures(abi)
                _GLOBAL_SIG_MAP[name] = sigs

                for func, sig in sigs.items():
                    selector = sig if not sig.startswith("0x") else sig[2:]
                    selector = selector[:8]
                    _GLOBAL_SELECTOR_MAP.setdefault(selector, []).append((name, func))

                loaded += 1
                logger.info(f"Loaded ABI '{name}' ({len(abi)} entries)")

            except Exception as e:
                logger.error(f"Failed to load {file_path.name}: {e}", exc_info=True)
                failed += 1

        self.reload_count += 1
        logger.info(f"ABIs loaded: {loaded}, failed: {failed}")

    def _extract_function_signatures(self, abi: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        From an ABI array, build a map function_name → signature.

        Args:
            abi: ABI JSON array.

        Returns:
            Dict[str, str]: e.g. {"transfer": "transfer(address,uint256)"}
        """
        sigs: Dict[str, str] = {}
        for item in abi:
            if item.get("type") != "function":
                continue
            name = item.get("name", "")
            inputs = item.get("inputs", [])
            calldata = ",".join(param.get("type", "") for param in inputs)
            signature = f"{name}({calldata})"
            sigs[name] = signature
        return sigs

    def list_available_abis(self) -> List[str]:
        """
        Return a list of ABI names currently loaded in the registry.
        """
        return list(self.abis.keys())

    def get_abi(self, name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve the ABI for `name`, loading it on-demand if missing.

        Args:
            name: Contract or file base name (with or without "_abi").

        Returns:
            Optional[List[Dict]]: The ABI array, or None.
        """
        key = name[:-4] if name.endswith("_abi") else name
        if key not in _GLOBAL_ABIS:
            # Attempt on-the-fly load, try both naming conventions
            path = self.abi_path / f"{key}.json"
            if not path.exists():
                path = self.abi_path / f"{key}_abi.json"

            if path.exists():
                self.load_abis()
            else:
                logger.error(f"ABI '{key}' not found and no file at {path}")
                return None
        return _GLOBAL_ABIS.get(key)

    def get_function_signature(self, contract: str, function: str) -> Optional[str]:
        """
        Return the ABI signature string for a given contract and function.

        Args:
            contract: Contract name (file stem, no "_abi").
            function: Function name.

        Returns:
            Optional[str]: e.g. "transfer(address,uint256)"
        """
        sigs = _GLOBAL_SIG_MAP.get(contract) or _GLOBAL_SIG_MAP.get(f"{contract}_abi")
        return sigs.get(function) if sigs else None

    def get_method_selector(self, selector: str) -> Optional[str]:
        """
        Map a 4-byte selector to its function name.

        Args:
            selector: e.g. "0xa9059cbb" or "a9059cbb"

        Returns:
            Optional[str]: Function name, or None.
        """
        sel = selector[2:] if selector.startswith("0x") else selector
        entries = _GLOBAL_SELECTOR_MAP.get(sel)
        return entries[0][1] if entries else None

    def validate_abi(self, name: str) -> bool:
        """
        Ensure an ABI includes all required functions for its category.

        Args:
            name: Category key in _REQUIRED (e.g. "erc20"), not file name.

        Returns:
            bool: True if valid or no requirements exist.
        """
        required = _REQUIRED.get(name)
        if not required:
            return True
        abi = self.get_abi(name)
        if not abi:
            return False
        funcs = {item.get("name") for item in abi if item.get("type") == "function"}
        missing = required - funcs
        if missing:
            logger.warning(f"ABI '{name}' missing functions: {missing}")
            return False
        return True

    def find_tokens_path(self) -> Path:
        """
        Locate the consolidated token JSON file.

        Returns:
            Path: Path to all_chains_tokens.json
        """
        tokens_path = self.abi_path.parent / "tokens" / "all_chains_tokens.json"
        if not tokens_path.exists():
            env = os.getenv("TOKEN_PATH")
            if env:
                tokens_path = Path(env) / "all_chains_tokens.json"
        return tokens_path

    async def _load_token_data(self) -> List[Dict[str, Any]]:
        """
        Load and cache the consolidated token data.

        Returns:
            List[Dict[str, Any]]: Token data from all_chains_tokens.json
        """
        if not hasattr(self, "_token_data"):
            tokens_path = self.find_tokens_path()
            if not tokens_path.exists():
                logger.warning(f"Token data file not found: {tokens_path}")
                self._token_data = []
                return self._token_data

            try:
                import asyncio

                def read_json_file(path):
                    with open(path, "r") as f:
                        return json.load(f)

                self._token_data = await asyncio.to_thread(read_json_file, tokens_path)
                logger.info(f"Loaded {len(self._token_data)} tokens from {tokens_path}")
            except Exception as e:
                logger.error(f"Failed to load token data from {tokens_path}: {e}")
                self._token_data = []

        return self._token_data

    async def get_token_addresses(self, chain_id: int = 1) -> Dict[str, str]:
        """
        Load symbol→address mapping for a chain.

        Args:
            chain_id: Blockchain chain ID.

        Returns:
            Dict[str, str]: e.g. {"WETH": "0x..."}.
        """
        token_data = await self._load_token_data()
        result = {}

        for token in token_data:
            addresses = token.get("addresses", {})
            address = addresses.get(str(chain_id))
            if address and token.get("symbol"):
                result[token["symbol"].upper()] = address

        return result

    async def get_token_symbols(self, chain_id: int = 1) -> Dict[str, str]:
        """
        Load address→symbol mapping for a chain.

        Args:
            chain_id: Blockchain chain ID.

        Returns:
            Dict[str, str]: e.g. {"0x...": "WETH"}.
        """
        token_data = await self._load_token_data()
        result = {}

        for token in token_data:
            addresses = token.get("addresses", {})
            address = addresses.get(str(chain_id))
            if address and token.get("symbol"):
                result[address.lower()] = token["symbol"]

        return result

    async def get_token_address(self, symbol: str, chain_id: int = 1) -> Optional[str]:
        """
        Look up a token address by symbol.

        Args:
            symbol: Token symbol (case-insensitive).
            chain_id: Blockchain chain ID.

        Returns:
            Optional[str]: Address string, or None.
        """
        symbol = symbol.upper()
        token_data = await self._load_token_data()

        for token in token_data:
            if token.get("symbol", "").upper() == symbol:
                addresses = token.get("addresses", {})
                return addresses.get(str(chain_id))

        return None

    async def get_token_symbol(self, address: str, chain_id: int = 1) -> Optional[str]:
        """
        Look up a token symbol by address.

        Args:
            address: Token address (case-insensitive).
            chain_id: Blockchain chain ID.

        Returns:
            Optional[str]: Symbol, or None.
        """
        address = address.lower()
        token_data = await self._load_token_data()

        for token in token_data:
            addresses = token.get("addresses", {})
            token_address = addresses.get(str(chain_id))
            if token_address and token_address.lower() == address:
                return token.get("symbol")

        return None

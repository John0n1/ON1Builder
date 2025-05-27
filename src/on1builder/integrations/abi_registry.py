# filepath: /home/on1/ON1Builder/src/on1builder/integrations/abi_registry.py
"""
ON1Builder – ABIRegistry
========================
A lightweight ABI registry for Ethereum smart contracts.
It loads and validates ABI JSON files from a specified directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from on1builder.utils.logger import setup_logging

logger = setup_logging("ABIRegistry", level="DEBUG")

# --------------------------------------------------------------------------- #
# constants & helpers                                                         #
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

# Global registry instance
_registry_instance = None


def get_registry(abi_path: Optional[str] = None) -> ABIRegistry:
    """Get the global ABI registry instance.

    Args:
        abi_path: Path to ABI files directory

    Returns:
        ABIRegistry: The global registry instance
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ABIRegistry(abi_path)
    return _registry_instance


class ABIRegistry:
    """Registry for ABI definitions.

    Loads and validates ABI JSON files from a specified directory.
    """

    def __init__(self, abi_path: Optional[str] = None) -> None:
        """Initialize the ABI registry.

        Args:
            abi_path: Path to ABI files directory
        """
        if abi_path is None:
            # Default to resources/abi directory relative to project root
            self.abi_path = self._find_default_abi_path()
        else:
            self.abi_path = Path(abi_path)

        # Initialize ABI cache
        self.abis: Dict[str, Any] = {}
        self.function_signatures: Dict[str, Dict[str, str]] = {}
        self._initialized = False

        # Load ABIs if path exists
        if self.abi_path.exists():
            self.load_abis()
        else:
            logger.warning(f"ABI path not found: {self.abi_path}")

    async def initialize(self) -> bool:
        """Initialize the ABI registry asynchronously.

        Returns:
            bool: True if initialization was successful
        """
        try:
            if not self._initialized:
                # Load ABIs if not already loaded
                if not self.abis and self.abi_path.exists():
                    self.load_abis()
                self._initialized = True
                logger.info("ABI Registry initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ABI Registry: {e}")
            return False

    async def is_healthy(self) -> bool:
        """Check if the ABI registry is healthy and operational.

        Returns:
            bool: True if registry is healthy
        """
        try:
            # Check if registry is initialized
            if not self._initialized:
                return False

            # Check if ABI path exists and is accessible
            if not self.abi_path.exists():
                logger.warning(f"ABI path does not exist: {self.abi_path}")
                return False

            # Check if we have loaded at least some ABIs or if directory is
            # empty
            return True
        except Exception as e:
            logger.error(f"Health check failed for ABI Registry: {e}")
            return False

    def _find_default_abi_path(self) -> Path:
        """Find the default ABI path based on module location.

        Returns:
            Path: Path to ABI directory
        """
        # Try to find resources/abi in the project structure
        module_dir = Path(__file__).parent  # integrations directory

        # First try: Check if we're in src/on1builder/integrations
        project_root = module_dir.parent.parent.parent  # Up to project root
        abi_path = project_root / "resources" / "abi"
        if abi_path.exists():
            return abi_path

        # Second try: Check if we're in a package inside site-packages
        abi_path = module_dir.parent / "resources" / "abi"
        if abi_path.exists():
            return abi_path

        # Fallback: Just use a relative resources/abi path
        return Path("resources/abi")

    def load_abis(self) -> None:
        """Load all ABIs from the ABI directory."""
        if not self.abi_path.exists():
            logger.error(f"ABI directory not found: {self.abi_path}")
            return

        loaded = 0
        failed = 0

        for file_path in self.abi_path.glob("*.json"):
            try:
                # Extract name from filename (without extension)
                name = file_path.stem
                if name.endswith("_abi"):
                    name = name[:-4]  # Remove _abi suffix if present

                # Load and parse ABI
                with open(file_path, "r") as f:
                    content = f.read()

                # Handle different ABI formats
                abi_data = json.loads(content)

                # Extract ABI array based on format
                if isinstance(abi_data, list):
                    # Direct ABI array
                    abi = abi_data
                elif isinstance(abi_data, dict) and "abi" in abi_data:
                    # Truffle/Hardhat format with "abi" field
                    abi = abi_data["abi"]
                else:
                    logger.warning(f"Unknown ABI format in {file_path}")
                    failed += 1
                    continue

                # Store ABI
                self.abis[name] = abi

                # Extract function signatures
                self.function_signatures[name] = self._extract_function_signatures(abi)

                loaded += 1

            except Exception as e:
                logger.error(f"Failed to load ABI from {file_path}: {e}")
                failed += 1

        logger.info(f"Loaded {loaded} ABIs, {failed} failed")

    def _extract_function_signatures(self, abi: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extract function signatures from ABI.

        Args:
            abi: ABI array

        Returns:
            Dict[str, str]: Mapping from function name to signature
        """
        signatures = {}

        for item in abi:
            if item.get("type") == "function":
                name = item.get("name", "")
                if name:
                    # Build function signature
                    inputs = item.get("inputs", [])
                    input_types = [
                        input_spec.get("type", "unknown") for input_spec in inputs
                    ]
                    signature = f"{name}({','.join(input_types)})"
                    signatures[name] = signature

        return signatures

    def get_abi(self, name: str) -> Optional[List[Dict[str, Any]]]:
        """Get ABI for a given name.

        Args:
            name: Name of the ABI

        Returns:
            Optional[List[Dict[str, Any]]]: The ABI or None if not found
        """
        # If not loaded yet, try loading
        if not self.abis and self.abi_path.exists():
            self.load_abis()

        return self.abis.get(name)

    def get_function_signature(
        self, contract_name: str, function_name: str
    ) -> Optional[str]:
        """Get function signature for a specific contract and function.

        Args:
            contract_name: Name of the contract
            function_name: Name of the function

        Returns:
            Optional[str]: Function signature or None if not found
        """
        if contract_name not in self.function_signatures:
            return None

        return self.function_signatures[contract_name].get(function_name)

    def validate_abi(self, name: str) -> bool:
        """Validate that an ABI has required functions.

        Args:
            name: Name of the ABI

        Returns:
            bool: True if valid, False otherwise
        """
        # Check if we have required functions for this ABI
        if name not in _REQUIRED:
            # No specific requirements
            return True

        abi = self.get_abi(name)
        if not abi:
            return False

        # Extract function names from ABI
        abi_functions = set()
        for item in abi:
            if item.get("type") == "function":
                abi_functions.add(item.get("name", ""))

        # Check if all required functions are present
        required_functions = _REQUIRED[name]
        missing = required_functions - abi_functions

        if missing:
            logger.warning(f"ABI {name} is missing required functions: {missing}")
            return False

        return True

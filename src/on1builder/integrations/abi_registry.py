# abi_registry.py
"""
ON1Builder – ABIRegistry
========================
A lightweight ABI registry for Ethereum smart contracts.
It loads and validates ABI JSON files from a specified directory.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eth_utils import function_signature_to_4byte_selector

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

_ABI_FILES: Dict[str, str] = {
    "erc20": "erc20_abi.json",
    "uniswap": "uniswap_abi.json",
    "sushiswap": "sushiswap_abi.json",
    "aave_flashloan": "aave_flashloan_abi.json",
    "aave": "aave_pool_abi.json",
}

# –– 256-entry LRU for selector look-ups
@functools.lru_cache(maxsize=256)
def _selector_to_name_lru(cache_key: Tuple[str, str]) -> Optional[str]:
    registry, selector = cache_key
    return ABIRegistry._GLOBAL_SELECTOR_MAP.get(registry, {}).get(selector)


class ABIValidationError(Exception):
    """Exception raised for ABI validation errors."""
    pass


class ABIRegistry:
    """
    Loads and validates ABI JSON files from `<base>/abi/`.
    Instances are cheap; they all share the same global maps.
    """

    # shared state (per-process)
    _GLOBAL_ABIS: Dict[str, List[Dict[str, Any]]] = {}
    _GLOBAL_SIG_MAP: Dict[str, Dict[str, str]] = {}
    _GLOBAL_SELECTOR_MAP: Dict[str, Dict[str, str]] = {}
    _FILE_HASH: Dict[str, str] = {}
    _init_lock = asyncio.Lock()
    _initialized = False
    _REGISTRY_HASH = ""  # Hash of all ABIs for cache invalidation

    def __init__(self):
        """Initialize the ABI registry."""
        # Each instance only needs to reference the global maps
        self.reset_counters()
        # Track background reload tasks
        self._tasks: set[asyncio.Task] = set()
        
    def reset_counters(self):
        """Reset counters used for stats."""
        self.load_count = 0
        self.lookup_count = 0
        self.cache_hit_count = 0
        self.reload_count = 0

    # ---------------- public API -------------------------

    async def initialize(self, base_path: Path) -> None:
        """
        Load & validate all ABIs if not done yet.  Multiple callers are safe.
        """
        async with self._init_lock:
            if self._initialized:
                return
            abi_dir = base_path / "data" / "abi"
            await self._load_all(abi_dir)
            self._initialized = True
            logger.info("ABIRegistry initialised (loaded %d ABIs)", len(self._GLOBAL_ABIS))
            # Create a hash of all ABIs for cache invalidation
            all_files = []
            for abi_type, abi in self._GLOBAL_ABIS.items():
                all_files.append(f"{abi_type}:{self._FILE_HASH.get(abi_type, '')}")
            all_files_str = "||".join(sorted(all_files))
            self._REGISTRY_HASH = hashlib.md5(all_files_str.encode()).hexdigest()

    def get_abi(self, abi_type: str) -> Optional[List[Dict[str, Any]]]:
        self._maybe_reload_if_changed(abi_type)
        return self._GLOBAL_ABIS.get(abi_type)

    def get_function_signature(self, abi_type: str, func_name: str) -> Optional[str]:
        self._maybe_reload_if_changed(abi_type)
        return self._GLOBAL_SIG_MAP.get(abi_type, {}).get(func_name)

    def get_method_selector(self, selector_hex: str) -> Optional[str]:
        """Get the method name for a given selector hex value."""
        # Consult LRU – key is (all-abis-hash-id, selector)
        cache_key = (self._REGISTRY_HASH, selector_hex)
        self.lookup_count += 1
        result = _selector_to_name_lru(cache_key)
        if result:
            self.cache_hit_count += 1
        return result

    # health probe for MainCore -------------------------------------------

    async def is_healthy(self) -> bool:  # noqa: D401
        """Return True if at least *erc20* ABI is available."""
        return bool(self._GLOBAL_ABIS.get("erc20"))

    # ---------------- internals -------------------------

    async def _load_all(self, abi_dir: Path) -> None:
        """Load all ABI files from the specified directory."""
        try:
            for file_path in abi_dir.glob("*.json"):
                abi_type = file_path.stem
                try:
                    await self._load_single(abi_type, file_path)
                except Exception as e:
                    logger.error(f"Error loading ABI {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading ABIs from {abi_dir}: {e}")
            raise

    async def _load_single(self, abi_type: str, file_path: Path) -> bool:
        """Load a single ABI file.
        
        Args:
            abi_type: Type of the ABI (e.g., 'erc20', 'aave_pool')
            file_path: Path to the ABI JSON file
            
        Returns:
            True if loaded successfully, False otherwise
            
        Raises:
            FileNotFoundError: If the file does not exist
            json.JSONDecodeError: If the file cannot be parsed as JSON
            ABIValidationError: If the ABI is invalid
        """
        self.load_count += 1
        
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"ABI file not found: {file_path}")
                
            # Calculate file hash for change detection
            file_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
            
            # Skip if file hasn't changed
            if abi_type in self._GLOBAL_ABIS and self._FILE_HASH.get(abi_type) == file_hash:
                return True
                
            # Load and parse ABI
            abi_json = json.loads(file_path.read_text())
            self._validate_schema(abi_json, abi_type)
            
            # Extract function signatures and method selectors
            sig_map, selector_map = self._extract_maps(abi_json)
            
            # Store in global maps
            self._GLOBAL_ABIS[abi_type] = abi_json
            self._GLOBAL_SIG_MAP[abi_type] = sig_map
            self._GLOBAL_SELECTOR_MAP.update(selector_map)
            self._FILE_HASH[abi_type] = file_hash
            
            logger.debug(f"Loaded ABI {abi_type} with {len(abi_json)} entries")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in ABI file {file_path}: {e}")
            raise
            
        except Exception as e:
            logger.error(f"Error loading ABI {abi_type} from {file_path}: {e}")
            raise

    @staticmethod
    def _validate_schema(abi: Any, abi_type: str) -> None:
        """Validate that the ABI conforms to the expected schema."""
        if not isinstance(abi, list):
            raise ABIValidationError(f"ABI {abi_type} must be a JSON array")
            
        for entry in abi:
            if not isinstance(entry, dict):
                raise ABIValidationError(f"ABI {abi_type} contains non-object entry")
                
            if "type" not in entry:
                raise ABIValidationError(f"ABI {abi_type} entry missing 'type' field")

    @staticmethod
    def _extract_maps(abi: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Extract function signatures and method selectors from ABI.
        
        Returns:
            Tuple containing (signature_map, selector_map)
        """
        sig_map: Dict[str, str] = {}
        selector_map: Dict[str, str] = {}
        
        for entry in abi:
            if entry.get("type") == "function":
                name = entry.get("name", "")
                if not name:
                    continue
                    
                inputs = entry.get("inputs", [])
                input_types = ",".join(i.get("type", "") for i in inputs)
                sig = f"{name}({input_types})"
                
                # Store function signature
                sig_map[name] = sig
                
                # Calculate and store method selector
                if "0x" not in name:  # Skip if name already looks like a selector
                    from web3 import Web3
                    selector = Web3.keccak(text=sig)[:4].hex()
                    selector_map[selector] = name
                    
        return sig_map, selector_map

    def _maybe_reload_if_changed(self, abi_type: str) -> None:
        """Check if the ABI file has changed and reload if necessary."""
        try:
            if abi_type not in self._GLOBAL_ABIS:
                return
                
            # Find the file path
            base_path = Path(__file__).parent.parent.parent
            file_path = base_path / "data" / "abi" / f"{abi_type}_abi.json"
            
            if not file_path.exists():
                return
                
            # Check if file has changed
            current_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
            if current_hash != self._FILE_HASH.get(abi_type, ""):
                self.reload_count += 1
                # Create and track background reload task
                task = asyncio.create_task(self._load_single(abi_type, file_path))
                self._tasks.add(task)
                task.add_done_callback(lambda t: self._tasks.discard(t))
                
        except Exception as e:
            logger.error(f"Error checking ABI file changes for {abi_type}: {e}")


# allow "fire-and-forget" one-shot usage -------------------------------------

_default_registry: Optional[ABIRegistry] = None


async def get_registry(base_path: Optional[Path] = None) -> ABIRegistry:
    """
    Convenience accessor for ad-hoc scripts:

    ```python
    reg = await abi_registry.get_registry(Path.cwd())
    erc20 = reg.get_abi("erc20")
    ```
    """
    global _default_registry
    if (_default_registry is None):
        _default_registry = ABIRegistry()
        await _default_registry.initialize(base_path or Path(__file__).parent.parent)
    return _default_registry

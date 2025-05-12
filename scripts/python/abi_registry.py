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

from logger_on1 import setup_logging

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

    # ---------------- public API -------------------------

    async def initialize(self, base_path: Path) -> None:
        """
        Load & validate all ABIs if not done yet.  Multiple callers are safe.
        """
        async with self._init_lock:
            if self._initialized:
                return
            abi_dir = base_path / "abi"
            await self._load_all(abi_dir)
            self._initialized = True
            logger.info("ABIRegistry initialised (loaded %d ABIs)", len(self._GLOBAL_ABIS))

    def get_abi(self, abi_type: str) -> Optional[List[Dict[str, Any]]]:
        self._maybe_reload_if_changed(abi_type)
        return self._GLOBAL_ABIS.get(abi_type)

    def get_function_signature(self, abi_type: str, func_name: str) -> Optional[str]:
        self._maybe_reload_if_changed(abi_type)
        return self._GLOBAL_SIG_MAP.get(abi_type, {}).get(func_name)

    def get_method_selector(self, selector_hex: str) -> Optional[str]:
        # consult LRU – key is (all-abis-hash-id, selector)
        global_hash = "|".join(self._FILE_HASH.values())
        return _selector_to_name_lru((global_hash, selector_hex))

    # health probe for MainCore -------------------------------------------

    async def is_healthy(self) -> bool:  # noqa: D401
        """Return True if at least *erc20* ABI is available."""
        return bool(self._GLOBAL_ABIS.get("erc20"))

    # ---------------- internals -------------------------

    async def _load_all(self, abi_dir: Path) -> None:
        tasks = [
            asyncio.create_task(self._load_single(abi_type, abi_dir / fname))
            for abi_type, fname in _ABI_FILES.items()
        ]
        failures = await asyncio.gather(*tasks)
        if any(x is False for x in failures):
            raise RuntimeError("Critical ABI file(s) missing or invalid")

    async def _load_single(self, abi_type: str, file_path: Path) -> bool:
        try:
            content = await asyncio.to_thread(file_path.read_bytes)
        except FileNotFoundError:
            logger.error("ABI file missing: %s", file_path)
            return False

        sha = hashlib.sha1(content).hexdigest()
        # skip reload if unchanged
        if self._FILE_HASH.get(abi_type) == sha:
            return True

        try:
            abi_json = json.loads(content)
            self._validate_schema(abi_json, abi_type)
        except Exception as exc:
            logger.error("Invalid ABI %s: %s", abi_type, exc)
            return False

        # build maps
        sig_map, sel_map = self._extract_maps(abi_json)
        self._GLOBAL_ABIS[abi_type] = abi_json
        self._GLOBAL_SIG_MAP[abi_type] = sig_map
        self._GLOBAL_SELECTOR_MAP[abi_type] = sel_map
        self._FILE_HASH[abi_type] = sha
        logger.debug("Loaded ABI %-14s (%4d funcs)", abi_type, len(sig_map))
        return True

    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_schema(abi: Any, abi_type: str) -> None:
        if not isinstance(abi, list):
            raise ValueError("Not a JSON-array")

        names = {e.get("name") for e in abi if e.get("type") == "function"}
        missing = _REQUIRED.get(abi_type, set()) - names
        if missing:
            raise ValueError(f"Missing required functions: {', '.join(missing)}")

    @staticmethod
    def _extract_maps(abi: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str]]:
        sigs: Dict[str, str] = {}
        sels: Dict[str, str] = {}
        for entry in abi:
            if entry.get("type") != "function":
                continue
            name = entry["name"]
            types = ",".join(arg.get("type", "") for arg in entry.get("inputs", []))
            sig = f"{name}({types})"
            sel = function_signature_to_4byte_selector(sig).hex()
            sigs[name] = sig
            sels[sel] = name
        return sigs, sels

    # ------------------------------------------------------------------ #

    def _maybe_reload_if_changed(self, abi_type: str) -> None:
        """
        Lightweight mtime check (1 s resolution) to auto-reload ABI if the file
        has changed on disk.  Cost: one `stat()` per call.
        """
        file_path = (Path(__file__).parent.parent / "abi" / _ABI_FILES[abi_type]).resolve()
        try:
            mtime = int(file_path.stat().st_mtime)
        except FileNotFoundError:
            return

        cache_key = f"_mt_{abi_type}"
        last_seen = getattr(self, cache_key, 0)
        if mtime != last_seen:
            setattr(self, cache_key, mtime)
            # soft reload in background so caller isn’t delayed
            asyncio.create_task(self._load_single(abi_type, file_path))


# allow “fire-and-forget” one-shot usage -------------------------------------

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
    if _default_registry is None:
        _default_registry = ABIRegistry()
        await _default_registry.initialize(base_path or Path(__file__).parent.parent)
    return _default_registry

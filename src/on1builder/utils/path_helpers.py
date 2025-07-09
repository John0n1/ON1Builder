# src/on1builder/utils/path_helpers.py
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def get_base_dir() -> Path:
    """
    Get the base directory of the ON1Builder project.
    Uses the path from the loaded settings for consistency, with fallback.
    """
    try:
        from on1builder.config.loaders import get_settings
        return get_settings().base_path
    except Exception:
        # Fallback to current working directory if settings not available
        return Path.cwd()

def get_resource_path(resource_type: str, filename: str) -> Path:
    """
    Get the absolute path to a specific resource file.

    Args:
        resource_type: The sub-directory within resources (e.g., 'abi', 'tokens', 'ml_models').
        filename: The name of the resource file.

    Returns:
        An absolute Path object to the resource file.
    """
    return get_resource_dir() / resource_type / filename

def get_abi_path(abi_name: str) -> Path:
    """
    Get the absolute path to a specific ABI JSON file.
    This is a convenience wrapper around get_resource_path for ABI files.
    
    Args:
        abi_name: The base name of the ABI file (e.g., 'uniswap_v2_router').

    Returns:
        An absolute Path object to the ABI file.
    """
    if not abi_name.lower().endswith(".json"):
        abi_name += ".json"
    return get_resource_path("abi", abi_name)

@lru_cache(maxsize=1)
def get_config_dir() -> Path:
    """Get the configuration directory."""
    return get_base_dir() / "src" / "on1builder" / "config"

@lru_cache(maxsize=1)
def get_resource_dir() -> Path:
    """Get the main resources directory."""
    return get_base_dir() / "src" / "on1builder" / "resources"

def get_chain_config_path(chain_id: int) -> Path:
    """Get the path to a chain-specific configuration file."""
    return get_config_dir() / f"chain_{chain_id}.json"

@lru_cache(maxsize=1)
def get_monitored_tokens_path() -> Path:
    """Get the absolute path to the monitored tokens JSON file from settings."""
    try:
        from on1builder.config.loaders import get_settings
        settings = get_settings()
        return settings.monitored_tokens_path
    except Exception:
        # Fallback to default path using the standard token path function
        return get_token_data_path("all_chains_tokens.json")

def get_token_data_path(filename: str) -> Path:
    """
    Get the path to a token data file.
    This is a convenience wrapper around get_resource_path for token files.
    """
    return get_resource_path("tokens", filename)

@lru_cache(maxsize=1)
def get_strategy_weights_path() -> Path:
    """Get the absolute path to the strategy weights JSON file."""
    return get_resource_path("ml_models", "strategy_weights.json")

def ensure_dir_exists(path: Path) -> None:
    """
    Ensures that the directory for a given path exists, creating it if necessary.
    If the path is a file, it ensures the parent directory exists.

    Args:
        path: A Path object for a file or directory.
    """
    target_dir = path.parent if path.suffix else path
    target_dir.mkdir(parents=True, exist_ok=True)
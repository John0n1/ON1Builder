"""
Path helper utilities for ON1Builder.
"""

from pathlib import Path


def get_base_dir() -> Path:
    """Get the base directory of the ON1Builder project."""
    return Path(__file__).resolve().parent.parent.parent.parent


def get_config_dir() -> Path:
    """Get the configs directory."""
    return get_base_dir() / "configs"


def get_resource_dir() -> Path:
    """Get the resources directory."""
    return get_base_dir() / "src" / "on1builder" / "resources"


def get_resource_path(resource_type: str, filename: str) -> Path:
    """Get path to a specific resource file.

    Args:
        resource_type: Type of resource ('abi', 'tokens', 'ml_models')
        filename: Name of the resource file

    Returns:
        Path to the resource file
    """
    return get_resource_dir() / resource_type / filename


def get_abi_path(abi_name: str) -> Path:
    """Get path to an ABI file."""
    if not abi_name.endswith(".json"):
        abi_name += ".json"
    return get_resource_path("abi", abi_name)


def get_token_data_path() -> Path:
    """Get path to the consolidated token data file."""
    return get_resource_path("tokens", "all_chains_tokens.json")


def get_strategy_weights_path() -> Path:
    """Get path to the strategy weights file."""
    return get_resource_path("ml_models", "strategy_weights.json")


def get_chain_config_path(chain_name: str) -> Path:
    """Get path to a chain configuration file."""
    return get_config_dir() / "chains" / f"{chain_name}.yaml"


def ensure_dir_exists(path: Path) -> None:
    """Ensure a directory exists, creating it if necessary."""
    if isinstance(path, str):
        path = Path(path)

    if path.is_file():
        path = path.parent

    path.mkdir(parents=True, exist_ok=True)

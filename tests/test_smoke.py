#!/usr/bin/env python3
"""
Basic smoke tests for ON1Builder package.
These tests verify that the package can be imported and basic functionality works.
"""

import pytest
import sys
from pathlib import Path

def test_package_import():
    """Test that the main package can be imported."""
    try:
        import on1builder
        assert on1builder.__version__ == "2.2.0"
        assert on1builder.__author__ == "john0n1"
    except ImportError as e:
        pytest.fail(f"Failed to import on1builder package: {e}")

def test_cli_import():
    """Test that the CLI module can be imported."""
    try:
        from on1builder.__main__ import cli
        assert callable(cli)
    except ImportError as e:
        pytest.fail(f"Failed to import CLI: {e}")

def test_config_import():
    """Test that config modules can be imported."""
    try:
        from on1builder.config.settings import GlobalSettings, APISettings
        assert GlobalSettings is not None
        assert APISettings is not None
    except ImportError as e:
        pytest.fail(f"Failed to import config modules: {e}")

def test_utils_import():
    """Test that utility modules can be imported."""
    try:
        from on1builder.utils.logging_config import get_logger
        from on1builder.utils.custom_exceptions import ConfigurationError
        logger = get_logger("test")
        assert logger is not None
        assert ConfigurationError is not None
    except ImportError as e:
        pytest.fail(f"Failed to import utils: {e}")

def test_resource_files_exist():
    """Test that required resource files exist."""
    from on1builder.utils.path_helpers import get_resource_dir
    
    resources_dir = get_resource_dir()
    assert resources_dir.exists(), f"Resources directory not found: {resources_dir}"
    
    # Check for key resource files
    abi_dir = resources_dir / "abi"
    tokens_file = resources_dir / "tokens" / "all_chains_tokens.json"
    
    assert abi_dir.exists(), "ABI directory not found"
    assert tokens_file.exists(), "Tokens file not found"

def test_version_consistency():
    """Test that version is consistent across files."""
    import on1builder
    
    # Read version from pyproject.toml
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        content = pyproject_path.read_text()
        # Simple version extraction (not perfect but good enough for test)
        for line in content.split('\n'):
            if line.strip().startswith('version = '):
                pyproject_version = line.split('"')[1]
                assert pyproject_version == on1builder.__version__, \
                    f"Version mismatch: pyproject.toml={pyproject_version}, __init__.py={on1builder.__version__}"
                break

if __name__ == "__main__":
    pytest.main([__file__])

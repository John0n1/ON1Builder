#!/usr/bin/env python3
"""
Tests for path helper utilities.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_get_base_dir():
    """Test get_base_dir function."""
    from on1builder.utils.path_helpers import get_base_dir
    
    # Should return a Path object
    base_dir = get_base_dir()
    assert isinstance(base_dir, Path)
    
    # Should be cached (same result on second call)
    base_dir2 = get_base_dir()
    assert base_dir == base_dir2

def test_get_resource_dir():
    """Test get_resource_dir function.""" 
    from on1builder.utils.path_helpers import get_resource_dir
    
    resource_dir = get_resource_dir()
    assert isinstance(resource_dir, Path)
    assert "resources" in str(resource_dir)

def test_get_config_dir():
    """Test get_config_dir function."""
    from on1builder.utils.path_helpers import get_config_dir
    
    config_dir = get_config_dir()
    assert isinstance(config_dir, Path)
    assert "config" in str(config_dir)

def test_get_resource_path():
    """Test get_resource_path function."""
    from on1builder.utils.path_helpers import get_resource_path
    
    path = get_resource_path("abi", "test.json")
    assert isinstance(path, Path)
    assert "abi" in str(path)
    assert "test.json" in str(path)

def test_get_abi_path():
    """Test get_abi_path function."""
    from on1builder.utils.path_helpers import get_abi_path
    
    # Test with .json extension
    path1 = get_abi_path("test.json")
    assert isinstance(path1, Path)
    assert "test.json" in str(path1)
    
    # Test without .json extension (should add it)
    path2 = get_abi_path("test")
    assert isinstance(path2, Path)
    assert "test.json" in str(path2)

def test_get_token_data_path():
    """Test get_token_data_path function."""
    from on1builder.utils.path_helpers import get_token_data_path
    
    path = get_token_data_path("tokens.json")
    assert isinstance(path, Path)
    assert "tokens" in str(path)
    assert "tokens.json" in str(path)

def test_get_chain_config_path():
    """Test get_chain_config_path function."""
    from on1builder.utils.path_helpers import get_chain_config_path
    
    path = get_chain_config_path(1)
    assert isinstance(path, Path)
    assert "chain_1.json" in str(path)

def test_get_strategy_weights_path():
    """Test get_strategy_weights_path function."""
    from on1builder.utils.path_helpers import get_strategy_weights_path
    
    path = get_strategy_weights_path()
    assert isinstance(path, Path)
    assert "strategy_weights.json" in str(path)

def test_ensure_dir_exists():
    """Test ensure_dir_exists function."""
    from on1builder.utils.path_helpers import ensure_dir_exists
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_dir = temp_path / "test_dir"
        test_file = test_dir / "test_file.txt"
        
        # Ensure directory creation for a file path
        ensure_dir_exists(test_file)
        assert test_dir.exists()
        
        # Ensure directory creation for a directory path
        test_dir2 = temp_path / "test_dir2"
        ensure_dir_exists(test_dir2)
        assert test_dir2.exists()

def test_get_monitored_tokens_path_fallback():
    """Test get_monitored_tokens_path fallback behavior.""" 
    from on1builder.utils.path_helpers import get_monitored_tokens_path
    
    # Test that it works and returns a path (tests the fallback since settings module has dependencies)
    path = get_monitored_tokens_path()
    assert isinstance(path, Path)
    assert "all_chains_tokens.json" in str(path)

if __name__ == "__main__":
    pytest.main([__file__])
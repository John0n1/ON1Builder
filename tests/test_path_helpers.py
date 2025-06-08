"""
Tests for path helper utilities.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from on1builder.utils.path_helpers import (
    get_base_dir,
    get_config_dir,
    get_resource_dir,
    get_resource_path,
    get_abi_path,
    get_token_data_path,
    get_strategy_weights_path,
    get_chain_config_path,
    ensure_dir_exists,
)


class TestPathHelpers:
    """Test suite for path helper functions."""
    
    def test_get_base_dir(self):
        """Test get_base_dir returns a valid path."""
        base_dir = get_base_dir()
        assert isinstance(base_dir, Path)
        assert base_dir.exists()
        
    def test_get_config_dir(self):
        """Test get_config_dir returns the correct path."""
        config_dir = get_config_dir()
        assert isinstance(config_dir, Path)
        assert config_dir.name == "configs"
        
    def test_get_resource_dir(self):
        """Test get_resource_dir returns the correct path."""
        resource_dir = get_resource_dir()
        assert isinstance(resource_dir, Path)
        assert resource_dir.name == "resources"
        
    def test_get_resource_path(self):
        """Test get_resource_path with different arguments."""
        # Test with valid resource type and filename
        path1 = get_resource_path("abi", "test.json")
        assert isinstance(path1, Path)
        assert path1.name == "test.json"
        assert "abi" in str(path1)
        
        # Test with tokens resource type
        path2 = get_resource_path("tokens", "chainid-1.json")
        assert isinstance(path2, Path)
        assert path2.name == "chainid-1.json"
        assert "tokens" in str(path2)
        
    def test_get_abi_path_with_json_extension(self):
        """Test get_abi_path with a filename that has .json extension."""
        abi_path = get_abi_path("test.json")
        assert isinstance(abi_path, Path)
        assert abi_path.name == "test.json"
        assert "abi" in str(abi_path)
        
    def test_get_abi_path_without_json_extension(self):
        """Test get_abi_path with a filename without .json extension."""
        abi_path = get_abi_path("test")
        assert isinstance(abi_path, Path)
        assert abi_path.name == "test.json"
        assert "abi" in str(abi_path)
        
    def test_get_token_data_path(self):
        """Test get_token_data_path returns correct path structure."""
        token_path = get_token_data_path()
        assert isinstance(token_path, Path)
        assert token_path.name == "all_chains_tokens.json"
        assert "tokens" in str(token_path)
        
    def test_get_strategy_weights_path(self):
        """Test get_strategy_weights_path returns correct path structure."""
        weights_path = get_strategy_weights_path()
        assert isinstance(weights_path, Path)
        assert weights_path.name == "strategy_weights.json"
        assert "ml_models" in str(weights_path)
        
    def test_get_chain_config_path(self):
        """Test get_chain_config_path returns correct path structure."""
        config_path = get_chain_config_path("ethereum")
        assert isinstance(config_path, Path)
        assert config_path.name == "ethereum.yaml"
        assert "chains" in str(config_path)
        
    @patch('pathlib.Path.mkdir')
    def test_ensure_dir_exists_with_path_object(self, mock_mkdir):
        """Test ensure_dir_exists with a Path object."""
        test_path = Path("/test/directory")
        ensure_dir_exists(test_path)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch('pathlib.Path.mkdir')
    def test_ensure_dir_exists_with_string(self, mock_mkdir):
        """Test ensure_dir_exists with a string path."""
        test_path = "/test/directory" 
        ensure_dir_exists(test_path)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_ensure_dir_exists_with_file_path(self):
        """Test ensure_dir_exists when given a file path."""
        with patch('on1builder.utils.path_helpers.Path') as mock_path_class:
            # Create a mock file path
            mock_path = MagicMock()
            mock_path.is_file.return_value = True
            mock_parent = MagicMock()
            mock_path.parent = mock_parent
            mock_path_class.return_value = mock_path
            
            # Call the function with a string path (which gets converted to Path)
            ensure_dir_exists("/test/directory/file.txt")
            
            # Verify mkdir was called on the parent
            mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_path_consistency(self):
        """Test that all path functions return consistent results."""
        base_dir = get_base_dir()
        config_dir = get_config_dir()
        resource_dir = get_resource_dir()

        # Config dir should be under base dir
        assert config_dir.parent == base_dir
        
        # Resource dir should be under src/on1builder which is under base dir
        assert base_dir in resource_dir.parents
        
        # ABI path should be under resource dir
        abi_path = get_abi_path("test.json")
        assert resource_dir in abi_path.parents
        
        # Token data path should be under resource dir
        token_path = get_token_data_path()
        assert resource_dir in token_path.parents
        
    def test_all_functions_return_path_objects(self):
        """Test that all path functions return Path objects."""
        functions_and_args = [
            (get_base_dir, []),
            (get_config_dir, []),
            (get_resource_dir, []),
            (get_resource_path, ["abi", "test.json"]),
            (get_abi_path, ["test"]),
            (get_token_data_path, []),
            (get_strategy_weights_path, []),
            (get_chain_config_path, ["ethereum"]),
        ]
        
        for func, args in functions_and_args:
            result = func(*args)
            assert isinstance(result, Path), f"{func.__name__} did not return a Path object"

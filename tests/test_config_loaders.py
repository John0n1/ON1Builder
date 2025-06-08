#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for ON1Builder configuration loaders
==========================================

This module contains comprehensive tests for configuration loading functions
defined in src/on1builder/config/loaders.py.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import mock_open, patch
import pytest
import yaml

from on1builder.config.loaders import (
    ConfigLoader,
    get_config_loader,
    load_configuration,
    load_global_settings,
    load_multi_chain_settings,
    load_chain_settings,
)
from on1builder.config.settings import ChainSettings, GlobalSettings, MultiChainSettings


class TestConfigLoader:
    """Test cases for ConfigLoader class."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / "configs"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.loader = ConfigLoader(base_path=self.temp_dir)

    def teardown_method(self):
        """Clean up after each test method."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test ConfigLoader initialization."""
        assert self.loader.base_path == self.temp_dir
        assert self.loader.config_dir == self.config_dir

    def test_initialization_default_path(self):
        """Test ConfigLoader initialization with default path."""
        loader = ConfigLoader()
        assert loader.base_path is not None
        assert loader.config_dir == loader.base_path / "configs"

    def test_load_yaml_valid_file(self):
        """Test loading a valid YAML file."""
        test_data = {"test_key": "test_value", "number": 42}
        config_file = self.config_dir / "test.yaml"
        
        with open(config_file, 'w') as f:
            yaml.dump(test_data, f)
        
        result = self.loader._load_yaml(config_file)
        assert result == test_data

    def test_load_yaml_empty_file(self):
        """Test loading an empty YAML file."""
        config_file = self.config_dir / "empty.yaml"
        config_file.touch()
        
        result = self.loader._load_yaml(config_file)
        assert result == {}

    def test_load_yaml_nonexistent_file(self):
        """Test loading a non-existent YAML file."""
        nonexistent_file = self.config_dir / "nonexistent.yaml"
        
        result = self.loader._load_yaml(nonexistent_file)
        assert result == {}

    def test_load_yaml_invalid_file(self):
        """Test loading an invalid YAML file."""
        config_file = self.config_dir / "invalid.yaml"
        
        with open(config_file, 'w') as f:
            f.write("invalid: yaml: content: [")
        
        result = self.loader._load_yaml(config_file)
        assert result == {}

    def test_load_from_env(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            "DEBUG": "true",
            "MIN_PROFIT": "1.5",
            "CONNECTION_RETRY_COUNT": "3",
            "WALLET_KEY": "test_key",
            "COINGECKO_API_KEY": "test_api_key"
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            result = self.loader._load_from_env()
        
        assert result["debug"] is True
        assert result["min_profit"] == 1.5
        assert result["connection_retry_count"] == 3
        assert result["wallet_key"] == "test_key"
        assert result["api"]["coingecko_api_key"] == "test_api_key"

    def test_load_from_env_invalid_values(self):
        """Test loading invalid environment variable values."""
        env_vars = {
            "DEBUG": "invalid_bool",
            "MIN_PROFIT": "invalid_float",
            "CONNECTION_RETRY_COUNT": "invalid_int"
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            result = self.loader._load_from_env()
        
        # Invalid values should be skipped
        assert "debug" not in result
        assert "min_profit" not in result
        assert "connection_retry_count" not in result

    def test_load_global_config_defaults(self):
        """Test loading global config with defaults only."""
        result = self.loader.load_global_config()
        
        assert isinstance(result, GlobalSettings)
        assert result.base_path == self.temp_dir

    def test_load_global_config_with_common_settings(self):
        """Test loading global config with common settings."""
        common_data = {"debug": True, "min_profit": 2.0}
        common_path = self.config_dir / "common_settings.yaml"
        
        with open(common_path, 'w') as f:
            yaml.dump(common_data, f)
        
        result = self.loader.load_global_config()
        
        assert result.debug is True
        assert result.min_profit == 2.0

    def test_load_global_config_with_specific_file(self):
        """Test loading global config with specific config file."""
        specific_data = {"web3_max_retries": 5}
        specific_path = self.config_dir / "specific.yaml"
        
        with open(specific_path, 'w') as f:
            yaml.dump(specific_data, f)
        
        result = self.loader.load_global_config("specific.yaml")
        
        assert result.web3_max_retries == 5

    def test_load_global_config_with_absolute_path(self):
        """Test loading global config with absolute path."""
        specific_data = {"web3_max_retries": 7}
        specific_path = self.temp_dir / "absolute_config.yaml"
        
        with open(specific_path, 'w') as f:
            yaml.dump(specific_data, f)
        
        result = self.loader.load_global_config(str(specific_path))
        
        assert result.web3_max_retries == 7

    def test_load_multi_chain_config_default(self):
        """Test loading multi-chain config with default path."""
        # Create default multi-chain config
        chains_dir = self.config_dir / "chains"
        chains_dir.mkdir(exist_ok=True)
        
        multi_chain_data = {
            "chains": {
                "ethereum": {
                    "name": "ethereum",
                    "chain_id": 1,
                    "http_endpoint": "http://localhost:8545"
                }
            }
        }
        multi_chain_path = chains_dir / "config_multi_chain.yaml"
        
        with open(multi_chain_path, 'w') as f:
            yaml.dump(multi_chain_data, f)
        
        result = self.loader.load_multi_chain_config()
        
        assert isinstance(result, MultiChainSettings)
        assert result.chains["ethereum"].name == "ethereum"
        assert result.chains["ethereum"].chain_id == 1
        assert result.chains["ethereum"].http_endpoint == "http://localhost:8545"

    def test_load_multi_chain_config_custom_path(self):
        """Test loading multi-chain config with custom path."""
        custom_data = {
            "chains": {
                "polygon": {
                    "name": "polygon",
                    "chain_id": 137,
                    "http_endpoint": "http://polygon:8545"
                }
            }
        }
        custom_path = self.config_dir / "custom_multi.yaml"
        
        with open(custom_path, 'w') as f:
            yaml.dump(custom_data, f)
        
        result = self.loader.load_multi_chain_config("custom_multi.yaml")
        
        assert isinstance(result, MultiChainSettings)
        assert result.chains["polygon"].name == "polygon"
        assert result.chains["polygon"].chain_id == 137
        assert result.chains["polygon"].http_endpoint == "http://polygon:8545"

    def test_load_chain_config_success(self):
        """Test loading chain-specific configuration."""
        chains_dir = self.config_dir / "chains"
        chains_dir.mkdir(exist_ok=True)
        
        chain_data = {
            "chain_id": 1,
            "http_endpoint": "http://localhost:8545",
            "currency": "ETH"
        }
        chain_path = chains_dir / "ethereum.yaml"
        
        with open(chain_path, 'w') as f:
            yaml.dump(chain_data, f)
        
        result = self.loader.load_chain_config("ethereum")
        
        assert isinstance(result, ChainSettings)
        assert result.name == "ethereum"
        assert result.chain_id == 1
        assert result.http_endpoint == "http://localhost:8545"

    def test_load_chain_config_not_found(self):
        """Test loading non-existent chain configuration."""
        with pytest.raises(FileNotFoundError):
            self.loader.load_chain_config("nonexistent_chain")


class TestGlobalFunctions:
    """Test cases for global configuration loading functions."""

    def setup_method(self):
        """Set up test environment before each test method."""
        # Clear the global config loader
        import on1builder.config.loaders
        on1builder.config.loaders._config_loader = None

    def test_get_config_loader_singleton(self):
        """Test that get_config_loader returns the same instance."""
        loader1 = get_config_loader()
        loader2 = get_config_loader()
        
        assert loader1 is loader2
        assert isinstance(loader1, ConfigLoader)

    @patch.object(ConfigLoader, 'load_global_config')
    def test_load_configuration_success(self, mock_load_global):
        """Test successful configuration loading."""
        mock_config = GlobalSettings()
        mock_load_global.return_value = mock_config
        
        result = load_configuration()
        
        assert isinstance(result, dict)
        mock_load_global.assert_called_once_with(None)

    @patch.object(ConfigLoader, 'load_global_config')
    @patch.object(ConfigLoader, 'load_chain_config')
    def test_load_configuration_with_chain(self, mock_load_chain, mock_load_global):
        """Test configuration loading with chain-specific config."""
        mock_global_config = GlobalSettings()
        mock_chain_config = ChainSettings(name="test", chain_id=1, http_endpoint="http://test")
        mock_load_global.return_value = mock_global_config
        mock_load_chain.return_value = mock_chain_config
        
        result = load_configuration(chain="test")
        
        assert isinstance(result, dict)
        mock_load_global.assert_called_once_with(None)
        mock_load_chain.assert_called_once_with("test")

    @patch.object(ConfigLoader, 'load_global_config')
    def test_load_configuration_error_handling(self, mock_load_global):
        """Test configuration loading error handling."""
        mock_load_global.side_effect = Exception("Load error")
        
        result = load_configuration()
        
        assert isinstance(result, dict)
        assert "debug" in result
        assert "base_path" in result

    @patch.object(ConfigLoader, 'load_global_config')
    def test_load_global_settings(self, mock_load_global):
        """Test load_global_settings function."""
        mock_config = GlobalSettings()
        mock_load_global.return_value = mock_config
        
        result = load_global_settings("test_config.yaml")
        
        assert result == mock_config
        mock_load_global.assert_called_once_with("test_config.yaml")

    @patch.object(ConfigLoader, 'load_multi_chain_config')
    def test_load_multi_chain_settings(self, mock_load_multi):
        """Test load_multi_chain_settings function."""
        mock_config = MultiChainSettings()
        mock_load_multi.return_value = mock_config
        
        result = load_multi_chain_settings("multi_config.yaml")
        
        assert result == mock_config
        mock_load_multi.assert_called_once_with("multi_config.yaml")

    @patch.object(ConfigLoader, 'load_chain_config')
    def test_load_chain_settings(self, mock_load_chain):
        """Test load_chain_settings function."""
        mock_config = ChainSettings(name="test", chain_id=1, http_endpoint="http://test")
        mock_load_chain.return_value = mock_config
        
        result = load_chain_settings("test")
        
        assert result == mock_config
        mock_load_chain.assert_called_once_with("test")

    def test_env_var_masking(self):
        """Test that sensitive environment variables are masked in logs."""
        loader = ConfigLoader()
        
        with patch.dict(os.environ, {"WALLET_KEY": "secret_key"}, clear=False):
            with patch('on1builder.config.loaders.logger') as mock_logger:
                result = loader._load_from_env()
                
                # Check that wallet_key was loaded
                assert result["wallet_key"] == "secret_key"
                
                # Check that it was logged as redacted
                mock_logger.debug.assert_any_call("Loaded wallet_key=<REDACTED>")

    def test_api_key_masking(self):
        """Test that API keys are masked in logs."""
        loader = ConfigLoader()
        
        with patch.dict(os.environ, {"COINGECKO_API_KEY": "api_secret"}, clear=False):
            with patch('on1builder.config.loaders.logger') as mock_logger:
                result = loader._load_from_env()
                
                # Check that API key was loaded
                assert result["api"]["coingecko_api_key"] == "api_secret"
                
                # Check that it was logged as redacted
                mock_logger.debug.assert_any_call("Loaded API key coingecko_api_key=<REDACTED>")


if __name__ == "__main__":
    pytest.main([__file__])

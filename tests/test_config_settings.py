#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for ON1Builder config.settings module.
Tests for 100% coverage of all Pydantic models and validation.
"""

import pytest
from pathlib import Path
from typing import Dict, Any
from pydantic import ValidationError

from on1builder.config.settings import (
    APISettings,
    ChainSettings,
    GlobalSettings,
    MultiChainSettings,
)


class TestAPISettings:
    """Test suite for APISettings Pydantic model."""

    def test_api_settings_empty(self):
        """Test APISettings with no parameters."""
        settings = APISettings()
        
        assert settings.coingecko_api_key is None
        assert settings.coinmarketcap_api_key is None
        assert settings.cryptocompare_api_key is None
        assert settings.etherscan_api_key is None
        assert settings.infura_project_id is None
        assert settings.infura_api_key is None
        assert settings.graph_api_key is None
        assert settings.uniswap_v2_subgraph_id is None

    def test_api_settings_with_values(self):
        """Test APISettings with all values provided."""
        settings = APISettings(
            coingecko_api_key="cg_test_key",
            coinmarketcap_api_key="cmc_test_key",
            cryptocompare_api_key="cc_test_key",
            etherscan_api_key="eth_test_key",
            infura_project_id="infura_project",
            infura_api_key="infura_key",
            graph_api_key="graph_key",
            uniswap_v2_subgraph_id="uniswap_id",
        )
        
        assert settings.coingecko_api_key == "cg_test_key"
        assert settings.coinmarketcap_api_key == "cmc_test_key"
        assert settings.cryptocompare_api_key == "cc_test_key"
        assert settings.etherscan_api_key == "eth_test_key"
        assert settings.infura_project_id == "infura_project"
        assert settings.infura_api_key == "infura_key"
        assert settings.graph_api_key == "graph_key"
        assert settings.uniswap_v2_subgraph_id == "uniswap_id"

    def test_api_settings_extra_fields_allowed(self):
        """Test that extra fields are allowed due to ConfigDict(extra='allow')."""
        settings = APISettings(
            etherscan_api_key="test_key",
            custom_api_key="custom_value",  # Extra field
            another_extra="another_value",   # Another extra field
        )
        
        assert settings.etherscan_api_key == "test_key"
        assert hasattr(settings, "custom_api_key")
        assert settings.custom_api_key == "custom_value"
        assert hasattr(settings, "another_extra")
        assert settings.another_extra == "another_value"

    def test_api_settings_dict_conversion(self):
        """Test conversion to and from dict."""
        data = {
            "infura_project_id": "test_project",
            "etherscan_api_key": "test_eth_key",
        }
        
        settings = APISettings(**data)
        assert settings.infura_project_id == "test_project"
        assert settings.etherscan_api_key == "test_eth_key"
        
        # Test model_dump
        result_dict = settings.model_dump()
        assert result_dict["infura_project_id"] == "test_project"
        assert result_dict["etherscan_api_key"] == "test_eth_key"

    def test_api_settings_json_serialization(self):
        """Test JSON serialization and deserialization."""
        settings = APISettings(
            coingecko_api_key="json_test",
            infura_project_id="json_project",
        )
        
        json_str = settings.model_dump_json()
        assert "json_test" in json_str
        assert "json_project" in json_str
        
        # Test loading from JSON
        loaded_settings = APISettings.model_validate_json(json_str)
        assert loaded_settings.coingecko_api_key == "json_test"
        assert loaded_settings.infura_project_id == "json_project"


class TestChainSettings:
    """Test suite for ChainSettings Pydantic model."""

    def test_chain_settings_minimal(self):
        """Test ChainSettings with minimal required fields."""
        settings = ChainSettings(
            name="test_chain",
            chain_id=1,
            http_endpoint="https://test.rpc.com",
        )
        
        assert settings.name == "test_chain"
        assert settings.chain_id == 1
        assert settings.http_endpoint == "https://test.rpc.com"
        assert settings.websocket_endpoint is None
        assert settings.ipc_endpoint is None
        assert settings.max_gas_price_gwei == 100  # Default value
        assert settings.gas_multiplier == 1.1      # Default value
        assert settings.is_poa is False           # Default value

    def test_chain_settings_all_fields(self):
        """Test ChainSettings with all fields provided."""
        settings = ChainSettings(
            name="ethereum",
            chain_id=1,
            http_endpoint="https://mainnet.infura.io/v3/key",
            websocket_endpoint="wss://mainnet.infura.io/ws/v3/key",
            ipc_endpoint="/home/user/.ethereum/geth.ipc",
            max_gas_price_gwei=200.5,
            gas_multiplier=1.5,
            is_poa=True,
        )
        
        assert settings.name == "ethereum"
        assert settings.chain_id == 1
        assert settings.http_endpoint == "https://mainnet.infura.io/v3/key"
        assert settings.websocket_endpoint == "wss://mainnet.infura.io/ws/v3/key"
        assert settings.ipc_endpoint == "/home/user/.ethereum/geth.ipc"
        assert settings.max_gas_price_gwei == 200.5
        assert settings.gas_multiplier == 1.5
        assert settings.is_poa is True

    def test_chain_settings_validation_positive_gas_price(self):
        """Test that max_gas_price_gwei must be positive."""
        with pytest.raises(ValidationError) as exc_info:
            ChainSettings(
                name="test",
                chain_id=1,
                http_endpoint="https://test.com",
                max_gas_price_gwei=0,  # Should fail, must be > 0
            )
        
        assert "greater than 0" in str(exc_info.value)

    def test_chain_settings_validation_positive_gas_multiplier(self):
        """Test that gas_multiplier must be positive."""
        with pytest.raises(ValidationError) as exc_info:
            ChainSettings(
                name="test",
                chain_id=1,
                http_endpoint="https://test.com",
                gas_multiplier=-1.0,  # Should fail, must be > 0
            )
        
        assert "greater than 0" in str(exc_info.value)

    def test_chain_settings_missing_required_fields(self):
        """Test validation error when required fields are missing."""
        with pytest.raises(ValidationError) as exc_info:
            ChainSettings(name="test", chain_id=1)  # Missing http_endpoint
        
        error_messages = str(exc_info.value)
        assert "http_endpoint" in error_messages
        assert "field required" in error_messages.lower() or "missing" in error_messages.lower()

    def test_chain_settings_extra_fields_allowed(self):
        """Test that extra fields are allowed."""
        settings = ChainSettings(
            name="test",
            chain_id=1,
            http_endpoint="https://test.com",
            custom_field="custom_value",  # Extra field
            another_custom=42,            # Another extra field
        )
        
        assert settings.name == "test"
        assert hasattr(settings, "custom_field")
        assert settings.custom_field == "custom_value"
        assert hasattr(settings, "another_custom")
        assert settings.another_custom == 42

    def test_chain_settings_type_conversion(self):
        """Test automatic type conversion."""
        settings = ChainSettings(
            name="test",
            chain_id="42",           # String should convert to int
            http_endpoint="https://test.com",
            max_gas_price_gwei="150.5",  # String should convert to float
            gas_multiplier="2.0",        # String should convert to float
            is_poa="true",              # String should convert to bool
        )
        
        assert settings.chain_id == 42
        assert settings.max_gas_price_gwei == 150.5
        assert settings.gas_multiplier == 2.0
        assert settings.is_poa is True


class TestGlobalSettings:
    """Test suite for GlobalSettings Pydantic model."""

    def test_global_settings_defaults(self):
        """Test GlobalSettings with default values."""
        settings = GlobalSettings()
        
        assert settings.debug is False
        assert isinstance(settings.base_path, Path)
        # Default base_path should be current directory or a sensible default

    def test_global_settings_with_values(self):
        """Test GlobalSettings with custom values."""
        custom_path = Path("/custom/path")
        
        settings = GlobalSettings(
            debug=True,
            base_path=custom_path,
        )
        
        assert settings.debug is True
        assert settings.base_path == custom_path

    def test_global_settings_path_conversion(self):
        """Test that string paths are converted to Path objects."""
        settings = GlobalSettings(
            base_path="/test/path/string"  # String should convert to Path
        )
        
        assert isinstance(settings.base_path, Path)
        assert str(settings.base_path) == "/test/path/string"

    def test_global_settings_extra_fields_allowed(self):
        """Test that extra fields are allowed."""
        settings = GlobalSettings(
            debug=True,
            extra_config="extra_value",
            another_field=123,
        )
        
        assert settings.debug is True
        assert hasattr(settings, "extra_config")
        assert settings.extra_config == "extra_value"
        assert hasattr(settings, "another_field")
        assert settings.another_field == 123

    def test_global_settings_type_validation(self):
        """Test type validation for GlobalSettings."""
        # Test invalid debug type
        with pytest.raises(ValidationError):
            GlobalSettings(debug="not_a_boolean")

    def test_global_settings_dict_operations(self):
        """Test dictionary operations on GlobalSettings."""
        settings = GlobalSettings(debug=True)
        
        # Test model_dump
        data = settings.model_dump()
        assert data["debug"] is True
        assert "base_path" in data

        # Test creating from dict
        new_settings = GlobalSettings(**data)
        assert new_settings.debug is True


class TestMultiChainSettings:
    """Test suite for MultiChainSettings Pydantic model."""

    def test_multi_chain_settings_empty(self):
        """Test MultiChainSettings with no chains."""
        settings = MultiChainSettings()
        
        assert settings.chains == {}

    def test_multi_chain_settings_with_chains(self):
        """Test MultiChainSettings with multiple chains."""
        chain1 = ChainSettings(
            name="ethereum",
            chain_id=1,
            http_endpoint="https://eth.rpc.com"
        )
        chain2 = ChainSettings(
            name="polygon",
            chain_id=137,
            http_endpoint="https://polygon.rpc.com"
        )
        
        settings = MultiChainSettings(
            chains={"ethereum": chain1, "polygon": chain2}
        )
        
        assert len(settings.chains) == 2
        assert "ethereum" in settings.chains
        assert "polygon" in settings.chains
        assert settings.chains["ethereum"].chain_id == 1
        assert settings.chains["polygon"].chain_id == 137

    def test_multi_chain_settings_from_dict(self):
        """Test creating MultiChainSettings from dictionary data."""
        data = {
            "chains": {
                "mainnet": {
                    "name": "ethereum",
                    "chain_id": 1,
                    "http_endpoint": "https://mainnet.infura.io/v3/key"
                },
                "testnet": {
                    "name": "goerli",
                    "chain_id": 5,
                    "http_endpoint": "https://goerli.infura.io/v3/key"
                }
            }
        }
        
        settings = MultiChainSettings(**data)
        
        assert len(settings.chains) == 2
        assert isinstance(settings.chains["mainnet"], ChainSettings)
        assert isinstance(settings.chains["testnet"], ChainSettings)
        assert settings.chains["mainnet"].name == "ethereum"
        assert settings.chains["testnet"].name == "goerli"

    def test_multi_chain_settings_extra_fields_allowed(self):
        """Test that extra fields are allowed in MultiChainSettings."""
        settings = MultiChainSettings(
            chains={},
            global_timeout=30,
            retry_attempts=3,
        )
        
        assert settings.chains == {}
        assert hasattr(settings, "global_timeout")
        assert settings.global_timeout == 30
        assert hasattr(settings, "retry_attempts")
        assert settings.retry_attempts == 3

    def test_multi_chain_settings_invalid_chain_data(self):
        """Test validation error with invalid chain data."""
        with pytest.raises(ValidationError):
            MultiChainSettings(
                chains={
                    "invalid": {
                        "name": "test",
                        # Missing required fields like chain_id and http_endpoint
                    }
                }
            )

    def test_multi_chain_settings_json_serialization(self):
        """Test JSON serialization of MultiChainSettings."""
        chain = ChainSettings(
            name="test",
            chain_id=42,
            http_endpoint="https://test.com"
        )
        settings = MultiChainSettings(chains={"test": chain})
        
        json_str = settings.model_dump_json()
        assert "test" in json_str
        assert "chain_id" in json_str
        assert "42" in json_str
        
        # Test loading from JSON
        loaded_settings = MultiChainSettings.model_validate_json(json_str)
        assert "test" in loaded_settings.chains
        assert loaded_settings.chains["test"].chain_id == 42


class TestModelIntegration:
    """Test integration between different settings models."""

    def test_nested_model_validation(self):
        """Test that nested models are properly validated."""
        # This should work
        valid_data = {
            "chains": {
                "eth": {
                    "name": "ethereum",
                    "chain_id": 1,
                    "http_endpoint": "https://eth.rpc.com"
                }
            }
        }
        settings = MultiChainSettings(**valid_data)
        assert isinstance(settings.chains["eth"], ChainSettings)

    def test_model_inheritance_and_config(self):
        """Test that all models properly inherit BaseModel features."""
        models_to_test = [
            APISettings(),
            ChainSettings(name="test", chain_id=1, http_endpoint="https://test.com"),
            GlobalSettings(),
            MultiChainSettings(),
        ]
        
        for model in models_to_test:
            # All should have model_dump method
            assert hasattr(model, "model_dump")
            assert callable(model.model_dump)
            
            # All should have model_dump_json method
            assert hasattr(model, "model_dump_json")
            assert callable(model.model_dump_json)
            
            # All should be able to convert to dict
            result = model.model_dump()
            assert isinstance(result, dict)
            
            # All should be able to convert to JSON
            json_result = model.model_dump_json()
            assert isinstance(json_result, str)

    def test_complex_configuration_scenario(self):
        """Test a complex configuration scenario combining all models."""
        # Create a comprehensive configuration
        api_settings = APISettings(
            infura_project_id="test_project",
            etherscan_api_key="test_eth_key"
        )
        
        eth_chain = ChainSettings(
            name="ethereum",
            chain_id=1,
            http_endpoint="https://mainnet.infura.io/v3/test_project",
            max_gas_price_gwei=100,
            gas_multiplier=1.2
        )
        
        polygon_chain = ChainSettings(
            name="polygon",
            chain_id=137,
            http_endpoint="https://polygon-mainnet.infura.io/v3/test_project",
            max_gas_price_gwei=50,
            gas_multiplier=1.1
        )
        
        global_settings = GlobalSettings(
            debug=True,
            base_path="/app"
        )
        
        multi_chain_settings = MultiChainSettings(
            chains={"ethereum": eth_chain, "polygon": polygon_chain}
        )
        
        # Verify all models work correctly
        assert api_settings.infura_project_id == "test_project"
        assert eth_chain.chain_id == 1
        assert polygon_chain.chain_id == 137
        assert global_settings.debug is True
        assert len(multi_chain_settings.chains) == 2
        
        # Verify serialization works for complex nested structure
        multi_chain_json = multi_chain_settings.model_dump_json()
        loaded_multi_chain = MultiChainSettings.model_validate_json(multi_chain_json)
        assert len(loaded_multi_chain.chains) == 2
        assert loaded_multi_chain.chains["ethereum"].name == "ethereum"
        assert loaded_multi_chain.chains["polygon"].name == "polygon"


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_empty_string_fields(self):
        """Test handling of empty string fields."""
        settings = ChainSettings(
            name="",  # Empty string
            chain_id=1,
            http_endpoint="https://test.com"
        )
        assert settings.name == ""

    def test_very_large_numbers(self):
        """Test handling of very large numbers."""
        settings = ChainSettings(
            name="test",
            chain_id=999999999999,  # Very large chain ID
            http_endpoint="https://test.com",
            max_gas_price_gwei=999999.999,  # Very large gas price
        )
        assert settings.chain_id == 999999999999
        assert settings.max_gas_price_gwei == 999999.999

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters."""
        settings = ChainSettings(
            name="测试链 🚀 émojis ñ",  # Unicode and emojis
            chain_id=1,
            http_endpoint="https://test.com/émoji-path",
        )
        assert "🚀" in settings.name
        assert "émoji" in settings.http_endpoint

    def test_none_vs_missing_fields(self):
        """Test distinction between None and missing optional fields."""
        # Explicitly set to None
        settings1 = ChainSettings(
            name="test",
            chain_id=1,
            http_endpoint="https://test.com",
            websocket_endpoint=None
        )
        
        # Not provided at all (should also be None)
        settings2 = ChainSettings(
            name="test",
            chain_id=1,
            http_endpoint="https://test.com"
        )
        
        assert settings1.websocket_endpoint is None
        assert settings2.websocket_endpoint is None

    def test_model_copy_and_update(self):
        """Test model copying and updating."""
        original = ChainSettings(
            name="original",
            chain_id=1,
            http_endpoint="https://original.com"
        )
        
        # Test model copy with updates
        updated = original.model_copy(update={"name": "updated", "chain_id": 2})
        
        assert original.name == "original"  # Original unchanged
        assert original.chain_id == 1
        assert updated.name == "updated"    # Updated version changed
        assert updated.chain_id == 2
        assert updated.http_endpoint == "https://original.com"  # Unchanged field preserved

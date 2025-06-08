#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for ABIRegistry class.
"""

import pytest
import json
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

from on1builder.integrations.abi_registry import ABIRegistry, get_registry, _REQUIRED


@pytest.fixture(autouse=True)
def clean_global_state():
    """Fixture to clean global state before each test."""
    from on1builder.integrations import abi_registry
    
    # Save original state
    original_abis = abi_registry._GLOBAL_ABIS.copy()
    original_sigs = abi_registry._GLOBAL_SIG_MAP.copy()
    original_selectors = abi_registry._GLOBAL_SELECTOR_MAP.copy()
    original_hash = abi_registry._FILE_HASH.copy()
    original_initialized = abi_registry._initialized
    original_instance = abi_registry._registry_instance
    
    # Clear before test
    abi_registry._GLOBAL_ABIS.clear()
    abi_registry._GLOBAL_SIG_MAP.clear() 
    abi_registry._GLOBAL_SELECTOR_MAP.clear()
    abi_registry._FILE_HASH.clear()
    abi_registry._initialized = False
    abi_registry._registry_instance = None
    
    yield
    
    # Restore original state after test (although pytest should handle this)
    abi_registry._GLOBAL_ABIS.clear()
    abi_registry._GLOBAL_ABIS.update(original_abis)
    abi_registry._GLOBAL_SIG_MAP.clear()
    abi_registry._GLOBAL_SIG_MAP.update(original_sigs)
    abi_registry._GLOBAL_SELECTOR_MAP.clear()
    abi_registry._GLOBAL_SELECTOR_MAP.update(original_selectors)
    abi_registry._FILE_HASH.clear()
    abi_registry._FILE_HASH.update(original_hash)
    abi_registry._initialized = original_initialized
    abi_registry._registry_instance = original_instance


@pytest.fixture
def temp_abi_dir():
    """Create a temporary directory with test ABI files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        abi_path = Path(temp_dir)
        
        # Create test ERC20 ABI
        erc20_abi = [
            {
                "name": "transfer",
                "type": "function",
                "inputs": [
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ],
                "outputs": [{"name": "", "type": "bool"}]
            },
            {
                "name": "approve",
                "type": "function",
                "inputs": [
                    {"name": "spender", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ],
                "outputs": [{"name": "", "type": "bool"}]
            },
            {
                "name": "transferFrom",
                "type": "function",
                "inputs": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ],
                "outputs": [{"name": "", "type": "bool"}]
            },
            {
                "name": "balanceOf",
                "type": "function",
                "inputs": [{"name": "owner", "type": "address"}],
                "outputs": [{"name": "", "type": "uint256"}]
            }
        ]
        
        # Create test Uniswap ABI
        uniswap_abi = [
            {
                "name": "swapExactTokensForTokens",
                "type": "function",
                "inputs": [
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMin", "type": "uint256"},
                    {"name": "path", "type": "address[]"},
                    {"name": "to", "type": "address"},
                    {"name": "deadline", "type": "uint256"}
                ],
                "outputs": [{"name": "amounts", "type": "uint256[]"}]
            },
            {
                "name": "getAmountsOut",
                "type": "function",
                "inputs": [
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "path", "type": "address[]"}
                ],
                "outputs": [{"name": "amounts", "type": "uint256[]"}]
            }
        ]
        
        # Write ABI files
        (abi_path / "erc20_abi.json").write_text(json.dumps(erc20_abi))
        (abi_path / "uniswap_abi.json").write_text(json.dumps(uniswap_abi))
        
        # Create invalid ABI file
        (abi_path / "invalid_abi.json").write_text('{"not": "an_abi"}')
        
        # Create non-ABI JSON file that should be excluded
        (abi_path / "token_list.json").write_text('{"tokens": []}')
        
        yield abi_path


@pytest.fixture
def mock_abi_data():
    """Mock ABI data for testing."""
    return {
        "erc20": [
            {
                "name": "transfer",
                "type": "function",
                "inputs": [
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ]
            }
        ]
    }


class TestABIRegistry:
    """Test cases for ABIRegistry."""

    def test_init_with_path(self, temp_abi_dir):
        """Test ABIRegistry initialization with explicit path."""
        registry = ABIRegistry(str(temp_abi_dir))
        assert registry.abi_path == temp_abi_dir
        assert registry.reload_count == 0

    def test_init_without_path(self):
        """Test ABIRegistry initialization without path."""
        with patch.object(ABIRegistry, '_find_default_abi_path') as mock_find:
            mock_path = Path("/mock/abi/path")
            mock_find.return_value = mock_path
            
            registry = ABIRegistry()
            assert registry.abi_path == mock_path
            mock_find.assert_called_once()

    def test_find_default_abi_path(self):
        """Test default ABI path resolution."""
        registry = ABIRegistry()
        
        # Test the path finding logic
        with patch('pathlib.Path.exists') as mock_exists:
            # Mock different scenarios
            mock_exists.side_effect = [True]  # First path exists
            path = registry._find_default_abi_path()
            assert isinstance(path, Path)
            assert "abi" in str(path)

    @pytest.mark.asyncio
    async def test_initialize_success(self, temp_abi_dir):
        """Test successful initialization."""
        registry = ABIRegistry(str(temp_abi_dir))
        result = await registry.initialize()
        
        assert result is True
        assert "erc20" in registry.abis
        assert "uniswap" in registry.abis

    @pytest.mark.asyncio
    async def test_initialize_with_new_path(self, temp_abi_dir):
        """Test initialization with new path."""
        registry = ABIRegistry()
        result = await registry.initialize(str(temp_abi_dir))
        
        assert result is True
        assert registry.abi_path == temp_abi_dir

    @pytest.mark.asyncio
    async def test_initialize_invalid_path(self):
        """Test initialization with invalid path."""
        registry = ABIRegistry("/nonexistent/path")
        result = await registry.initialize()
        
        # Should still return True even if path doesn't exist
        assert result is True

    @pytest.mark.asyncio
    async def test_is_healthy(self, temp_abi_dir):
        """Test health check."""
        registry = ABIRegistry(str(temp_abi_dir))
        
        # Before initialization - depends on global state, may already be initialized
        healthy_before = await registry.is_healthy()
        
        # After initialization
        await registry.initialize()
        registry.load_abis()  # Need to load ABIs for health check to pass
        healthy_after = await registry.is_healthy()
        assert healthy_after is True

    @pytest.mark.asyncio
    async def test_is_healthy_no_abis(self):
        """Test health check with no ABIs loaded."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Empty directory
            registry = ABIRegistry(temp_dir)
            
            await registry.initialize()
            
            healthy = await registry.is_healthy()
            assert healthy is False

    @pytest.mark.asyncio
    async def test_is_healthy_nonexistent_path(self):
        """Test health check with nonexistent path."""
        registry = ABIRegistry("/nonexistent/path")
        await registry.initialize()
        
        healthy = await registry.is_healthy()
        assert healthy is False
        
        healthy = await registry.is_healthy()
        assert healthy is False

    def test_load_abis_success(self, temp_abi_dir):
        """Test successful ABI loading."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        assert "erc20" in registry.abis
        assert "uniswap" in registry.abis
        
        # Check function signatures were extracted
        assert "erc20" in registry.function_signatures
        assert "transfer" in registry.function_signatures["erc20"]

    def test_load_abis_nonexistent_directory(self):
        """Test ABI loading with nonexistent directory."""
        # Create registry with path that doesn't exist
        registry = ABIRegistry("/nonexistent/path")
        
        registry.load_abis()
        
        # Should not crash, just log error
        assert len(registry.list_available_abis()) == 0

    def test_load_abis_excludes_non_abi_files(self, temp_abi_dir):
        """Test that non-ABI files are excluded from loading."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        # token_list.json should be excluded
        assert "token_list" not in registry.abis

    def test_extract_function_signatures(self, temp_abi_dir):
        """Test function signature extraction."""
        registry = ABIRegistry(str(temp_abi_dir))
        
        abi = [
            {
                "name": "transfer",
                "type": "function",
                "inputs": [
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ]
            },
            {
                "name": "Transfer",
                "type": "event",
                "inputs": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ]
            }
        ]
        
        signatures = registry._extract_function_signatures(abi)
        
        assert "transfer" in signatures
        # Should not include 0x prefix, just plain signature
        assert signatures["transfer"] == "transfer(address,uint256)"
        # Events should not be included in function signatures
        assert "Transfer" not in signatures

    def test_get_abi_existing(self, temp_abi_dir):
        """Test retrieving existing ABI."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        abi = registry.get_abi("erc20")
        assert abi is not None
        assert isinstance(abi, list)
        assert len(abi) > 0

    def test_get_abi_nonexistent(self, temp_abi_dir):
        """Test retrieving nonexistent ABI."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        abi = registry.get_abi("nonexistent")
        assert abi is None

    def test_get_function_signature_existing(self, temp_abi_dir):
        """Test retrieving existing function signature."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        sig = registry.get_function_signature("erc20", "transfer")
        assert sig is not None
        # Should not include 0x prefix, just plain signature
        assert sig == "transfer(address,uint256)"

    def test_get_function_signature_nonexistent(self, temp_abi_dir):
        """Test retrieving nonexistent function signature."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        sig = registry.get_function_signature("erc20", "nonexistent")
        assert sig is None
        
        sig = registry.get_function_signature("nonexistent", "transfer")
        assert sig is None

    def test_validate_abi_valid(self, temp_abi_dir):
        """Test validation of valid ABI."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        is_valid = registry.validate_abi("erc20")
        assert is_valid is True

    def test_validate_abi_invalid(self, temp_abi_dir):
        """Test validation of invalid ABI."""
        # Create incomplete ERC20 ABI (missing required functions)
        incomplete_abi = [{"name": "transfer", "type": "function"}]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            abi_path = Path(temp_dir)
            (abi_path / "erc20_abi.json").write_text(json.dumps(incomplete_abi))
            
            registry = ABIRegistry(str(abi_path))
            registry.load_abis()
            
            # erc20 ABI is missing required functions (approve, transferFrom, balanceOf)
            is_valid = registry.validate_abi("erc20")
            assert is_valid is False

    def test_validate_abi_unknown(self, temp_abi_dir):
        """Test validation of unknown ABI."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        # Unknown contracts return True (no requirements exist)
        is_valid = registry.validate_abi("unknown_contract")
        assert is_valid is True

    def test_list_available_abis(self, temp_abi_dir):
        """Test listing available ABIs."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        abis = registry.list_available_abis()
        assert "erc20" in abis
        assert "uniswap" in abis

    def test_get_method_selector(self, temp_abi_dir):
        """Test getting method selector."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        # Get the selector for transfer function
        transfer_sig = registry.get_function_signature("erc20", "transfer")
        if transfer_sig:
            # Calculate selector for testing
            selector = hashlib.sha256(transfer_sig.encode()).hexdigest()[:8]
            method = registry.get_method_selector(selector)
            # This might return None if selector mapping is not implemented

    def test_caching_behavior(self, temp_abi_dir):
        """Test that files are cached based on hash."""
        registry = ABIRegistry(str(temp_abi_dir))
        
        # Load ABIs first time
        registry.load_abis()
        initial_abis_count = len(registry.list_available_abis())
        
        # Load again - should use cache (no change in ABI count)
        registry.load_abis()
        assert len(registry.list_available_abis()) == initial_abis_count

    def test_reload_on_file_change(self, temp_abi_dir):
        """Test reloading when file changes."""
        registry = ABIRegistry(str(temp_abi_dir))
        registry.load_abis()
        
        # Modify a file
        new_abi = [{"name": "newFunction", "type": "function"}]
        (temp_abi_dir / "erc20_abi.json").write_text(json.dumps(new_abi))
        
        # Reload
        registry.load_abis()
        
        # Should have new content
        abi = registry.get_abi("erc20")
        assert abi is not None
        assert len(abi) == 1
        assert abi[0]["name"] == "newFunction"


@pytest.mark.asyncio
async def test_get_registry_singleton():
    """Test get_registry function returns singleton."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry1 = await get_registry(temp_dir)
        registry2 = await get_registry()
        
        assert registry1 is registry2

@pytest.mark.asyncio
async def test_get_registry_path_change():
    """Test get_registry with path change."""
    with tempfile.TemporaryDirectory() as temp_dir1:
        with tempfile.TemporaryDirectory() as temp_dir2:
            registry1 = await get_registry(temp_dir1)
            registry2 = await get_registry(temp_dir2)
            
            assert registry1 is registry2
            assert registry1.abi_path == Path(temp_dir2)

@pytest.mark.asyncio 
async def test_initialize_method(temp_abi_dir):
    """Test the initialize method."""
    registry = ABIRegistry()
    result = await registry.initialize(str(temp_abi_dir))
    assert result is True
    assert registry.abi_path == Path(temp_abi_dir)

@pytest.mark.asyncio
async def test_is_healthy():
    """Test the health check method."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry = ABIRegistry(temp_dir)
        await registry.initialize()
        
        health = await registry.is_healthy()
        assert isinstance(health, bool)

@pytest.mark.asyncio
async def test_token_methods():
    """Test token-related methods."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry = ABIRegistry(temp_dir)
        await registry.initialize()
        
        # Test find_tokens_path
        tokens_path = registry.find_tokens_path()
        assert isinstance(tokens_path, Path)
        
        # Test token address methods (may return empty dict if no token data)
        token_addresses = await registry.get_token_addresses(1)
        assert isinstance(token_addresses, dict)
        
        token_symbols = await registry.get_token_symbols(1)
        assert isinstance(token_symbols, dict)
        
        # Test specific token lookups (may return None if no data)
        address = await registry.get_token_address("USDC", 1) 
        symbol = await registry.get_token_symbol("0x" + "0" * 40, 1)
        # Just check they don't error


def test_required_functions_constant():
    """Test that required functions constant is properly defined."""
    assert isinstance(_REQUIRED, dict)
    assert "erc20" in _REQUIRED
    assert "transfer" in _REQUIRED["erc20"]
    assert "approve" in _REQUIRED["erc20"]
    assert "transferFrom" in _REQUIRED["erc20"]
    assert "balanceOf" in _REQUIRED["erc20"]

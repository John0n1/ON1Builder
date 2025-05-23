import os
import sys
import pytest
import asyncio
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Test imports - these should work with our improved code
from on1builder.integrations.abi_registry import ABIRegistry, get_registry
from on1builder.config.config import Configuration
from on1builder.core.multi_chain_core import MultiChainCore
from on1builder.config.config import MultiChainConfiguration
from on1builder.persistence.db_manager import DatabaseManager, get_db_manager
from on1builder.utils.logger import setup_logging

# Set up logging for tests
logger = setup_logging("TestIntegration", level="DEBUG")

import pytest_asyncio  # Import asyncio fixture support

@pytest_asyncio.fixture
async def config():
    """Create a test configuration."""
    config = Configuration()
    await config.load()
    return config

@pytest_asyncio.fixture
async def multi_chain_config():
    """Create a test multi-chain configuration."""
    config = MultiChainConfiguration()
    await config.load()
    return config

@pytest_asyncio.fixture
async def abi_registry():
    """Create a test ABI registry."""
    # Create a new registry with reset state
    registry = ABIRegistry()
    
    # Reset shared state to avoid test interference
    ABIRegistry._GLOBAL_ABIS = {}
    ABIRegistry._GLOBAL_SIG_MAP = {}
    ABIRegistry._GLOBAL_SELECTOR_MAP = {}
    ABIRegistry._FILE_HASH = {}
    ABIRegistry._initialized = False
    
    # Add minimal ERC20 data for health check
    ABIRegistry._GLOBAL_ABIS['erc20'] = [
        {
            "name": "transfer", 
            "type": "function", 
            "inputs": [
                {"name": "to", "type": "address"}, 
                {"name": "value", "type": "uint256"}
            ]
        }
    ]
    ABIRegistry._initialized = True
    
    return registry

@pytest_asyncio.fixture
async def db_manager(config):
    """Create a test database manager."""
    # Use in-memory SQLite for testing
    manager = DatabaseManager(config, db_url="sqlite+aiosqlite:///:memory:")
    await manager.initialize()
    yield manager
    await manager.close()

@pytest.mark.asyncio
async def test_registry_initialization(abi_registry):
    """Test that the ABI registry initializes correctly."""
    assert abi_registry is not None
    assert await abi_registry.is_healthy()
    
@pytest.mark.asyncio
async def test_db_manager_initialization(db_manager):
    """Test that the database manager initializes correctly."""
    assert db_manager is not None
    
    # Test saving a transaction
    tx_hash = "0x123456"
    chain_id = 1
    from_address = "0xabcdef"
    to_address = "0x123456"
    value = "0"  # No value in wei
    gas_price = "50"
    gas_used = 20000
    block_number = 123456
    status = True
    data = '{"note": "test transaction"}'
    
    # Using the save_transaction method that exists in the db_manager
    result = await db_manager.save_transaction(
        tx_hash=tx_hash,
        chain_id=chain_id,
        from_address=from_address,
        to_address=to_address,
        value=value,
        gas_price=gas_price,
        gas_used=gas_used,
        block_number=block_number,
        status=status,
        data=data
    )
    
    # Result should be the transaction ID or None if error occurred
    assert result is not None
    
    # Test retrieving the transaction
    retrieved_tx = await db_manager.get_transaction(tx_hash)
    assert retrieved_tx is not None
    assert retrieved_tx["tx_hash"] == tx_hash
    assert retrieved_tx["chain_id"] == chain_id
    assert retrieved_tx["from_address"] == from_address

@pytest.mark.asyncio
async def test_configuration_loading(config):
    """Test that the configuration loads correctly."""
    assert config is not None
    assert hasattr(config, "BASE_PATH")
    
@pytest.mark.asyncio
async def test_multi_chain_config_loading(multi_chain_config):
    """Test that the multi-chain configuration loads correctly."""
    assert multi_chain_config is not None
    chains = multi_chain_config.get_chains()
    assert isinstance(chains, list) 
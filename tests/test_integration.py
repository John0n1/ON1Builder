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

@pytest.fixture
async def config():
    """Create a test configuration."""
    config = Configuration()
    await config.load()
    return config

@pytest.fixture
async def multi_chain_config():
    """Create a test multi-chain configuration."""
    config = MultiChainConfiguration()
    await config.load()
    return config

@pytest.fixture
async def abi_registry():
    """Create a test ABI registry."""
    base_path = Path(__file__).parent.parent
    registry = await get_registry(base_path)
    return registry

@pytest.fixture
async def db_manager():
    """Create a test database manager."""
    db_path = ":memory:"  # Use in-memory SQLite for testing
    manager = DatabaseManager(db_path)
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
    
    # Test recording a transaction
    tx = {
        "tx_hash": "0x123456",
        "chain_id": "1",
        "from_address": "0xabcdef",
        "to_address": "0x123456",
        "gas_price": 50,
        "total_gas_cost": 1000000,
        "status": "success"
    }
    
    result = await db_manager.record_transaction(tx)
    assert result is True
    
    # Test retrieving the transaction
    retrieved_tx = await db_manager.get_transaction("0x123456")
    assert retrieved_tx is not None
    assert retrieved_tx["tx_hash"] == "0x123456"

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
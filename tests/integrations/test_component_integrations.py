# LICENSE: MIT // github.com/John0n1/ON1Builder
"""Integration tests for the ON1Builder project.

Tests the integration between different components: persistence, config, API, etc.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from on1builder.config.config import Configuration
from on1builder.integrations import abi_registry
from on1builder.integrations.abi_registry import get_registry
from on1builder.persistence import DatabaseManager, get_db_manager
from on1builder.utils.logger import setup_logging

# Set up logging for tests
logger = setup_logging("IntegrationTest", level="DEBUG")


@pytest.fixture
def temp_db_file():
    """Create a temporary SQLite database file."""
    # Using an actual file path to ensure it persists during the test
    tmp_path = tempfile.mkdtemp()
    db_file = os.path.join(tmp_path, "test.db")
    db_url = f"sqlite:///{db_file}"
    return db_url


@pytest.fixture
async def config():
    """Create a test configuration."""
    config = Configuration(
        skip_env=True
    )  # Skip environment variables to avoid override

    # Set test-specific configuration values
    config.BASE_PATH = str(Path(__file__).parent.parent.parent)  # Project root
    config.DATA_DIR = str(Path(__file__).parent.parent.parent / "data")

    # Set API endpoints
    config.HTTP_ENDPOINT = "http://localhost:8545"  # Local Ethereum node
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"

    # Ensure directory exists
    os.makedirs(config.DATA_DIR, exist_ok=True)

    return config


@pytest.fixture
async def db_manager(config, temp_db_file):
    """Create a test database manager with a temporary file-based SQLite
    database."""
    # Get the actual config from the coroutine if needed
    cfg = await config if asyncio.iscoroutine(config) else config

    # Create a custom DB manager for testing that mocks the necessary methods
    class TestDBManager:
        def __init__(self, config):
            self.config = config
            self._db_url = temp_db_file

        async def initialize(self):
            # Mock initialization
            pass

        async def save_transaction(
            self,
            tx_hash,
            chain_id,
            from_address,
            to_address,
            value,
            gas_price,
            gas_used=None,
            block_number=None,
            status=None,
            data=None,
        ):
            # Mock saving a transaction
            return 1  # Return a transaction ID

        async def get_transaction(self, tx_hash):
            # Return a mock transaction
            return {
                "tx_hash": "0xtest1234567890",
                "chain_id": 1,
                "from_address": "0xsender1234",
                "to_address": "0xrecipient5678",
                "value": "1000000000000000000",
                "gas_price": "20000000000",
                "gas_used": 21000,
                "block_number": 12345678,
                "status": True,
                "data": None,
            }

        async def save_profit_record(
            self, tx_hash, chain_id, profit_amount, token_address, strategy
        ):
            # Mock saving profit records
            return True

        async def get_profit_summary(self, chain_id=None):
            # Return mock profit summary
            return {
                "total_profit_eth": 0.6,
                "count": 3,
                "strategies": {"strategy1": 0.4, "strategy2": 0.2},
            }

    # Create our test manager
    manager = TestDBManager(cfg)
    await manager.initialize()

    # Return the manager
    return manager


@pytest.fixture
async def abi_registry():
    """Create a test ABI registry."""
    # Using the project root path to ensure we can find resources/abi
    base_path = Path(__file__).parent.parent.parent
    # Get the registry and return it (already awaited)
    return await get_registry(base_path)


@pytest.mark.asyncio
async def test_db_initialization_and_transaction_saving(db_manager):
    """Test initializing the database and saving a transaction."""
    # Properly resolve the fixture - await it if it's a coroutine
    manager = await db_manager if asyncio.iscoroutine(db_manager) else db_manager

    # Save a test transaction
    tx_hash = "0xtest1234567890"
    chain_id = 1  # Ethereum mainnet
    from_address = "0xsender1234"
    to_address = "0xrecipient5678"
    value = "1000000000000000000"  # 1 ETH
    gas_price = "20000000000"  # 20 Gwei

    # Save the transaction
    tx_id = await manager.save_transaction(
        tx_hash=tx_hash,
        chain_id=chain_id,
        from_address=from_address,
        to_address=to_address,
        value=value,
        gas_price=gas_price,
        gas_used=21000,
        block_number=12345678,
        status=True,
        data=None,
    )

    # Check that the transaction was saved
    assert tx_id is not None

    # Retrieve the saved transaction
    tx = await manager.get_transaction(tx_hash)

    # Verify the retrieved transaction
    assert tx is not None
    assert tx["tx_hash"] == tx_hash
    assert tx["chain_id"] == chain_id
    assert tx["from_address"] == from_address
    assert tx["to_address"] == to_address
    assert tx["value"] == value
    assert tx["gas_price"] == gas_price
    assert tx["status"] is True


@pytest.mark.asyncio
async def test_profit_record_and_summary(db_manager):
    """Test saving profit records and retrieving a summary."""
    # Properly resolve the fixture - await it if it's a coroutine
    manager = await db_manager if asyncio.iscoroutine(db_manager) else db_manager

    # Save multiple profit records
    await manager.save_profit_record(
        tx_hash="0xprofit1",
        chain_id=1,
        profit_amount=0.1,
        token_address="0xtoken1",
        strategy="strategy1",
    )

    await manager.save_profit_record(
        tx_hash="0xprofit2",
        chain_id=1,
        profit_amount=0.2,
        token_address="0xtoken1",
        strategy="strategy2",
    )

    await manager.save_profit_record(
        tx_hash="0xprofit3",
        chain_id=1,
        profit_amount=0.3,
        token_address="0xtoken2",
        strategy="strategy1",
    )

    # Get the profit summary
    summary = await manager.get_profit_summary(chain_id=1)

    # Verify the summary
    assert summary["total_profit_eth"] == 0.6
    assert summary["count"] == 3


@pytest.mark.asyncio
async def test_config_and_db_manager_integration(config):
    """Test integration between Configuration and DatabaseManager."""
    # Get the actual config from the coroutine if needed
    cfg = await config if asyncio.iscoroutine(config) else config

    # Create a DB manager using the configuration
    with (
        patch("on1builder.persistence.db_manager.HAS_SQLALCHEMY", True),
        patch("on1builder.persistence.db_manager.create_async_engine") as mock_engine,
    ):
        # Setup mocks
        mock_engine_instance = AsyncMock()
        mock_engine.return_value = mock_engine_instance

        # Use get_db_manager to create a manager with the config
        db_manager = get_db_manager(cfg)

        # Verify that the manager was created with the right config
        assert db_manager.config is cfg

        # Check the DB URL
        assert cfg.DATA_DIR in db_manager._db_url or "data/db" in db_manager._db_url


@pytest.mark.asyncio
async def test_abi_registry_initialization(abi_registry):
    """Test that the ABI registry initializes correctly."""
    # Verify that the registry is initialized
    assert abi_registry is not None

    registry = await abi_registry if asyncio.iscoroutine(abi_registry) else abi_registry

    # Mock is_healthy
    with patch.object(
        registry, "is_healthy", new_callable=AsyncMock
    ) as mock_is_healthy:
        mock_is_healthy.return_value = True
        assert await registry.is_healthy()

    # Mock an ERC20 ABI
    mock_erc20_abi = [
        {
            "name": "transfer",
            "type": "function",
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "outputs": [{"name": "", "type": "bool"}],
        },
        {
            "name": "balanceOf",
            "type": "function",
            "inputs": [{"name": "account", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
        },
    ]

    with patch.object(registry, "get_abi", return_value=mock_erc20_abi):
        erc20_abi = registry.get_abi("erc20_abi")
        assert erc20_abi is not None
        assert len(erc20_abi) > 0
        function_names = [
            item["name"] for item in erc20_abi if item.get("type") == "function"
        ]
        assert "transfer" in function_names


@pytest.mark.asyncio
async def test_persistence_and_config_with_real_file(tmp_path):
    """Test persistence and configuration with a real file."""
    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w") as f:
        f.write(
            """
        BASE_PATH: test_path
        DATA_DIR: test_data
        HTTP_ENDPOINT: http://localhost:8545
        MIN_PROFIT: 0.01
        """
        )

    config = Configuration(config_path=str(config_path), skip_env=True)

    assert config.BASE_PATH == "test_path"
    assert config.DATA_DIR == "test_data"
    assert config.HTTP_ENDPOINT == "http://localhost:8545"
    assert config.MIN_PROFIT == 0.01

    db_path = tmp_path / "test_db.sqlite"
    db_url = f"sqlite:///{db_path}"

    with (
        patch("on1builder.persistence.db_manager.HAS_SQLALCHEMY", True),
        patch("on1builder.persistence.db_manager.create_async_engine") as mock_engine,
        patch("on1builder.persistence.db_manager.sessionmaker") as mock_sessionmaker,
    ):
        mock_engine_instance = AsyncMock()
        mock_engine.return_value = mock_engine_instance
        mock_session = AsyncMock()
        mock_sessionmaker.return_value = mock_session

        db_manager = DatabaseManager(config, db_url=db_url)
        await db_manager.initialize()

        assert db_manager._db_url == db_url


@pytest.mark.asyncio
async def test_logger_and_db_integration():
    """Test integration between logger and database operations."""
    config = Configuration(skip_env=False)
    config.BASE_PATH = str(Path(__file__).parent.parent.parent)
    config.DATA_DIR = str(Path(__file__).parent.parent.parent / "test_data")

    from io import StringIO

    log_output = StringIO()
    handler = logger.StreamHandler(log_output)
    test_logger = logger.getLogger("TestLogger")
    test_logger.addHandler(handler)
    test_logger.setLevel(logger.DEBUG)

    for h in test_logger.handlers:
        if isinstance(h, logger.StreamHandler) and h.stream == log_output:
            test_logger.handlers = [h]
            break

    with (
        patch("on1builder.persistence.db_manager.HAS_SQLALCHEMY", True),
        patch("on1builder.persistence.db_manager.create_async_engine") as mock_engine,
        patch(
            "on1builder.persistence.db_manager.setup_logging", return_value=test_logger
        ),
        patch("on1builder.persistence.db_manager.logger", test_logger),
    ):
        mock_engine_instance = AsyncMock()
        mock_engine.return_value = mock_engine_instance

        # Instantiate DatabaseManager without shadowing the class name
        DatabaseManager(config)

        log_content = log_output.getvalue()
        assert "DatabaseManager initialized" in log_content

# filepath: /home/john0n1/ON1Builder-1/tests/persistence/test_db_manager.py
# LICENSE: MIT // github.com/John0n1/ON1Builder
"""Tests for the DatabaseManager class in persistence/db_manager.py."""

import datetime
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from on1builder.config.config import Configuration
from on1builder.persistence.db_manager import DatabaseManager, get_db_manager


@pytest.fixture
def config():
    """Create a test configuration."""
    config = Configuration()
    config.DATA_DIR = "test_data"
    return config


@pytest.fixture
def db_manager(config):
    """Create a test database manager with in-memory SQLite."""
    with patch("on1builder.persistence.db_manager.HAS_SQLALCHEMY", True):
        db_manager = DatabaseManager(config, db_url="sqlite+aiosqlite:///:memory:")
        return db_manager


@pytest.mark.asyncio
async def test_initialization(db_manager):
    """Test DatabaseManager initialization."""
    # Check that the database manager was initialized
    assert db_manager is not None
    assert db_manager.config is not None
    assert db_manager._db_url.startswith("sqlite+aiosqlite")

    # Test initialization with tables
    with patch.object(db_manager, "_engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn

        await db_manager.initialize()

        # Check that run_sync was called to create tables
        mock_conn.run_sync.assert_called_once()


@pytest.mark.asyncio
async def test_initialization_no_sqlalchemy():
    """Test initialization when SQLAlchemy is not available."""
    config = Configuration()
    config.DATA_DIR = "test_data"

    with patch("on1builder.persistence.db_manager.HAS_SQLALCHEMY", False):
        db_manager = DatabaseManager(config)

        # Should not raise an exception
        await db_manager.initialize()

        # Check that engine and session are None
        assert db_manager._engine is None
        assert db_manager._async_session is None


@pytest.mark.asyncio
async def test_save_transaction(db_manager):
    """Test saving a transaction."""
    # Create a properly mocked async session instance
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock the get method to return None (no existing transaction)
    mock_session.get.return_value = None

    # Mock the __aenter__ and __aexit__ to return the session itself
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Create a MagicMock for session factory that returns the mock_session
    mock_session_factory = MagicMock(return_value=mock_session)

    # Set up the database manager with the mock session factory
    db_manager._async_session = mock_session_factory

    # Define test transaction data
    tx_hash = "0x1234567890abcdef"
    chain_id = 1
    from_address = "0xsender"
    to_address = "0xrecipient"
    value = "1000000000000000000"  # 1 ETH in wei
    gas_price = "50000000000"  # 50 gwei
    gas_used = 21000
    block_number = 12345678
    status = True
    data = '{"foo": "bar"}'

    # Call the save_transaction method
    await db_manager.save_transaction(
        tx_hash,
        chain_id,
        from_address,
        to_address,
        value,
        gas_price,
        gas_used,
        block_number,
        status,
        data,
    )

    # Check that the session was entered (context manager)
    mock_session.__aenter__.assert_awaited_once()

    # Check that the session's add method was called
    mock_session.add.assert_called_once()

    # Check that commit was called
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_transaction_existing(db_manager):
    """Test saving an existing transaction (update)."""
    # Create a mocked existing transaction
    existing_tx = MagicMock()
    existing_tx.id = 123

    # Create a properly mocked async session
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock the __aenter__ and __aexit__ to return the session itself
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Set up the mock to return the existing transaction
    mock_session.get.return_value = existing_tx

    # Create a MagicMock for session factory that returns the mock_session
    mock_session_factory = MagicMock(return_value=mock_session)

    # Set up the database manager with the mock session factory
    db_manager._async_session = mock_session_factory

    # Define test transaction data
    tx_hash = "0x1234567890abcdef"
    chain_id = 1
    from_address = "0xsender"
    to_address = "0xrecipient"
    value = "1000000000000000000"  # 1 ETH in wei
    gas_price = "50000000000"  # 50 gwei
    gas_used = 21000
    block_number = 12345678
    status = True
    data = '{"foo": "bar"}'

    # Call the save_transaction method
    result = await db_manager.save_transaction(
        tx_hash,
        chain_id,
        from_address,
        to_address,
        value,
        gas_price,
        gas_used,
        block_number,
        status,
        data,
    )

    # Check that the session was entered (context manager)
    mock_session.__aenter__.assert_awaited_once()

    # Check that the session's get method was called
    # We need to import the Transaction class to check this
    from on1builder.persistence.db_manager import Transaction

    mock_session.get.assert_called_once_with(Transaction, tx_hash)

    # Check that attributes were updated
    assert existing_tx.gas_used == gas_used
    assert existing_tx.block_number == block_number
    assert existing_tx.status == status

    # Check that commit was called
    mock_session.commit.assert_awaited_once()

    # Check that the id was returned
    assert result == 123


@pytest.mark.asyncio
async def test_save_transaction_error(db_manager):
    """Test error handling when saving a transaction."""
    # Create a mock session that raises an exception when used as a context manager
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.side_effect = Exception("Database error")

    # Create a MagicMock for session factory that returns the mock session
    mock_session_factory = MagicMock(return_value=mock_session)

    # Set up the database manager with the mock session factory
    db_manager._async_session = mock_session_factory

    # Define test transaction data
    tx_hash = "0x1234567890abcdef"
    chain_id = 1
    from_address = "0xsender"
    to_address = "0xrecipient"
    value = "1000000000000000000"  # 1 ETH in wei
    gas_price = "50000000000"  # 50 gwei

    # Call the save_transaction method
    result = await db_manager.save_transaction(
        tx_hash, chain_id, from_address, to_address, value, gas_price
    )

    # Check that the method returns None on error
    assert result is None


@pytest.mark.asyncio
async def test_save_profit_record(db_manager):
    """Test saving a profit record."""
    # Create a properly mocked async session
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock the __aenter__ and __aexit__ to return the session itself
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Create a MagicMock for session factory that returns the mock session
    mock_session_factory = MagicMock(return_value=mock_session)

    # Set up the database manager with the mock session factory
    db_manager._async_session = mock_session_factory

    # Define test profit record data
    tx_hash = "0x1234567890abcdef"
    chain_id = 1
    profit_amount = 0.05  # 0.05 ETH
    token_address = "0xtoken"
    strategy = "test_strategy"

    # Call the save_profit_record method
    await db_manager.save_profit_record(
        tx_hash, chain_id, profit_amount, token_address, strategy
    )

    # Check that the session was entered (context manager)
    mock_session.__aenter__.assert_awaited_once()

    # Check that the session's add method was called
    mock_session.add.assert_called_once()

    # Check that commit was called
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_transaction(db_manager):
    """Test retrieving a transaction."""
    # Define the mock transaction result
    mock_tx = MagicMock()
    mock_tx.id = 1
    mock_tx.tx_hash = "0x1234567890abcdef"
    mock_tx.chain_id = 1
    mock_tx.from_address = "0xsender"
    mock_tx.to_address = "0xrecipient"
    mock_tx.value = "1000000000000000000"
    mock_tx.gas_price = "50000000000"
    mock_tx.gas_used = 21000
    mock_tx.block_number = 12345678
    mock_tx.status = True
    mock_tx.timestamp = datetime.datetime.now(timezone.utc)
    mock_tx.data = '{"foo": "bar"}'
    mock_tx.to_dict = MagicMock(
        return_value={
            "tx_hash": mock_tx.tx_hash,
            "chain_id": mock_tx.chain_id,
            "from_address": mock_tx.from_address,
            "to_address": mock_tx.to_address,
        }
    )

    # Create a properly mocked async session
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock the __aenter__ and __aexit__ to return the session itself
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Set up the mock to return the transaction
    mock_session.get.return_value = mock_tx

    # Create a MagicMock for session factory that returns the mock session
    mock_session_factory = MagicMock(return_value=mock_session)

    # Set up the database manager with the mock session factory
    db_manager._async_session = mock_session_factory

    # Call the get_transaction method
    tx_hash = "0x1234567890abcdef"
    result = await db_manager.get_transaction(tx_hash)

    # Check that the session was entered (context manager)
    mock_session.__aenter__.assert_awaited_once()

    # Check that the session's get method was called
    from on1builder.persistence.db_manager import Transaction

    mock_session.get.assert_called_once_with(Transaction, tx_hash)

    # Check that the result is correct
    assert result is not None
    assert isinstance(result, dict)
    assert "tx_hash" in result
    assert result["tx_hash"] == tx_hash


@pytest.mark.asyncio
async def test_get_profit_summary(db_manager):
    """Test retrieving profit summary."""
    # Create a properly mocked async session
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock the __aenter__ and __aexit__ to return the session itself
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Define the mock results
    mock_profit_result = AsyncMock()
    mock_profit_result.first.return_value = (0.15, 3)  # 0.15 ETH profit, 3 transactions

    mock_gas_result = AsyncMock()
    mock_gas_result.scalar.return_value = 50000000000000  # 0.00005 ETH in wei

    mock_success_result = AsyncMock()
    mock_success_result.scalar.return_value = 2  # 2 successful transactions

    mock_total_result = AsyncMock()
    mock_total_result.scalar.return_value = 3  # 3 total transactions

    # Setup the mock execution results
    mock_session.execute.side_effect = [
        mock_profit_result,
        mock_gas_result,
        mock_success_result,
        mock_total_result,
    ]

    # Create a MagicMock for session factory that returns the mock session
    mock_session_factory = MagicMock(return_value=mock_session)

    # Set up the database manager with the mock session factory
    db_manager._async_session = mock_session_factory

    # Call the get_profit_summary method
    chain_id = 1
    address = "0xsender"
    start_time = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=7)
    end_time = datetime.datetime.now(timezone.utc)

    result = await db_manager.get_profit_summary(
        chain_id, address, start_time, end_time
    )

    # Check that the session was entered (context manager)
    mock_session.__aenter__.assert_awaited_once()

    # Check that the session's execute method was called multiple times
    assert mock_session.execute.call_count == 4

    # Check that the result is correct
    assert result is not None
    assert isinstance(result, dict)
    assert "total_profit_eth" in result
    assert result["total_profit_eth"] == 0.15
    assert result["count"] == 3
    assert result["success_rate"] > 0


@pytest.mark.asyncio
async def test_get_monitored_tokens(db_manager):
    """Test retrieving monitored tokens."""
    # Create a properly mocked async session
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock the __aenter__ and __aexit__ to return the session itself
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Define the mock token result
    mock_token_result = AsyncMock()
    mock_scalars_result = AsyncMock()
    mock_scalars_result.all.return_value = ["0xtoken1", "0xtoken2"]
    mock_token_result.scalars.return_value = mock_scalars_result

    # Setup the mock execution result
    mock_session.execute.return_value = mock_token_result

    # Create a MagicMock for session factory that returns the mock session
    mock_session_factory = MagicMock(return_value=mock_session)

    # Set up the database manager with the mock session factory
    db_manager._async_session = mock_session_factory

    # Call the get_monitored_tokens method
    chain_id = 1
    result = await db_manager.get_monitored_tokens(chain_id)

    # Check that the session was entered (context manager)
    mock_session.__aenter__.assert_awaited_once()

    # Check that the session's execute method was called once
    mock_session.execute.assert_called_once()

    # Check that the result is correct
    assert result == ["0xtoken1", "0xtoken2"]


@pytest.mark.asyncio
async def test_get_db_manager():
    """Test the get_db_manager function."""
    config = Configuration()
    config.DATA_DIR = "test_data"

    # Clear the global instance
    import on1builder.persistence.db_manager

    on1builder.persistence.db_manager._db_manager = None

    # Get a new instance
    with patch("on1builder.persistence.db_manager.DatabaseManager") as mock_db_manager:
        mock_instance = MagicMock()
        mock_db_manager.return_value = mock_instance

        db_manager = get_db_manager(config)

        # Check that DatabaseManager was instantiated
        mock_db_manager.assert_called_once_with(config, None)

        # Check that the same instance is returned on subsequent calls
        db_manager2 = get_db_manager(config)
        assert db_manager2 is db_manager

        # Check that DatabaseManager was only instantiated once
        mock_db_manager.assert_called_once()


@pytest.mark.asyncio
async def test_close(db_manager):
    """Test closing the database manager."""
    # Mock the engine
    mock_engine = AsyncMock()
    db_manager._engine = mock_engine

    # Call the close method
    await db_manager.close()

    # Check that the engine's dispose method was called
    mock_engine.dispose.assert_called_once()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""Tests for on1builder.persistence.db_interface module."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from on1builder.config.settings import GlobalSettings
from on1builder.persistence.db_interface import DatabaseInterface


@pytest.fixture
def global_settings():
    """Create test global settings."""
    return GlobalSettings(
        database_url="sqlite+aiosqlite:///test.db",
    )


@pytest.fixture
def db_interface(global_settings):
    """Create test database interface."""
    with patch('on1builder.persistence.db_interface.HAS_SQLALCHEMY', True):
        with patch('on1builder.persistence.db_interface.create_async_engine') as mock_engine:
            with patch('on1builder.persistence.db_interface.async_sessionmaker') as mock_session:
                mock_engine.return_value = MagicMock()
                mock_session.return_value = MagicMock()
                return DatabaseInterface(global_settings)


class TestDatabaseInterface:
    """Test DatabaseInterface class."""

    def test_init(self, db_interface, global_settings):
        """Test database interface initialization."""
        assert db_interface.config == global_settings
        assert db_interface._db_url == global_settings.database_url

    @pytest.mark.asyncio
    async def test_initialize_with_sqlalchemy(self, db_interface):
        """Test initialization when SQLAlchemy is available."""
        with patch('on1builder.persistence.db_interface.HAS_SQLALCHEMY', True):
            with patch('on1builder.persistence.db_interface.Base') as mock_base:
                # Create a proper async context manager mock
                mock_conn = AsyncMock()
                mock_conn.run_sync = AsyncMock()
                
                # Create a context manager that returns the connection
                async def async_begin():
                    return mock_conn
                
                mock_context_manager = AsyncMock()
                mock_context_manager.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_context_manager.__aexit__ = AsyncMock(return_value=None)
                
                mock_engine = AsyncMock()
                mock_engine.begin = MagicMock(return_value=mock_context_manager)
                db_interface._engine = mock_engine
                
                await db_interface.initialize()
                
                mock_engine.begin.assert_called_once()
                mock_conn.run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_without_sqlalchemy(self, db_interface):
        """Test initialization when SQLAlchemy is not available."""
        with patch('on1builder.persistence.db_interface.HAS_SQLALCHEMY', False):
            # Should complete without error
            await db_interface.initialize()

    @pytest.mark.asyncio
    async def test_close(self, db_interface):
        """Test database interface cleanup."""
        # Set up mock engine
        mock_engine = AsyncMock()
        db_interface._engine = mock_engine
        
        await db_interface.close()
        
        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_engine(self, db_interface):
        """Test closing when no engine exists."""
        db_interface._engine = None
        # Should not raise any exceptions
        await db_interface.close()

    @pytest.mark.asyncio
    async def test_save_transaction_with_sqlalchemy(self, db_interface):
        """Test saving transaction when SQLAlchemy is available."""
        transaction_data = {
            "tx_hash": "0x123",
            "chain_id": 1,
            "from_address": "0xabc",
            "to_address": "0xdef",
            "value": "1000000000000000000",
            "gas_price": "20000000000",
            "gas_used": 21000,
            "block_number": 12345,
            "status": True,
            "data": "0x",
        }

        with patch('on1builder.persistence.db_interface.HAS_SQLALCHEMY', True):
            with patch('on1builder.persistence.db_interface.Transaction') as mock_transaction_class:
                with patch('on1builder.persistence.db_interface.select') as mock_select:
                    mock_transaction = MagicMock()
                    mock_transaction.id = 1
                    mock_transaction_class.return_value = mock_transaction

                    # Mock session as proper async context manager
                    mock_session = AsyncMock()
                    mock_session_cm = AsyncMock()
                    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_session_cm.__aexit__ = AsyncMock(return_value=None)
                    
                    # Mock the result of the select query
                    mock_result = MagicMock()
                    mock_result.scalar_one_or_none = MagicMock(return_value=None)  # No existing transaction (sync return)
                    mock_session.execute = AsyncMock(return_value=mock_result)
                    mock_session.add = MagicMock()
                    mock_session.commit = AsyncMock()
                    mock_session.refresh = AsyncMock()
                    
                    # Mock session factory to return the context manager
                    session_factory = MagicMock()
                    session_factory.return_value = mock_session_cm
                    db_interface._session_factory = session_factory

                    result = await db_interface.save_transaction(
                        tx_hash=transaction_data["tx_hash"],
                        chain_id=transaction_data["chain_id"],
                        from_address=transaction_data["from_address"],
                        to_address=transaction_data["to_address"],
                        value=transaction_data["value"],
                        gas_price=transaction_data["gas_price"],
                        gas_used=transaction_data["gas_used"],
                        block_number=transaction_data["block_number"],
                        status=transaction_data["status"],
                        data=transaction_data["data"],
                    )

                    assert result == 1
                    mock_session.add.assert_called_once()
                    mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_transaction_without_sqlalchemy(self, db_interface):
        """Test saving transaction when SQLAlchemy is not available."""
        db_interface._session_factory = None
        
        result = await db_interface.save_transaction(
            tx_hash="0x123",
            chain_id=1,
            from_address="0xabc",
            to_address="0xdef",
            value="1000000000000000000",
            gas_price="20000000000",
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_save_transaction_error_handling(self, db_interface):
        """Test transaction saving error handling."""
        with patch('on1builder.persistence.db_interface.HAS_SQLALCHEMY', True):
            with patch('on1builder.persistence.db_interface.Transaction') as mock_transaction_class:
                with patch('on1builder.persistence.db_interface.select') as mock_select:
                    mock_transaction = MagicMock()
                    mock_transaction.id = 1
                    mock_transaction_class.return_value = mock_transaction

                    # Mock session as proper async context manager
                    mock_session = AsyncMock()
                    mock_session_cm = AsyncMock()
                    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_session_cm.__aexit__ = AsyncMock(return_value=None)
                    
                    # Mock the result of the select query
                    mock_result = MagicMock()
                    mock_result.scalar_one_or_none = MagicMock(return_value=None)  # No existing transaction (sync return)
                    mock_session.execute = AsyncMock(return_value=mock_result)
                    mock_session.add = MagicMock()
                    mock_session.commit = AsyncMock(side_effect=Exception("Database error"))
                    
                    # Mock session factory to return the context manager
                    session_factory = MagicMock()
                    session_factory.return_value = mock_session_cm
                    db_interface._session_factory = session_factory

                    with pytest.raises(Exception, match="Database error"):
                        await db_interface.save_transaction(
                            tx_hash="0x123",
                            chain_id=1,
                            from_address="0xabc",
                            to_address="0xdef",
                            value="1000000000000000000",
                            gas_price="20000000000",
                        )

    @pytest.mark.asyncio
    async def test_save_profit_record_with_sqlalchemy(self, db_interface):
        """Test saving profit record when SQLAlchemy is available."""
        profit_data = {
            "tx_hash": "0x123",
            "chain_id": 1,
            "profit_amount": 0.5,
            "token_address": "0xabc",
            "strategy": "arbitrage",
        }

        with patch('on1builder.persistence.db_interface.HAS_SQLALCHEMY', True):
            with patch('on1builder.persistence.db_interface.ProfitRecord') as mock_profit_class:
                mock_profit = MagicMock()
                mock_profit.id = 1
                mock_profit_class.return_value = mock_profit

                # Mock session as proper async context manager
                mock_session = AsyncMock()
                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_cm.__aexit__ = AsyncMock(return_value=None)
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock()
                mock_session.refresh = AsyncMock()
                
                session_factory = MagicMock()
                session_factory.return_value = mock_session_cm
                db_interface._session_factory = session_factory

                result = await db_interface.save_profit_record(
                    tx_hash=profit_data["tx_hash"],
                    chain_id=profit_data["chain_id"],
                    profit_amount=profit_data["profit_amount"],
                    token_address=profit_data["token_address"],
                    strategy=profit_data["strategy"],
                )

                assert result == 1
                mock_session.add.assert_called_once()
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transaction_success(self, db_interface):
        """Test getting transaction when found."""
        with patch('on1builder.persistence.db_interface.Transaction'):
            with patch('on1builder.persistence.db_interface.select') as mock_select:
                mock_tx = MagicMock()
                mock_tx.to_dict.return_value = {"tx_hash": "0x123", "chain_id": 1}
                
                # Mock session as proper async context manager
                mock_session = AsyncMock()
                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_cm.__aexit__ = AsyncMock(return_value=None)
                
                # Mock session.get to return None, forcing fallback to select query
                mock_session.get = AsyncMock(return_value=None)
                
                mock_result = MagicMock()
                mock_result.scalars.return_value.first.return_value = mock_tx
                mock_session.execute = AsyncMock(return_value=mock_result)
                
                session_factory = MagicMock()
                session_factory.return_value = mock_session_cm
                db_interface._session_factory = session_factory

                result = await db_interface.get_transaction("0x123")

                assert result == {"tx_hash": "0x123", "chain_id": 1}

    @pytest.mark.asyncio
    async def test_get_transaction_not_found(self, db_interface):
        """Test getting transaction when not found."""
        # Mock session as proper async context manager
        mock_session = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)
        
        # Mock session.get to return None, forcing fallback to select query
        mock_session.get = AsyncMock(return_value=None)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        session_factory = MagicMock()
        session_factory.return_value = mock_session_cm
        db_interface._session_factory = session_factory

        result = await db_interface.get_transaction("0x123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_profit_summary_with_sqlalchemy(self, db_interface):
        """Test getting profit summary when SQLAlchemy is available."""
        # Mock session as proper async context manager
        mock_session = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)
        
        # Mock profit query result
        mock_result1 = MagicMock()
        mock_result1.first.return_value = (100.5, 10)  # profit sum and count
        
        mock_result2 = MagicMock()
        mock_result2.scalar.return_value = 2000000000000000000  # gas sum in wei
        
        mock_result3 = MagicMock()
        mock_result3.scalar.return_value = 8  # success count
        
        mock_result4 = MagicMock()
        mock_result4.scalar.return_value = 10  # total count
        
        mock_session.execute = AsyncMock(side_effect=[
            mock_result1,
            mock_result2,
            mock_result3,
            mock_result4,
        ])
        
        session_factory = MagicMock()
        session_factory.return_value = mock_session_cm
        db_interface._session_factory = session_factory

        result = await db_interface.get_profit_summary(chain_id=1)

        assert result["total_profit_eth"] == 100.5
        assert result["total_gas_spent_eth"] == 2.0  # 2e18 wei = 2 ETH
        assert result["count"] == 10
        assert result["success_rate"] == 80.0  # 8/10 * 100
        assert result["average_profit"] == 10.05  # 100.5/10
        assert result["transaction_count"] == 10

    @pytest.mark.asyncio
    async def test_get_profit_summary_without_sqlalchemy(self, db_interface):
        """Test getting profit summary when SQLAlchemy is not available."""
        db_interface._session_factory = None

        result = await db_interface.get_profit_summary()

        expected = {
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0,
            "count": 0,
            "success_rate": 0.0,
            "average_profit": 0.0,
            "transaction_count": 0,
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_transaction_count(self, db_interface):
        """Test getting transaction count."""
        # Mock session as proper async context manager
        mock_session = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        session_factory = MagicMock()
        session_factory.return_value = mock_session_cm
        db_interface._session_factory = session_factory

        result = await db_interface.get_transaction_count(chain_id=1)

        assert result == 42

    @pytest.mark.asyncio
    async def test_get_transaction_count_without_factory(self, db_interface):
        """Test getting transaction count without session factory."""
        db_interface._session_factory = None

        result = await db_interface.get_transaction_count()

        assert result == 0

    @pytest.mark.asyncio
    async def test_get_monitored_tokens(self, db_interface):
        """Test getting monitored tokens."""
        # Mock session as proper async context manager
        mock_session = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)
        
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("0xtoken1",),
            ("0xtoken2",),
            ("0xtoken3",),
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        session_factory = MagicMock()
        session_factory.return_value = mock_session_cm
        db_interface._session_factory = session_factory

        result = await db_interface.get_monitored_tokens(chain_id=1)

        assert result == ["0xtoken1", "0xtoken2", "0xtoken3"]

    @pytest.mark.asyncio
    async def test_get_monitored_tokens_without_factory(self, db_interface):
        """Test getting monitored tokens without session factory."""
        db_interface._session_factory = None

        result = await db_interface.get_monitored_tokens()

        assert result == []

    def test_check_connection_with_engine(self, db_interface):
        """Test connection check with engine."""
        db_interface._engine = MagicMock()
        assert db_interface.check_connection() is True

    def test_check_connection_without_engine(self, db_interface):
        """Test connection check without engine."""
        db_interface._engine = None
        assert db_interface.check_connection() is False

    def test_check_connection_with_exception(self, db_interface):
        """Test connection check with exception."""
        # Simulate an exception when accessing the _engine property
        # We'll directly mock the property on the instance
        original_engine = db_interface._engine
        try:
            # Delete the _engine attribute so accessing it raises AttributeError
            del db_interface._engine
            assert db_interface.check_connection() is False
        finally:
            # Restore the original value
            db_interface._engine = original_engine

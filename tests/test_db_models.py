"""
Tests for the db_models module.
"""

import datetime
from unittest.mock import patch

import pytest

from on1builder.persistence.db_models import HAS_SQLALCHEMY


class TestHASSQLAlchemy:
    """Test SQLAlchemy availability check."""

    def test_has_sqlalchemy_import(self):
        """Test that HAS_SQLALCHEMY is properly set."""
        # This should be True in our test environment
        assert isinstance(HAS_SQLALCHEMY, bool)


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
class TestTransactionModel:
    """Test Transaction model when SQLAlchemy is available."""

    def test_transaction_creation(self):
        """Test transaction model creation."""
        from on1builder.persistence.db_models import Transaction
        
        # Create a transaction instance
        tx = Transaction()
        
        # Test to_dict method with empty instance
        result = tx.to_dict()
        assert isinstance(result, dict)
        assert "id" in result
        assert "tx_hash" in result
        assert "chain_id" in result

    def test_transaction_to_dict_with_data(self):
        """Test transaction to_dict method with data."""
        from on1builder.persistence.db_models import Transaction
        
        # Create a transaction instance and set values directly
        tx = Transaction()
        
        # Use setattr to avoid type checker issues
        setattr(tx, 'id', 1)
        setattr(tx, 'tx_hash', "0x123456789abcdef")
        setattr(tx, 'chain_id', 1)
        setattr(tx, 'from_address', "0xabc")
        setattr(tx, 'to_address', "0xdef")
        setattr(tx, 'value', "1000000000000000000")
        setattr(tx, 'gas_price', "20000000000")
        setattr(tx, 'gas_used', 21000)
        setattr(tx, 'block_number', 12345)
        setattr(tx, 'status', True)
        setattr(tx, 'timestamp', datetime.datetime(2023, 1, 1, 12, 0, 0))
        setattr(tx, 'data', "0x")
        
        result = tx.to_dict()
        
        assert result["id"] == 1
        assert result["tx_hash"] == "0x123456789abcdef"
        assert result["chain_id"] == 1
        assert result["timestamp"] == "2023-01-01T12:00:00"

    def test_transaction_to_dict_none_timestamp(self):
        """Test transaction to_dict with None timestamp."""
        from on1builder.persistence.db_models import Transaction
        
        tx = Transaction()
        setattr(tx, 'timestamp', None)
        
        result = tx.to_dict()
        assert result["timestamp"] is None


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
class TestProfitRecordModel:
    """Test ProfitRecord model when SQLAlchemy is available."""

    def test_profit_record_creation(self):
        """Test profit record model creation."""
        from on1builder.persistence.db_models import ProfitRecord
        
        # Create a profit record instance
        profit = ProfitRecord()
        
        # Test to_dict method with empty instance
        result = profit.to_dict()
        assert isinstance(result, dict)
        assert "id" in result
        assert "tx_hash" in result
        assert "chain_id" in result
        assert "profit_amount" in result
        assert "strategy" in result

    def test_profit_record_to_dict_with_data(self):
        """Test profit record to_dict method with data."""
        from on1builder.persistence.db_models import ProfitRecord
        
        # Create a profit record instance
        profit = ProfitRecord()
        
        # Use setattr to avoid type checker issues
        setattr(profit, 'id', 1)
        setattr(profit, 'tx_hash', "0x123456789abcdef")
        setattr(profit, 'chain_id', 1)
        setattr(profit, 'profit_amount', 0.5)
        setattr(profit, 'token_address', "0xabc")
        setattr(profit, 'timestamp', datetime.datetime(2023, 1, 1, 12, 0, 0))
        setattr(profit, 'strategy', "arbitrage")
        
        result = profit.to_dict()
        
        assert result["id"] == 1
        assert result["tx_hash"] == "0x123456789abcdef"
        assert result["chain_id"] == 1
        assert result["profit_amount"] == 0.5
        assert result["timestamp"] == "2023-01-01T12:00:00"
        assert result["strategy"] == "arbitrage"

    def test_profit_record_to_dict_none_timestamp(self):
        """Test profit record to_dict with None timestamp."""
        from on1builder.persistence.db_models import ProfitRecord
        
        profit = ProfitRecord()
        setattr(profit, 'timestamp', None)
        
        result = profit.to_dict()
        assert result["timestamp"] is None


@pytest.mark.skipif(HAS_SQLALCHEMY, reason="Testing without SQLAlchemy")
class TestWithoutSQLAlchemy:
    """Test models when SQLAlchemy is not available."""

    def test_placeholder_transaction_without_sqlalchemy(self):
        """Test placeholder Transaction class without SQLAlchemy."""
        with patch('on1builder.persistence.db_models.HAS_SQLALCHEMY', False):
            # Re-import to get the placeholder class
            import importlib
            from on1builder.persistence import db_models
            importlib.reload(db_models)
            
            transaction = db_models.Transaction()
            result = transaction.to_dict()
            assert result == {}

    def test_placeholder_profit_record_without_sqlalchemy(self):
        """Test placeholder ProfitRecord class without SQLAlchemy."""
        with patch('on1builder.persistence.db_models.HAS_SQLALCHEMY', False):
            # Re-import to get the placeholder class
            import importlib
            from on1builder.persistence import db_models
            importlib.reload(db_models)
            
            profit = db_models.ProfitRecord()
            result = profit.to_dict()
            assert result == {}


class TestBaseClass:
    """Test Base class configuration."""

    @pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
    def test_base_class_with_sqlalchemy(self):
        """Test that Base is properly configured with SQLAlchemy."""
        from on1builder.persistence.db_models import Base
        
        # Base should be a declarative base
        assert hasattr(Base, 'metadata')

    @pytest.mark.skipif(HAS_SQLALCHEMY, reason="Testing without SQLAlchemy")  
    def test_base_class_without_sqlalchemy(self):
        """Test that Base is object when SQLAlchemy is not available."""
        with patch('on1builder.persistence.db_models.HAS_SQLALCHEMY', False):
            # Re-import to get the placeholder Base
            import importlib
            from on1builder.persistence import db_models
            importlib.reload(db_models)
            
            # Base should be object when SQLAlchemy is not available
            assert db_models.Base == object

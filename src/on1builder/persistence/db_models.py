"""
SQLAlchemy database models for ON1Builder.
"""

import datetime
from typing import Any, Dict

try:
    from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()
    HAS_SQLALCHEMY = True
except ImportError:
    Base = object  # type: ignore
    HAS_SQLALCHEMY = False


if HAS_SQLALCHEMY:

    class Transaction(Base):
        """Transaction record model."""

        __tablename__ = "transactions"

        id = Column(Integer, primary_key=True)
        tx_hash = Column(String(66), unique=True, index=True)
        chain_id = Column(Integer, index=True)
        from_address = Column(String(42))
        to_address = Column(String(42))
        value = Column(String(78))  # store big ints as strings
        gas_price = Column(String(78))
        gas_used = Column(Integer, nullable=True)
        block_number = Column(Integer, nullable=True)
        status = Column(Boolean, nullable=True)
        timestamp = Column(DateTime, default=datetime.datetime.now)
        data = Column(Text, nullable=True)

        def to_dict(self) -> Dict[str, Any]:
            """Convert transaction to dictionary."""
            return {
                "id": self.id,
                "tx_hash": self.tx_hash,
                "chain_id": self.chain_id,
                "from_address": self.from_address,
                "to_address": self.to_address,
                "value": self.value,
                "gas_price": self.gas_price,
                "gas_used": self.gas_used,
                "block_number": self.block_number,
                "status": self.status,
                "timestamp": (
                    self.timestamp.isoformat() if self.timestamp is not None else None
                ),
                "data": self.data,
            }

    class ProfitRecord(Base):
        """Profit tracking record model."""

        __tablename__ = "profit_records"

        id = Column(Integer, primary_key=True)
        tx_hash = Column(String(66), index=True)
        chain_id = Column(Integer, index=True)
        profit_amount = Column(Float)
        token_address = Column(String(42))
        timestamp = Column(DateTime, default=datetime.datetime.utcnow)
        strategy = Column(String(100))

        def to_dict(self) -> Dict[str, Any]:
            """Convert profit record to dictionary."""
            return {
                "id": self.id,
                "tx_hash": self.tx_hash,
                "chain_id": self.chain_id,
                "profit_amount": self.profit_amount,
                "token_address": self.token_address,
                "timestamp": (
                    self.timestamp.isoformat() if self.timestamp is not None else None
                ),
                "strategy": self.strategy,
            }

else:
    # Placeholder classes when SQLAlchemy is not available
    class Transaction:
        def to_dict(self):
            return {}

    class ProfitRecord:
        def to_dict(self):
            return {}

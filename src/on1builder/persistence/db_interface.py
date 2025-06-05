#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Database Manager
==============================
Manages DB connections and CRUD for transactions and profit records.
License: MIT
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    and_,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from on1builder.config.settings import GlobalSettings

from ..utils.logging_config import get_logger

logger = get_logger(__name__)

# Try to enable SQLAlchemy ORM; otherwise disable DB features
try:
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False
    Base = None

# ---------------------------------------------
# ORM models
# ---------------------------------------------
if HAS_SQLALCHEMY and Base is not None:

    class Transaction(Base):
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
        __tablename__ = "profit_records"

        id = Column(Integer, primary_key=True)
        tx_hash = Column(String(66), index=True)
        chain_id = Column(Integer, index=True)
        profit_amount = Column(Float)
        token_address = Column(String(42))
        timestamp = Column(DateTime, default=datetime.datetime.utcnow)
        strategy = Column(String(100))

        def to_dict(self) -> Dict[str, Any]:
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
    # Stub classes when SQLAlchemy is not available
    class Transaction:  # type: ignore
        pass

    class ProfitRecord:  # type: ignore
        pass


# ---------------------------------------------
# Manager
# ---------------------------------------------
class DatabaseInterface:
    """Async DB manager for ON1Builder."""

    def __init__(self, config: GlobalSettings, db_url: Optional[str] = None) -> None:
        self.config = config
        self._db_url = db_url or config.database_url
        self._engine = None
        self._session_factory: Optional[async_sessionmaker] = None

        if HAS_SQLALCHEMY:
            self._engine = create_async_engine(self._db_url, echo=False)
            self._session_factory = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.debug("Async engine created for %s", self._db_url)
        else:
            logger.warning("SQLAlchemy not available; DB disabled")

    async def initialize(self) -> None:
        """Create tables if needed."""
        if not HAS_SQLALCHEMY or not self._engine or Base is None:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # type: ignore
        logger.info("Database schema initialized")

    async def save_transaction(
        self,
        tx_hash: str,
        chain_id: int,
        from_address: str,
        to_address: str,
        value: str,
        gas_price: str,
        gas_used: Optional[int] = None,
        block_number: Optional[int] = None,
        status: Optional[bool] = None,
        data: Optional[str] = None,
    ) -> Optional[int]:
        """Insert or update a transaction record."""
        if not self._session_factory:
            return None

        async with self._session_factory() as session:
            # Try existing - search by tx_hash field, not primary key
            result = await session.execute(
                select(Transaction).where(Transaction.tx_hash == tx_hash)
            )
            existing = result.scalar_one_or_none()
            if existing:
                if gas_used is not None:
                    existing.gas_used = gas_used
                if block_number is not None:
                    existing.block_number = block_number
                if status is not None:
                    existing.status = status
                await session.commit()
                return existing.id

            # Insert new
            record = Transaction(
                tx_hash=tx_hash,
                chain_id=chain_id,
                from_address=from_address,
                to_address=to_address,
                value=value,
                gas_price=gas_price,
                gas_used=gas_used,
                block_number=block_number,
                status=status,
                data=data,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return int(record.id)

    async def save_profit_record(
        self,
        tx_hash: str,
        chain_id: int,
        profit_amount: float,
        token_address: str,
        strategy: str,
    ) -> Optional[int]:
        """Record profit from a strategy execution."""
        if not self._session_factory:
            return None

        async with self._session_factory() as session:
            rec = ProfitRecord(
                tx_hash=tx_hash,
                chain_id=chain_id,
                profit_amount=profit_amount,
                token_address=token_address,
                strategy=strategy,
            )
            session.add(rec)
            await session.commit()
            await session.refresh(rec)
            return int(rec.id)

    def check_connection(self) -> bool:
        """Simple health check for the database connection."""
        try:
            # If SQLAlchemy engine is available, assume connection is OK
            return self._engine is not None
        except Exception:
            return False

    async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Fetch a transaction by hash."""
        if not self._session_factory:
            return None

        async with self._session_factory() as session:
            tx = await session.get(Transaction, tx_hash)
            if not tx:
                result = await session.execute(
                    select(Transaction).where(Transaction.tx_hash == tx_hash)
                )
                tx = result.scalars().first()
            return tx.to_dict() if tx else None

    async def get_profit_summary(
        self,
        chain_id: Optional[int] = None,
        address: Optional[str] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate profit, gas spent, counts, and success rate."""
        if not self._session_factory:
            return {
                "total_profit_eth": 0.0,
                "total_gas_spent_eth": 0.0,
                "count": 0,
                "success_rate": 0.0,
                "average_profit": 0.0,
                "transaction_count": 0,
            }

        async with self._session_factory() as session:
            # Profit sum & count
            q1 = select(func.sum(ProfitRecord.profit_amount), func.count())
            filters: List[Any] = []
            if chain_id is not None:
                filters.append(ProfitRecord.chain_id == chain_id)
            if start_time:
                filters.append(ProfitRecord.timestamp >= start_time)
            if end_time:
                filters.append(ProfitRecord.timestamp <= end_time)
            if filters:
                q1 = q1.where(and_(*filters))
            total_profit, profit_count = (await session.execute(q1)).first() or (0.0, 0)

            # Gas spent = sum(tx.gas_used * tx.gas_price)
            q2 = select(func.sum(Transaction.gas_used * Transaction.gas_price))
            filters = []
            if chain_id is not None:
                filters.append(Transaction.chain_id == chain_id)
            if address:
                filters.append(Transaction.from_address == address)
            if start_time:
                filters.append(Transaction.timestamp >= start_time)
            if end_time:
                filters.append(Transaction.timestamp <= end_time)
            if filters:
                q2 = q2.where(and_(*filters))
            total_gas_wei = (await session.execute(q2)).scalar() or 0
            total_gas_eth = float(total_gas_wei) / 1e18

            # Success rate
            q3 = select(func.count()).where(Transaction.status.is_(True))
            if filters:
                q3 = q3.where(and_(*filters))
            success_count = (await session.execute(q3)).scalar() or 0

            # Total tx count
            q4 = select(func.count())
            if filters:
                q4 = q4.where(and_(*filters))
            total_count = (await session.execute(q4)).scalar() or 0

            success_rate = (success_count / total_count * 100) if total_count else 0.0
            avg_profit = (total_profit / profit_count) if profit_count else 0.0

            return {
                "total_profit_eth": float(total_profit),
                "total_gas_spent_eth": total_gas_eth,
                "count": profit_count,
                "success_rate": success_rate,
                "average_profit": avg_profit,
                "transaction_count": total_count,
            }

    async def get_transaction_count(
        self, chain_id: Optional[int] = None, address: Optional[str] = None
    ) -> int:
        """Count transactions, optionally filtered."""
        if not self._session_factory:
            return 0

        async with self._session_factory() as session:
            q = select(func.count())
            if chain_id is not None or address:
                conds = []
                if chain_id is not None:
                    conds.append(Transaction.chain_id == chain_id)
                if address:
                    conds.append(Transaction.from_address == address)
                q = q.where(and_(*conds))
            return (await session.execute(q)).scalar() or 0

    async def get_monitored_tokens(self, chain_id: Optional[int] = None) -> List[str]:
        """Return distinct `to_address` values for the chain."""
        if not self._session_factory:
            return []

        async with self._session_factory() as session:
            q = select(Transaction.to_address).distinct()
            if chain_id is not None:
                q = q.where(Transaction.chain_id == chain_id)
            result = await session.execute(q)
            return [row[0] for row in result.all()]

    async def close(self) -> None:
        """Dispose of the engine."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database engine disposed")


# ---------------------------------------------
# Type alias and singleton accessor
# ---------------------------------------------

# Type alias for backwards compatibility
DatabaseManager = DatabaseInterface

_db_manager: Optional[DatabaseInterface] = None


def get_db_manager(
    config: GlobalSettings, db_url: Optional[str] = None
) -> DatabaseInterface:
    """Return a singleton DatabaseManager (initialize on first call)."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseInterface(config, db_url)
    return _db_manager

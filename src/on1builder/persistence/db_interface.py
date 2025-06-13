# src/on1builder/persistence/db_interface.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from on1builder.config.loaders import settings
from on1builder.utils.logging_config import get_logger
from on1builder.utils.singleton import SingletonMeta
from .db_models import Base, Transaction, ProfitRecord

logger = get_logger(__name__)

class DatabaseInterface(metaclass=SingletonMeta):
    """
    Asynchronous database manager for all persistence operations.
    Handles engine creation, session management, and provides a clean API for CRUD operations.
    """

    def __init__(self):
        self._db_url = settings.database.url
        self._engine = create_async_engine(self._db_url, echo=settings.debug)
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._initialized = False
        logger.info(f"DatabaseInterface initialized for URL: {self._db_url}")

    async def initialize_db(self) -> None:
        """Creates all database tables based on the ORM models if they don't exist."""
        if self._initialized:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._initialized = True
        logger.info("Database schema checked and initialized.")

    async def save_transaction(self, tx_data: Dict[str, Any]) -> Optional[Transaction]:
        """
        Saves a single transaction record to the database.

        Args:
            tx_data: A dictionary containing transaction data.
        
        Returns:
            The saved Transaction object or None on failure.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    transaction = Transaction(**tx_data)
                    session.add(transaction)
                await session.refresh(transaction)
                return transaction
        except Exception as e:
            logger.error(f"Failed to save transaction {tx_data.get('tx_hash')}: {e}", exc_info=True)
            return None

    async def save_profit_record(self, profit_data: Dict[str, Any]) -> Optional[ProfitRecord]:
        """
        Saves a single profit record to the database.

        Args:
            profit_data: A dictionary containing profit data.
        
        Returns:
            The saved ProfitRecord object or None on failure.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    profit_record = ProfitRecord(**profit_data)
                    session.add(profit_record)
                await session.refresh(profit_record)
                return profit_record
        except Exception as e:
            logger.error(f"Failed to save profit record for tx {profit_data.get('tx_hash')}: {e}", exc_info=True)
            return None

    async def get_transaction_by_hash(self, tx_hash: str) -> Optional[Transaction]:
        """
        Retrieves a transaction from the database by its hash.

        Args:
            tx_hash: The transaction hash to search for.
            
        Returns:
            The Transaction object or None if not found.
        """
        async with self._session_factory() as session:
            stmt = select(Transaction).where(Transaction.tx_hash == tx_hash)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_recent_transactions(self, chain_id: int, limit: int = 100) -> List[Transaction]:
        """
        Retrieves the most recent transactions for a given chain.

        Args:
            chain_id: The chain ID to filter by.
            limit: The maximum number of transactions to return.
            
        Returns:
            A list of Transaction objects.
        """
        async with self._session_factory() as session:
            stmt = (
                select(Transaction)
                .where(Transaction.chain_id == chain_id)
                .order_by(Transaction.timestamp.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_profit_summary(self, chain_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Aggregates and returns a summary of profits.

        Args:
            chain_id: Optional chain ID to filter the summary.
            
        Returns:
            A dictionary containing the profit summary.
        """
        async with self._session_factory() as session:
            query = select(
                func.sum(ProfitRecord.profit_amount_eth).label("total_profit_eth"),
                func.sum(ProfitRecord.profit_amount_usd).label("total_profit_usd"),
                func.count(ProfitRecord.id).label("trade_count")
            )
            if chain_id:
                query = query.where(ProfitRecord.chain_id == chain_id)
            
            result = await session.execute(query)
            summary = result.one_or_none()

            if summary is None or summary.trade_count == 0:
                return {"total_profit_eth": 0.0, "total_profit_usd": 0.0, "trade_count": 0}

            return {
                "total_profit_eth": summary.total_profit_eth or 0.0,
                "total_profit_usd": summary.total_profit_usd or 0.0,
                "trade_count": summary.trade_count
            }

    async def close(self) -> None:
        """Disposes of the database engine connection pool."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database engine disposed.")
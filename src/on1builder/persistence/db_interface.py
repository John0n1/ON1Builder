#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from on1builder.config.loaders import settings
from on1builder.config.settings import DatabaseSettings
from on1builder.utils.logging_config import get_logger
from .db_models import Base, Transaction, ProfitRecord, MarketPrice
import asyncio

logger = get_logger(__name__)


class DatabaseInterface:
    """
    Asynchronous database manager for all persistence operations.
    Handles engine creation, session management, and provides a clean API for CRUD operations.
    """

    _instance: Optional["DatabaseInterface"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized_once = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized_once", False):
            return

        raw_db_settings = getattr(settings, "database", None)
        if isinstance(raw_db_settings, DatabaseSettings):
            db_settings = raw_db_settings
        elif isinstance(raw_db_settings, dict):
            db_settings = DatabaseSettings(**raw_db_settings)
        else:
            db_settings = DatabaseSettings()

        self._db_settings = db_settings
        self._db_url = db_settings.url
        self._engine = create_async_engine(
            self._db_url, echo=getattr(settings, "debug", False)
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._initialized = False
        # Detect stub engine by presence of _store attribute
        self._is_stub = hasattr(self._engine, "_store")
        self._initialized_once = True
        logger.debug("DatabaseInterface initialized for URL: %s", self._db_url)

    async def __aenter__(self) -> "DatabaseInterface":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance for tests."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Compatibility accessors
    # ------------------------------------------------------------------
    @property
    def config(self) -> DatabaseSettings:
        """Return resolved database settings for legacy callers."""
        return self._db_settings

    @property
    def settings(self) -> DatabaseSettings:
        """Alias maintained for callers expecting ``settings`` attribute."""
        return self._db_settings

    async def initialize_db(self) -> None:
        """Creates all database tables based on the ORM models if they don't exist."""
        if self._initialized:
            return
        if self._is_stub:
            # Nothing to initialize for in-memory stub
            self._engine._store.setdefault("transactions", [])
            self._engine._store.setdefault("profit_records", [])
            self._engine._store.setdefault("market_prices", [])
        else:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        self._initialized = True
        logger.debug("Database schema checked and initialized.")

    async def health_check(self) -> bool:
        """Lightweight DB health check."""
        try:
            if self._is_stub:
                return True
            async with self._engine.begin() as conn:
                await conn.execute(select(1))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def save_transaction(
        self, tx_data: Dict[str, Any], retries: int = 2
    ) -> Optional[Transaction]:
        """
        Saves a single transaction record to the database.

        Args:
            tx_data: A dictionary containing transaction data.

        Returns:
            The saved Transaction object or None on failure.
        """
        attempt = 0
        while attempt <= retries:
            try:
                if self._is_stub:
                    transaction = Transaction(**tx_data)
                    self._engine._store["transactions"].append(transaction)
                    return transaction

                async with self._session_factory() as session:
                    async with session.begin():
                        transaction = Transaction(**tx_data)
                        session.add(transaction)
                    await session.refresh(transaction)
                    return transaction
            except Exception as e:
                attempt += 1
                logger.error(
                    f"Failed to save transaction {tx_data.get('tx_hash')}: {e} (attempt {attempt}/{retries + 1})",
                    exc_info=True,
                )
                if attempt > retries:
                    return None
                await asyncio.sleep(0.5 * attempt)

    async def save_profit_record(
        self, profit_data: Dict[str, Any], retries: int = 2
    ) -> Optional[ProfitRecord]:
        """
        Saves a single profit record to the database.

        Args:
            profit_data: A dictionary containing profit data.

        Returns:
            The saved ProfitRecord object or None on failure.
        """
        attempt = 0
        while attempt <= retries:
            try:
                if self._is_stub:
                    profit_record = ProfitRecord(**profit_data)
                    self._engine._store["profit_records"].append(profit_record)
                    return profit_record

                async with self._session_factory() as session:
                    async with session.begin():
                        profit_record = ProfitRecord(**profit_data)
                        session.add(profit_record)
                    await session.refresh(profit_record)
                    return profit_record
            except Exception as e:
                attempt += 1
                logger.error(
                    f"Failed to save profit record for tx {profit_data.get('tx_hash')}: {e} (attempt {attempt}/{retries + 1})",
                    exc_info=True,
                )
                if attempt > retries:
                    return None
                await asyncio.sleep(0.5 * attempt)

    async def save_market_price(
        self, price_data: Dict[str, Any], retries: int = 1
    ) -> Optional[MarketPrice]:
        """
        Saves a single market price snapshot to the database.

        Args:
            price_data: A dictionary containing market price data.

        Returns:
            The saved MarketPrice object or None on failure.
        """
        attempt = 0
        while attempt <= retries:
            try:
                if self._is_stub:
                    record = MarketPrice(**price_data)
                    self._engine._store["market_prices"].append(record)
                    return record

                async with self._session_factory() as session:
                    async with session.begin():
                        record = MarketPrice(**price_data)
                        session.add(record)
                    await session.refresh(record)
                    return record
            except Exception as e:
                attempt += 1
                logger.error(
                    "Failed to save market price %s: %s (attempt %s/%s)",
                    price_data.get("symbol"),
                    e,
                    attempt,
                    retries + 1,
                    exc_info=True,
                )
                if attempt > retries:
                    return None
                await asyncio.sleep(0.5 * attempt)

    async def get_latest_market_price(
        self, chain_id: int, symbol: str
    ) -> Optional[MarketPrice]:
        """
        Retrieves the most recent market price for a token on a chain.

        Args:
            chain_id: Chain ID to filter by.
            symbol: Token symbol to filter by.

        Returns:
            The latest MarketPrice record or None if not found.
        """
        symbol_upper = symbol.upper()
        if self._is_stub:
            records = [
                record
                for record in self._engine._store.get("market_prices", [])
                if getattr(record, "chain_id", None) == chain_id
                and getattr(record, "symbol", "").upper() == symbol_upper
            ]
            return records[-1] if records else None

        async with self._session_factory() as session:
            stmt = (
                select(MarketPrice)
                .where(MarketPrice.chain_id == chain_id)
                .where(MarketPrice.symbol == symbol_upper)
                .order_by(MarketPrice.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_transaction_by_hash(self, tx_hash: str) -> Optional[Transaction]:
        """
        Retrieves a transaction from the database by its hash.

        Args:
            tx_hash: The transaction hash to search for.

        Returns:
            The Transaction object or None if not found.
        """
        if self._is_stub:
            for tx in reversed(self._engine._store.get("transactions", [])):
                if getattr(tx, "tx_hash", None) == tx_hash:
                    return tx
            return None

        async with self._session_factory() as session:
            stmt = select(Transaction).where(Transaction.tx_hash == tx_hash)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_recent_transactions(
        self, chain_id: int, limit: int = 100
    ) -> List[Transaction]:
        """
        Retrieves the most recent transactions for a given chain.

        Args:
            chain_id: The chain ID to filter by.
            limit: The maximum number of transactions to return.

        Returns:
            A list of Transaction objects.
        """
        if self._is_stub:
            txs = [
                tx
                for tx in self._engine._store.get("transactions", [])
                if getattr(tx, "chain_id", None) == chain_id
            ]
            return list(reversed(txs))[:limit]

        async with self._session_factory() as session:
            stmt = (
                select(Transaction)
                .where(Transaction.chain_id == chain_id)
                .order_by(Transaction.timestamp.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_profit_summary(
        self, chain_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Aggregates and returns a summary of profits.

        Args:
            chain_id: Optional chain ID to filter the summary.

        Returns:
            A dictionary containing the profit summary.
        """
        if self._is_stub:
            records = self._engine._store.get("profit_records", [])
            if chain_id is not None:
                records = [
                    r for r in records if getattr(r, "chain_id", None) == chain_id
                ]
            trade_count = len(records)
            total_profit_eth = sum(
                getattr(r, "profit_amount_eth", 0.0) or 0.0 for r in records
            )
            total_profit_usd = sum(
                getattr(r, "profit_amount_usd", 0.0) or 0.0 for r in records
            )
            if trade_count == 0:
                return {
                    "total_profit_eth": 0.0,
                    "total_profit_usd": 0.0,
                    "trade_count": 0,
                }
            return {
                "total_profit_eth": total_profit_eth,
                "total_profit_usd": total_profit_usd,
                "trade_count": trade_count,
            }

        async with self._session_factory() as session:
            query = select(
                func.sum(ProfitRecord.profit_amount_eth).label("total_profit_eth"),
                func.sum(ProfitRecord.profit_amount_usd).label("total_profit_usd"),
                func.count(ProfitRecord.id).label("trade_count"),
            )
            if chain_id:
                query = query.where(ProfitRecord.chain_id == chain_id)

            result = await session.execute(query)
            summary = result.one_or_none()

            if summary is None or summary.trade_count == 0:
                return {
                    "total_profit_eth": 0.0,
                    "total_profit_usd": 0.0,
                    "trade_count": 0,
                }

            return {
                "total_profit_eth": summary.total_profit_eth or 0.0,
                "total_profit_usd": summary.total_profit_usd or 0.0,
                "trade_count": summary.trade_count,
            }

    async def close(self) -> None:
        """Disposes of the database engine connection pool."""
        if self._engine and hasattr(self._engine, "dispose"):
            await self._engine.dispose()
            logger.info("Closing database and disposing engine connections.")

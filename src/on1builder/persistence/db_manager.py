"""
ON1Builder - Database Manager
===========================

Manages database connections and operations for persisting transaction data
and monitoring information.
"""

from __future__ import annotations
import asyncio
import datetime
import os
import logging
from typing import Any, Dict, List, Optional, Union, Tuple

try:
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, select
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

from on1builder.config.config import Configuration
from on1builder.utils.logger import setup_logging

logger = setup_logging("DatabaseManager", level="DEBUG")

# Base class for ORM models if SQLAlchemy is available
if HAS_SQLALCHEMY:
    Base = declarative_base()
else:
    Base = object


# Define ORM models if SQLAlchemy is available
if HAS_SQLALCHEMY:
    class Transaction(Base):
        """Transaction record."""
        __tablename__ = "transactions"
        
        id = Column(Integer, primary_key=True)
        tx_hash = Column(String(66), unique=True, index=True)
        chain_id = Column(Integer)
        from_address = Column(String(42))
        to_address = Column(String(42))
        value = Column(String(78))  # Big numbers stored as strings
        gas_price = Column(String(78))
        gas_used = Column(Integer)
        block_number = Column(Integer, nullable=True)
        status = Column(Boolean, nullable=True)
        timestamp = Column(DateTime, default=datetime.datetime.utcnow)
        data = Column(Text, nullable=True)
        
        def to_dict(self) -> Dict[str, Any]:
            """Convert to dictionary."""
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
                "timestamp": self.timestamp.isoformat() if self.timestamp else None,
                "data": self.data,
            }
    
    class ProfitRecord(Base):
        """Profit tracking record."""
        __tablename__ = "profit_records"
        
        id = Column(Integer, primary_key=True)
        tx_hash = Column(String(66), index=True)
        chain_id = Column(Integer)
        profit_amount = Column(Float)
        token_address = Column(String(42))
        timestamp = Column(DateTime, default=datetime.datetime.utcnow)
        strategy = Column(String(100))
        
        def to_dict(self) -> Dict[str, Any]:
            """Convert to dictionary."""
            return {
                "id": self.id,
                "tx_hash": self.tx_hash,
                "chain_id": self.chain_id,
                "profit_amount": self.profit_amount,
                "token_address": self.token_address,
                "timestamp": self.timestamp.isoformat() if self.timestamp else None,
                "strategy": self.strategy,
            }


class DatabaseManager:
    """
    Database management for the application.
    
    Handles database connections, schema creation, and CRUD operations
    for storing transaction and monitoring data.
    """
    
    def __init__(
        self, 
        config: Configuration,
        db_url: Optional[str] = None,
    ) -> None:
        """
        Initialize database manager.
        
        Args:
            config: Global configuration
            db_url: Database connection URL (defaults to SQLite)
        """
        self.config = config
        self._db_url = db_url
        self._engine = None
        self._async_session = None
        
        # Default to SQLite if no URL provided
        if not self._db_url:
            # Data directory from config or default
            data_dir = config.get("DATA_DIR", "data/db")
            os.makedirs(data_dir, exist_ok=True)
            
            # Use SQLite by default
            self._db_url = f"sqlite+aiosqlite:///{data_dir}/on1builder.db"
        
        self._setup_db()
        logger.info("DatabaseManager initialized")
    
    def _setup_db(self) -> None:
        """Set up database connection and tables."""
        if not HAS_SQLALCHEMY:
            logger.warning("SQLAlchemy not installed, database functionality disabled")
            return
        
        try:
            # Create engine and session
            self._engine = create_async_engine(self._db_url, echo=False)
            self._async_session = sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            # Tables will be created in the initialize method
            logger.debug(f"Database engine created for {self._db_url}")
        except Exception as e:
            logger.error(f"Error setting up database: {str(e)}")
    
    async def initialize(self) -> None:
        """Initialize database by creating tables."""
        if not HAS_SQLALCHEMY or not self._engine:
            logger.warning("Database not available, skipping initialization")
            return
        
        try:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created")
        except Exception as e:
            logger.error(f"Error creating database tables: {str(e)}")
    
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
        """
        Save transaction to database.
        
        Args:
            tx_hash: Transaction hash
            chain_id: Chain ID
            from_address: Sender address
            to_address: Recipient address
            value: Transaction value
            gas_price: Gas price
            gas_used: Gas used
            block_number: Block number
            status: Transaction status
            data: Additional data (JSON string)
            
        Returns:
            Record ID or None if error
        """
        if not HAS_SQLALCHEMY or not self._async_session:
            logger.warning("Database not available, skipping save_transaction")
            return None
        
        try:
            async with self._async_session() as session:
                # Check if transaction already exists
                existing_tx = await session.get(Transaction, tx_hash)
                
                if existing_tx:
                    # Update existing record
                    if gas_used is not None:
                        existing_tx.gas_used = gas_used
                    if block_number is not None:
                        existing_tx.block_number = block_number
                    if status is not None:
                        existing_tx.status = status
                    
                    await session.commit()
                    logger.debug(f"Updated transaction record for {tx_hash}")
                    return existing_tx.id
                else:
                    # Create new record
                    tx_record = Transaction(
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
                    
                    session.add(tx_record)
                    await session.commit()
                    logger.debug(f"Saved new transaction record for {tx_hash}")
                    return tx_record.id
        except Exception as e:
            logger.error(f"Error saving transaction {tx_hash}: {str(e)}")
            return None
    
    async def save_profit_record(
        self,
        tx_hash: str,
        chain_id: int,
        profit_amount: float,
        token_address: str,
        strategy: str,
    ) -> Optional[int]:
        """
        Save profit record to database.
        
        Args:
            tx_hash: Transaction hash
            chain_id: Chain ID
            profit_amount: Profit amount
            token_address: Token address
            strategy: Strategy name
            
        Returns:
            Record ID or None if error
        """
        if not HAS_SQLALCHEMY or not self._async_session:
            logger.warning("Database not available, skipping save_profit_record")
            return None
        
        try:
            async with self._async_session() as session:
                profit_record = ProfitRecord(
                    tx_hash=tx_hash,
                    chain_id=chain_id,
                    profit_amount=profit_amount,
                    token_address=token_address,
                    timestamp=datetime.datetime.utcnow(),
                    strategy=strategy,
                )
                
                session.add(profit_record)
                await session.commit()
                logger.debug(f"Saved profit record for {tx_hash}: {profit_amount}")
                return profit_record.id
        except Exception as e:
            logger.error(f"Error saving profit record for {tx_hash}: {str(e)}")
            return None
    
    async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get transaction by hash.
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction data or None if not found
        """
        if not HAS_SQLALCHEMY or not self._async_session:
            logger.warning("Database not available, skipping get_transaction")
            return None
        
        try:
            async with self._async_session() as session:
                # First try direct get by primary key
                tx = await session.get(Transaction, tx_hash)
                
                if tx is None:
                    # If not found, try with a query
                    query = select(Transaction).where(Transaction.tx_hash == tx_hash)
                    result = await session.execute(query)
                    
                    # Handle scalar result appropriately
                    scalar_result = result.scalars().first()
                    if hasattr(scalar_result, '__await__'):
                        scalar_result = await scalar_result
                    
                    if scalar_result:
                        tx = scalar_result
                
                if tx:
                    # Convert to dictionary (handle both sync and async implementations)
                    if hasattr(tx.to_dict, '__await__'):
                        return await tx.to_dict()
                    else:
                        return tx.to_dict()
                return None
                
        except Exception as e:
            logger.error(f"Error getting transaction {tx_hash}: {str(e)}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
    
    async def get_profit_summary(
        self,
        chain_id: Optional[int] = None,
        address: Optional[str] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get profit summary for a time period.
        
        Args:
            chain_id: Filter by chain ID
            address: Filter by wallet address
            start_time: Start time for summary
            end_time: End time for summary
            
        Returns:
            Summary dictionary with total profit and related metrics
        """
        if not HAS_SQLALCHEMY or not self._async_session:
            logger.warning("Database not available, skipping get_profit_summary")
            return {
                "total_profit_eth": 0.0,
                "total_gas_spent_eth": 0.0,
                "count": 0,
                "success_rate": 0.0,
                "average_profit": 0.0
            }
        
        try:
            async with self._async_session() as session:
                from sqlalchemy import select, func, and_
                
                # Base query for profit records
                profit_query = select(
                    func.sum(ProfitRecord.profit_amount),
                    func.count(ProfitRecord.id)
                )
                
                # Apply filters
                filters = []
                if chain_id is not None:
                    filters.append(ProfitRecord.chain_id == chain_id)
                if start_time is not None:
                    filters.append(ProfitRecord.timestamp >= start_time)
                if end_time is not None:
                    filters.append(ProfitRecord.timestamp <= end_time)
                    
                if filters:
                    profit_query = profit_query.where(and_(*filters))
                    
                # Execute query
                result = await session.execute(profit_query)
                # Handle both direct results and coroutines
                first_result = result.first()
                if hasattr(first_result, '__await__'):  # Check if it's a coroutine
                    first_result = await first_result
                total_profit, profit_count = first_result or (0.0, 0)
                
                # Get gas spent from transactions
                tx_query = select(
                    func.sum(Transaction.gas_used * Transaction.gas_price)
                )
                
                tx_filters = []
                if chain_id is not None:
                    tx_filters.append(Transaction.chain_id == chain_id)
                if address is not None:
                    tx_filters.append(Transaction.from_address == address)
                if start_time is not None:
                    tx_filters.append(Transaction.timestamp >= start_time)
                if end_time is not None:
                    tx_filters.append(Transaction.timestamp <= end_time)
                
                if tx_filters:
                    tx_query = tx_query.where(and_(*tx_filters))
                    
                result = await session.execute(tx_query)
                scalar_result = result.scalar()
                if hasattr(scalar_result, '__await__'):  # Check if it's a coroutine
                    scalar_result = await scalar_result
                total_gas_wei = scalar_result or 0
                
                # Convert wei to ETH (approximate)
                total_gas_eth = float(total_gas_wei) / 1e18 if total_gas_wei else 0.0
                
                # Count successful transactions
                success_query = select(func.count(Transaction.id)).where(Transaction.status == True)
                if tx_filters:
                    success_query = success_query.where(and_(*tx_filters))
                    
                success_result = await session.execute(success_query)
                scalar_success = success_result.scalar()
                if hasattr(scalar_success, '__await__'):  # Check if it's a coroutine
                    scalar_success = await scalar_success
                success_count = scalar_success or 0
                
                # Get total transaction count
                total_query = select(func.count(Transaction.id))
                if tx_filters:
                    total_query = total_query.where(and_(*tx_filters))
                    
                total_result = await session.execute(total_query)
                scalar_total = total_result.scalar()
                if hasattr(scalar_total, '__await__'):  # Check if it's a coroutine
                    scalar_total = await scalar_total
                total_count = scalar_total or 0
                
                # Calculate metrics
                success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
                avg_profit = total_profit / profit_count if profit_count > 0 else 0
                
                return {
                    "total_profit_eth": float(total_profit),
                    "total_gas_spent_eth": total_gas_eth,
                    "count": profit_count,
                    "success_rate": success_rate,
                    "average_profit": avg_profit,
                    "transaction_count": total_count
                }
                
        except Exception as e:
            logger.error(f"Error getting profit summary: {str(e)}")
            return {
                "total_profit_eth": 0.0,
                "total_gas_spent_eth": 0.0,
                "count": 0,
                "success_rate": 0.0,
                "average_profit": 0.0
            }
    
    async def get_transaction_count(
        self,
        chain_id: Optional[int] = None,
        address: Optional[str] = None
    ) -> int:
        """Get count of transactions, optionally filtered by chain_id and from_address."""
        if not HAS_SQLALCHEMY or not self._async_session:
            logger.warning("Database not available, skipping get_transaction_count")
            return 0
        from sqlalchemy import select, func, and_
        try:
            async with self._async_session() as session:
                query = select(func.count(Transaction.id))
                conditions = []
                if chain_id is not None:
                    conditions.append(Transaction.chain_id == chain_id)
                if address:
                    conditions.append(Transaction.from_address == address)
                if conditions:
                    query = query.where(and_(*conditions))
                result = await session.execute(query)
                count = result.scalar() or 0
                return count
        except Exception as e:
            logger.error(f"Error getting transaction count: {e}")
            return 0
    
    async def get_monitored_tokens(
        self,
        chain_id: Optional[int] = None
    ) -> List[str]:
        """Get distinct recipient token addresses for a given chain ID."""
        if not HAS_SQLALCHEMY or not self._async_session:
            logger.warning("Database not available, skipping get_monitored_tokens")
            return []
        from sqlalchemy import select, distinct
        try:
            async with self._async_session() as session:
                stmt = select(distinct(Transaction.to_address))
                if chain_id is not None:
                    stmt = stmt.where(Transaction.chain_id == chain_id)
                result = await session.execute(stmt)
                
                # Handle both direct results and coroutines
                scalars_result = result.scalars()
                if hasattr(scalars_result, '__await__'):  # Check if it's a coroutine
                    scalars_result = await scalars_result
                
                all_result = scalars_result.all() if hasattr(scalars_result, 'all') else scalars_result
                if hasattr(all_result, '__await__'):  # Check if it's a coroutine
                    all_result = await all_result
                
                return all_result if isinstance(all_result, list) else list(all_result)
        except Exception as e:
            logger.error(f"Error getting monitored tokens: {e}")
            return []
    
    async def close(self) -> None:
        """Close database connection."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connection closed")


# Singleton instance
_db_manager = None


def get_db_manager(config: Optional[Configuration] = None, db_url: Optional[str] = None) -> DatabaseManager:
    """
    Get the singleton database manager instance.
    
    Args:
        config: Global configuration (only needed for first call)
        db_url: Database URL (only needed for first call)
        
    Returns:
        Database manager instance
    """
    global _db_manager
    if _db_manager is None:
        if config is None:
            raise ValueError("Configuration must be provided for first call")
        _db_manager = DatabaseManager(config, db_url)
    return _db_manager

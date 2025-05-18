#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ON1Builder – Database Manager
=============================================
Provides database connectivity and operations for storing transaction history.
"""

import os
import sys
import logging
import asyncio
import datetime
import functools
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union, Callable, TypeVar, Awaitable
import sqlite3
import aiosqlite

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DBManager")

# Type variable for the decorator
T = TypeVar('T')

def retry_db_operation(max_retries: int = 5, initial_delay: float = 0.5):
    """Decorator for retrying database operations with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds between retries
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            retries = 0
            delay = initial_delay
            last_exception = None
            
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except (aiosqlite.OperationalError, aiosqlite.DatabaseError) as e:
                    last_exception = e
                    if "database is locked" in str(e) or "busy" in str(e):
                        retries += 1
                        if retries < max_retries:
                            logger.warning(f"Database locked/busy, retrying in {delay:.2f}s ({retries}/{max_retries})")
                            await asyncio.sleep(delay)
                            delay *= 2  # Exponential backoff
                        continue
                    raise  # Re-raise other database errors
                except Exception as e:
                    logger.error(f"Unhandled exception in {func.__name__}: {e}")
                    raise
            
            # If we got here, we exhausted all retries
            logger.error(f"Failed after {max_retries} retries: {last_exception}")
            raise last_exception
            
        return wrapper
    return decorator

class DatabaseManager:
    """Database manager for ON1Builder."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the database manager.
        
        Args:
            db_path: Path to the SQLite database file, defaults to data/db/on1builder.db
        """
        self.db_path = db_path or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                               "data", "db", "on1builder.db")
        self.schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                       "data", "schema", "transaction_history.sql")
        self._connection = None
        self._transaction_lock = asyncio.Lock()  # Lock for transaction isolation
        
    async def initialize(self) -> bool:
        """Initialize the database connection and create tables if they don't exist.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        retries = 3
        retry_delay = 1
        
        for attempt in range(retries):
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                
                # Connect to database with proper settings
                self._connection = await aiosqlite.connect(
                    self.db_path,
                    isolation_level=None,  # We'll manage transactions manually
                    timeout=60.0  # Longer timeout to wait for locks
                )
                
                # Enable foreign keys
                await self._connection.execute("PRAGMA foreign_keys = ON")
                
                # Execute schema
                with open(self.schema_path, 'r') as f:
                    schema_script = f.read()
                    
                async with self._connection.cursor() as cursor:
                    # Begin transaction for schema setup
                    await cursor.execute("BEGIN TRANSACTION")
                    try:
                        # Split SQL commands and execute them
                        for statement in schema_script.split(';'):
                            statement = statement.strip()
                            if statement:
                                await cursor.execute(statement)
                        await cursor.execute("COMMIT")
                    except Exception as e:
                        await cursor.execute("ROLLBACK")
                        raise e
                        
                logger.info(f"Database initialized at {self.db_path}")
                return True
                
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(f"Database initialization attempt {attempt+1} failed: {e}, retrying in {retry_delay}s")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Error initializing database after {retries} attempts: {e}")
                    return False
    
    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    async def __aenter__(self):
        """Context manager entry."""
        if not self._connection:
            await self.initialize()
        return self
            
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
    
    @retry_db_operation(max_retries=5)
    async def record_transaction(self, transaction: Dict[str, Any]) -> bool:
        """Record a transaction in the database with retry logic.
        
        Args:
            transaction: Dictionary with transaction details
            
        Returns:
            True if recording was successful, False otherwise
        """
        async with self._transaction_lock:
            try:
                required_fields = ['tx_hash', 'chain_id', 'from_address', 'to_address', 
                                'gas_price', 'total_gas_cost', 'status']
                
                for field in required_fields:
                    if field not in transaction:
                        logger.error(f"Missing required field in transaction: {field}")
                        return False
                
                # Begin transaction
                async with self._connection.cursor() as cursor:
                    await cursor.execute("BEGIN TRANSACTION")
                    try:
                        query = """
                        INSERT INTO transaction_history 
                            (tx_hash, chain_id, block_number, from_address, to_address, 
                            value, gas_price, gas_used, total_gas_cost, input_data, 
                            status, error_message, timestamp, profit, strategy_used, tx_type)
                        VALUES 
                            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(tx_hash) DO UPDATE SET
                            block_number = excluded.block_number,
                            status = excluded.status,
                            gas_used = excluded.gas_used,
                            total_gas_cost = excluded.total_gas_cost,
                            error_message = excluded.error_message,
                            profit = excluded.profit
                        """
                        
                        params = (
                            transaction['tx_hash'],
                            transaction['chain_id'],
                            transaction.get('block_number'),
                            transaction['from_address'],
                            transaction['to_address'],
                            transaction.get('value', 0),
                            transaction['gas_price'],
                            transaction.get('gas_used'),
                            transaction['total_gas_cost'],
                            transaction.get('input_data'),
                            transaction['status'],
                            transaction.get('error_message'),
                            transaction.get('timestamp', datetime.datetime.now().isoformat()),
                            transaction.get('profit'),
                            transaction.get('strategy_used'),
                            transaction.get('tx_type')
                        )
                        
                        await cursor.execute(query, params)
                        await cursor.execute("COMMIT")
                        logger.debug(f"Recorded transaction: {transaction['tx_hash']}")
                        return True
                    except Exception as e:
                        # Roll back on error
                        await cursor.execute("ROLLBACK")
                        logger.error(f"Error recording transaction: {e}")
                        return False
            except Exception as e:
                logger.error(f"Error recording transaction: {e}")
                return False
    
    @retry_db_operation(max_retries=5)
    async def update_transaction(self, tx_hash: str, updates: Dict[str, Any]) -> bool:
        """Update an existing transaction with retry logic.
        
        Args:
            tx_hash: Transaction hash
            updates: Fields to update
            
        Returns:
            True if update was successful, False otherwise
        """
        async with self._transaction_lock:
            try:
                # Begin transaction
                async with self._connection.cursor() as cursor:
                    await cursor.execute("BEGIN TRANSACTION")
                    try:
                        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
                        query = f"UPDATE transaction_history SET {set_clause} WHERE tx_hash = ?"
                        
                        params = list(updates.values())
                        params.append(tx_hash)
                        
                        await cursor.execute(query, params)
                        await cursor.execute("COMMIT")
                        logger.debug(f"Updated transaction: {tx_hash}")
                        return True
                    except Exception as e:
                        # Roll back on error
                        await cursor.execute("ROLLBACK")
                        logger.error(f"Error updating transaction: {e}")
                        return False
            except Exception as e:
                logger.error(f"Error updating transaction: {e}")
                return False
    
    @retry_db_operation(max_retries=3)
    async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get a transaction by hash with retry logic.
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction details or None if not found
        """
        try:
            query = "SELECT * FROM transaction_history WHERE tx_hash = ?"
            async with self._connection.execute(query, (tx_hash,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    column_names = [description[0] for description in cursor.description]
                    return dict(zip(column_names, row))
                    
                return None
                
        except Exception as e:
            logger.error(f"Error getting transaction: {e}")
            return None
    
    @retry_db_operation(max_retries=3)
    async def get_transactions_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get transactions by status with retry logic.
        
        Args:
            status: Transaction status
            limit: Maximum number of transactions to return
            
        Returns:
            List of transactions
        """
        try:
            query = "SELECT * FROM transaction_history WHERE status = ? ORDER BY timestamp DESC LIMIT ?"
            async with self._connection.execute(query, (status, limit)) as cursor:
                rows = await cursor.fetchall()
                
                if not rows:
                    return []
                    
                column_names = [description[0] for description in cursor.description]
                return [dict(zip(column_names, row)) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting transactions by status: {e}")
            return []
    
    @retry_db_operation(max_retries=3)
    async def get_chain_profits(self, chain_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get profit data for a chain over the specified number of days.
        
        Args:
            chain_id: Chain ID
            days: Number of days to look back
            
        Returns:
            List of profit records
        """
        try:
            query = """
            SELECT * FROM profit_tracking 
            WHERE chain_id = ? AND date >= date('now', ?) 
            ORDER BY date DESC
            """
            days_param = f"-{days} days"
            
            async with self._connection.execute(query, (chain_id, days_param)) as cursor:
                rows = await cursor.fetchall()
                
                if not rows:
                    return []
                    
                column_names = [description[0] for description in cursor.description]
                return [dict(zip(column_names, row)) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting chain profits: {e}")
            return []
    
    async def update_daily_profit_stats(self, chain_id: str, date: Optional[str] = None) -> bool:
        """Update daily profit statistics.
        
        Args:
            chain_id: Chain ID
            date: Date in YYYY-MM-DD format, defaults to today
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            if date is None:
                date = datetime.date.today().isoformat()
                
            # Get transaction stats for the day
            query = """
            SELECT 
                COUNT(*) as total_txs,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_txs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_txs,
                SUM(CASE WHEN profit IS NOT NULL THEN profit ELSE 0 END) as total_profit,
                SUM(total_gas_cost) as total_gas_spent
            FROM transaction_history 
            WHERE chain_id = ? AND date(timestamp) = ?
            """
            
            async with self._connection.execute(query, (chain_id, date)) as cursor:
                stats_row = await cursor.fetchone()
                
                if not stats_row or stats_row[0] == 0:
                    logger.info(f"No transactions for {chain_id} on {date}, skipping stats update")
                    return False
                
                total_txs, successful_txs, failed_txs, total_profit, total_gas_spent = stats_row
                
                # Get most profitable transaction
                query2 = """
                SELECT tx_hash, profit, strategy_used
                FROM transaction_history 
                WHERE chain_id = ? AND date(timestamp) = ? AND profit IS NOT NULL
                ORDER BY profit DESC
                LIMIT 1
                """
                
                async with self._connection.execute(query2, (chain_id, date)) as cursor2:
                    profit_row = await cursor2.fetchone()
                    
                    most_profitable_tx_hash = profit_row[0] if profit_row else None
                    highest_profit_amount = profit_row[1] if profit_row else 0
                    most_profitable_strategy = profit_row[2] if profit_row else None
                
                # Calculate net profit and averages
                net_profit = float(total_profit or 0) - float(total_gas_spent or 0)
                avg_profit_per_tx = float(total_profit or 0) / successful_txs if successful_txs > 0 else 0
                
                # Insert or update profit tracking record
                upsert_query = """
                INSERT INTO profit_tracking
                    (chain_id, date, total_transactions, successful_transactions, failed_transactions,
                     total_profit, total_gas_spent, net_profit, avg_profit_per_tx,
                     most_profitable_strategy, most_profitable_tx_hash, highest_profit_amount)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chain_id, date) DO UPDATE SET
                    total_transactions = excluded.total_transactions,
                    successful_transactions = excluded.successful_transactions,
                    failed_transactions = excluded.failed_transactions,
                    total_profit = excluded.total_profit,
                    total_gas_spent = excluded.total_gas_spent,
                    net_profit = excluded.net_profit,
                    avg_profit_per_tx = excluded.avg_profit_per_tx,
                    most_profitable_strategy = excluded.most_profitable_strategy,
                    most_profitable_tx_hash = excluded.most_profitable_tx_hash,
                    highest_profit_amount = excluded.highest_profit_amount
                """
                
                await self._connection.execute(upsert_query, (
                    chain_id, date, total_txs, successful_txs, failed_txs,
                    total_profit, total_gas_spent, net_profit, avg_profit_per_tx,
                    most_profitable_strategy, most_profitable_tx_hash, highest_profit_amount
                ))
                
                await self._connection.commit()
                logger.info(f"Updated profit stats for {chain_id} on {date}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating daily profit stats: {e}")
            return False
    
    async def update_strategy_performance(self, strategy_name: str, chain_id: str, 
                                         execution_time_ms: float, success: bool, 
                                         profit: float = 0, gas_cost: float = 0) -> bool:
        """Update strategy performance statistics.
        
        Args:
            strategy_name: Name of the strategy
            chain_id: Chain ID
            execution_time_ms: Execution time in milliseconds
            success: Whether execution was successful
            profit: Profit amount (if successful)
            gas_cost: Gas cost
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            date = datetime.date.today().isoformat()
            
            # Check if record exists for today
            check_query = """
            SELECT id, executions, successes, failures, total_profit, total_gas_spent, 
                   net_profit, avg_execution_time_ms
            FROM strategy_performance
            WHERE strategy_name = ? AND chain_id = ? AND date = ?
            """
            
            async with self._connection.execute(check_query, (strategy_name, chain_id, date)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    # Update existing record
                    id, executions, successes, failures, total_profit, total_gas_spent, net_profit, avg_exec_time = row
                    
                    new_executions = executions + 1
                    new_successes = successes + 1 if success else successes
                    new_failures = failures + 1 if not success else failures
                    new_total_profit = total_profit + profit if success else total_profit
                    new_total_gas_spent = total_gas_spent + gas_cost
                    new_net_profit = new_total_profit - new_total_gas_spent
                    
                    # Update average execution time
                    new_avg_exec_time = ((avg_exec_time * executions) + execution_time_ms) / new_executions
                    
                    # Calculate new weight based on success rate and profit
                    success_rate = new_successes / new_executions if new_executions > 0 else 0
                    avg_profit = new_total_profit / new_successes if new_successes > 0 else 0
                    new_weight = (success_rate * 0.5) + (min(avg_profit * 20, 0.5))  # Scale profit influence
                    new_weight = max(0.1, min(10.0, new_weight))  # Clamp between 0.1 and 10.0
                    
                    update_query = """
                    UPDATE strategy_performance
                    SET executions = ?, successes = ?, failures = ?,
                        total_profit = ?, total_gas_spent = ?, net_profit = ?,
                        avg_execution_time_ms = ?, weight = ?
                    WHERE id = ?
                    """
                    
                    await self._connection.execute(update_query, (
                        new_executions, new_successes, new_failures,
                        new_total_profit, new_total_gas_spent, new_net_profit,
                        new_avg_exec_time, new_weight, id
                    ))
                    
                else:
                    # Create new record
                    new_executions = 1
                    new_successes = 1 if success else 0
                    new_failures = 1 if not success else 0
                    new_total_profit = profit if success else 0
                    new_total_gas_spent = gas_cost
                    new_net_profit = new_total_profit - new_total_gas_spent
                    new_avg_exec_time = execution_time_ms
                    
                    # Initial weight based on success
                    new_weight = 1.0 if success else 0.5
                    
                    insert_query = """
                    INSERT INTO strategy_performance
                        (strategy_name, chain_id, date, executions, successes, failures,
                         total_profit, total_gas_spent, net_profit, avg_execution_time_ms, weight)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    await self._connection.execute(insert_query, (
                        strategy_name, chain_id, date, new_executions, new_successes,
                        new_failures, new_total_profit, new_total_gas_spent, new_net_profit,
                        new_avg_exec_time, new_weight
                    ))
                
                await self._connection.commit()
                logger.debug(f"Updated performance for strategy {strategy_name} on {chain_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating strategy performance: {e}")
            return False
            
    async def record_gas_price(self, chain_id: str, block_number: int, 
                              gas_price_gwei: float, priority_fee_gwei: Optional[float] = None,
                              base_fee_gwei: Optional[float] = None, 
                              network_congestion: Optional[float] = None) -> bool:
        """Record current gas price information.
        
        Args:
            chain_id: Chain ID
            block_number: Block number
            gas_price_gwei: Gas price in Gwei
            priority_fee_gwei: Priority fee in Gwei (EIP-1559)
            base_fee_gwei: Base fee in Gwei (EIP-1559)
            network_congestion: Network congestion level (0-100)
            
        Returns:
            True if recording was successful, False otherwise
        """
        try:
            query = """
            INSERT INTO gas_price_history
                (chain_id, block_number, gas_price_gwei, priority_fee_gwei, base_fee_gwei, network_congestion)
            VALUES
                (?, ?, ?, ?, ?, ?)
            """
            
            await self._connection.execute(query, (
                chain_id, block_number, gas_price_gwei, 
                priority_fee_gwei, base_fee_gwei, network_congestion
            ))
            
            await self._connection.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error recording gas price: {e}")
            return False
    
    async def get_average_gas_price(self, chain_id: str, hours: int = 1) -> Optional[float]:
        """Get average gas price for a chain over the specified time period.
        
        Args:
            chain_id: Chain ID
            hours: Number of hours to look back
            
        Returns:
            Average gas price in Gwei or None if data not available
        """
        try:
            query = """
            SELECT AVG(gas_price_gwei) FROM gas_price_history
            WHERE chain_id = ? AND timestamp >= datetime('now', ?)
            """
            hours_param = f"-{hours} hours"
            
            async with self._connection.execute(query, (chain_id, hours_param)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row[0] is not None else None
                
        except Exception as e:
            logger.error(f"Error getting average gas price: {e}")
            return None
            
    async def get_strategy_weights(self, chain_id: str) -> Dict[str, float]:
        """Get current strategy weights for a chain.
        
        Args:
            chain_id: Chain ID
            
        Returns:
            Dictionary of strategy weights
        """
        try:
            query = """
            SELECT strategy_name, weight FROM strategy_performance
            WHERE chain_id = ? AND date = ?
            """
            date = datetime.date.today().isoformat()
            
            weights = {}
            async with self._connection.execute(query, (chain_id, date)) as cursor:
                rows = await cursor.fetchall()
                
                for row in rows:
                    weights[row[0]] = float(row[1])
                
            return weights
                
        except Exception as e:
            logger.error(f"Error getting strategy weights: {e}")
            return {}

# Singleton instance
_db_manager = None

async def get_db_manager() -> DatabaseManager:
    """Get a database manager instance.
    
    Returns:
        A DatabaseManager instance
    """
    db_manager = DatabaseManager()
    if not await db_manager.initialize():
        logger.error("Failed to initialize database manager")
        raise RuntimeError("Database initialization failed")
    return db_manager

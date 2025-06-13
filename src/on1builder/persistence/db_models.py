# src/on1builder/persistence/db_models.py
from __future__ import annotations

import datetime
from typing import Any, Dict

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    BigInteger,
    Index
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Transaction(Base):
    """Enhanced SQLAlchemy model for storing transaction records with comprehensive tracking."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String(66), unique=True, nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    block_number = Column(Integer, index=True, nullable=True)
    from_address = Column(String(42), nullable=False, index=True)
    to_address = Column(String(42), nullable=True, index=True)
    value = Column(BigInteger, nullable=False)  # Value in Wei
    gas_used = Column(BigInteger, nullable=True)
    gas_price = Column(BigInteger, nullable=True)  # Gas price in Wei
    gas_cost_eth = Column(Float, nullable=True)  # Total gas cost in ETH
    status = Column(Boolean, nullable=True)  # True for success (1), False for failure (0)
    strategy = Column(String(50), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    raw_tx = Column(Text, nullable=True)
    
    # Enhanced tracking fields
    execution_time_s = Column(Float, nullable=True)  # Execution time in seconds
    nonce = Column(BigInteger, nullable=True)
    max_fee_per_gas = Column(BigInteger, nullable=True)  # EIP-1559
    max_priority_fee_per_gas = Column(BigInteger, nullable=True)  # EIP-1559
    balance_before = Column(Float, nullable=True)  # Balance before transaction (ETH)
    balance_after = Column(Float, nullable=True)   # Balance after transaction (ETH)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the model instance to a dictionary."""
        return {
            "id": self.id,
            "tx_hash": self.tx_hash,
            "chain_id": self.chain_id,
            "block_number": self.block_number,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "value": str(self.value),
            "gas_used": str(self.gas_used) if self.gas_used is not None else None,
            "gas_price": str(self.gas_price) if self.gas_price is not None else None,
            "gas_cost_eth": self.gas_cost_eth,
            "status": self.status,
            "strategy": self.strategy,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "execution_time_s": self.execution_time_s,
            "nonce": str(self.nonce) if self.nonce is not None else None,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
        }


class ProfitRecord(Base):
    """Enhanced SQLAlchemy model for tracking profits with comprehensive metrics."""
    __tablename__ = "profit_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String(66), nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    profit_amount_eth = Column(Float, nullable=False)
    profit_amount_usd = Column(Float, nullable=True)
    gas_cost_eth = Column(Float, nullable=True)
    net_profit_eth = Column(Float, nullable=True)  # Profit after gas costs
    roi_percentage = Column(Float, nullable=True)  # Return on investment
    strategy = Column(String(50), nullable=False, index=True)
    base_token_address = Column(String(42), nullable=True)
    quote_token_address = Column(String(42), nullable=True)
    execution_time_s = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    
    # Strategy-specific fields
    flashloan_amount = Column(Float, nullable=True)  # Amount borrowed via flashloan
    arbitrage_spread = Column(Float, nullable=True)  # Price spread captured
    slippage_experienced = Column(Float, nullable=True)  # Actual slippage vs expected
    
    # Risk metrics
    max_exposure_eth = Column(Float, nullable=True)  # Maximum capital at risk
    risk_score = Column(Float, nullable=True)  # Calculated risk score (0-1)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the model instance to a dictionary."""
        return {
            "id": self.id,
            "tx_hash": self.tx_hash,
            "chain_id": self.chain_id,
            "profit_amount_eth": self.profit_amount_eth,
            "profit_amount_usd": self.profit_amount_usd,
            "gas_cost_eth": self.gas_cost_eth,
            "net_profit_eth": self.net_profit_eth,
            "roi_percentage": self.roi_percentage,
            "strategy": self.strategy,
            "base_token_address": self.base_token_address,
            "quote_token_address": self.quote_token_address,
            "execution_time_s": self.execution_time_s,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "flashloan_amount": self.flashloan_amount,
            "arbitrage_spread": self.arbitrage_spread,
            "slippage_experienced": self.slippage_experienced,
            "max_exposure_eth": self.max_exposure_eth,
            "risk_score": self.risk_score,
        }


class StrategyPerformance(Base):
    """Model for tracking strategy performance metrics over time."""
    __tablename__ = "strategy_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy = Column(String(50), nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    
    # Performance metrics
    total_executions = Column(Integer, default=0)
    successful_executions = Column(Integer, default=0)
    total_profit_eth = Column(Float, default=0.0)
    total_gas_spent_eth = Column(Float, default=0.0)
    avg_execution_time_s = Column(Float, nullable=True)
    success_rate = Column(Float, nullable=True)  # Percentage
    avg_profit_per_execution = Column(Float, nullable=True)
    
    # ML metrics
    ml_weight = Column(Float, default=1.0)
    confidence_score = Column(Float, nullable=True)
    exploration_count = Column(Integer, default=0)
    
    # Time tracking
    last_execution = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Performance window (e.g., daily, hourly)
    window_start = Column(DateTime, nullable=True)
    window_end = Column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the model instance to a dictionary."""
        return {
            "id": self.id,
            "strategy": self.strategy,
            "chain_id": self.chain_id,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "total_profit_eth": self.total_profit_eth,
            "total_gas_spent_eth": self.total_gas_spent_eth,
            "avg_execution_time_s": self.avg_execution_time_s,
            "success_rate": self.success_rate,
            "avg_profit_per_execution": self.avg_profit_per_execution,
            "ml_weight": self.ml_weight,
            "confidence_score": self.confidence_score,
            "exploration_count": self.exploration_count,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class MarketCondition(Base):
    """Model for tracking market conditions and their impact on strategy performance."""
    __tablename__ = "market_conditions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chain_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    
    # Gas market conditions
    gas_price_gwei = Column(Float, nullable=True)
    gas_price_percentile = Column(Float, nullable=True)  # 0-100
    network_congestion = Column(Float, nullable=True)    # 0-1 scale
    
    # Price volatility
    eth_price_usd = Column(Float, nullable=True)
    volatility_24h = Column(Float, nullable=True)
    
    # MEV market conditions
    mev_opportunities_detected = Column(Integer, default=0)
    avg_opportunity_profit = Column(Float, nullable=True)
    competition_level = Column(Float, nullable=True)  # 0-1 scale
    
    # Strategy performance during these conditions
    most_profitable_strategy = Column(String(50), nullable=True)
    avg_success_rate = Column(Float, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the model instance to a dictionary."""
        return {
            "id": self.id,
            "chain_id": self.chain_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "gas_price_gwei": self.gas_price_gwei,
            "gas_price_percentile": self.gas_price_percentile,
            "network_congestion": self.network_congestion,
            "eth_price_usd": self.eth_price_usd,
            "volatility_24h": self.volatility_24h,
            "mev_opportunities_detected": self.mev_opportunities_detected,
            "avg_opportunity_profit": self.avg_opportunity_profit,
            "competition_level": self.competition_level,
            "most_profitable_strategy": self.most_profitable_strategy,
            "avg_success_rate": self.avg_success_rate,
        }


# Create composite indexes for better query performance
Index('idx_transactions_strategy_timestamp', Transaction.strategy, Transaction.timestamp)
Index('idx_transactions_chain_status', Transaction.chain_id, Transaction.status)
Index('idx_profit_records_strategy_timestamp', ProfitRecord.strategy, ProfitRecord.timestamp)
Index('idx_strategy_performance_strategy_chain', StrategyPerformance.strategy, StrategyPerformance.chain_id)
Index('idx_market_conditions_chain_timestamp', MarketCondition.chain_id, MarketCondition.timestamp)
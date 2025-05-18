-- ON1Builder Transaction History Schema
-- This schema is for storing transaction history in a SQLite or PostgreSQL database

-- Transaction History Table
CREATE TABLE IF NOT EXISTS transaction_history (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    chain_id VARCHAR(20) NOT NULL,
    block_number BIGINT,
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42) NOT NULL,
    value NUMERIC(36, 18) NOT NULL DEFAULT 0,
    gas_price NUMERIC(36, 18) NOT NULL,
    gas_used BIGINT,
    total_gas_cost NUMERIC(36, 18) NOT NULL,
    input_data TEXT,
    status VARCHAR(20) NOT NULL,  -- 'success', 'failed', 'pending'
    error_message TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    profit NUMERIC(36, 18),
    strategy_used VARCHAR(50),
    tx_type VARCHAR(30)  -- 'front_run', 'back_run', 'sandwich', 'arbitrage', etc.
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_tx_history_chain_id ON transaction_history(chain_id);
CREATE INDEX IF NOT EXISTS idx_tx_history_block_number ON transaction_history(block_number);
CREATE INDEX IF NOT EXISTS idx_tx_history_from_address ON transaction_history(from_address);
CREATE INDEX IF NOT EXISTS idx_tx_history_to_address ON transaction_history(to_address);
CREATE INDEX IF NOT EXISTS idx_tx_history_timestamp ON transaction_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_history_status ON transaction_history(status);
CREATE INDEX IF NOT EXISTS idx_tx_history_strategy ON transaction_history(strategy_used);
CREATE INDEX IF NOT EXISTS idx_tx_history_type ON transaction_history(tx_type);

-- Profit Tracking Table
CREATE TABLE IF NOT EXISTS profit_tracking (
    id SERIAL PRIMARY KEY,
    chain_id VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    total_transactions INTEGER NOT NULL DEFAULT 0,
    successful_transactions INTEGER NOT NULL DEFAULT 0,
    failed_transactions INTEGER NOT NULL DEFAULT 0,
    total_profit NUMERIC(36, 18) NOT NULL DEFAULT 0,
    total_gas_spent NUMERIC(36, 18) NOT NULL DEFAULT 0,
    net_profit NUMERIC(36, 18) NOT NULL DEFAULT 0,
    avg_profit_per_tx NUMERIC(36, 18),
    most_profitable_strategy VARCHAR(50),
    most_profitable_tx_hash VARCHAR(66),
    highest_profit_amount NUMERIC(36, 18),
    UNIQUE(chain_id, date)
);

-- Create indexes for profit tracking
CREATE INDEX IF NOT EXISTS idx_profit_tracking_chain_id ON profit_tracking(chain_id);
CREATE INDEX IF NOT EXISTS idx_profit_tracking_date ON profit_tracking(date);

-- Strategy Performance Table
CREATE TABLE IF NOT EXISTS strategy_performance (
    id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(50) NOT NULL,
    chain_id VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    executions INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    total_profit NUMERIC(36, 18) NOT NULL DEFAULT 0,
    total_gas_spent NUMERIC(36, 18) NOT NULL DEFAULT 0,
    net_profit NUMERIC(36, 18) NOT NULL DEFAULT 0,
    avg_execution_time_ms NUMERIC NOT NULL DEFAULT 0,
    weight NUMERIC(10, 5) NOT NULL DEFAULT 1.0,
    UNIQUE(strategy_name, chain_id, date)
);

-- Create indexes for strategy performance
CREATE INDEX IF NOT EXISTS idx_strategy_perf_strategy ON strategy_performance(strategy_name);
CREATE INDEX IF NOT EXISTS idx_strategy_perf_chain_id ON strategy_performance(chain_id);
CREATE INDEX IF NOT EXISTS idx_strategy_perf_date ON strategy_performance(date);

-- Gas Price History Table
CREATE TABLE IF NOT EXISTS gas_price_history (
    id SERIAL PRIMARY KEY,
    chain_id VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    block_number BIGINT,
    gas_price_gwei NUMERIC(20, 9) NOT NULL,
    priority_fee_gwei NUMERIC(20, 9),
    base_fee_gwei NUMERIC(20, 9),
    network_congestion NUMERIC(5, 2)  -- A value from 0 to 100 representing congestion %
);

-- Create indexes for gas price history
CREATE INDEX IF NOT EXISTS idx_gas_price_chain_id ON gas_price_history(chain_id);
CREATE INDEX IF NOT EXISTS idx_gas_price_timestamp ON gas_price_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_gas_price_block ON gas_price_history(block_number); 
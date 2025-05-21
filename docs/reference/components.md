# Components Reference

This document provides a detailed reference for the key components of ON1Builder, including their purpose, functionality, and interaction with other components.

## Core Components

### MainCore

`MainCore` is the central orchestration component of ON1Builder, responsible for bootstrapping and coordinating all other components.

**Key Responsibilities:**
- Managing the AsyncIO event loop
- Initializing all system components
- Coordinating startup and shutdown sequences
- Maintaining the application lifecycle
- Providing central error handling

**Usage:**
```python
from on1builder.core import MainCore

# Initialize with configuration
core = MainCore(config_path="config.yaml")

# Start and run the system
await core.start()

# Perform operations
status = await core.get_status()
result = await core.execute_strategy("flash_loan", params)

# Gracefully shut down
await core.stop()
```

**Lifecycle:**
1. Load configuration
2. Initialize Web3 connections
3. Initialize blockchain interfaces
4. Start monitoring systems
5. Initialize transaction management
6. Enter main operation loop
7. Graceful shutdown on exit

### MultiChainCore

`MultiChainCore` extends `MainCore` to manage operations across multiple blockchains simultaneously.

**Key Responsibilities:**
- Managing multiple blockchain connections
- Coordinating cross-chain operations
- Providing unified interfaces for multi-chain interactions
- Optimizing resource usage across chains

**Usage:**
```python
from on1builder.core import MultiChainCore

# Initialize with multi-chain configuration
core = MultiChainCore(config_path="config_multi_chain.yaml")

# Get chain-specific workers
eth_worker = core.get_chain_worker(chain_id=1)
polygon_worker = core.get_chain_worker(chain_id=137)

# Execute chain-specific operations
eth_result = await eth_worker.execute_strategy("flash_loan", eth_params)
polygon_result = await polygon_worker.execute_strategy("flash_loan", polygon_params)

# Execute cross-chain operations
result = await core.execute_cross_chain_strategy("arbitrage", params)
```

**Chain Worker Management:**
- Creates chain-specific workers based on configuration
- Manages resource allocation between chains
- Provides isolation between chain operations
- Enables parallel execution when possible

### ChainWorker

`ChainWorker` handles blockchain-specific operations for a single chain, managed by `MultiChainCore`.

**Key Responsibilities:**
- Connecting to specific blockchain nodes
- Monitoring chain-specific events
- Executing chain-specific strategies
- Managing chain-specific transactions
- Reporting chain-specific metrics

**Components:**
- Chain-specific Web3 connection
- Block and transaction monitors
- Chain-specific transaction core
- Chain-specific safety checks

**Key Methods:**
- `monitor_blocks()`: Monitor new blocks on the chain
- `monitor_transactions()`: Monitor mempool for pending transactions
- `execute_strategy()`: Execute a strategy on this chain
- `get_chain_status()`: Get chain-specific status information

### TransactionCore

`TransactionCore` handles all transaction-related operations, providing a high-level interface for transaction management.

**Key Responsibilities:**
- Building transaction objects
- Signing transactions with wallet keys
- Estimating gas costs
- Simulating transactions before execution
- Submitting transactions to the network
- Tracking transaction status
- Handling transaction errors and retries

**Usage:**
```python
from on1builder.core import TransactionCore

# Create a transaction
tx = await tx_core.build_transaction(
    to_address="0x...",
    value=0.1,  # ETH
    data="0x...",
    gas_price_strategy="fast"
)

# Estimate gas
gas_estimate = await tx_core.estimate_gas(tx)

# Simulate transaction
simulation = await tx_core.simulate_transaction(tx)

# Check profitability
is_profitable = await tx_core.check_profitability(
    tx,
    expected_profit=0.05,
    gas_estimate=gas_estimate
)

# Send transaction
receipt = await tx_core.send_transaction(tx)

# Get transaction status
status = await tx_core.get_transaction_status(tx_hash)
```

**Transaction Types Supported:**
- Standard ETH transfers
- ERC20 token transfers
- Contract interactions
- Flash loans
- Complex MEV operations
- EIP-1559 transactions

### NonceCore

`NonceCore` manages transaction nonces to ensure proper transaction ordering and prevent nonce conflicts.

**Key Responsibilities:**
- Tracking on-chain nonce values
- Managing nonce allocation for concurrent transactions
- Handling nonce recovery in error cases
- Preventing nonce conflicts

**Key Methods:**
- `get_current_nonce()`: Get the current on-chain nonce
- `reserve_nonce()`: Reserve a nonce for a transaction
- `release_nonce()`: Release a reserved nonce
- `reset_nonce()`: Reset nonce tracking to on-chain value
- `handle_nonce_conflict()`: Resolve nonce conflicts

**Usage:**
```python
from on1builder.core import NonceCore

# Get current nonce
nonce = await nonce_core.get_current_nonce()

# Reserve a nonce for a transaction
async with nonce_core.nonce_lock:
    tx_nonce = await nonce_core.reserve_nonce()
    try:
        # Use the nonce for a transaction
        tx = await tx_core.build_transaction(
            to_address="0x...",
            value=0.1,
            nonce=tx_nonce
        )
        await tx_core.send_transaction(tx)
    except Exception as e:
        # Release the nonce on error
        await nonce_core.release_nonce(tx_nonce)
        raise
```

### SafetyNet

`SafetyNet` implements safeguards to protect against risks and ensure system stability.

**Key Responsibilities:**
- Transaction validation before execution
- Profitability checks
- Gas price limits and controls
- Error handling and recovery procedures
- Fund protection mechanisms

**Safety Features:**
- Pre-execution simulation
- Gas price limits
- Minimum profit requirements
- Slippage protection
- Maximum exposure limits
- Balance monitoring
- Critical error handling

**Key Methods:**
- `validate_transaction()`: Validate a transaction against safety rules
- `check_profitability()`: Check if a transaction meets profit requirements
- `validate_gas_price()`: Ensure gas price is within acceptable limits
- `check_wallet_balance()`: Verify sufficient wallet balance
- `emergency_shutdown()`: Trigger emergency shutdown if needed

## Monitoring Components

### MarketMonitor

`MarketMonitor` tracks market conditions, token prices, and other market data needed for strategy execution.

**Key Responsibilities:**
- Tracking token prices from multiple sources
- Monitoring trading pair liquidity
- Tracking gas prices and network congestion
- Detecting market anomalies

**Data Sources:**
- On-chain price feeds
- Public APIs (CoinGecko, CoinMarketCap, etc.)
- DEX liquidity pools
- Gas price oracles

**Key Methods:**
- `get_token_price()`: Get current price of a token
- `get_pair_price()`: Get price of a token pair
- `get_historical_prices()`: Get historical price data
- `get_gas_price()`: Get current gas price
- `get_market_volatility()`: Get market volatility metrics

### TxpoolMonitor

`TxpoolMonitor` monitors the transaction mempool for pending transactions and MEV opportunities.

**Key Responsibilities:**
- Monitoring the mempool for pending transactions
- Analyzing transactions for potential MEV opportunities
- Detecting arbitrage opportunities
- Identifying sandwich attack vectors

**Key Methods:**
- `monitor_mempool()`: Start monitoring the mempool
- `analyze_transaction()`: Analyze a transaction for MEV opportunities
- `get_pending_transactions()`: Get all pending transactions
- `get_mempool_stats()`: Get statistics about the current mempool

### Monitoring System

The monitoring system provides comprehensive monitoring, logging, and alerting capabilities.

**Key Components:**
- Logging system
- Prometheus metrics
- Health check endpoints
- Alerting integrations

**Features:**
- Structured logging
- Performance metrics
- Transaction tracking
- System health monitoring
- Real-time alerting
- Visualization via Grafana

## Strategy Components

### StrategyNet

`StrategyNet` implements and manages trading strategies, including MEV strategies.

**Key Responsibilities:**
- Managing available strategies
- Scanning for strategy opportunities
- Executing strategy operations
- Calculating profitability
- Tracking strategy performance

**Included Strategies:**
- Arbitrage between DEXes
- Flash loans for arbitrage
- Liquidation opportunities
- Frontrunning profitable transactions
- Backrunning profitable transactions
- Sandwich attacks on large swaps

**Key Methods:**
- `get_available_strategies()`: List available strategies
- `find_opportunities()`: Scan for opportunities across strategies
- `execute_strategy()`: Execute a specific strategy
- `calculate_profitability()`: Calculate potential profit for a strategy
- `get_strategy_stats()`: Get performance statistics for strategies

### Strategy Base Class

The `Strategy` base class provides a framework for implementing custom strategies.

**Key Methods to Implement:**
- `find_opportunities()`: Find opportunities for this strategy
- `simulate()`: Simulate the strategy execution
- `execute()`: Execute the strategy
- `calculate_profit()`: Calculate expected profit
- `validate()`: Validate the strategy parameters

**Example Implementation:**
```python
from on1builder.strategies import Strategy

class ArbitrageStrategy(Strategy):
    name = "arbitrage"
    description = "DEX arbitrage strategy"
    
    def __init__(self, config, tx_core, market_monitor):
        super().__init__(config, tx_core, market_monitor)
        # Strategy-specific initialization
        
    async def find_opportunities(self):
        # Logic to find arbitrage opportunities
        opportunities = []
        # ... analyze price differences between DEXes ...
        return opportunities
        
    async def simulate(self, opportunity):
        # Simulate the arbitrage execution
        # ... build and simulate transactions ...
        return simulation_result
        
    async def execute(self, opportunity):
        # Execute the arbitrage
        # ... build and send transactions ...
        return execution_result
        
    async def calculate_profit(self, opportunity):
        # Calculate expected profit
        # ... calculate based on price differences and gas costs ...
        return expected_profit
```

## Persistence Components

### DatabaseManager

`DatabaseManager` handles all database operations for persistent storage.

**Key Responsibilities:**
- Managing database connections
- Storing transaction history
- Tracking execution results
- Maintaining performance metrics
- Supporting data analysis

**Supported Databases:**
- SQLite (default for development)
- PostgreSQL (recommended for production)

**Key Methods:**
- `record_transaction()`: Record transaction details
- `record_profit()`: Record profit from a transaction
- `get_transaction_history()`: Retrieve transaction history
- `get_performance_metrics()`: Retrieve performance metrics
- `backup_database()`: Create database backup

## Integration Components

### APIConfig

`APIConfig` manages external API integrations for market data and other services.

**Key Responsibilities:**
- Managing API configurations
- Handling API authentication
- Fetching data from external APIs
- Caching API responses
- Handling API rate limits
- Implementing fallbacks

**Supported APIs:**
- CoinGecko
- CoinMarketCap
- Etherscan
- PolygonScan
- DefiLlama
- 1inch API

### RESTAPIServer

`RESTAPIServer` provides a REST API for monitoring and controlling the system.

**Key Responsibilities:**
- Exposing system status and metrics
- Providing control endpoints
- Supporting external integrations
- Enabling programmatic control

**Key Endpoints:**
- `/status`: System status information
- `/metrics`: Prometheus metrics
- `/transactions`: Transaction history
- `/control`: System control endpoints
- `/config`: Configuration management

## Utility Components

### ABIRegistry

`ABIRegistry` manages contract ABIs (Application Binary Interfaces) for interacting with smart contracts.

**Key Responsibilities:**
- Loading and caching contract ABIs
- Providing ABIs for contract interactions
- Detecting ABI requirements from transactions
- Handling ABI versioning

**Key Methods:**
- `get_abi()`: Get ABI for a specific contract
- `load_abi_from_file()`: Load ABI from a file
- `load_abi_from_etherscan()`: Load ABI from Etherscan
- `detect_required_abi()`: Detect ABI needed for a transaction

### ConfigManager

`ConfigManager` handles configuration loading, validation, and management.

**Key Responsibilities:**
- Loading configuration from files
- Validating configuration values
- Providing access to configuration
- Handling configuration updates
- Managing environment variables

**Key Methods:**
- `load_config()`: Load configuration from file
- `validate_config()`: Validate configuration values
- `get_config()`: Get current configuration
- `update_config()`: Update configuration values
- `get_environment()`: Get current environment

## Component Interactions

### Transaction Flow

The flow of a transaction through the system:

1. **Opportunity Detection**:
   - `StrategyNet` identifies an opportunity
   - `MarketMonitor` provides market data

2. **Transaction Preparation**:
   - `TransactionCore` builds the transaction
   - `NonceCore` provides the nonce
   - `SafetyNet` validates the transaction

3. **Transaction Simulation**:
   - `TransactionCore` simulates the transaction
   - `SafetyNet` verifies profitability

4. **Transaction Execution**:
   - `TransactionCore` sends the transaction
   - `NonceCore` updates nonce tracking

5. **Transaction Monitoring**:
   - `TransactionCore` monitors transaction status
   - `DatabaseManager` records the transaction

6. **Result Processing**:
   - `DatabaseManager` records results
   - `Monitoring` updates metrics
   - `StrategyNet` updates strategy statistics

### Multi-Chain Interaction

The interaction between chains in multi-chain mode:

1. **MultiChainCore** manages all chains
2. **ChainWorker** instances handle chain-specific operations
3. **Cross-chain strategies** coordinate between chain workers
4. **SharedResources** manage resources across chains

## Extending Components

ON1Builder is designed to be extensible. Here's how to extend key components:

### Creating Custom Strategies

Implement the `Strategy` base class:

```python
from on1builder.strategies import Strategy, register_strategy

class MyCustomStrategy(Strategy):
    name = "my_custom_strategy"
    description = "My custom trading strategy"
    
    # Implement required methods
    async def find_opportunities(self):
        # Your opportunity detection logic
        pass
        
    async def execute(self, opportunity):
        # Your execution logic
        pass

# Register your strategy
register_strategy(MyCustomStrategy)
```

### Adding Custom Monitoring

Extend the monitoring system:

```python
from on1builder.monitoring import MetricsRegistry

# Add custom metrics
custom_metric = MetricsRegistry.counter(
    name="my_custom_metric",
    description="My custom metric",
    labels=["label1", "label2"]
)

# Use the metric
custom_metric.inc(labels={"label1": "value1", "label2": "value2"})
```

### Implementing Custom Safety Checks

Add custom safety checks:

```python
from on1builder.safety import SafetyCheck, register_safety_check

class MyCustomSafetyCheck(SafetyCheck):
    name = "my_custom_check"
    description = "My custom safety check"
    
    async def check(self, transaction):
        # Your safety check logic
        if unsafe_condition:
            return False, "Unsafe transaction: reason"
        return True, None

# Register your safety check
register_safety_check(MyCustomSafetyCheck)
```

## Component Configuration

Configuration options for main components:

### MainCore Configuration

```yaml
# MainCore configuration
CORE_WORKERS: 4  # Number of worker threads
HEARTBEAT_INTERVAL: 30  # Heartbeat interval in seconds
MAX_CONCURRENT_OPERATIONS: 20  # Maximum concurrent operations
```

### TransactionCore Configuration

```yaml
# TransactionCore configuration
TX_CONFIRMATION_BLOCKS: 2  # Blocks to wait for confirmation
SIMULATE_TRANSACTIONS: true  # Simulate before execution
MAX_PENDING_TRANSACTIONS: 5  # Maximum pending transactions
TX_CONFIRMATION_TIMEOUT: 300  # Confirmation timeout in seconds
```

### SafetyNet Configuration

```yaml
# SafetyNet configuration
MIN_PROFIT: 0.001  # Minimum profit in ETH
MAX_GAS_PRICE_GWEI: 500  # Maximum gas price in Gwei
SLIPPAGE_DEFAULT: 0.05  # Default slippage (5%)
FUND_RECOVERY_THRESHOLD: 0.9  # Fund recovery threshold
```

### Monitoring Configuration

```yaml
# Monitoring configuration
ENABLE_PROMETHEUS: true  # Enable Prometheus metrics
PROMETHEUS_PORT: 9090  # Prometheus port
LOG_LEVEL: "INFO"  # Logging level
ENABLE_SLACK_ALERTS: true  # Enable Slack alerts
SLACK_WEBHOOK_URL: "https://hooks.slack.com/services/..."  # Slack webhook
```

## Conclusion

This component reference provides a comprehensive overview of ON1Builder's components, their interactions, and how to extend them. For more information, refer to:

- [Architecture Overview](architecture.md): High-level system architecture
- [API Reference](api.md): Detailed API documentation
- [Configuration Reference](configuration_reference.md): Complete configuration options

---

**Next Steps:**

- Try the [Single Chain Example](../examples/single_chain_example.md) to see components in action
- Follow the [Multi-Chain Example](../examples/multi_chain_example.md) for multi-chain deployment
- Create your own [Custom Strategy](../examples/custom_strategy_example.md)
- Return to the [Main Documentation](../index.md)

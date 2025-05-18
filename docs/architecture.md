# ON1Builder Architecture

This document outlines the architecture and design principles of the ON1Builder system, a multi-chain MEV (Miner/Maximal Extractable Value) trading bot platform.

## System Overview

ON1Builder is designed as a modular, scalable system for running trading strategies across multiple EVM-compatible blockchains. The architecture follows a microservice-oriented approach with clear separation of concerns.

```
                                +-----------------+
                                |     UI / API    |
                                +-----------------+
                                        |
                                        v
+----------------+            +-------------------+            +-----------------+
|                |            |                   |            |                 |
|  Monitoring    |<---------->|  Multi-Chain Core |<---------->|  External APIs  |
|  (Prometheus/  |            |                   |            |                 |
|   Grafana)     |            +-------------------+            +-----------------+
|                |                     |
+----------------+                     |
                                       v
                          +---------------------------+
                          |                           |
                    +-----v------+             +------v-----+
                    |            |             |            |
                    | Chain      |     ...     | Chain      |
                    | Worker 1   |             | Worker N   |
                    |            |             |            |
                    +-----+------+             +------+-----+
                          |                           |
                          v                           v
                    +------------+               +------------+
                    | Blockchain |               | Blockchain |
                    | Network 1  |               | Network N  |
                    +------------+               +------------+
```

## Core Components

### Multi-Chain Core (`multi_chain_core.py`)

The central orchestration layer that manages:
- Initialization of chain-specific workers
- Coordination between chains
- Global configuration handling
- Metrics aggregation

### Chain Worker (`chain_worker.py`)

Each blockchain has a dedicated worker responsible for:
- Blockchain connection management
- Transaction handling for that chain
- Mempool monitoring
- Opportunity detection

### Safety Net (`safety_net.py`)

Provides risk management and guardrails:
- Gas price monitoring and optimization
- Transaction profitability checks
- Slippage protection
- Network congestion awareness

### Transaction Core (`transaction_core.py`)

Handles all transaction-related operations:
- Transaction building
- Signing and broadcasting
- Simulation and estimation
- Flashloan execution
- Bundle creation

### Strategy Net (`strategy_net.py`)

Manages and executes trading strategies:
- Strategy selection based on reinforcement learning
- Strategy performance tracking
- Adaptive strategy weights
- Dynamic strategy parameters

### Market Monitor (`market_monitor.py`)

Analyzes market conditions:
- Price prediction with machine learning
- Volatility monitoring
- Liquidity assessment
- Market trend analysis

### API Configuration (`api_config.py`)

Manages external API integrations:
- Price data aggregation
- Token metadata
- External service integration
- Rate limiting

### Configuration Management (`configuration.py`, `configuration_multi_chain.py`)

Handles system configuration:
- Environment-specific settings
- Chain-specific parameters
- Secret management via Vault integration
- Configuration validation

## Data Flow

1. **Initialization Flow**:
   - Load configuration from YAML and environment variables
   - Initialize Vault connection for secrets
   - Create chain workers for each configured chain
   - Connect to blockchain nodes
   - Initialize components (API, market monitor, etc.)

2. **Transaction Flow**:
   - Mempool transaction detected by `txpool_monitor`
   - Transaction analyzed for profit opportunity
   - Strategy selected by `strategy_net`
   - Transaction built by `transaction_core`
   - Safety checks performed by `safety_net`
   - Transaction signed and broadcast
   - Results tracked and metrics updated

3. **Monitoring Flow**:
   - Metrics collected from all components
   - Pushed to Prometheus
   - Visualized in Grafana dashboards
   - Alerts generated based on thresholds

## Security Architecture

Security is implemented at multiple layers:

1. **Secret Management**:
   - HashiCorp Vault for private keys and API tokens
   - Strict file permissions
   - Environment isolation

2. **Network Security**:
   - Rate limiting
   - Connection pooling
   - Retry mechanisms with exponential backoff

3. **Transaction Security**:
   - Multiple validation steps
   - Simulation before execution
   - Gas price and limit safeguards

4. **System Security**:
   - Privilege separation
   - Container isolation
   - Minimal base images

## Design Principles

1. **Modularity**:
   Each component has a single responsibility and can be tested in isolation.

2. **Resilience**:
   The system is designed to handle failures at various levels with appropriate recovery mechanisms.

3. **Observability**:
   Comprehensive logging and metrics collection throughout the system.

4. **Scalability**:
   Adding support for additional chains or strategies requires minimal changes.

5. **Security**:
   Defense in depth with multiple layers of protection.

## Technology Stack

- **Language**: Python 3.12+
- **Blockchain Connectivity**: Web3.py
- **API Framework**: Flask
- **Secret Management**: HashiCorp Vault
- **Monitoring**: Prometheus, Grafana
- **Containerization**: Docker
- **Machine Learning**: Scikit-learn, Joblib
- **Data Storage**: JSON, CSV

## Deployment Architecture

ON1Builder supports both single-chain and multi-chain deployment models:

### Single-Chain Deployment

```
+------------------+
| Docker Compose   |
|                  |
| +-------------+  |
| | ON1Builder  |  |
| +-------------+  |
|                  |
| +-------------+  |
| | Vault       |  |
| +-------------+  |
|                  |
| +-------------+  |
| | Prometheus  |  |
| +-------------+  |
|                  |
| +-------------+  |
| | Grafana     |  |
| +-------------+  |
+------------------+
```

### Multi-Chain Deployment

```
+------------------+
| Docker Compose   |
|                  |
| +-------------+  |
| | ON1Builder  |  |
| | Multi-Chain |  |
| +-------------+  |
|                  |
| +-------------+  |
| | Vault       |  |
| +-------------+  |
|                  |
| +-------------+  |
| | Prometheus  |  |
| +-------------+  |
|                  |
| +-------------+  |
| | Grafana     |  |
| +-------------+  |
+------------------+
```

## Future Architecture Considerations

1. **Sharding**: As the number of chains grows, implement sharding to distribute load
2. **Event-Driven Architecture**: Move toward a more event-driven model using message queues
3. **Advanced ML Pipeline**: Separate ML training and inference for better scalability
4. **Distributed Execution**: Support for distributed strategy execution across multiple nodes
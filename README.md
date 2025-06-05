# ON1Builder

**Multi-chain blockchain transaction execution framework**

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg?logo=python)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/on1builder.svg?logo=pypi&logoColor=blue)](https://pypi.org/project/on1builder/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg?logo=python&logoColor=black)](https://github.com/psf/black)
[![Code Quality: flake8](https://img.shields.io/badge/code%20quality-flake8-black.svg?logo=python&logoColor=white)](https://flake8.pycqa.org/en/latest/)
[![Type Checker: mypy](https://img.shields.io/badge/type%20checker-mypy-black.svg?logo=python&logoColor=green)](https://mypy.readthedocs.io/)

A high-performance framework for building, signing, simulating, and dispatching blockchain transactions across multiple chains. Built with a focus on MEV strategies, safety, and operational reliability.

---

## Features

### Core Capabilities
- **Multi-chain Support**: Execute transactions across multiple blockchain networks simultaneously
- **High Performance**: Asynchronous architecture with concurrent transaction processing
- **Safety First**: Built-in safety guards, gas limit protection, and transaction validation
- **Market Intelligence**: Real-time mempool monitoring and market data analysis
- **MEV Strategies**: Framework for arbitrage, sandwich attacks, and liquidation strategies
- **Gas Optimization**: Dynamic gas price adjustment and optimization algorithms
- **Nonce Management**: Sophisticated nonce tracking across multiple chains and accounts
- **Monitoring**: Comprehensive metrics, logging, and alerting system

### Technical Excellence
- **Modern Python**: Built with Python 3.12+ and modern async patterns
- **Type Safety**: Full type hints with mypy validation
- **Configuration**: Flexible YAML-based configuration with Pydantic validation
- **Modular Design**: Clean architecture with dependency injection
- **Well Tested**: Comprehensive test suite with pytest
- **Production Ready**: Docker support, CI/CD ready, monitoring integration

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Usage](#cli-usage)
- [Architecture](#architecture)
- [Development](#development)
- [Docker](#docker)
- [Contributing](#contributing)
- [License](#license)

---

## Quick Start

### Quickstart with guidance (recommended)
```bash
# Clone the repository
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder
python -m venv venv  # Create a virtual environment
source venv/bin/activate  # Activate the virtual environment (Linux/Mac)
cd tools
python ignition.py
```


### Prerequisites
- Python 3.12 or higher
- Node.js 18+ (for contract compilation)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder
```
```bash
# Install with pip (recommended)
pip install -e .
```
```bash
# Or install with development dependencies
pip install -e ".[dev]"
```

### Basic Usage

```bash
# Check status and connectivity
on1builder status
```
```bash
# View configuration
on1builder config show
```
```bash
# Run with default configuration
on1builder run
```
```bash
# Run with custom configuration
on1builder run --config configs/my_config.yaml
```
```bash
# Enable verbose logging
on1builder --verbose run
```

---

## Installation

### From PyPI (Production)
```bash
pip install on1builder
```

### From Source (Development)
```bash
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder
pip install -e ".[dev]"
```

### With Poetry
```bash
poetry install
poetry install --with dev  # Include development dependencies
```

### System Requirements
- **Python**: 3.12+ (3.13 supported)
- **Memory**: 32GB+ RAM recommended
- **Storage**: 1TB+ free space
- **Network**: Stable internet connection for blockchain RPC calls

---

## Configuration

### Environment Setup

1. **Copy environment template:**
    ```bash
    cp .env.example .env
    ```

2. **Configure API keys:**
    ```bash
    # Required API keys
    export INFURA_PROJECT_ID="your_infura_project_id"
    export ALCHEMY_API_KEY="your_alchemy_api_key"
    export ETHERSCAN_API_KEY="your_etherscan_api_key"
    
    # Optional API keys for enhanced features
    export COINMARKETCAP_API_KEY="your_cmc_api_key"
    export COINGECKO_API_KEY="your_coingecko_api_key"
    export CRYPTOCOMPARE_API_KEY="your_cryptocompare_api_key"
    export CHAINLINK_API_KEY="your_chainlink_api_key"
    ```

3. **Set up private keys (securely):**
    ```bash
    # For mainnet (use hardware wallet or secure key management)
    export PRIVATE_KEY="0x..."
    
    # For testnet development
    export TESTNET_PRIVATE_KEY="0x..."
    ```

### Configuration Files

ON1Builder uses YAML configuration files with environment variable substitution:

#### Global Settings (`configs/common_settings.yaml`)
```yaml
global:
  log_level: "INFO"
  prometheus_port: 9090
  monitor_interval: 5
  tx_confirmation_blocks: 2
  max_retries: 3
  gas_price_multiplier: 1.1

api:
  infura_project_id: "${INFURA_PROJECT_ID}"
  alchemy_api_key: "${ALCHEMY_API_KEY}"
  rate_limits:
     infura: 100
     alchemy: 200
```

#### Chain-Specific Configuration (`configs/chains/config.yaml`)
```yaml
chain:
  chain_id: 1
  name: "ethereum"
  rpc_url: "http://127.0.1:8545" # Local RPC URL, preferably via Geth or Nethermind
  block_explorer_url: "https://etherscan.io"
  private_key: "${PRIVATE_KEY}"
  
  gas:
     max_gas_price: "50000000000"  # 50 gwei
     max_priority_fee: "2000000000"  # 2 gwei
     
  contracts:
     flashloan_factory: "0x..."
```

#### Multi-Chain Configuration (`configs/chains/config_multi_chain.yaml`)
```yaml
chains:
  ethereum:
     chain_id: 1
     rpc_url: "http://127.0.1:8545" # Local RPC URL, preferably via Geth or Nethermind
     block_explorer_url: "https://etherscan.io"

  polygon:
     chain_id: 137
     rpc_url: "http://127.0.1:8545" # Local RPC URL, preferably via Geth or Nethermind
     block_explorer_url: "https://polygonscan.com"

  arbitrum:
     chain_id: 42161
     rpc_url: "http://127.0.1:8545" # Local RPC URL, preferably via Geth or Nethermind
     block_explorer_url: "https://arbiscan.io"
```

---

## CLI Usage

### Commands Overview

| Command | Description | Example |
|---------|-------------|---------|
| `status` | Check system status and connectivity | `on1builder status` |
| `config` | Configuration management | `on1builder config show` |
| `run` | Execute strategies | `on1builder run --config my_config.yaml` |
| `version` | Show version information | `on1builder version` |

### Status Command
```bash
# Basic status check
on1builder status

# With verbose output
on1builder --verbose status

# Check specific configuration
on1builder status --config configs/chains/config.yaml
```

### Configuration Commands
```bash
# Show current configuration
on1builder config show

# Validate configuration file
on1builder config validate --config-path configs/my_config.yaml

# Show configuration help
on1builder config --help
```

### Run Commands
```bash
# Run with default configuration
on1builder run

# Run with specific configuration
on1builder run --config configs/chains/config.yaml

# Run in multi-chain mode
on1builder run --config configs/chains/config_multi_chain.yaml

# Run with custom settings
on1builder run --dry-run --max-workers 4
```

### Global Options
```bash
# Enable verbose logging
on1builder --verbose [command]

# Enable debug logging
on1builder --debug [command]

# Custom log file
on1builder --log-file /path/to/logfile.log [command]

# Show help
on1builder --help
on1builder [command] --help
```

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                           ON1Builder                            │
├─────────────────────────────────────────────────────────────────┤
│  CLI Layer                                                      │
│  ├─ status_cmd.py    ├─ config_cmd.py    ├─ run_cmd.py         │
├─────────────────────────────────────────────────────────────────┤
│  Core Orchestration                                             │
│  ├─ MainOrchestrator           ├─ MultiChainOrchestrator        │
│  ├─ ChainWorker               ├─ NonceManager                  │
│  └─ TransactionManager                                          │
├─────────────────────────────────────────────────────────────────┤
│  Execution Engines                                              │
│  ├─ StrategyExecutor          ├─ SafetyGuard                   │
├─────────────────────────────────────────────────────────────────┤
│  Monitoring & Data                                              │
│  ├─ MarketDataFeed           ├─ TxPoolScanner                  │
│  ├─ ExternalAPIs             ├─ NotificationService            │
├─────────────────────────────────────────────────────────────────┤
│  Infrastructure                                                 │
│  ├─ DatabaseInterface        ├─ LoggingConfig                  │
│  ├─ Container (DI)           ├─ CustomExceptions               │
└─────────────────────────────────────────────────────────────────┘
```

### Core Components

#### **Orchestration Layer**
- **MainOrchestrator**: Single-chain strategy execution coordinator
- **MultiChainOrchestrator**: Multi-chain strategy execution coordinator  
- **ChainWorker**: Individual blockchain worker with RPC management
- **NonceManager**: Sophisticated nonce tracking and management
- **TransactionManager**: Transaction lifecycle management

#### **Execution Engines**
- **StrategyExecutor**: MEV strategy implementation and execution
- **SafetyGuard**: Transaction safety validation and risk management

#### **Monitoring & Intelligence**
- **MarketDataFeed**: Real-time price and market data aggregation
- **TxPoolScanner**: Mempool monitoring and transaction analysis
- **ExternalAPIs**: Integration with external data providers

#### **Infrastructure**
- **DatabaseInterface**: Persistent storage with SQLAlchemy
- **LoggingConfig**: Structured logging with rich formatting
- **Container**: Dependency injection and service location
- **NotificationService**: Alert and notification management

### Data Flow

1. **Initialization**: Configuration loading, database setup, service registration
2. **Market Monitoring**: Continuous price feeds and mempool scanning
3. **Opportunity Detection**: Strategy analysis and MEV opportunity identification
4. **Safety Validation**: Transaction simulation and safety checks
5. **Execution**: Transaction building, signing, and broadcast
6. **Monitoring**: Transaction tracking and performance metrics

---

## Development

### Development Setup

```bash
# Clone and setup
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder

# Install development dependencies
pip install -e ".[dev]"

# Or with poetry
poetry install --with dev

# Run development setup script
./setup_dev.sh
```

### Code Quality Tools

```bash
# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/

# Security scanning
bandit -r src/

# Dependency vulnerability check
safety check
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_components.py

# Run with verbose output
pytest -v
```

### Project Structure

```
ON1Builder/
├── src/on1builder/           # Main package
│   ├── cli/                  # Command-line interface
│   ├── config/              # Configuration management
│   ├── core/                # Core orchestration
│   ├── engines/             # Execution engines
│   ├── integrations/        # External integrations
│   ├── monitoring/          # Market & mempool monitoring
│   ├── persistence/         # Database layer
│   └── utils/               # Utilities and helpers
├── configs/                 # Configuration files
│   ├── chains/             # Chain-specific configs
│   └── common_settings.yaml # Global settings
├── resources/              # Static resources
│   ├── abi/               # Contract ABIs
│   ├── contracts/         # Solidity contracts
│   └── tokens/            # Token metadata
├── tests/                 # Test suite
├── tools/                 # Development tools
└── docs/                  # Documentation
```

### Adding New Features

1. **Create Feature Branch**
    ```bash
    git checkout -b feature/new-strategy
    ```

2. **Implement Feature**
    - Add code to appropriate module
    - Include comprehensive type hints
    - Add docstrings and comments
    - Follow existing patterns

3. **Add Tests**
    ```bash
    # Create test file
    touch tests/test_new_feature.py
    
    # Write comprehensive tests
    pytest tests/test_new_feature.py
    ```

4. **Quality Checks**
    ```bash
    # Format and check
    black src/ tests/
    mypy src/
    flake8 src/ tests/
    pytest
    ```

5. **Submit Pull Request**

### Architecture Principles

- **Separation of Concerns**: Each module has a single responsibility
- **Dependency Injection**: Use container for service management
- **Async First**: All I/O operations are asynchronous
- **Type Safety**: Complete type annotations with mypy validation
- **Error Handling**: Comprehensive exception handling with custom exceptions
- **Logging**: Structured logging throughout the application
- **Configuration**: External configuration with validation
- **Testing**: Unit tests for all critical components

---

## Docker

### Quick Start with Docker

```bash
# Build image
docker build -t on1builder .

# Run with default configuration
docker run -d --name on1builder-app on1builder

# Run with custom configuration
docker run -d --name on1builder-app \
  -v $(pwd)/configs:/app/configs \
  -e RPC_URL="http://127.0.0.1:8545" \
  on1builder

# Run with docker-compose
docker-compose up -d
```

### Docker Compose

```yaml
version: '3.8'
services:
  on1builder:
     build: .
     environment:
        - INFURA_PROJECT_ID=${INFURA_PROJECT_ID}
        - ALCHEMY_API_KEY=${ALCHEMY_API_KEY}
        - PRIVATE_KEY=${PRIVATE_KEY}
     volumes:
        - ./configs:/app/configs
        - ./logs:/app/logs
     restart: unless-stopped
```

### Production Deployment

```bash
# Production build
docker build -t on1builder:latest .

# Run with production settings
docker run -d \
  --name on1builder-prod \
  --restart unless-stopped \
  -v /opt/on1builder/configs:/app/configs \
  -v /opt/on1builder/logs:/app/logs \
  -e ENVIRONMENT=production \
  on1builder:latest
```

---

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Quick Contribution Steps

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes**: Follow the development guidelines
4. **Add tests**: Ensure your changes are tested
5. **Run quality checks**: `black`, `mypy`, `flake8`, `pytest`
6. **Commit changes**: `git commit -m 'Add amazing feature'`
7. **Push to branch**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

### Development Guidelines

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use [Black](https://black.readthedocs.io/) for code formatting
- Include type hints for all functions and methods
- Write comprehensive docstrings
- Add tests for new functionality
- Update documentation as needed

---

## Performance & Monitoring

### Metrics Collection

ON1Builder includes built-in metrics collection:

- **Transaction Metrics**: Success rates, gas usage, execution times
- **Market Metrics**: Price feeds, arbitrage opportunities, slippage
- **System Metrics**: Memory usage, CPU utilization, network latency
- **Strategy Metrics**: Profit/loss, win rates, risk metrics

### Prometheus Integration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'on1builder'
     static_configs:
        - targets: ['localhost:9090']
```

### Grafana Dashboards

Pre-built dashboards available for:
- Transaction volume and success rates
- Gas price optimization effectiveness
- MEV opportunity detection
- System performance metrics

---

## Security

### Best Practices

1. **Private Key Management**
    - Use hardware wallets for mainnet
    - Store keys in secure environment variables
    - Never commit keys to version control
    - Rotate keys regularly

2. **API Security**
    - Use API key rotation
    - Implement rate limiting
    - Monitor API usage
    - Use HTTPS for all external calls

3. **Transaction Safety**
    - Enable safety guards
    - Set reasonable gas limits
    - Implement slippage protection
    - Use transaction simulation

### Security Features

- **Safety Guards**: Prevent dangerous transactions
- **Gas Limit Protection**: Automatic gas limit enforcement
- **Slippage Protection**: Maximum slippage enforcement
- **Nonce Management**: Prevent transaction conflicts
- **Balance Monitoring**: Insufficient balance detection

---

## Strategies & MEV

### Supported Strategy Types

1. **Arbitrage**
    - Cross-exchange arbitrage
    - Cross-chain arbitrage
    - Flash loan arbitrage

2. **Liquidation**
    - Compound liquidations
    - Aave liquidations
    - Custom protocol liquidations

3. **Sandwich Attacks**
    - Front-running detection
    - Back-running optimization
    - MEV protection bypassing

4. **Market Making**
    - Automated market making
    - Dynamic pricing
    - Inventory management

### Example Strategy Implementation

```python
from on1builder.engines.strategy_executor import StrategyExecutor
from on1builder.core.chain_worker import ChainWorker

class ArbitrageStrategy:
     def __init__(self, chain_worker: ChainWorker):
          self.chain_worker = chain_worker
          
     async def execute(self, opportunity):
          # Strategy implementation
          transaction = await self.build_arbitrage_tx(opportunity)
          result = await self.chain_worker.execute_transaction(transaction)
          return result
```

---

## Multi-Chain Support

### Supported Networks

| Network | Chain ID | Status | Features |
|---------|----------|---------|----------|
| Ethereum | 1 | ✅ Full | All features |
| Polygon | 137 | ✅ Full | All features |
| Arbitrum | 42161 | ✅ Full | All features |
| Optimism | 10 | Planned | Coming soon |
| BSC | 56 | Planned | Coming soon |

### Adding New Chains

1. **Add chain configuration**:
    ```yaml
    # configs/chains/new_chain.yaml
    chain:
      chain_id: 250
      name: "fantom"
      rpc_url: "http://127.0.0.1:8545" # Local RPC URL, preferably via Geth or Nethermind
    ```

2. **Update token mappings**:
    ```bash
    mkdir resources/tokens/chainid-250
    # Add token metadata files
    ```

3. **Test connectivity**:
    ```bash
    on1builder status --config configs/chains/new_chain.yaml
    ```

---

## API Reference

### Core Classes

#### ChainWorker
```python
class ChainWorker:
     async def execute_transaction(self, tx: dict) -> dict
     async def get_gas_price(self) -> int
     async def simulate_transaction(self, tx: dict) -> dict
```

#### StrategyExecutor
```python
class StrategyExecutor:
     async def execute_strategy(self, strategy_config: dict) -> dict
     async def analyze_market_conditions(self) -> dict
     async def deploy_flashloan_contract(self) -> str
```

#### NonceManager
```python
class NonceManager:
     async def get_next_nonce(self, address: str) -> int
     async def reserve_nonce(self, address: str) -> int
     async def release_nonce(self, address: str, nonce: int) -> None
```

---

## Troubleshooting

### Common Issues

#### Connection Issues
```bash
# Check RPC connectivity
on1builder status

# Test specific RPC endpoint
curl -X POST -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  http://127.0.0.1:8545
```

#### Configuration Issues
```bash
# Validate configuration
on1builder config validate --config-path configs/my_config.yaml

# Show current configuration
on1builder config show
```

#### Transaction Issues
```bash
# Enable debug logging
on1builder --debug run

# Check gas price
on1builder status --verbose
```

### Log Analysis

```bash
# View recent logs
tail -f logs/on1builder.log

# Search for errors
grep -i error logs/on1builder.log

# Monitor specific operations
grep -i "transaction" logs/on1builder.log
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 John0n1

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## Acknowledgments

- **Ethereum Foundation** - For the robust blockchain infrastructure
- **Web3.py Team** - For the excellent Python Web3 library
- **Pydantic Team** - For the powerful data validation framework
- **FastAPI/Typer Teams** - For the excellent CLI framework
- **Async Community** - For advancing Python's async capabilities

---

## Support & Community

- **Issues**: [GitHub Issues](https://github.com/john0n1/ON1Builder/issues)
- **Discussions**: [GitHub Discussions](https://github.com/john0n1/ON1Builder/discussions)
- **Email**: on1@on1.no
- **Documentation**: [Full Documentation](https://on1builder.readthedocs.io/)

---

<div align="center">

**Built with ❤️ by the ON1Builder team**

[⭐ Star us on GitHub](https://github.com/john0n1/ON1Builder) | [🐛 Report Bug](https://github.com/john0n1/ON1Builder/issues) | [✨ Request Feature](https://github.com/john0n1/ON1Builder/issues)

</div>


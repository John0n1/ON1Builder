# ON1Builder

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Type Checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

**A high-performance, multi-chain blockchain transaction execution framework with a focus on MEV strategies, mempool monitoring, and automated trading.**

##  Overview

ON1Builder is a sophisticated framework designed for professional blockchain developers and traders who need reliable, high-performance tools for:

- **Multi-chain transaction management** across Ethereum and compatible networks
- **Real-time mempool monitoring** and transaction pool analysis  
- **MEV opportunity detection** and automated strategy execution
- **Market data integration** from multiple sources (Coingecko, CoinMarketCap, etc.)
- **Advanced safety mechanisms** with circuit breakers and risk management
- **Gas optimization** and intelligent transaction timing
- **Performance monitoring** with comprehensive metrics and health checks

### Key Features

**Multi-Chain Support** - Execute strategies across multiple blockchain networks simultaneously  
**Async Architecture** - Built with Python's asyncio for maximum performance  
**Real-time Monitoring** - Track mempool activity, market data, and system health  
**Safety First** - Comprehensive safety guards and risk management systems  
**Extensible Design** - Modular architecture for easy customization and extension  
**Professional Tooling** - Type hints, comprehensive testing, and CI/CD ready  
**Interactive Console** - User-friendly TUI for configuration and monitoring  

## Table of Contents

- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [CLI Usage](#-cli-usage)
- [Interactive Console](#-interactive-console)
- [Architecture](#-architecture)
- [Development](#-development)
- [Testing](#-testing)
- [API Documentation](#-api-documentation)
- [Contributing](#-contributing)
- [License](#-license)

## 🛠 Installation

### Prerequisites

- **Python 3.12+** (3.13 supported)
- **pip** or **uv** package manager
- **Git** for development installation

### Production Installation

```bash
# Install from PyPI
pip install on1builder

# Or install from source
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder
pip install .
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e .[dev]

# Or use the setup script
./scripts/setup_dev_environment.sh
```

### Docker Installation

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build manually
docker build -t on1builder .
docker run -it on1builder
```

## Quick Start

### 1. Basic Setup

First, set up your environment variables:

```bash
# Copy the example environment file
cp .env.example .env

# Edit with your API keys and configuration
nano .env
```

Required environment variables:
```bash
# Blockchain RPC endpoints
RPC_URL=http://127.0.1:8545  # Local node or Infura/Alchemy endpoint
INFURA_PROJECT_ID=your_infura_project_id
ALCHEMY_API_KEY=your_alchemy_api_key

# API keys for market data
COINMARKETCAP_API_KEY=your_cmc_api_key
COINGECKO_API_KEY=your_coingecko_api_key

# Wallet configuration (use test keys for development)
WALLET_KEY=0x1234...  # Your private key
WALLET_ADDRESS=0x742d35Cc...  # Corresponding address
```

### 2. Configuration

Create or customize your chain configuration:

```bash
# View available configurations
ls configs/chains/

# Copy and customize a configuration
cp configs/chains/ethereum_mainnet.yaml configs/chains/my_config.yaml
```

### 3. Run the Application

```bash
# Using the CLI
on1builder run --config configs/chains/ethereum_mainnet.yaml

# Or using Python module
python -m on1builder run --config configs/chains/ethereum_mainnet.yaml

# Check version and help
on1builder --help
on1builder version
```

### 4. Interactive Console

For a user-friendly experience, use the interactive console:

```bash
# Launch the interactive console
python tools/ignition.py

# Navigate through the menus to:
# - Configure settings
# - Start/stop services  
# - Monitor performance
# - View logs and metrics
```

## ⚙️ Configuration

ON1Builder uses a hierarchical configuration system with YAML files and environment variables.

### Configuration Structure

```
configs/
├── common_settings.yaml      # Global defaults
└── chains/
    ├── ethereum_mainnet.yaml # Ethereum mainnet config
    ├── polygon_mainnet.yaml  # Polygon config
    └── custom_chain.yaml     # Your custom configuration
```

### Example Chain Configuration

```yaml
# Chain identification
CHAIN_ID: 1
CHAIN_NAME: "ethereum_mainnet"

# RPC endpoints
HTTP_ENDPOINT: "https://mainnet.infura.io/v3/${INFURA_PROJECT_ID}"
WEBSOCKET_ENDPOINT: "wss://mainnet.infura.io/v3/${INFURA_PROJECT_ID}"

# Wallet configuration
WALLET_KEY: "${WALLET_KEY}"
WALLET_ADDRESS: "${WALLET_ADDRESS}"

# Monitoring settings
monitored_tokens:
  - "0xA0b86a33E6441Cc8e4F9553c3d37EAD0F5f3C5e8"  # USDC
  - "0xdAC17F958D2ee523a2206206994597C13D831ec7"  # USDT

# Strategy configuration
strategies:
  arbitrage:
    enabled: true
    min_profit_wei: 1000000000000000  # 0.001 ETH
    max_slippage: 0.01  # 1%
```

### Environment Variables

Key environment variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `INFURA_PROJECT_ID` | Infura project ID for RPC access | Yes |
| `ALCHEMY_API_KEY` | Alchemy API key (alternative to Infura) | No |
| `WALLET_KEY` | Private key for transaction signing | Yes |
| `WALLET_ADDRESS` | Wallet address (for validation) | No |
| `COINMARKETCAP_API_KEY` | CoinMarketCap API key | No |
| `COINGECKO_API_KEY` | CoinGecko API key | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No |

## 💻 CLI Usage

ON1Builder provides a comprehensive command-line interface built with Typer:

### Main Commands

```bash
# Show version information
on1builder version

# Configuration management
on1builder config validate --config path/to/config.yaml
on1builder config show --config path/to/config.yaml

# Run the main application
on1builder run --config path/to/config.yaml [OPTIONS]

# Check application status
on1builder status
```

### CLI Options

```bash
# Global options
--verbose, -v          Enable verbose logging
--debug               Enable debug logging  
--log-file PATH       Specify log file path
--help, -h            Show help message

# Run command options
--config PATH         Configuration file path
--dry-run            Simulate without executing transactions
--chains TEXT        Comma-separated list of chains to run
```

### Examples

```bash
# Run with verbose logging
on1builder -v run --config configs/chains/ethereum_mainnet.yaml

# Dry run to test configuration
on1builder run --config configs/chains/ethereum_mainnet.yaml --dry-run

# Run specific chains only
on1builder run --config configs/common_settings.yaml --chains ethereum,polygon
```

## 🎮 Interactive Console

The interactive console (`tools/ignition.py`) provides a user-friendly interface for managing ON1Builder:

### Features

- **Configuration Management** - View, edit, and validate configurations
- **Real-time Monitoring** - Live metrics, logs, and system health
- **Service Control** - Start, stop, and restart services
- **Performance Metrics** - Transaction stats, gas usage, profitability
- **Quick Actions** - Common tasks with keyboard shortcuts

### Navigation

```bash
# Launch interactive console
python tools/ignition.py

# Menu navigation:
# ↑/↓ arrows - Navigate options
# Enter - Select option
# q - Quit current menu
# Ctrl+C - Emergency exit
```

### Console Sections

1. **Launch ON1Builder** - Start the main application
2. **Configuration** - Manage settings and chain configs
3. **Monitoring** - View metrics and system status
4. **Tools** - Utilities and diagnostic tools
5. **Help** - Documentation and support

## 🏗 Architecture

ON1Builder follows a modular, event-driven architecture designed for scalability and maintainability.

### Core Components

```
src/on1builder/
├── cli/                 # Command-line interface
├── config/             # Configuration management
├── core/               # Core business logic
│   ├── main_orchestrator.py       # Main application controller
│   ├── multi_chain_orchestrator.py # Multi-chain coordination
│   ├── chain_worker.py            # Single-chain worker
│   ├── transaction_manager.py     # Transaction handling
│   └── nonce_manager.py          # Nonce management
├── engines/            # Strategy execution engines
│   ├── safety_guard.py           # Risk management
│   └── strategy_executor.py      # Strategy implementation
├── monitoring/         # Monitoring and data feeds
│   ├── market_data_feed.py       # Market data integration
│   └── txpool_scanner.py         # Mempool monitoring
├── integrations/       # External API integrations
├── persistence/        # Database and storage
└── utils/             # Utilities and helpers
```

### Key Design Patterns

- **Dependency Injection** - Clean separation of concerns
- **Observer Pattern** - Event-driven component communication
- **Circuit Breaker** - Fault tolerance and system protection
- **Factory Pattern** - Dynamic component creation
- **Async/Await** - Non-blocking I/O operations

## 🔧 Development

### Development Environment

```bash
# Install development dependencies
pip install -e .[dev]

# Install pre-commit hooks
pre-commit install

# Run development checks
make lint      # Code formatting and linting
make test      # Run test suite
make coverage  # Generate coverage reports
make docs     # Build documentation
```

### Code Quality

ON1Builder maintains high code quality standards:

- **Type Hints** - Full mypy type checking
- **Code Formatting** - Black and isort
- **Linting** - Flake8 with custom rules
- **Security** - Bandit security analysis
- **Testing** - Pytest with async support
- **Coverage** - 80%+ test coverage requirement

### Development Workflow

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/new-feature
   ```

2. **Make Changes**
   - Follow PEP 8 style guidelines
   - Add type hints to all functions
   - Write tests for new functionality
   - Update documentation

3. **Run Quality Checks**
   ```bash
   make lint test coverage
   ```

4. **Submit Pull Request**
   - Ensure all checks pass
   - Include clear description
   - Add relevant tests

### Adding New Strategies

```python
# Example: Custom arbitrage strategy
from on1builder.engines.strategy_executor import BaseStrategy

class MyArbitrageStrategy(BaseStrategy):
    async def analyze_opportunity(self, market_data):
        # Your analysis logic
        pass
    
    async def execute_trade(self, opportunity):
        # Your execution logic
        pass
```

## Testing

ON1Builder includes comprehensive testing with pytest and async support.

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=on1builder

# Run specific test categories
pytest -m "not slow"        # Skip slow tests
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only

# Run tests with verbose output
pytest -v
```

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── unit/                 # Unit tests
│   ├── test_chain_worker.py
│   ├── test_transaction_manager.py
│   └── ...
├── integration/          # Integration tests
│   ├── test_full_workflow.py
│   └── ...
└── fixtures/            # Test data and mocks
```

### Writing Tests

```python
import pytest
from on1builder.core.chain_worker import ChainWorker

@pytest.mark.asyncio
async def test_chain_worker_initialization():
    # Test async components
    worker = ChainWorker(config)
    await worker.initialize()
    assert worker.initialized
    
def test_configuration_validation():
    # Test synchronous components
    config = load_config("test_config.yaml")
    assert config.is_valid()
```

## API Documentation

### Core Classes

#### ChainWorker
Manages single-chain operations including transaction execution, monitoring, and health checks.

```python
from on1builder.core.chain_worker import ChainWorker

# Initialize chain worker
worker = ChainWorker(
    chain_cfg=chain_config,
    global_cfg=global_config
)

# Start monitoring and execution
await worker.initialize()
await worker.start()
```

#### TransactionManager  
Handles transaction building, signing, simulation, and submission.

```python
from on1builder.core.transaction_manager import TransactionManager

# Create transaction manager
tx_manager = TransactionManager(
    web3=web3_instance,
    account=account,
    config=config
)

# Build and send transaction
tx_hash = await tx_manager.send_transaction(
    to_address="0x...",
    value=Web3.to_wei(0.1, "ether"),
    data="0x..."
)
```

#### SafetyGuard
Provides risk management and safety checks for all transactions.

```python
from on1builder.engines.safety_guard import SafetyGuard

# Initialize safety guard
safety = SafetyGuard(
    web3=web3_instance,
    config=config,
    account=account
)

# Check transaction safety
is_safe = await safety.check_transaction_safety(transaction)
```

### Configuration API

```python
from on1builder.config.settings import load_global_settings

# Load configuration
config = load_global_settings("configs/common_settings.yaml")

# Access settings
api_keys = config.api
monitoring = config.monitoring
chains = config.chains
```

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Quick Contribution Steps

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** following our coding standards
4. **Add tests** for new functionality
5. **Run quality checks**: `make lint test`
6. **Commit changes**: `git commit -m 'Add amazing feature'`
7. **Push to branch**: `git push origin feature/amazing-feature`
8. **Submit a Pull Request**

### Development Guidelines

- Follow PEP 8 style guidelines
- Add comprehensive type hints
- Write clear docstrings
- Include unit tests for new features
- Update documentation as needed
- Ensure backward compatibility

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Links

- **Homepage**: https://github.com/john0n1/ON1Builder
- **Documentation**: https://github.com/john0n1/ON1Builder#readme
- **Bug Reports**: https://github.com/john0n1/ON1Builder/issues
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)

## Disclaimer

**Important Security Notice**: ON1Builder is designed for educational and research purposes. When using this software:

- **Never use mainnet private keys in development**
- **Start with testnets** (Goerli, Sepolia, Mumbai)
- **Use small amounts** for initial testing
- **Understand the risks** of MEV and automated trading
- **Review all code** before production use

The authors are not responsible for any financial losses incurred through the use of this software.

---

**Built with ❤️ by the ON1Builder Team**

*For questions, support, or collaboration opportunities, please open an issue or reach out to john@on1.no*

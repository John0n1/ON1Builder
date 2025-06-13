# ON1Builder MEV Bot

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?logo=github)](https://opensource.org/licenses/MIT)
[![PyPI Version](https://img.shields.io/pypi/v/on1builder?logo=pypi&logoColor=white)](https://pypi.org/project/on1builder/)

[![Warning](https://img.shields.io/badge/⚠️-Development%20Build-red.svg)](https://github.com/john0n1/ON1Builder)



A sophisticated, Maximum Extractable Value (MEV) bot designed for multi-chain arbitrage, front-running, advanced DeFi strategies - utilizing Flashloans via Aave V3. Built with enterprise-grade architecture, comprehensive safety mechanisms, and real-time market analysis.

##  Features

### Core Capabilities
- **Multi-Chain Support**: Simultaneous operations across Ethereum, Polygon, Arbitrum, and other EVM-compatible chains
- **Advanced MEV Strategies**: Arbitrage, front-running, back-running, and sandwich attacks (configurable)
- **Flash Loan Integration**: Automated flash loans from Aave V3 for capital-efficient strategies
- **Real-Time Market Analysis**: Live price feeds, liquidity monitoring, and market sentiment analysis
- **Machine Learning Optimization**: Adaptive strategy weights based on historical performance

### Safety & Risk Management
- **Multi-Layer Safety Guards**: Transaction validation, slippage protection, and emergency stops
- **Dynamic Risk Assessment**: Real-time portfolio risk calculation and position sizing
- **Gas Optimization**: Intelligent gas pricing with EIP-1559 support and cost minimization
- **Balance Management**: Automated balance monitoring with emergency thresholds

### Monitoring & Analytics
- **Comprehensive Logging**: Structured logging with configurable verbosity levels
- **Performance Metrics**: Real-time profit tracking, success rates, and ROI analysis
- **Multi-Channel Notifications**: Slack, Telegram, Discord, and email alerts
- **Database Integration**: SQLite/PostgreSQL support for transaction and profit history

##  Architecture

```
├── src/on1builder/
│   ├── core/                 # Core orchestration and chain management
│   │   ├── main_orchestrator.py      # Main application controller
│   │   ├── multi_chain_orchestrator.py # Cross-chain coordination
│   │   ├── chain_worker.py           # Per-chain operation handler
│   │   ├── transaction_manager.py    # Transaction execution
│   │   └── balance_manager.py        # Portfolio management
│   ├── engines/              # Strategy execution engines
│   │   ├── strategy_executor.py      # MEV strategy implementation
│   │   └── safety_guard.py          # Risk management
│   ├── monitoring/           # Market data and transaction monitoring
│   │   ├── market_data_feed.py      # Price feeds and market analysis
│   │   └── txpool_scanner.py        # Mempool monitoring
│   ├── integrations/         # External service integrations
│   │   ├── external_apis.py         # API managers (CoinGecko, etc.)
│   │   └── abi_registry.py          # Smart contract interfaces
│   ├── utils/               # Utilities and helpers
│   │   ├── gas_optimizer.py        # Gas price optimization
│   │   ├── profit_calculator.py    # P&L calculation
│   │   └── notification_service.py  # Alert system
│   ├── config/              # Configuration management
│   └── persistence/         # Data storage layer
```

##  Prerequisites

- **Synced Geth/Nethermind Node**: For blockchain RPC access
- **Python 3.11+**
- **Node.js 16+** (for some utilities)
- **Git**
- **Virtual Environment** (recommended)

### Required API Keys
- **CoinGecko/CoinMarketCap**: For price data (free API tier available)
- **CryptoCompare/Binance**: For additional market data (free API tier available)
- **Etherscan**: For contract and ABI verification (optional)

##  Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/ON1Builder.git
cd ON1Builder
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  
# On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration Setup
```bash
# Copy example configuration
cp .env.example .env

# Edit configuration file
nano .env # Or use your favorite text editor
```

## Configuration

### Environment Variables

Create a `.env` file in the project root with the following configuration:

```bash
# Wallet Configuration
WALLET_KEY=0xYourPrivateKeyHere
WALLET_ADDRESS=0xYourWalletAddressHere
PROFIT_RECEIVER_ADDRESS=0xOptionalSeparateProfitAddress

# Blockchain Configuration
CHAINS=1,137,42161  # Ethereum, Polygon, Arbitrum
POA_CHAINS=137      # Proof of Authority chains

# RPC Endpoints (replace with your node endpoint(s)
RPC_URL_1=127.0.0.1:8545
RPC_URL_137=127.0.0.1:8546
RPC_URL_42161=127.0.0.1:8547

# WebSocket Endpoints (optional, for real-time data)
WEBSOCKET_URL_1=wss://127.0.0.1:8545

# Strategy Configuration (Adjust as needed)
MIN_PROFIT_ETH=0.005
MIN_PROFIT_PERCENTAGE=0.1
SLIPPAGE_TOLERANCE=0.5
MAX_GAS_PRICE_GWEI=200

# Flash Loan Settings (AAVE V3, optional)
FLASHLOAN_ENABLED=true
FLASHLOAN_MAX_AMOUNT_ETH=1000.0
FLASHLOAN_BUFFER_PERCENTAGE=0.1

# Risk Management
MAX_POSITION_SIZE_PERCENT=20.0
DAILY_LOSS_LIMIT_PERCENT=5.0
EMERGENCY_BALANCE_THRESHOLD=0.01

# API Keys (optional)
ETHERSCAN_API_KEY=your_etherscan_api_key
COINGECKO_API_KEY=your_coingecko_api_key
COINMARKETCAP_API_KEY=your_coinmarketcap_api_key
CRYPTOCOMPARE_API_KEY=your_cryptocompare_api_key
BINANCE_API_KEY=your_binance_api_key # Optional for additional market data
INFURA_PROJECT_ID=your_infura_project_id

# Notifications (optional)
NOTIFICATION_CHANNELS=slack,telegram
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Database
DATABASE_URL=sqlite+aiosqlite:///on1builder_data.db
```

### Contract Addresses

Configure DEX router addresses in your `.env`:

```bash
# Uniswap V2 Router addresses per chain
UNISWAP_V2_ROUTER_ADDRESSES={"1":"0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D","137":"0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"}

# Sushiswap Router addresses
SUSHISWAP_ROUTER_ADDRESSES={"1":"0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F","137":"0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"}

# Aave V3 Pool addresses for flash loans
AAVE_V3_POOL_ADDRESSES={"1":"0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2","137":"0x794a61358D6845594F94dc1DB02A252b5b4814aD"}
```

##  Usage

### Basic Usage

```bash
# Start the MEV bot
python -m on1builder

# Or using the main module
python src/on1builder/__main__.py
```

### Advanced Usage

```bash
# Run with debug logging
DEBUG=true python -m on1builder

# Run specific strategies only
MEV_STRATEGIES_ENABLED=true FRONT_RUNNING_ENABLED=false python -m on1builder

# Run in dry-run mode (no actual transactions)
DRY_RUN=true python -m on1builder
```

### CLI Commands

```bash
# Check configuration
python -m on1builder config check

# Monitor current status
python -m on1builder status

# View recent performance
python -m on1builder status --detailed
```

##  Monitoring & Analytics

### Real-Time Monitoring
- **Dashboard**: Web-based monitoring interface (optional)
- **Logs**: Structured JSON logs for external analysis
- **Metrics**: Prometheus-compatible metrics endpoint

### Key Metrics Tracked
- **Profit/Loss**: Real-time P&L calculation in ETH and USD
- **Success Rate**: Strategy success rates and execution times
- **Gas Efficiency**: Gas costs vs. profit ratios
- **Market Opportunities**: Detected vs. executed opportunities

### Notification Alerts
- **Trade Execution**: Successful arbitrage and MEV captures
- **Risk Events**: High slippage, failed transactions, low balances
- **System Health**: Connection issues, configuration errors

##  Safety Features

### Built-in Protections
- **Slippage Protection**: Configurable maximum slippage tolerance
- **Gas Limit Controls**: Maximum gas price and limit enforcement
- **Balance Monitoring**: Automatic low balance detection and alerts
- **Emergency Stops**: Immediate halt mechanisms for unusual conditions

### Risk Management
- **Position Sizing**: Automatic position sizing based on portfolio balance
- **Daily Loss Limits**: Automatic trading halt after significant losses
- **Transaction Validation**: Multi-layer validation before execution
- **Market Condition Checks**: Halt trading during extreme volatility

##  Development

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run with coverage
python -m pytest tests/ --cov=on1builder

# Run specific test categories
python -m pytest tests/test_core/ -v
```

### Code Quality
```bash
# Format code
black src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/
```

### Development Setup
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run pre-commit checks
pre-commit run --all-files
```

##  Performance Optimization

### Gas Optimization
- **Dynamic Gas Pricing**: Real-time gas price optimization
- **EIP-1559 Support**: Priority fee calculation for faster inclusion
- **Gas Limit Estimation**: Accurate gas estimation for complex transactions

### Execution Speed
- **Async Architecture**: Non-blocking operations for maximum throughput
- **Connection Pooling**: Persistent RPC connections for reduced latency
- **Parallel Processing**: Concurrent opportunity scanning across chains

### Capital Efficiency
- **Flash Loan Integration**: Zero-capital arbitrage opportunities
- **Just-In-Time Execution**: Minimal capital lock-up periods
- **Dynamic Rebalancing**: Automatic capital allocation across chains

##  Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Workflow
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`python -m pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Code Standards
- Follow PEP 8 style guidelines
- Add type hints for all functions
- Include docstrings for public methods
- Maintain test coverage above 80%

## Disclaimer

**Important Legal and Financial Disclaimers:**

- **High Risk**: MEV bot trading involves substantial financial risk. You may lose some or all of your capital.
- **No Financial Advice**: This software is provided for educational and research purposes only. It does not constitute financial advice.
- **Regulatory Compliance**: Ensure compliance with local laws and regulations in your jurisdiction.
- **Use at Your Own Risk**: The developers are not responsible for any financial losses incurred through the use of this software.
- **Testnet First**: Always test thoroughly on testnets before deploying to mainnet.

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

### Documentation
- **Wiki**: Comprehensive guides and tutorials
- **API Reference**: Detailed API documentation
- **Examples**: Sample configurations and use cases

### Community
- **Discord**: [Join our Discord server](https://discord.gg/yourdiscord)
- **Telegram**: [Official Telegram group](https://t.me/yourgroup)
- **GitHub Issues**: Bug reports and feature requests

### Professional Support
For enterprise deployments and custom development:
- **Email**: support@on1builder.com
- **Consulting**: Available for custom strategy development

## Acknowledgments

- **Web3.py**: For blockchain interaction capabilities
- **Aave Protocol**: For flash loan infrastructure
- **Uniswap**: For decentralized exchange protocols
- **OpenZeppelin**: For smart contract security standards
- **The Ethereum Community**: For continuous innovation in DeFi

## Disclaimer
![Warning](https://img.shields.io/badge/⚠️-red.svg)

**IN NO EVENT SHALL THE
AUTHORS, CONTRIBUTORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.**

*You should always do your own research and understand the risks involved in trading and using MEV bots. This software is provided "as is" without any warranties or guarantees of any kind.*

---

**Built with ❤️ by the ON1Builder team**


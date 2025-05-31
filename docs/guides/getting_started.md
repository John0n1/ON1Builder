# Getting Started with ON1Builder

This guide will help you get started with ON1Builder, covering the key concepts, installation, basic configuration, and your first run.

## What is ON1Builder?

ON1Builder is a multi-chain blockchain transaction framework designed for high-performance, security, and reliability. It specializes in:

- Building, signing, and dispatching transactions across multiple blockchains
- Detecting and capitalizing on MEV (Maximal Extractable Value) opportunities
- Simulating transactions before execution to estimate costs and profitability
- Providing robust monitoring and alerting mechanisms

## Key Concepts

Before diving into the installation, let's understand some key concepts:

### Multi-Chain Architecture

ON1Builder can run across multiple blockchains simultaneously, with each chain having a dedicated worker managing blockchain-specific operations.

### Chain Workers

Chain Workers are responsible for:
- Maintaining connection to the blockchain
- Monitoring the mempool for transactions
- Executing strategies on specific chains

### Safety Net

The Safety Net component provides protective mechanisms:
- Ensures transactions are profitable
- Manages gas prices and optimization
- Prevents execution during unsafe network conditions

### Transaction Simulation

Before executing transactions, ON1Builder can simulate them to:
- Estimate gas costs
- Calculate expected profit
- Identify potential issues

## Quick Installation

Here's a simplified installation process:

1. Clone the repository:
   ```bash
   git clone https://github.com/John0n1/ON1Builder.git
   cd ON1Builder
   ```

2. Set up your environment:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and wallet information
   ```

3. Install dependencies:
   ```bash
   ./setup_dev.sh
   poetry shell
   ```

4. Run a basic test:
   ```bash
   python -m on1builder test-connection --config configs/chains/config.yaml
   ```

For detailed installation instructions, see the [Installation Guide](installation.md).

## Basic Configuration

The minimal configuration includes:

1. **Blockchain RPC Endpoints**: HTTP and WebSocket endpoints for each chain
2. **Wallet Information**: Address and private key for transaction signing
3. **Strategy Settings**: Parameters for trading strategies

Example configuration (simplified):

```yaml
# Chain-specific configuration
CHAIN_ID: "1"
CHAIN_NAME: "Ethereum Mainnet"
HTTP_ENDPOINT: "https://mainnet.infura.io/v3/YOUR_INFURA_KEY"
WEBSOCKET_ENDPOINT: "wss://mainnet.infura.io/ws/v3/YOUR_INFURA_KEY"
WALLET_ADDRESS: "0xYourEthereumWalletAddress"
WALLET_KEY: "YOUR_PRIVATE_KEY"

# Safety parameters
MAX_GAS_PRICE_GWEI: 100
MIN_PROFIT: 0.001
SLIPPAGE_DEFAULT: 0.05

# Monitoring
ENABLE_PROMETHEUS: true
```

For complete configuration options, see the [Configuration Guide](configuration.md).

## Your First Run

To run ON1Builder in a basic single-chain mode:

```bash
python -m on1builder run --config configs/chains/config.yaml
```

The system will:
1. Initialize connections to the blockchain
2. Set up monitoring components
3. Begin watching for opportunities
4. Execute transactions when profitable opportunities are found

You'll see log output indicating the system's status and any actions taken.

## What's Next?

Now that you have ON1Builder running, you might want to:

1. Explore [advanced configuration options](configuration.md)
2. Set up the [monitoring system](monitoring.md)
3. Try running on [multiple chains](../examples/multi_chain_example.md)
4. Learn how to create [custom strategies](../examples/custom_strategy_example.md)

For any issues, check the [Troubleshooting Guide](troubleshooting.md).

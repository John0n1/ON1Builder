# ON1Builder

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**ON1Builder is a sophisticated, production-grade, multi-chain Maximum Extractable Value (MEV) trading bot designed for Ethereum Mainnet and Polygon Mainnet (and easily configurable for others). It incorporates advanced features like secure secret management, comprehensive monitoring, automated strategies, and robust deployment practices.**

**Note:** This bot interacts with real cryptocurrency markets and involves significant financial risk. Use at your own discretion and risk.

## Documentation

- [Deployment Guide](DEPLOYMENT.md)
- [Security Guidelines](SECURITY.md)
- [Post-Deployment Checklist](post_deployment_checklist.md)

---

**Table of Contents**

1.  [Disclaimer](#disclaimer)
2.  [Architecture Overview](#architecture-overview)
3.  [Key Features](#key-features)
4.  [Prerequisites](#prerequisites)
5.  [Setup and Installation](#setup-and-installation)
    *   [Cloning the Repository](#cloning-the-repository)
    *   [Environment Setup](#environment-setup)
    *   [Configuration](#configuration)
    *   [Node Access](#node-access)
    *   [Vault Setup](#vault-setup)
6.  [Running the Bot](#running-the-bot)
    *   [Production Deployment (Docker Compose)](#production-deployment-docker-compose)
    *   [Development / Direct Execution](#development--direct-execution)
    *   [API Server](#api-server)
7.  [Configuration Details](#configuration-details)
    *   [Configuration Hierarchy](#configuration-hierarchy)
    *   [Key Configuration Files](#key-configuration-files)
    *   [Chain Configuration](#chain-configuration)
    *   [Secret Management (Vault)](#secret-management-vault)
8.  [Core Logic and Strategies](#core-logic-and-strategies)
    *   [Mempool Monitoring](#mempool-monitoring)
    *   [Strategy Selection (StrategyNet)](#strategy-selection-strategynet)
    *   [Transaction Execution (TransactionCore)](#transaction-execution-transactioncore)
    *   [Safety Checks (SafetyNet)](#safety-checks-safetynet)
    *   [Nonce Management (NonceCore)](#nonce-management-noncecore)
    *   [Market Analysis & Prediction (MarketMonitor)](#market-analysis--prediction-marketmonitor)
    *   [Flashloans](#flashloans)
    *   [Implemented Strategies](#implemented-strategies)
9.  [Multi-Chain Operation](#multi-chain-operation)
10. [Security](#security)
11. [Monitoring and Alerting](#monitoring-and-alerting)
12. [Maintenance](#maintenance)
13. [Development and Contribution](#development-and-contribution)
14. [Troubleshooting](#troubleshooting)
15. [License](#license)
16. [Contact and Support](#contact-and-support)

---

## Disclaimer

**Trading cryptocurrencies and engaging in MEV activities involves substantial risk of financial loss. ON1Builder is provided "AS IS" without warranty of any kind. The authors or contributors are not responsible for any financial losses incurred through the use of this software. This is not financial advice. Always do your own research and understand the risks before deploying any trading bot.**

---

## Architecture Overview

ON1Builder employs a modular architecture designed for robustness, scalability, and security, especially in a multi-chain production environment.

**Key Components:**

*   **MultiChainCore:** The central orchestrator, managing multiple `ChainWorker` instances for different blockchains.
*   **ChainWorker:** Handles all operations specific to a single blockchain (connection, transactions, nonce management).
*   **Configuration (`configuration_multi_chain.py`):** Loads settings from YAML, `.env`, environment variables, and Vault, handling chain-specific overrides.
*   **Vault:** Securely stores sensitive data like private keys and API keys (using HashiCorp Vault).
*   **TxpoolMonitor:** Scans the mempool (or recent blocks) for potential MEV opportunities.
*   **StrategyNet:** Uses reinforcement learning to select the best strategy (front-run, back-run, sandwich) for an opportunity and updates strategy weights based on performance.
*   **TransactionCore:** Constructs, signs, simulates, and dispatches transactions for the selected strategies, interacting with DEXs (Uniswap, SushiSwap) and lending protocols (Aave for Flashloans).
*   **SafetyNet:** Provides crucial pre-transaction checks for profitability, gas limits, and network congestion.
*   **NonceCore:** Manages transaction nonces reliably, handling caching and synchronization.
*   **MarketMonitor:** Fetches market data (prices, volume), analyzes conditions, and uses a machine learning model (`price_model.joblib`) for price prediction.
*   **APIConfig:** Aggregates data from various external APIs (CoinGecko, Etherscan, DEX Screener, etc.).
*   **Monitoring Stack:** Uses Prometheus for metrics collection (via Pushgateway) and Grafana for visualization. Alerting via Slack/email is configured through scripts.
*   **API Server (`app_multi_chain.py`):** A Flask-based server providing endpoints to control (start/stop) and monitor (status/metrics) the bot.

---

## Key Features

*   **Multi-Chain Support:** Natively designed to operate concurrently on multiple EVM-compatible chains (e.g., Ethereum Mainnet, Polygon Mainnet, Sepolia Testnet). Easily configurable for others.
*   **Advanced MEV Strategies:** Implements common MEV strategies:
    *   Front-running
    *   Back-running
    *   Sandwich Attacks
    *   Includes variations leveraging Flashloans and market conditions (volatility, price dips, high volume).
*   **Reinforcement Learning Strategy Selection:** `StrategyNet` dynamically chooses the best strategy variation based on learned weights and performance, adapting over time.
*   **Machine Learning Price Prediction:** `MarketMonitor` utilizes a predictive model (e.g., Linear Regression, RandomForest) trained on historical data to inform strategies.
*   **Flashloan Integration:** Leverages Aave V3 Flashloans for capital-efficient strategies (See `contracts/SimpleFlashloan.sol`).
*   **Robust Security:**
    *   Secure secret management using **HashiCorp Vault**.
    *   Comprehensive security practices outlined (See [Security](#security) and `SECURITY.md`).
*   **Production-Grade Deployment:**
    *   Dockerized application for consistent environments (`docker-compose.multi-chain.yml`).
    *   Systemd service files provided for process management (`deploy/`).
    *   Automated deployment scripts (`secure_deploy_multi_chain.sh`).
*   **Comprehensive Monitoring:**
    *   Metrics exposed via Prometheus Pushgateway.
    *   Pre-configured Grafana dashboard (`dashboards/on1builder-multi-chain-dashboard.json`).
    *   Logging to console and file (`app.log`).
*   **Automated Maintenance:** Scripts for routine tasks like key rotation, backups, and alerts (See `scripts/` and `post_deployment_checklist.md`).
*   **Safety Mechanisms:** `SafetyNet` performs crucial checks before executing transactions to mitigate losses due to gas spikes or unprofitability.
*   **Reliable Nonce Management:** `NonceCore` prevents nonce conflicts and transaction failures.
*   **Flexible Configuration:** Hierarchical configuration system using YAML and `.env` files.

---

## Prerequisites

Before you begin, ensure you have the following installed and configured:

*   **Git:** For cloning the repository.
*   **Python:** Version 3.12 or higher.
*   **Docker & Docker Compose:** For containerized deployment (recommended for production).
*   **HashiCorp Vault:** For secure secret management (See [Vault Setup](#vault-setup)).
*   **Ethereum Node Access:** Access to RPC/WebSocket endpoints for each chain you intend to run on (e.g., local node, Infura, Alchemy).
*   **API Keys:** For services like Etherscan, Infura/Alchemy (if used), potentially CoinGecko, etc.
*   **Test Wallet:** An account with testnet funds for development and testing.
*   **Production Wallet:** A funded wallet for live trading (**securely managed!**).

---

## Setup and Installation

### Cloning the Repository

```bash
git clone https://github.com/John0n1/ON1Builder.git
cd ON1Builder
```

### Environment Setup

It's highly recommended to use a Python virtual environment.

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

### Configuration

1.  **Copy Environment Template:** Create your environment file from the multi-chain template. This file is primarily used by Docker Compose but also informs direct execution if variables aren't otherwise set.
    ```bash
    cp .env.multi-chain.template .env.multi-chain
    ```
    *Note: You might also use a simple `.env` file based on `template.env` for local development secrets, which will be loaded by `python-dotenv`.*

2.  **Edit `.env.multi-chain`:** Fill in the required environment variables, especially:
    *   `CHAINS`: Comma-separated list of Chain IDs (e.g., `1,137`).
    *   Chain-specific endpoints (`CHAIN_1_HTTP_ENDPOINT`, `CHAIN_137_WEBSOCKET_ENDPOINT`, etc.).
    *   Chain-specific wallet addresses (`CHAIN_1_WALLET_ADDRESS`, etc.).
    *   `VAULT_ADDR` and `VAULT_TOKEN` (especially for production).
    *   Other API keys (`ETHERSCAN_API_KEY`, etc.).
    *   `GO_LIVE` and `DRY_RUN` flags.

3.  **Configure `config_multi_chain.yaml`:** Review and adjust settings in `config_multi_chain.yaml`. This file defines default parameters for different environments (`development`, `production`) and chain-specific overrides if needed (though `.env.multi-chain` often takes precedence for endpoints/wallets). Key areas:
    *   Chain IDs and names.
    *   Default API keys (can be overridden by env vars).
    *   Strategy parameters (gas limits, slippage, profit margins).
    *   Paths to ABI and data files.
    *   Vault path (`VAULT_PATH`).

### Node Access

Ensure you have reliable RPC/WebSocket access for *each* chain specified in your `CHAINS` configuration. Options include:
*   **Local Node:** Running Geth, Erigon, Nethermind, etc., locally. Provides lowest latency but requires significant resources.
*   **Private Node:** Using a dedicated node instance in the cloud.
*   **Node Providers:** Services like Infura, Alchemy, QuickNode, etc. (ensure your plan supports the required request volume).

Configure the respective `CHAIN_<ID>_HTTP_ENDPOINT` and `CHAIN_<ID>_WEBSOCKET_ENDPOINT` variables.

### Vault Setup

Securely storing private keys and API keys is paramount. ON1Builder integrates with HashiCorp Vault.

*   **Development:** The `docker-compose.multi-chain.yml` includes a Vault service running in *development mode*. This is convenient but **NOT SECURE** for production. Secrets are stored in memory and lost on restart. A default root token (`on1builder-dev-token` unless overridden by `VAULT_TOKEN` in `.env.multi-chain`) is used.
*   **Production:** **CRITICAL:** Follow the production hardening guide for Vault. This involves:
    *   Using a persistent storage backend (Consul, Filesystem, S3, etc.).
    *   Initializing Vault properly and managing unseal keys securely.
    *   Configuring access control with policies and roles (AppRole is used by the deployment scripts).
    *   Enabling audit logs.
    *   Setting up TLS.
    *   Refer to `DEPLOYMENT.md` for scripts (`vault_prod_init.sh`) that assist with this process and the [Vault Production Hardening Guide](https://developer.hashicorp.com/vault/docs/concepts/production).

You need to populate Vault with secrets under the configured `VAULT_PATH` (e.g., `secret/on1builder`). The `generate_env.sh` script (used in production deployment) fetches secrets from Vault to create the final `.env.multi-chain` file used by the container. Key secrets include:
*   `WALLET_KEY` (for each chain, e.g., `CHAIN_1_WALLET_KEY`, `CHAIN_137_WALLET_KEY`)
*   `ETHERSCAN_API_KEY`
*   Other sensitive API keys or credentials.

---

## Running the Bot

### Production Deployment (Docker Compose)

This is the recommended method for running ON1Builder in a production environment. It utilizes Docker Compose to manage the bot application, Vault, Prometheus, Pushgateway, and Grafana services.

1.  **Prerequisites:** Ensure Docker, Docker Compose, and potentially Vault (if running externally) are installed. The `./scripts/install_prereqs.sh` script can assist on Linux systems.
2.  **Vault:** Set up Vault in production mode (see [Vault Setup](#vault-setup) and `DEPLOYMENT.md`).
3.  **Environment:** Generate the secure environment file using Vault:
    ```bash
    # Ensure VAULT_ADDR and VAULT_TOKEN are set correctly in your shell env
    # or modify the script
    ./scripts/generate_env.sh
    ```
    This creates `.env.multi-chain` containing secrets fetched from Vault and non-secrets from `.env.multi-chain.template`.
4.  **Build & Push (Optional):** If deploying to multiple hosts or using a private registry:
    ```bash
    # Configure registry details if needed
    ./scripts/build_and_push.sh
    ```
5.  **Run:** Start the services using Docker Compose:
    ```bash
    docker-compose -f docker-compose.multi-chain.yml up -d
    ```
    Alternatively, use the provided systemd service files (`deploy/on1builder.service`, `deploy/vault.service`) for better integration with the host system, as detailed in `DEPLOYMENT.md`.
6.  **Secure Deployment Script:** For a fully automated setup (including Vault initialization, environment generation, building, and starting containers), use the secure deployment script:
    ```bash
    # Review the script first!
    ./secure_deploy_multi_chain.sh --go-live
    ```
7.  **Verification:** Check the status and logs:
    ```bash
    ./scripts/verify_live.sh
    docker-compose -f docker-compose.multi-chain.yml logs -f app
    sudo journalctl -u on1builder # If using systemd
    ```
8.  **Monitoring:** Access the Grafana dashboard (default: `http://<your-server-ip>:3000`, user/pass: `admin`/`admin` unless changed).

Refer to `DEPLOYMENT.md` for comprehensive production deployment instructions.

### Development / Direct Execution

For development or debugging, you can run the bot directly using Python.

1.  **Activate Environment:** `source venv/bin/activate`
2.  **Set Environment Variables:** Ensure necessary variables (endpoints, wallet keys, API keys) are set either in your shell environment or in a `.env` file (which `configuration_multi_chain.py` will load). Make sure `GO_LIVE` is set appropriately (likely `false` for development).
3.  **Run:** Execute the multi-chain main script:
    ```bash
    python python/main_multi_chain.py
    ```
    The bot will load the configuration, initialize workers for the configured chains, and start monitoring/trading based on the `GO_LIVE` flag.

### API Server

ON1Builder includes a Flask-based API server (`python/app_multi_chain.py`) for monitoring and basic control when running via Docker Compose or systemd.

*   **Endpoints:**
    *   `/healthz`: Health check.
    *   `/metrics`: Prometheus-compatible metrics (aggregated from all chains).
    *   `/status`: Current running status, uptime, active chains.
    *   `/start` (POST): Start the bot (if stopped).
    *   `/stop` (POST): Stop the bot gracefully.
    *   `/api/test-alert` (POST): Send a test alert (implementation may vary).
    *   `/api/simulate-transaction` (POST): Simulate a transaction (implementation may vary).
*   **Access:** The server typically runs on port `5001` inside the `app` container (exposed in `docker-compose.multi-chain.yml`).

---

## Configuration Details

### Configuration Hierarchy

Settings are loaded in the following order of precedence (higher numbers override lower ones):

1.  **Internal Defaults:** Hard-coded values in `configuration_multi_chain.py`.
2.  **YAML File (`config_multi_chain.yaml`):** Environment-specific sections (`development`, `production`) provide baseline settings.
3.  **Environment Variables / `.env` file:** Variables matching configuration keys (e.g., `MAX_GAS_PRICE_GWEI`, `CHAIN_1_HTTP_ENDPOINT`) override YAML values. `.env` is loaded automatically if present.
4.  **Vault Secrets:** If `GO_LIVE=true`, secrets specified in `_SECRET_KEYS` are fetched from Vault and override previous values.

### Key Configuration Files

*   **`config_multi_chain.yaml`:** Defines default parameters, strategy thresholds, file paths, and structure for different environments.
*   **`.env.multi-chain.template` / `.env.multi-chain`:** Template and instance file for environment variables, especially endpoints, wallet addresses, API keys, and Vault details. Used heavily by Docker Compose.
*   **`.env` (Optional):** Standard dotenv file for local development secrets.

### Chain Configuration

Multi-chain operation is configured primarily through environment variables (typically in `.env.multi-chain`):

*   `CHAINS`: A comma-separated string of chain IDs to activate (e.g., "1,137,11155111").
*   `CHAIN_<ID>_*`: Chain-specific settings override global defaults for that particular chain ID. Examples:
    *   `CHAIN_1_HTTP_ENDPOINT`: RPC URL for Ethereum Mainnet (ID 1).
    *   `CHAIN_137_WALLET_ADDRESS`: Wallet address for Polygon (ID 137).
    *   `CHAIN_11155111_WALLET_KEY`: Wallet private key for Sepolia (ID 11155111) - **Load from Vault in production!**
    *   `CHAIN_1_MAX_GAS_PRICE_GWEI`: Chain-specific gas cap.

If `CHAINS` is not set, the bot operates in single-chain mode using the global configuration values (e.g., `HTTP_ENDPOINT`, `WALLET_ADDRESS`).

### Secret Management (Vault)

*   When `GO_LIVE=true`, the application attempts to fetch secrets listed in `_SECRET_KEYS` (and their chain-specific variants like `CHAIN_1_WALLET_KEY`) from HashiCorp Vault.
*   Vault connection details (`VAULT_ADDR`, `VAULT_TOKEN`) and the secret path (`VAULT_PATH`) must be configured (usually via environment variables).
*   Ensure the Vault token has read permissions for the specified path(s).
*   **Production:** Use AppRole authentication and secure Vault deployment as outlined in `DEPLOYMENT.MD` and `SECURITY.MD`.

---

## Core Logic and Strategies

### Mempool Monitoring

*   **`TxpoolMonitor`:** Continuously scans for new transactions entering the mempool.
*   **Filtering:** Uses `eth_newPendingTransactionFilter` if available, otherwise falls back to polling recent blocks.
*   **Prioritization:** Analyzes transaction gas prices to prioritize potentially more urgent opportunities.
*   **Profitability Heuristic:** Performs a lightweight check to identify transactions that *might* be profitable targets for MEV strategies.
*   **Queuing:** Places potentially profitable transactions onto a queue for `StrategyNet`.

### Strategy Selection (StrategyNet)

*   **Reinforcement Learning:** Uses a simple ε-greedy approach over strategy weights. It explores new strategies occasionally and exploits the currently best-performing ones most of the time.
*   **Weight Management:** Maintains weights for different strategy implementations (e.g., multiple front-running variations). Weights are updated based on the success and profitability (`reward`) of each execution.
*   **Persistence:** Strategy weights are periodically saved to `strategy_weights.json` and loaded on startup.
*   **Metrics:** Tracks performance metrics (success rate, average execution time, total profit) for each strategy type.

### Transaction Execution (TransactionCore)

*   **Transaction Building:** Constructs transactions based on strategy requirements, interacting with protocols like Uniswap, SushiSwap, and Aave.
*   **Gas Management:** Determines appropriate gas prices (legacy vs EIP-1559) and estimates gas limits. Implements retry logic with gas bumping.
*   **Signing:** Signs transactions using the configured private key (loaded securely from Vault in production).
*   **Dispatching:** Sends signed transactions to the network via the appropriate `ChainWorker`.
*   **Bundle Execution:** Supports sending sequences of transactions (bundles) serially.

### Safety Checks (SafetyNet)

*   **Pre-computation:** Before executing a strategy, `SafetyNet` performs critical checks:
    *   **Profitability:** Estimates potential profit against minimum thresholds (`MIN_PROFIT`), accounting for estimated gas costs and slippage.
    *   **Gas Limits:** Ensures gas price is within configured limits (`MAX_GAS_PRICE_GWEI`).
    *   **Congestion:** Adjusts slippage tolerance based on current network congestion.
    *   **Balance:** Checks if sufficient funds are available (implicitly via gas cost calculation).
*   **Price Oracle:** Uses `APIConfig` (falling back to on-chain DEX quotes) for reliable token pricing.
*   **Dynamic Gas:** Fetches current gas prices, considering EIP-1559 base fees and priority fees.

### Nonce Management (NonceCore)

*   **Reliability:** Ensures correct nonce usage to prevent transaction failures.
*   **Caching:** Caches the last known nonce locally for speed.
*   **Reservation:** Temporarily reserves nonces while transactions are pending.
*   **Synchronization:** Periodically refreshes the nonce from the blockchain (`pending` and `latest` transaction counts) to stay accurate.

### Market Analysis & Prediction (MarketMonitor)

*   **Data Aggregation:** Uses `APIConfig` to fetch real-time and historical price/volume data.
*   **Condition Checks:** Analyzes market conditions like volatility, trends, and liquidity.
*   **ML Prediction:** Loads a pre-trained model (`ml/price_model.joblib`) to predict short-term price movements. The model is likely trained on features extracted from `ml/training_data.csv`.
*   **Retraining:** Periodically fetches new data, updates `training_data.csv`, and retrains the model to keep it current.

### Flashloans

*   **Aave V3 Integration:** The `SimpleFlashloan.sol` contract enables borrowing assets from Aave V3 pools without upfront capital.
*   **`executeOperation` Callback:** Contains the logic to be executed within the flashloan (e.g., perform arbitrage swaps).
*   **Profit Repayment:** The contract ensures the borrowed amount plus the Aave premium is repaid within the same transaction, leaving the profit in the contract for later withdrawal.
*   **`TransactionCore` Interaction:** Functions like `flashloan_front_run` and `flashloan_sandwich_attack` in `TransactionCore` likely trigger the `requestFlashLoan` function on the deployed `SimpleFlashloan` contract.

### Implemented Strategies

*   **Front-running:** Executing a transaction just before a target transaction to profit from the price impact (standard, aggressive, flashloan-based, predictive, volatility-aware variations).
*   **Back-running:** Executing a transaction immediately after a target transaction, often to capture arbitrage opportunities created by it (standard, price-dip, flashloan-based, high-volume variations).
*   **Sandwich Attacks:** Placing one transaction before and another after a target transaction to manipulate the price and profit from the difference (standard, flashloan-based variations).
*   **Simple ETH Transfers:**

---

## Multi-Chain Operation

*   **`MultiChainCore`:** Orchestrates operations across all configured chains.
*   **`ChainWorker`:** An instance of `ChainWorker` is created for each chain ID listed in the `CHAINS` environment variable.
*   **Isolation:** Each `ChainWorker` maintains its own Web3 connection, account details (if needed), nonce state, and metrics specific to its chain.
*   **Configuration:** Chain-specific parameters (endpoints, wallets, gas limits) are loaded via the configuration system (e.g., `CHAIN_1_HTTP_ENDPOINT`).
*   **Concurrency:** Workers run concurrently using Python's `asyncio`, allowing the bot to monitor and act on multiple chains simultaneously.
*   **Shared Services:** Components like `APIConfig`, `ABIRegistry`, and the core MEV logic (`StrategyNet`, `MarketMonitor`) are typically shared across workers, though they operate on data relevant to specific chains when executing transactions.

---

## Security

**Security is paramount when dealing with MEV bots and private keys.**

*   **Secret Management:** **HashiCorp Vault** is the designated tool for storing private keys, API keys, and other secrets. **NEVER** commit secrets directly to the repository or hardcode them.
*   **Vault Production Hardening:** The default Docker Compose setup uses Vault in development mode. **THIS IS NOT SECURE.** For production, follow the hardening steps in `DEPLOYMENT.MD` and the official Vault documentation. Use AppRole or other secure authentication methods.
*   **Key Rotation:** Implement regular rotation for wallet keys and API keys. Scripts like `rotate_wallet_keys.sh` and `backup_wallet_keys.sh` are provided as examples (see `post_deployment_checklist.md`).
*   **Environment Separation:** Use separate configurations, wallets, and potentially Vault paths for development, staging, and production.
*   **Network Security:** Restrict access to deployment servers and API endpoints. Use firewalls and consider VPNs for sensitive operations.
*   **Dependency Scanning:** Regularly scan dependencies (`requirements.txt`) for known vulnerabilities.
*   **Principle of Least Privilege:** Ensure the Vault token used by the application only has the necessary permissions.
*   **Code Audits:** Regularly review the codebase for potential security flaws.

**Refer to `SECURITY.md` for a comprehensive security policy, checklist, and best practices.**

---

## Monitoring and Alerting

A robust monitoring stack is crucial for observing bot performance and detecting issues.

*   **Metrics:** The application exposes metrics compatible with Prometheus. `MultiChainCore` aggregates metrics from all active `ChainWorker` instances.
*   **Prometheus:** The `docker-compose.multi-chain.yml` sets up a Prometheus server to scrape metrics (via the included Pushgateway, as the main app might be short-lived or scaled).
*   **Grafana:** A Grafana instance is included with a pre-configured dashboard (`dashboards/on1builder-multi-chain-dashboard.json`) to visualize key metrics like wallet balances, profits, gas prices, and transaction counts per chain. Access it at `http://<server-ip>:3000` (default credentials: admin/admin).
*   **Pushgateway:** Used to allow the potentially ephemeral bot application instances to push metrics to Prometheus.
*   **Alerting:** While Alertmanager setup isn't explicitly in the compose file, the project structure suggests integration. Scripts (`cron_setup.sh`) mention setting up alerts for PnL, gas prices, and faucet balances, likely sending notifications via Slack or email. Configure these alerts according to your needs.
*   **Logging:** Check application logs (`docker-compose logs -f app` or `journalctl -u on1builder`) and Vault logs (`journalctl -u vault`) for detailed information and errors.

---

## Maintenance

Regular maintenance is essential for smooth and secure operation.

*   **Key Management:** Regularly rotate and securely back up wallet keys (see `scripts/rotate_wallet_keys.sh`, `scripts/backup_wallet_keys.sh`).
*   **Updates:** Keep Python dependencies (`pip install -r requirements.txt --upgrade`), Docker images, Vault, and system packages up-to-date.
*   **Log Review:** Periodically check application and system logs for errors or unusual patterns.
*   **Backup:** Regularly back up Vault data, configurations, and monitoring data (Prometheus/Grafana volumes).
*   **Performance Monitoring:** Keep an eye on Grafana dashboards and Prometheus alerts.
*   **Review Checklist:** Consult the `post_deployment_checklist.md` for a detailed list of ongoing operational tasks and checks.

---

## Development and Contribution

Contributions are welcome! Please follow these guidelines:

1.  **Fork & Clone:** Fork the repository and clone it locally.
2.  **Setup:** Create a virtual environment and install dependencies (`pip install -r requirements.txt`).
3.  **Configure:** Set up your `.env` file and potentially `config_multi_chain.yaml` for development.
4.  **Branch:** Create a new branch for your feature or bug fix (e.g., `feature/new-strategy` or `fix/nonce-issue`).
5.  **Code:**
    *   Follow PEP 8 style guidelines.
    *   Write clear, concise code with meaningful variable names.
    *   Add unit tests for new functionality in the `tests/` directory.
    *   Update documentation (`README.md`, other `.md` files) if necessary.
6.  **Test:** Run tests using `pytest tests/`.
7.  **Submit PR:** Create a Pull Request with a clear title and description, linking any related issues.

Please refer to `CONTRIBUTING.md` for more details.

---

## Troubleshooting

*   **Deployment Issues:** Check logs from Docker Compose (`docker-compose logs app`), systemd (`journalctl -u on1builder`), and Vault (`journalctl -u vault`). Refer to the `Troubleshooting` section in `DEPLOYMENT.md`.
*   **Connection Errors:** Verify your RPC/WebSocket endpoints in the configuration (`.env.multi-chain` or `config_multi_chain.yaml`) and ensure node accessibility.
*   **Transaction Failures:** Check Etherscan (or the relevant block explorer) for the transaction hash. Common causes include insufficient gas, incorrect nonce, or contract logic errors. Review bot logs for details.
*   **Vault Errors:** Ensure Vault is running, unsealed, and accessible. Verify the `VAULT_ADDR`, `VAULT_TOKEN`, and `VAULT_PATH` are correct and the token has the required permissions.
*   **Performance Issues:** Check system resource usage (CPU, RAM, network) on the host machine and within containers. Monitor Grafana dashboards for bottlenecks.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Contact and Support

*   **Issues:** For bug reports or feature requests, please open an issue on the GitHub repository.
*   **Discussions:** Join the community discussions (e.g., GitHub Discussions).

---

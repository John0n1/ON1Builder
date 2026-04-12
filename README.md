# ON1Builder

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/John0n1/ON1Builder/actions/workflows/ci.yml/badge.svg)](https://github.com/John0n1/ON1Builder/actions/workflows/ci.yml)

```bash
pip install -e .
```

Async, multi-chain MEV/arbitrage engine with safety rails, flashloan support, and live telemetry. Highly customizable via config.

## Overview
ON1Builder is a modular MEV searcher framework designed for building and deploying arbitrage, front-running, and back-running strategies across multiple EVM-compatible blockchains. It emphasizes safety, configurability, and observability, making it suitable for both development and production environments.

---

## Key Features
- **Multi-Chain Support**: Easily connect to any EVM-compatible chain with configurable RPC and WebSocket endpoints (prefers Nethermind, Geth nodes).
- **MEV Strategies**: Built-in support for common MEV strategies including arbitrage, front-running, back-running, and flashloan-based trades.
- **Safety Mechanisms**: Configurable slippage caps, gas price ceilings, and balance tiers to minimize risk.
- **Flashloan Integration**: Seamless integration with popular flashloan providers for capital-efficient trading.
- **Simulation Backends**: Supports multiple simulation backends (eth_call, Anvil, Tenderly) for pre-execution validation.
- **Telemetry & Monitoring**: Heartbeats, performance summaries, structured logging, and notification channels (Slack, Telegram, Discord, Email) for real-time monitoring.
- **Extensible Architecture**: Modular design allows for easy addition of new strategies, chains, and features.

## Quick Snapshot

| Track | Summary |
| ----- | ------- |
| Core Focus | MEV searcher: arbitrage, back/front-run, flashloans |
| Chains | Ethereum ready (public RPC OK); multi-chain capable |
| Safety | Slippage caps, gas ceilings, balance tiers, emergency stop |
| Telemetry | Heartbeats, perf summaries, structured logs, notifications |

## Feature Highlights

<img width="9867" height="2500" alt="Dia" src="https://github.com/user-attachments/assets/9acc0ac1-c5f3-45f1-a8c9-bf6bf1f3b232" />

## Quick Start

### 1. Clone & env
```bash
git clone https://github.com/John0n1/ON1Builder.git
cd ON1Builder
```
- Windows
```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
pip install -e .
```
- Linux/MacOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Configure (minimum)
```bash
copy .env.example .env
# edit:
#   WALLET_KEY, WALLET_ADDRESS
#   RPC_URL_1="https://ethereum-rpc.publicnode.com"
#   WEBSOCKET_URL_1="wss://ethereum-rpc.publicnode.com"   # public WS is auto-skipped for txpool
#   ETHERSCAN_API_KEY=...
```

### 3. Run
```bash
python -m on1builder status check
python -m on1builder run start
```


> With public RPC/WS, txpool scanning is disabled on purpose (unreliable pending tx support). Provide a private WS endpoint if you want pending tx monitoring.

## Architecture

<img width="6265" height="4722" alt="Arch" src="https://github.com/user-attachments/assets/934d3aaa-fae0-49c2-b28d-e740bedf0e2f" />

### Module Dependency Graph

```
cli/               → config/, core/
core/              → config/, engines/, integrations/, monitoring/, persistence/, utils/
engines/           → config/, integrations/, utils/
integrations/      → config/, utils/
monitoring/        → config/, integrations/, utils/
persistence/       → config/, utils/
utils/             → (standalone, no internal deps except config.loaders)
```

### Key Design Patterns

| Pattern | Where | Purpose |
| ------- | ----- | ------- |
| Singleton | `ExternalAPIManager`, `NonceManager`, `DatabaseInterface`, `NotificationService` | Shared state, connection pooling |
| Circuit Breaker | `error_recovery.py` | Protect against cascading failures |
| Async Context Manager | `DatabaseInterface`, `NotificationService` | Guaranteed resource cleanup |
| Strategy | `StrategyExecutor` | Pluggable MEV strategies |
| Observer | `TxPoolScanner` → `StrategyExecutor` | Decouple mempool monitoring from execution |

## Configuration Cheat Sheet

| Setting | Description |
| ------- | ----------- |
| `WALLET_KEY`, `WALLET_ADDRESS` | Required for signing/monitoring |
| `RPC_URL_1` | HTTP RPC endpoint (public OK) |
| `WEBSOCKET_URL_1` | WS endpoint; use private if you want txpool scanning |
| `ETHERSCAN_API_KEY` | Optional but recommended for ABI/tx metadata |
| `MIN_PROFIT_ETH` | Profit floor per trade (ETH) |
| `MAX_GAS_PRICE_GWEI` | Hard gas ceiling |
| `SUBMISSION_MODE` | `public`, `private`, or `bundle` (relay submission) |
| `PRIVATE_RPC_URL` | Private RPC endpoint (Flashbots Protect, etc.) |
| `BUNDLE_RELAY_URL` | Bundle relay endpoint (MEV-Boost/Flashbots) |
| `SIMULATION_BACKEND` | `eth_call`, `anvil`, or `tenderly` |
| `SIMULATION_CONCURRENCY` | Max concurrent simulations |
| `NOTIFICATION_CHANNELS` | `slack,telegram,discord,email` (blank = off) |
| `ORACLE_FEEDS` | JSON map of chain_id → symbol → Chainlink feed address |
| `ORACLE_STALE_SECONDS` | Max age (seconds) before oracle price is treated as stale |
| `MARKET_PRICE_PERSIST_INTERVAL` | Persist price snapshots to DB every N seconds (0 disables) |
| `STARTUP_TEST_TRANSACTION` | Run a diagnostic self-tx on startup (requires `ALLOW_INSUFFICIENT_FUNDS_TESTS`) |
| `ALLOW_INSUFFICIENT_FUNDS_TESTS` | Bypass local balance checks for test sends (debug only) |

Full list lives in `.env.example`.

PublicNode endpoints can be used for EVM chains listed in `.env.example`. Non-EVM endpoints
(Sui, Aptos, Osmosis, Avalanche P/X, Polygon Heimdall) are not supported by ON1Builder.

## Running & Monitoring

```bash
# Validate config
python -m on1builder status check

# Start bot
python -m on1builder run start

# View logs
tail -f logs/on1builder.log          # *nix
Get-Content logs\\on1builder.log -Wait  # Windows
```

Heartbeats report balance tier, pending tx count (0 if txpool scanner is disabled), and memory usage.

## Testing

```bash
# Run all tests (fast, no external deps)
python -m pytest tests/ -q

# Run with verbose output
python -m pytest tests/ -v --tb=short

# Run with coverage report
python -m pytest tests/ --cov=on1builder --cov-report=html

# Run a specific test file
python -m pytest tests/test_edge_cases.py -v

# Run live API tests (requires network access)
RUN_LIVE_API_TESTS=1 python -m pytest tests/test_external_api_integration.py
```

### Test Categories

| Category | Files | Focus |
| -------- | ----- | ----- |
| Smoke | `test_smoke.py` | Package imports, version consistency, resource files |
| Core Logic | `test_balance_manager.py`, `test_nonce_manager_logic.py`, `test_transaction_manager_logic.py` | Balance tiers, nonce management, TX building |
| Engines | `test_safety_and_gas_guardrails.py`, `test_logic_behaviors.py` | Safety guards, strategy execution |
| Monitoring | `test_txpool_end_to_end.py`, `test_market_data_feed_logic.py`, `test_websocket_*.py` | Mempool scanning, market data, WS resilience |
| API | `test_external_api_logic.py`, `test_external_api_integration.py` | Price feeds, oracle integration |
| Config | `test_config_manager.py`, `test_validation.py`, `test_cli_commands.py` | Settings loading, validation, CLI |
| Utils | `test_utils.py`, `test_error_handling.py`, `test_path_helpers.py`, `test_logging_config.py` | Utilities, error handling, DI container |
| Edge Cases | `test_edge_cases.py` | Boundary values, error paths, constants sanity |

## Development

<img width="15082" height="7425" alt="flow" src="https://github.com/user-attachments/assets/c7838b3d-65f1-4856-ae90-34bb55d82e3e" />

```bash
# Lint and format
black --target-version py312 src tests
python -m compileall -q src tests

# Run full test suite
python -m pytest tests/ -q
```

Pre-commit hooks are configured in `.pre-commit-config.yaml`.

## Troubleshooting

| Problem | Cause | Solution |
| ------- | ----- | -------- |
| `parsimonious` version conflict | `eth-abi` requires `<0.11.0` | Use `parsimonious>=0.10.0,<0.11.0` (already pinned) |
| txpool scanning silent | Public WS endpoint | Use a private node (Alchemy, Infura, self-hosted) |
| `ConfigurationError` on start | Missing `.env` values | Run `python -m on1builder status check` to diagnose |
| Gas estimation fails | Network congestion / bad RPC | Falls back to `default_gas_limit`; check RPC health |
| Notifications not sending | Channels not configured | Set `NOTIFICATION_CHANNELS` in `.env` |
| Tests fail with singleton state | Stale singleton between tests | Each test file resets singletons via fixtures |

## Optional Utilities

ON1Builder ships a few utilities that are not required for core execution but can be
integrated in advanced deployments:

- `src/on1builder/utils/error_recovery.py`: Retry/circuit-breaker helpers and a recovery
  manager. The TransactionManager now reports failures to this manager for tracking and
  optional recovery strategies, but most strategies are placeholders by default.
- `src/on1builder/utils/container.py`: A lightweight DI container for advanced lifecycle
  management. The core runtime does not use it yet; opt in if you want centralized wiring.
- `src/on1builder/utils/memory_optimizer.py`: Memory monitoring and GC management for
  long-running deployments. Tracks process memory and triggers cleanup when thresholds
  are exceeded.

## Flashloan setup
You need to deploy your own flashloan provider contract or use an existing one. Make sure to configure the flashloan provider address in your strategy settings.

To learn about deploying a flashloan contract, refer to the documentation of the flashloan provider you intend to use (e.g., Aave, dYdX) we recommend  [Aave](https://docs.aave.com/developers/guides/flash-loans)

Here's a basic outline of the steps involved:

1. Choose a Flashloan Provider: Decide which flashloan provider you want to use (e.g., Aave, dYdX).
2. We recommend using Remix IDE for deploying smart contracts. Open Remix IDE in your web browser.
3. Create a New File: In Remix, create a new Solidity file (e.g., FlashloanProvider.sol) and write or paste the flashloan contract code.
4. Compile the Contract: Use the Solidity compiler in Remix to compile your flashloan contract.
5. Deploy the Contract:
   - Select the appropriate environment (e.g., Injected Web3 for MetaMask).
   - Choose the contract you want to deploy.
   - Click the "Deploy" button and confirm the transaction in your wallet.
6. Note the Contract Address: After deployment, copy the contract address. You'll need to configure this address in .env

## API Keys

The bot is able to function without API keys, but some features are limited. It's recommended to set up the following free API keys for best experience:

- **Etherscan API Key**: For fetching contract ABIs and transaction metadata. Sign up at [Etherscan](https://etherscan.io/apis).
- **Tenderly Account**: For advanced simulation backend. Sign up at [Tenderly](https://tenderly.co/).
- **CoinGecko API Key**: Optional, for additional price data. Sign up at [CoinGecko](https://www.coingecko.com/en/api).


## Safety Notes

- Public WS endpoints are auto-skipped for txpool scanning to avoid noisy failures.
- Price lookups are limited to a small, well-known token set; repeated failures are silenced after blacklisting.
- Emergency balance tiers keep the bot idle when funds are low.
- Gas estimation includes a 20% buffer with a hard cap at 30M (Ethereum block gas limit).

## License

MIT - see [LICENSE](LICENSE).

## Disclaimer

Use at your own risk. No warranty. MEV strategies can be volatile and may incur losses. Keep keys safe; never use production keys on public demos.

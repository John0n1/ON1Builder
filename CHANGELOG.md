# Changelog

All notable changes to ON1Builder will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.4] - 2025-06-12

### Added
- Comprehensive multi-chain architecture with ChainWorker design
- Interactive TUI launcher (ignition.py) for easy setup and monitoring
- Robust CLI interface with Typer for advanced users
- Safety mechanisms with circuit-breaker and pre-transaction checks
- Real-time notification service with multiple channels (Slack, Telegram, Discord, Email)
- Database integration with SQLAlchemy for transaction and profit logging
- Resource management for ABIs, contracts, and token configurations
- Comprehensive configuration management with Pydantic settings

### Features
- **Multi-Chain Support**: Native support for Ethereum and EVM-compatible networks
- **Asynchronous Core**: Built on asyncio for high-performance, non-blocking operations
- **Strategy Engine**: Lightweight reinforcement learning for profit optimization
- **Flash Loan Integration**: Complete toolkit for Aave flash loans and MEV strategies
- **Monitoring**: Real-time mempool scanning and market data feeds
- **Security**: Encrypted wallet handling and secure configuration management

### Technical
- Python 3.12+ compatibility
- Modern async/await patterns throughout
- Type hints and Pydantic validation
- Comprehensive error handling and logging
- Modular architecture with clean separation of concerns
- Docker support for containerized deployment

### Dependencies
- Web3.py for blockchain interactions
- Pydantic for configuration validation
- SQLAlchemy for database operations
- Rich for beautiful terminal output
- Typer for CLI interface
- Questionary for interactive prompts
- And many more (see requirements.txt)

### Documentation
- Comprehensive README with setup instructions
- Example configuration files
- API documentation for core modules
- Development setup guides

### Security
- Secure wallet key handling
- Environment variable validation
- Safe configuration loading
- No hardcoded secrets or keys

## [Unreleased 2.3.0] - 2026-02-04

### Added
- Intent-focused tests across orchestrators, transaction manager profit/safety, market data, MEV scanner resilience, nonce manager, and optional live API probes.
- On-chain market data path (Uniswap V2 reserves + ERC20 totalSupply via public RPC) with Binance/Coingecko keyless fallbacks to keep pricing and supply lookups free of API keys.
- Per-chain oracle feed mapping (`_oracle_feeds_by_chain`) with `_load_configured_oracle_feeds()` method for merging user-configured Chainlink feeds from settings.

### Changed
- External API integrations drop CoinMarketCap/CryptoCompare/Infura; rely on public RPC, Binance, and keyless Coingecko, with Etherscan optional.
- README updated (Python 3.12+, clean architecture tree, clarified test commands and public RPC usage).
- `.env.example` refreshed with public Ethereum RPC defaults, Etherscan-only key guidance, and clearer feature toggles (including `RUN_LIVE_API_TESTS`).
- Ignition launcher displays v2.3.0; pyproject dev/test extras modernized for current toolchain.

### Fixed
- Dependency conflict: `parsimonious` version constraint relaxed to `>=0.10.0,<0.11.0` to resolve conflict with `eth-abi`.
- Bare `except:` clauses in `cli/status_cmd.py` and `core/multi_chain_orchestrator.py` (2 instances) replaced with `except Exception as e:` with proper logging.
- Duplicate "ON1Builder" in system status table title.
- Silent exception swallowing in `settings.py` `validate_complete_settings` now logs coercion failures.
- Gas estimation overflow: capped with `MAX_GAS_LIMIT` constant (via `utils.constants`) in `transaction_manager.py`.
- RPC connection check in `config/manager.py` using `str(chain_id)` when `rpc_urls` is keyed by `int`.
- Dependency resolution: removed 40+ hard-pinned transitive dependencies from `pyproject.toml` and `requirements.txt`; only direct project dependencies listed with ranges; pip resolves the transitive tree (fixes CI/CD dependency conflicts).
- `_load_configured_oracle_feeds()` now called during `ExternalAPIManager._initialize()` so user-supplied oracle feeds take effect at runtime.
- Test `test_txpool_scanner_identifies_mev_relevance_and_opportunities` now provides valid ABI-encoded swap calldata.
- Test `test_get_price_skips_unhealthy_providers` now mocks oracle fallback to avoid false positive.
- Vague assertions in `test_balance_manager.py` (always-true `in` checks) replaced with exact tier assertions.
- Vague assertions in `test_cli_commands.py` strengthened.
- Black formatting applied to all source and test files.

### Removed
- `twine` removed from dev dependencies (PyPI publishing not part of CI).
- `test_mangle.py` removed (425 lines of tests duplicated across 8 other dedicated test files).
- `test_basic_smoke.py` consolidated into `test_smoke.py`.
- 40+ hard-pinned transitive dependencies removed from `pyproject.toml` and `requirements.txt` (web3/eth-* stack, aiohttp/pydantic/rich/sqlalchemy internals); `aiosqlite` added as explicit dependency for async SQLite support.

### Documentation
- SECURITY.md: Added 2.3.x to supported versions table.
- CONTRIBUTING.md: Updated minimum Python version to 3.12, added coding conventions (exception hierarchy, singleton patterns, async context managers).
- README.md: Added CI badge, architecture module dependency graph, design patterns table, testing guide with categories, troubleshooting table, memory optimizer docs.
- CHANGELOG.md: Comprehensive documentation of all fixes and changes.

### Testing
- Rewrote `test_utils.py` from 5 import-only tests to 15 behavioral tests (Container, ConfigRedactor, GasOptimizer, ProfitCalculator).
- Added `test_edge_cases.py` with 36 edge case tests covering balance boundaries, validation, exception hierarchy, constants sanity, and error recovery.
- Consolidated smoke tests into `test_smoke.py` with module structure and container checks.
- Total: 297 tests pass (up from 275), 2 skipped (live API, env-specific logging).

### Planned
- ON1Builder strategy algorithms
- Additional DEX integrations
- Performance optimizations
- Extended test coverage
- Advanced monitoring dashboards

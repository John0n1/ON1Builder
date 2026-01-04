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
- Python 3.10+ compatibility
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

## [Unreleased 2.2.0] - 2026-02-04

### Added
- Intent-focused tests across orchestrators, transaction manager profit/safety, market data, MEV scanner resilience, nonce manager, and optional live API probes.
- Missing provider helpers in `integrations/external_apis.py` (Binance volume, CoinMarketCap market cap) to stabilize comprehensive market data calls.

### Changed
- README updated (Python 3.10+, clean architecture tree, clarified test commands and public RPC usage).
- `.env.example` refreshed with public Ethereum RPC defaults and clearer API key/feature toggles (including `RUN_LIVE_API_TESTS`).
- Ignition launcher displays v2.2.0; pyproject dev/test extras modernized for current toolchain.

### Planned
- Enhanced strategy algorithms
- Additional DEX integrations
- Performance optimizations
- Extended test coverage
- Advanced monitoring dashboards

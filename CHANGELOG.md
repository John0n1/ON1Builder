# Changelog

All notable changes to the ON1Builder project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Complete package restructuring following PEP 660 src/ layout
- Poetry-based dependency management
- Proper module hierarchy with organized subpackages
- Typer-based enhanced CLI with fallback to basic argparse
- Dependency injection system to avoid circular imports
- Graceful shutdown handlers for all core components
- CI/CD setup with GitHub Actions
- Restructured test directory to mirror src/ layout
- Added edge case tests for transaction retry logic and network failures
- Implemented robust websocket reconnection logic with exponential backoff
- Fixed web3.py v7 provider compatibility issues
- Fixed import paths throughout codebase for compatibility with package structure
- Improved logging system with string/int level handling

### Changed
- Updated file and directory structure to follow Python best practices
- Replaced ad-hoc configuration with centralized config management
- Updated all import statements in tests to use the new package structure
- Updated shell scripts to reference new source directory structure
- Enhanced logging with structured log format
- Moved all Docker-related files to docker/ directory
- Updated resource paths in configuration files

### Fixed
- Fixed circular dependency issues between core modules
- Improved error handling and reporting
- Fixed memory leaks in long-running monitors

## [0.1.0] - 2025-05-15

### Added
- Initial release of ON1Builder framework
- Support for multi-chain operations
- Mempool monitoring and transaction submission
- Market data integration
- Strategy execution framework

### Changed
- Initial codebase cleanup and refactoring
- Improved documentation and code comments
### Fixed
- Fixed initial bugs in transaction handling
- Resolved initial memory leaks in monitors                 
- Fixed initial websocket connection issues
## [2.0.1] - 2025-05-26

### Added
- Added support for new blockchain networks
- Enhanced transaction retry logic
- Improved error handling in websocket connections
### Changed
- Updated dependency versions for security and performance
### Fixed
- Fixed issues with transaction submission under high load
- Resolved websocket reconnection issues
## [2.0.0] - 2025-05-26
### Added
- Major refactor of core components
- Introduced new configuration management system


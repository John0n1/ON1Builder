# Test Organization

The tests have been organized into a structured directory hierarchy that mirrors the source code organization. This makes it easier to locate and maintain tests for specific modules.

## Directory Structure

```text
tests/
├── cli/                    # CLI module tests
│   ├── test_cli_modules.py
│   └── test_main.py
├── config/                 # Configuration module tests
│   ├── test_config_loaders.py
│   └── test_config_settings.py
├── core/                   # Core module tests
│   ├── test_chain_worker.py
│   ├── test_main_orchestrator.py
│   ├── test_multi_chain_orchestrator.py
│   ├── test_nonce_manager.py
│   └── test_transaction_manager.py
├── engines/                # Engine module tests
│   ├── test_safety_guard.py
│   └── test_strategy_executor_fixed.py
├── integrations/           # Integration module tests
│   ├── test_abi_registry.py
│   └── test_external_apis.py
├── monitoring/             # Monitoring module tests
│   ├── test_market_data_feed.py
│   └── test_txpool_scanner.py
├── persistence/            # Database/persistence tests
│   ├── test_db_interface.py
│   └── test_db_models.py
├── utils/                  # Utility module tests
│   ├── test_container.py
│   ├── test_custom_exceptions.py
│   ├── test_logging_config.py
│   ├── test_notification_service.py
│   └── test_path_helpers.py
├── functional/             # Functional and integration tests
│   ├── test_components.py
│   ├── test_functional.py
│   └── test_package_structure.py
└── legacy/                 # Legacy test files
    ├── config_cmd-test.py
    └── run_cfg-tests.py
```

## Running Tests

### Run all tests

```bash
python -m pytest tests/
```

### Run tests for a specific module

```bash
# Core module tests
python -m pytest tests/core/

# Configuration tests
python -m pytest tests/config/

# Integration tests
python -m pytest tests/integrations/
```

### Run a specific test file

```bash
python -m pytest tests/core/test_transaction_manager.py
```

### Run with coverage

```bash
python -m pytest tests/ --cov=src/on1builder --cov-report=term-missing
```

## Test Guidelines

1. **Naming Convention**: Test files should be named `test_<module_name>.py`
2. **Organization**: Tests should be placed in the directory that corresponds to their source module
3. **Structure**: Each test directory contains an `__init__.py` file to make it a proper Python package
4. **Legacy**: Old test files that don't fit the new structure are in the `legacy/` directory

## Test Coverage Status

The test suite has been significantly improved with the following coverage achievements:

- **Overall**: 47%+ coverage
- **Transaction Manager**: 50% coverage (all tests passing)
- **Main Orchestrator**: 53% coverage
- **Multi Chain Orchestrator**: 93% coverage
- **Chain Worker**: 78% coverage
- **ABI Registry**: 80% coverage
- **External APIs**: 80% coverage
- **DB Interface**: 84% coverage

All critical hanging and failing tests have been resolved, and the test suite runs reliably without manual intervention.

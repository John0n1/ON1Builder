# Tests for ON1Builder

This directory contains the test suite for ON1Builder.

## Running Tests

```bash
# Install test dependencies
pip install -e ".[test]"

# Run all tests
pytest

# Run with coverage
pytest --cov=on1builder --cov-report=html
```

## Test Structure

- `test_config/` - Configuration and settings tests
- `test_core/` - Core functionality tests
- `test_utils/` - Utility module tests
- `test_integration/` - Integration tests

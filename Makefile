# =============================================================================
# ON1Builder Development Makefile
# =============================================================================

.PHONY: help install install-dev clean lint format test coverage docs build dist upload

# Default target
help:
	@echo "ON1Builder Development Commands:"
	@echo ""
	@echo "Setup Commands:"
	@echo "  install          Install package in production mode"
	@echo "  install-dev      Install package in development mode with all dependencies"
	@echo "  clean            Clean build artifacts and caches"
	@echo ""
	@echo "Development Commands:"
	@echo "  lint             Run all linting checks (black, isort, flake8, mypy)"
	@echo "  format           Auto-format code with black and isort"
	@echo "  test             Run test suite"
	@echo "  coverage         Run tests with coverage report"
	@echo "  quick-check      Run quick checks (lint + fast tests)"
	@echo ""
	@echo "Documentation:"
	@echo "  docs             Build documentation (if available)"
	@echo ""
	@echo "Distribution:"
	@echo "  build            Build package distributions"
	@echo "  dist             Create distribution packages"
	@echo "  upload           Upload to PyPI (requires credentials)"
	@echo ""
	@echo "Utility:"
	@echo "  run-example      Run with example configuration"
	@echo "  interactive      Launch interactive console"

# Installation targets
install:
	pip install .

install-dev:
	pip install -e .[dev]
	pre-commit install

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Code quality
lint:
	@echo "Running code quality checks..."
	black --check src/ tests/ tools/
	isort --check-only src/ tests/ tools/
	flake8 src/ tests/ tools/
	mypy src/

format:
	@echo "Formatting code..."
	black src/ tests/ tools/
	isort src/ tests/ tools/

# Testing
test:
	@echo "Running test suite..."
	pytest

coverage:
	@echo "Running tests with coverage..."
	pytest --cov=on1builder --cov-report=html --cov-report=term-missing

quick-check: format lint
	@echo "Running quick tests..."
	pytest -x --tb=short -q

# Documentation
docs:
	@echo "Building documentation..."
	@echo "Documentation build not yet configured"

# Distribution
build: clean
	python -m build

dist: build
	@echo "Distribution packages created in dist/"

upload: build
	@echo "Uploading to PyPI..."
	python -m twine upload dist/*

# Utility targets
run-example:
	@echo "Running ON1Builder with example configuration..."
	python -m on1builder run --config configs/chains/ethereum_mainnet.yaml --dry-run

interactive:
	@echo "Launching interactive console..."
	python tools/ignition.py

# Development server with auto-reload
dev-server:
	@echo "Starting development server..."
	python -m on1builder run --config configs/chains/ethereum_mainnet.yaml --debug

# Check dependencies for security vulnerabilities
security:
	@echo "Checking for security vulnerabilities..."
	bandit -r src/
	safety check

# Generate requirements files
requirements:
	@echo "Generating requirements files..."
	pip-compile pyproject.toml --output-file requirements.txt
	pip-compile pyproject.toml --extra dev --output-file requirements-dev.txt

# Docker targets
docker-build:
	docker build -t on1builder:latest .

docker-run:
	docker-compose up --build

docker-clean:
	docker-compose down
	docker system prune -f

# Git hooks and commit checks
pre-commit:
	pre-commit run --all-files

commit-check: format lint test
	@echo "✅ All checks passed - ready to commit!"

# Version management
version-patch:
	bump2version patch

version-minor:
	bump2version minor

version-major:
	bump2version major

# Environment setup
setup-env:
	@echo "Setting up development environment..."
	python -m venv venv
	@echo "Virtual environment created. Activate with:"
	@echo "  source venv/bin/activate  # Linux/Mac"
	@echo "  venv\\Scripts\\activate     # Windows"
	@echo "Then run: make install-dev"

# Database operations (if using database)
db-init:
	@echo "Initializing database..."
	python -c "from src.on1builder.persistence.db_interface import create_tables; create_tables()"

db-migrate:
	@echo "Running database migrations..."
	# Add migration commands here when available

# Performance testing
perf-test:
	@echo "Running performance tests..."
	pytest tests/ -m "performance" --benchmark-only

# Integration testing
integration-test:
	@echo "Running integration tests..."
	pytest tests/integration/ -v

# Continuous Integration targets
ci-install:
	pip install -e .[test]

ci-test: ci-install
	pytest --cov=on1builder --cov-report=xml

ci-lint:
	black --check src/ tests/
	isort --check-only src/ tests/
	flake8 src/ tests/
	mypy src/

# Help with common development tasks
dev-help:
	@echo "Common development workflows:"
	@echo ""
	@echo "First time setup:"
	@echo "  make setup-env"
	@echo "  source venv/bin/activate"
	@echo "  make install-dev"
	@echo ""
	@echo "Before committing:"
	@echo "  make commit-check"
	@echo ""
	@echo "Daily development:"
	@echo "  make quick-check    # Fast feedback loop"
	@echo "  make test          # Full test suite"
	@echo "  make interactive   # Launch console"

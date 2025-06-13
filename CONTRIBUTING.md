# Contributing to ON1Builder

Thank you for your interest in contributing to ON1Builder! This document provides guidelines and information for contributors.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- A virtual environment tool (venv, conda, etc.)

### Setting up the Development Environment

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/john0n1/ON1Builder.git
   cd ON1Builder
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install the package in development mode**:
   ```bash
   pip install -e ".[dev]"
   ```

4. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

5. **Copy the example environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Development Workflow

### Before Making Changes

1. **Create a new branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Run tests to ensure everything works**:
   ```bash
   pytest
   ```

### Making Changes

1. **Write your code** following the existing style and patterns
2. **Add tests** for new functionality
3. **Update documentation** if needed
4. **Run the test suite**:
   ```bash
   pytest
   pytest --cov=on1builder --cov-report=html
   ```

5. **Run code quality checks**:
   ```bash
   black src/ tests/
   isort src/ tests/
   flake8 src/ tests/
   mypy src/
   ```

### Committing Changes

1. **Stage your changes**:
   ```bash
   git add .
   ```

2. **Commit with a descriptive message**:
   ```bash
   git commit -m "feat: add new feature description"
   ```

   Use conventional commit messages:
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation changes
   - `style:` for formatting changes
   - `refactor:` for code refactoring
   - `test:` for adding tests
   - `chore:` for maintenance tasks

3. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request** on GitHub

## Code Style and Standards

### Python Code Style

- **Black** for code formatting (line length: 100)
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

### Documentation

- Use clear, descriptive docstrings for all public functions and classes
- Follow Google-style docstrings
- Update README.md for user-facing changes
- Add inline comments for complex logic

### Testing

- Write unit tests for all new functionality
- Use pytest framework
- Aim for high test coverage (>80%)
- Write integration tests for complex features
- Mock external dependencies in tests

## Project Structure

```
ON1Builder/
├── src/on1builder/          # Main package source
│   ├── cli/                 # Command-line interface
│   ├── config/              # Configuration management
│   ├── core/                # Core application logic
│   ├── engines/             # Strategy and safety engines
│   ├── integrations/        # External API integrations
│   ├── monitoring/          # Market and mempool monitoring
│   ├── persistence/         # Database operations
│   ├── resources/           # Static resources (ABIs, tokens)
│   └── utils/              # Utility modules
├── tests/                   # Test suite
├── logs/                    # Log files directory
├── ignition.py             # Interactive launcher
├── pyproject.toml          # Project configuration
├── requirements.txt        # Dependencies
└── .env.example           # Environment configuration template
```

## Running the Application

### Using the CLI
```bash
python -m on1builder --help
python -m on1builder run start
python -m on1builder config show
python -m on1builder status check
```

### Using the Interactive Launcher
```bash
python ignition.py
```

## Adding New Features

### Adding a New Strategy
1. Create a new file in `src/on1builder/engines/`
2. Implement the strategy interface
3. Add configuration options to `settings.py`
4. Write comprehensive tests
5. Update documentation

### Adding a New Chain
1. Add chain configuration to `all_chains_tokens.json`
2. Update contract addresses in `.env.example`
3. Test with the new chain
4. Update documentation

### Adding New Integrations
1. Create integration module in `src/on1builder/integrations/`
2. Implement error handling and retries
3. Add configuration options
4. Write tests with mocked responses
5. Document the integration

## Security Considerations

- **Never commit** private keys, API keys, or sensitive data
- **Always use** environment variables for configuration
- **Validate** all external inputs
- **Use** secure communication (HTTPS/WSS) for API calls
- **Implement** proper error handling to avoid information leakage

## Performance Guidelines

- **Use async/await** for I/O operations
- **Implement** proper connection pooling
- **Cache** expensive computations when appropriate
- **Monitor** memory usage and clean up resources
- **Profile** performance-critical code paths

## Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Code Review**: All contributions go through code review

## License

By contributing to ON1Builder, you agree that your contributions will be licensed under the MIT License.

## Code of Conduct

This project follows a code of conduct to ensure a welcoming environment for all contributors. Please be respectful and professional in all interactions.

Thank you for contributing to ON1Builder! 🚀

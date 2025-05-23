# ON1Builder

ON1Builder is a multi-chain blockchain transaction framework designed for high-performance, security, and reliability. It specializes in building, signing, simulating, and dispatching MEV-style transactions across multiple blockchains.

## Key Features

- **Multi-Chain Support**: Run the framework across multiple blockchains simultaneously
- **MEV Detection**: Identify and capitalize on Miner Extractable Value opportunities
- **Transaction Simulation**: Estimate gas costs and evaluate profitability before execution
- **Real-time Alerts**: Get notified of important events via Slack and email
- **Production-Ready**: Complete with monitoring, backup, and security tools

## Quick Start

### Prerequisites

- Python 3.12 or higher
- Docker and Docker Compose (for production deployment)
- 8+ GB RAM (16+ GB recommended)
- SSD with at least 100GB free space

### Installation

```bash
# Clone the repository
git clone https://github.com/John0n1/ON1Builder.git
cd ON1Builder

# Set up the environment
cp template.env .env
# Edit .env with your configuration

# Install dependencies with Poetry (recommended)
./setup_dev.sh

# Activate virtual environment
poetry shell
```

### Running ON1Builder

```bash
# Run in single-chain mode
python -m on1builder run --config configs/chains/config.yaml

# Run in multi-chain mode
python -m on1builder run --config configs/chains/config_multi_chain.yaml
```

### Converting Markdown to HTML

ON1Builder includes a script to convert all `.md` files in the `docs` directory to HTML format.

1. Ensure you have the `markdown2` library installed:
   ```bash
   pip install markdown2
   ```

2. Run the conversion script:
   ```bash
   python scripts/convert_md_to_html.py
   ```

## Documentation

For complete documentation, visit our [Documentation Center](docs/index.md).

### User Guides

- [Getting Started Guide](docs/guides/getting_started.md)
- [Installation Guide](docs/guides/installation.md)
- [Configuration Guide](docs/guides/configuration.md)
- [Running Guide](docs/guides/running.md)
- [Monitoring Guide](docs/guides/monitoring.md)
- [Troubleshooting Guide](docs/guides/troubleshooting.md)

### Reference Docs

- [Architecture Overview](docs/reference/architecture.md)
- [API Reference](docs/reference/api.md)
- [Configuration Reference](docs/reference/configuration_reference.md)
- [Components Reference](docs/reference/components.md)
- [Glossary](docs/reference/glossary.md)

### Examples

- [Single Chain Example](docs/examples/single_chain_example.md)
- [Multi-Chain Example](docs/examples/multi_chain_example.md)
- [Custom Strategy Example](docs/examples/custom_strategy_example.md)

## Deployment Tools

The project includes several tools to help with deployment and management:

- **deploy_helper.sh**: Interactive helper for common operations
- **security_audit.sh**: Check for security issues
- **emergency_shutdown.sh**: Safe shutdown procedure
- **backup_config.sh** and **backup_data.sh**: Backup tools

## System Requirements

- Python 3.12 or higher
- Docker and Docker Compose
- 8+ GB RAM (16+ GB recommended)
- 4+ CPU cores
- SSD with at least 100GB free space

## Core Components

- **Multi-Chain Core**: Manages operations across multiple blockchains
- **Chain Workers**: Handle chain-specific transaction monitoring
- **Safety Net**: Implements protection mechanisms and fail-safes
- **Transaction Core**: Handles transaction creation, signing, and submission
- **Monitoring and Metrics**: Prometheus and Grafana integration for real-time monitoring

## Contributing

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational purposes only. Trading cryptocurrencies involves significant risk. Always test thoroughly in a sandbox environment before using in production. The authors are not responsible for any financial losses.

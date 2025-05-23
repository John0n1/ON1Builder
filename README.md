# ON1Builder 

#### ON1BUILDER is a high-performance, multi-chain blockchain transaction framework.  

#### It specializes in the construction, signing, simulation, and dispatch of MEV-style transactions across multiple blockchains, leveraging flash loans to eliminate upfront capital requirements.

- [Getting Started Guide](docs/guides/getting_started.md)
- [Installation Guide](docs/guides/installation.md)
- [Configuration Guide](docs/guides/configuration.md)
- [Running Guide](docs/guides/running.md)
- [Monitoring Guide](docs/guides/monitoring.md)
- [Troubleshooting Guide](docs/guides/troubleshooting.md)

## Key Features

- **Multi-Chain Support**: Run the framework across multiple blockchains simultaneously
- **MEV Detection**: Identify and capitalize on Miner Extractable Value opportunities
- **Transaction Simulation**: Estimate gas costs and evaluate profitability before execution
- **Real-time Alerts**: Get notified of important events via Slack and email
- **Production-Ready**: Complete with monitoring, backup, and security tools

## Quick Start
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

For complete documentation, visit our [Documentation Center](docs/index.md).

## Contributing

Please see [CONTRIBUTING.md](CONTRIBUTING)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

Trading cryptocurrencies involves significant risk. Always test thoroughly in a sandbox environment before using in production. The authors are not responsible for any financial losses.
 
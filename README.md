# ON1Builder

[![PyPI version](https://img.shields.io/pypi/v/on1builder.svg?color=green&logo=pypi&logoColor=white&style=flat)](https://pypi.org/project/on1builder/)
[![license](https://img.shields.io/badge/License-MIT-green.svg?logo=github)](LICENSE)
[![python](https://img.shields.io/badge/Python-3.12--14%2B-green.svg?logo=python&logoColor=green&style=flat)](pyproject.toml)


> **Multi-Chain MEV Transaction Execution Framework** 
> Asynchronous engine for scanning mempools, analyzing on-chain & market data, and dispatching profitable MEV trades **across any EVM chain** – complete with safety-nets, RL-powered strategy selection, and an interactive terminal experience.

⚠️ **Warning:** This project is in **alpha** development phase and undergoing rapid iteration. Expect breaking changes and incomplete features.

---

## Quick Start

The **easiest way** to enter ON1Builder Framework is through our interactive ignition system:

```bash
# 1. Clone and enter the ignition system
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder
python ignition.py
# 2. Follow the prompts:
#    - Select "Install and set up dependencies"

### Alternative (Traditional CLI)

If you prefer the traditional approach:

```bash
# 1. Setup environment
./setup_dev.sh

# 2. Run directly
on1builder run -c configs/chains/config.yaml --dry-run
```

---

## What Makes ON1Builder Special

|  Feature |  Description |
|------------|------------|
| **Auto-Setup** | One-click dependency installation, virtual environment setup, and configuration |
| **Multi-Chain** | `MultiChainCore` spawns workers per chain with shared safety & metrics |
| **MEV Strategies** | Front-run, back-run, sandwich (+ flash-loan variants) with RL-powered auto-selection |
| **Robust Safety** | `SafetyNet` with balance, gas, slippage checks + circuit-breaker alerts |
| **Real-time Monitoring** | Mempool & market monitors feeding live data to RL agents |
| **Nonce-safe** | Thread-safe nonce management under high concurrency |
| **Dynamic ABIs** | Hot-loadable JSON ABIs with automatic validation |
| **Full Persistence** | Async SQLAlchemy recording every transaction for analytics |

---

## Project Structure

```
ON1Builder/
├── ignition.py              ← MAIN ENTRY POINT
├── src/on1builder/          ← Core Python package
│   ├──  cli/                ← Command-line interfaces  
│   ├── config/             ← Configuration management
│   ├── core/                ← Main execution engines
│   ├── engines/             ← Safety, strategy, and worker engines
│   ├── integrations/        ← ABI registry & external adapters
│   ├── monitoring/          ← Mempool & market monitors
│   ├── persistence/         ← Database management
│   └── utils/              ← Logging, notifications, utilities
├── configs/                 ← Configuration templates
├── resources/              ← ABIs, contracts, token data
├── docs/                    ← Documentation
└── docker-compose.yml       ← Development environment
```

---

## Interactive Features

### Dependency Management
The ignition system automatically:
- Checks for required packages
- Installs missing dependencies
- Sets up Python virtual environments
- Configures development environment
- Provides fallback systems for missing packages

### Menu System
Navigate through beautiful terminal menus:
- **Install and set up dependencies** - One-click setup
- **Launch ON1Builder** - Start the MEV engine
- **Configure Settings** - Interactive configuration
- **View System Status** - Health checks and diagnostics
- **Manage Configuration Files** - Edit and create configs
- **View Logs** - Real-time log monitoring
- **Help & Documentation** - Built-in help system

---

## Getting Started Guide

### Method 1: (Recommended)
```bash
# Enter the Matrix
python ignition.py

# Follow the prompts:
# 1. Select "Install and set up dependencies"
# 2. Let it set up everything automatically
# 3. Configure your settings
# 4. Launch ON1Builder!
```

### Method 2: Manual Setup
```bash
# 1. Clone the repository
git clone https://github.com/john0n1/ON1Builder.git
cd ON1Builder

# 2. Run setup script
chmod +x setup_dev.sh
./setup_dev.sh

# 3. Activate virtual environment (if created)
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# 4. Install dependencies
pip install -r requirements.txt
pip install -e .

# 5. Configure your settings
cp configs/chains/example_config.yaml configs/chains/my_config.yaml
# Edit my_config.yaml with your settings

# 6. Set up environment variables
cp .env.example .env
# Edit .env with your private keys and RPC URLs

# 7. Launch via ignition (recommended)
python ignition.py

# OR launch directly
on1builder run -c configs/chains/my_config.yaml
```

---

## Configuration

Configuration is handled through:
- **YAML files** in `configs/chains/`
- **Environment variables** in `.env` (for secrets)
- **Interactive setup** via ignition.py

### Quick Config Commands
```bash
# Generate template config
on1builder config init > my_chain.yaml

# Validate configuration
on1builder config validate my_chain.yaml

# Or use the interactive system
python ignition.py
# → Select "Manage Configuration Files"
```

---

## Development

### Requirements
- **Python ≥ 3.12** 
- **Poetry** (optional, for advanced dependency management)
- **Git**

### Development Setup
```bash
# Use ignition for automatic setup
python ignition.py

# Or manual setup
poetry install --with dev
pre-commit install
pytest -q
```

### VS Code Integration
- Pre-configured settings in `.vscode/`
- Automatic Python environment detection
- Integrated debugging and testing

---

## Docker & Monitoring

```bash
# Start full stack (Grafana + Prometheus + Node)
docker compose up -d

# Access Grafana dashboard
# → http://localhost:3000
```

---

## Security & Support

- **Production keys**: Always use `.env` files; never commit secrets
- **Bug reports**: Create GitHub issues or email `security@on1.no`
- **Community**: Join our Discord at [https://discord.gg/on1builder](https://discord.gg/on1builder)
- **Security issues**: Use GPG key in [SECURITY.md](SECURITY.md)

---

## Contributing

We welcome contributions!

1. Fork the repository
2. Use `python ignition.py` to set up your development environment
3. Create a feature branch
4. Make your changes
5. Run tests via ignition system
6. Submit a pull request

---

## License

```

MIT © 2025 John0n1/ON1Builder
See LICENSE for full terms
```

---

*"There is no spoon... only profitable MEV opportunities."* 🥄


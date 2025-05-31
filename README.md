# ON1Builder 
*Multi-Chain MEV Transaction Execution Framework*  



- [Getting Started Guide](docs/guides/getting_started.md)
- [Installation Guide](docs/guides/installation.md)
- [Configuration Guide](docs/guides/configuration.md)
- [Running Guide](docs/guides/running.md)
- [Monitoring Guide](docs/guides/monitoring.md)
- [Troubleshooting Guide](docs/guides/troubleshooting.md)
> ⚠️ **Warning:** This project is in **alpha** development phase and undergoing rapid iteration. Expect breaking changes and incomplete features.

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![docs](https://img.shields.io/badge/docs-gh--pages-success.svg)](https://john0n1.github.io/ON1Builder/)


> Asynchronous, production-ready engine for scanning mempools, analyzing on-chain
> & market data, and dispatching profitable MEV trades **across any EVM chain** –
> with first-class safety-nets, RL-powered strategy selection, pluggable ABIs and
> a fully async SQL persistence layer.

## Key Features
| Category | Highlights |
|----------|------------|
| **Multi-Chain** | `MultiChainCore` spawns a *worker* per chain with shared safety & metrics. |
| **MEV Strategies** | Front-run, back-run, sandwich (+ flash-loan variants) – auto-selected by `StrategyNet` (ε-greedy with reward shaping). |
| **Robust Safety** | `SafetyNet` enforces balance, gas, value, slippage, duplicate-tx & dynamic congestion checks – activates circuit-breaker + alerting. |
| **Mempool & Markets** | `TxpoolMonitor` filters pending txs; `MarketMonitor` streams price / volume / volatility; both feed the RL agent. |
| **Nonce-safe** | `NonceCore` guarantees sequential, thread-safe nonces even under high concurrency. |
| **Dynamic ABIs** | Hot-loads JSON ABIs, validates required functions, maps 4-byte selectors. |
| **Persistence** | `DatabaseManager` (SQLAlchemy async) records every tx & profit for dashboards (Grafana/Prometheus configs shipped). |
| **Pluggable** | Ultra-light DI `Container` for circular deps, plus clean module boundaries. |

---

## Project Layout
```

src/on1builder/               ← main Python package
├── cli/                      ← Typer & argparse entrypoints
├── config/                   ← Configuration helpers (YAML + .env)
├── core/                     ← Main/MultiChain/Nonce/Transaction cores
├── engines/                  ← SafetyNet, ChainWorker, StrategyNet …
├── integrations/             ← ABI registry + external adapters
├── monitoring/               ← Txpool & market monitors
├── persistence/              ← DatabaseManager (async SQLAlchemy)
└── utils/                    ← Logger, notifications, DI container, …
resources/                    ← ABIs, Solidity contracts, tokens, ML data
configs/                      ← Example YAMLs, Grafana & Prometheus bundles
docs/                         ← Sphinx docs (rendered at gh-pages)
setup_dev.sh                  ← one-liner dev bootstrap
setup.py                      ← setup 
README.md                     ← you-are-here
pyproject.toml                ← Poetry build / deps
requirements.txt              ← slim runtime-only requirements

````

---

## Quick Start

```bash
# 1. clone & enter
git clone https://github.com/john0n1/ON1Builder.git && cd ON1Builder

# 2. bootstrap (installs Poetry + venv + deps + .env)
./scripts/setup_dev.sh

# 3. dry-run on a single chain
on1builder run -c configs/chains/config.yaml --dry-run

# 4. go multi-chain (reads chains:[] list in YAML)
on1builder run --multi-chain

# 5. mempool / market monitor only
on1builder monitor --chain ethereum
````

**Configuration** lives in YAML (`configs/chains/*.yaml`) + `.env`.
Generate a template with:

```bash
on1builder config init > my_chain.yaml
```

Validate before boot:

```bash
on1builder config validate my_chain.yaml
```

---

## CLI Usage

| Command                                | Purpose                                   |
| -------------------------------------- | ----------------------------------------- |
| `on1builder run …`                     | start the full bot (default single chain) |
| `on1builder run --multi-chain`         | read multiple chains and launch workers   |
| `on1builder monitor …`                 | run only Market + Txpool monitors         |
| `on1builder config validate file.yaml` | static YAML sanity-check                  |

See `on1builder --help` for all flags.

---

## Developer Guide

### 1 · Environment

* **Python ≥ 3.12** (async-friendly).
* Install extras for lint/test:

  ```bash
  poetry install --with dev
  ```

### 2 · Pre-Commit

```bash
pre-commit install   # black, isort, flake8, mypy on every commit
```

### 3 · Tests

```bash
pytest -q  # async-aware tests live in tests/
```

### 4 · Docs Live-Reload

```bash
cd docs
make livehtml  # → http://127.0.0.1:8000
```

### 5 · Docker Compose (Node + Prometheus + Grafana)

```bash
docker compose up -d
```

Connect Grafana → `http://localhost:3000` (dashboard config shipped at `configs/grafana/`).

### 6 · VS Code

`.vscode/settings.json` already points to Poetry venv, sets `python.analysis.typeCheckingMode` to *strict*.

---

## Security & Support

* **Production keys**: always load via `.env`; never commit secrets.
* Bug / security issue? Email `security@on1.no` *(GPG key in SECURITY.md)*.
* Join the Discord: [https://discord.gg/on1builder](https://discord.gg/on1builder) – channels #dev and #mev-strategies.

---

## License

> MIT © 2025 John0n1/ON1Builder – contributions welcome!
> See [LICENSE](LICENSE) for full text.


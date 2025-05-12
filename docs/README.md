# ON1Builder

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**ON1Builder is a sophisticated, production-grade, multi-chain Maximum Extractable Value (MEV) trading bot designed for Ethereum Mainnet and Polygon Mainnet (and easily configurable for others). It incorporates advanced features like secure secret management, comprehensive monitoring, automated strategies, and robust deployment practices.**

**Note:** This bot interacts with real cryptocurrency markets and involves significant financial risk. Use at your own discretion and risk.

## Documentation

- [Deployment Guide](docs/DEPLOYMENT.md)
- [Security Guidelines](docs/SECURITY.md)
- [Post-Deployment Checklist](docs/post_deployment_checklist.md)

## Project Structure

```
ON1Builder/
├── config/                   # Configuration files
│   ├── config.yaml          # Main configuration
│   ├── config_multi_chain.yaml  # Multi-chain configuration
│   └── template.env         # Environment template
├── contracts/               # Smart contracts
│   ├── IERC20.sol
│   └── SimpleFlashloan.sol
├── dashboards/             # Grafana dashboards
│   └── on1builder-multi-chain-dashboard.json
├── data/                   # Data files
│   ├── abi/               # Contract ABIs
│   │   ├── aave_flashloan_abi.json
│   │   ├── aave_pool_abi.json
│   │   ├── erc20_abi.json
│   │   ├── gas_price_oracle_abi.json
│   │   ├── sushiswap_abi.json
│   │   └── uniswap_abi.json
│   ├── ml/                # Machine Learning files
│   │   ├── price_model.joblib
│   │   └── training_data.csv
│   ├── erc20_signatures.json
│   ├── token_addresses.json
│   └── token_symbols.json
├── deploy/                 # Deployment scripts
│   ├── build_and_push.sh
│   ├── cron_setup.sh
│   ├── deploy_prod.sh
│   ├── deploy_prod_multi_chain.sh
│   ├── vault_init.sh
│   └── vault_init_multi_chain.sh
├── docs/                   # Documentation
│   ├── DEPLOYMENT.md
│   ├── SECURITY.md
│   ├── architecture.md
│   ├── flow_old.svg
│   └── post_deployment_checklist.md
├── scripts/               # Python source code
│   └── python/           # Python modules
│       ├── abi_registry.py
│       ├── api_config.py
│       ├── app.py
│       ├── app_multi_chain.py
│       ├── chain_worker.py
│       ├── configuration.py
│       ├── configuration_multi_chain.py
│       ├── logger_on1.py
│       ├── main.py
│       ├── main_core.py
│       ├── main_multi_chain.py
│       ├── market_monitor.py
│       ├── multi_chain_core.py
│       ├── nonce_core.py
│       ├── safety_net.py
│       ├── strategy_net.py
│       ├── transaction_core.py
│       ├── txpool_monitor.py
│       └── pyutils/
│           ├── __init__.py
│           └── strategyexecutionerror.py
├── tests/                 # Test files
│   ├── test_abiregistry.py
│   ├── test_apiconfig.py
│   └── ...
└── ui/                    # User interface files
    └── index.html
```

[Previous content continues unchanged...]

Okay, this is a significant refactoring task. Let's design a new, cleaner repository structure and create a detailed migration plan.

## Proposed New Repository Structure:

```
on1builder/
├── .github/
│   ├── FUNDING.yml
│   ├── dependabot.yml
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.yml
│       └── feature_request.yml
├── .gitignore
├── Dockerfile
├── LICENSE
├── README.md
├── configs/                             # User-facing configurations
│   ├── common_settings.yaml             # Global defaults, API keys (via env vars)
│   ├── chains/
│   │   ├── ethereum_mainnet.yaml        # Example chain-specific config
│   │   └── polygon_mainnet.yaml         # Example chain-specific config
│   └── .env.example                     # Moved here for clarity
├── docker-compose.yml
├── pyproject.toml                       # Single source of truth for dependencies & project metadata
├── scripts/
│   └── setup_dev_environment.sh         # Renamed and refined setup script
├── src/
│   └── on1builder/                      # Main application package
│       ├── __init__.py
│       ├── __main__.py                  # Main CLI entry point
│       ├── cli/                         # CLI command modules
│       │   ├── __init__.py
│       │   ├── config_cmd.py
│       │   ├── run_cmd.py
│       │   └── status_cmd.py
│       ├── config/                      # Configuration loading and models
│       │   ├── __init__.py
│       │   ├── loaders.py               # Logic for loading YAML, env vars
│       │   └── settings.py              # Pydantic models for typed configuration
│       ├── core/                        # Core application logic
│       │   ├── __init__.py
│       │   ├── chain_worker.py
│       │   ├── main_orchestrator.py     # Renamed from main_core.py
│       │   ├── multi_chain_orchestrator.py # Renamed from multi_chain_core.py
│       │   ├── nonce_manager.py
│       │   └── transaction_manager.py
│       ├── engines/                     # Business logic engines
│       │   ├── __init__.py
│       │   ├── safety_guard.py          # Renamed from safety_net.py
│       │   └── strategy_executor.py     # Renamed from strategy_net.py
│       ├── integrations/                # External service interactions
│       │   ├── __init__.py
│       │   ├── abi_registry.py
│       │   └── external_apis.py         # For CoinGecko, Etherscan, etc.
│       ├── monitoring/                  # Data monitoring services
│       │   ├── __init__.py
│       │   ├── market_data_feed.py      # Renamed from market_monitor.py
│       │   └── txpool_scanner.py        # Renamed from txpool_monitor.py
│       ├── persistence/                 # Database interaction
│       │   ├── __init__.py
│       │   ├── db_interface.py          # Renamed from db_manager.py
│       │   └── db_models.py             # SQLAlchemy models
│       ├── resources/                   # Static data files (ABIs, token lists)
│       │   ├── abi/
│       │   │   ├── erc20.json
│       │   │   ├── aave_v3_pool.json    # Corrected Aave Pool ABI
│       │   │   └── uniswap_v2_router.json # Example
│       │   ├── tokens/
│       │   │   └── all_chains_tokens.json # Consolidated token data
│       │   └── ml_models/               # For strategy weights if ML-based
│       │       └── strategy_weights.json
│       ├── strategies/                  # (Optional) For pluggable strategy modules
│       │   ├── __init__.py
│       │   ├── base_strategy.py
│       │   └── examples/
│       │       └── example_arbitrage_strategy.py
│       └── utils/                       # Common utilities
│           ├── __init__.py
│           ├── container.py
│           ├── custom_exceptions.py     # e.g., StrategyExecutionError
│           ├── logging_config.py
│           ├── notification_service.py  # Renamed from notifications.py
│           └── path_helpers.py          # For consistent path resolution
├── tests/                               # Unit and integration tests
│   ├── __init__.py
│   ├── conftest.py
│   ├── integration/
│   └── unit/
└── tools/                               # Developer tools, helper scripts
    └── ignition_launcher.py             # Interactive launcher (ignition.py moved here)

```

## Detailed Full Migration Plan Checklist:

**Phase 0: Preparation & Setup**

1.  [ ] **Backup Repository:** Create a full backup of the current repository.
2.  [ ] **New Branch:** Create a new Git branch for this major refactoring (e.g., `refactor/repo-structure`).
3.  [ ] **Tooling:** Ensure you have tools for mass search/replace (e.g., `grep`, `sed`, IDE features).

**Phase 1: Dependency Management & Basic Structure**

4.  [ ] **Consolidate Dependencies (`pyproject.toml`):**
    *   [ ] Edit `pyproject.toml`.
    *   [ ] Ensure `[tool.poetry.dependencies]` contains *all* runtime dependencies:
        `python`, `aiohttp`, `aiosqlite`, `attrs`, `cachetools`, `eth-account`, `eth-hash`, `eth-keyfile`, `eth-keys`, `eth-rlp`, `eth-typing`, `eth-utils`, `eth_abi`, `joblib` (if used), `numpy` (if used), `pandas` (if used), `pydantic`, `psutil`, `python-dotenv`, `sqlalchemy`, `web3`, `typer`, `pyyaml`, `questionary`, `rich` (if `ignition_launcher.py` uses it).
    *   [ ] Remove `asyncio` from any dependency list (it's built-in).
    *   [ ] Ensure `[tool.poetry.group.dev.dependencies]` is correct.
    *   [ ] Remove the `[project.dependencies]` section if it's redundant with `[tool.poetry.dependencies]`. Poetry uses `[tool.poetry.dependencies]`.
5.  [ ] **Cleanup `setup.py`:**
    *   [ ] Delete `install_requires=[...]` from `./setup.py`. Poetry handles this.
    *   [ ] Keep `setup.py` minimal if needed for `setuptools` compatibility or specific `entry_points`. Poetry can often generate this. If not needed, plan to remove it later.
6.  [ ] **Handle `requirements.txt`:**
    *   [ ] Delete the existing `./requirements.txt`.
    *   [ ] If needed for specific Docker builds (that don't use multi-stage Poetry builds), generate it later using `poetry export -f requirements.txt --output requirements.txt --without-hashes`.
7.  [ ] **Create New Top-Level Directories:**
    *   [ ] `mkdir scripts`
    *   [ ] `mkdir -p src/on1builder` (if `src` layout isn't already used)
    *   [ ] `mkdir tests` (if not present)
    *   [ ] `mkdir docs` (if not present)
    *   [ ] `mkdir examples` (if not present)
    *   [ ] `mkdir tools`
8.  [ ] **Move/Rename `setup_dev.sh`:**
    *   [ ] Delete the first (top) duplicated version of the script content in `./setup_dev.sh`.
    *   [ ] Retain only the second, cleaner version (starting `# setup_dev.sh — bootstrap development environment for ON1Builder`).
    *   [ ] `mv ./setup_dev.sh ./scripts/setup_dev_environment.sh`
    *   [ ] Review `scripts/setup_dev_environment.sh`:
        *   [ ] Simplify Poetry installation logic (the single `curl ... | python3 -` is good).
        *   [ ] Ensure PATH updates are handled cleanly.
        *   [ ] Ensure Poetry commands use `python3 -m poetry` for consistency if `poetry` isn't directly on PATH initially.
9.  [ ] **Move `.env.example`:**
    *   [ ] `mv ./.env.example ./configs/.env.example`
10. [ ] **Move `ignition.py`:**
    *   [ ] `mv ./ignition.py ./tools/ignition_launcher.py`

**Phase 2: `src/on1builder` Directory Refactoring**

11. [ ] **Create `src/on1builder` Subdirectories:**
    *   [ ] `cd src/on1builder`
    *   [ ] `mkdir cli core engines integrations monitoring persistence resources utils strategies` (as per new structure)
    *   [ ] `mkdir resources/abi resources/tokens resources/ml_models`
    *   [ ] `cd ../..` (back to project root)
12. [ ] **Migrate `config` Module:**
    *   [ ] `mv ./src/on1builder/config/__init__.py ./src/on1builder/config/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/config/__init__.py`.
    *   [ ] Create `src/on1builder/config/loaders.py`.
        *   [ ] Move YAML and environment variable loading logic from `config/config.py::Configuration` here.
    *   [ ] Create `src/on1builder/config/settings.py`.
        *   [ ] Define Pydantic models for configuration structures (e.g., `ChainSettings`, `GlobalSettings`, `APISettings`). This replaces the `Configuration` class's `__getattr__` and direct dict manipulation.
    *   [ ] Delete `src/on1builder/config/config.py`.
    *   [ ] Delete `src/on1builder/config/configuration.py`.
13. [ ] **Migrate `core` Module:**
    *   [ ] `mv ./src/on1builder/core/__init__.py ./src/on1builder/core/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/core/__init__.py`.
    *   [ ] `mv ./src/on1builder/core/main_core.py ./src/on1builder/core/main_orchestrator.py`
    *   [ ] `mv ./src/on1builder/core/multi_chain_core.py ./src/on1builder/core/multi_chain_orchestrator.py`
    *   [ ] `mv ./src/on1builder/engines/chain_worker.py ./src/on1builder/core/chain_worker.py` (moved from engines)
    *   [ ] `mv ./src/on1builder/core/transaction_core.py ./src/on1builder/core/transaction_manager.py`
    *   [ ] `mv ./src/on1builder/core/nonce_core.py ./src/on1builder/core/nonce_manager.py`
14. [ ] **Migrate `engines` Module:**
    *   [ ] `mv ./src/on1builder/engines/__init__.py ./src/on1builder/engines/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/engines/__init__.py`.
    *   [ ] `mv ./src/on1builder/engines/safety_net.py ./src/on1builder/engines/safety_guard.py`
    *   [ ] `mv ./src/on1builder/engines/strategy_net.py ./src/on1builder/engines/strategy_executor.py`
15. [ ] **Migrate `integrations` Module:**
    *   [ ] `mv ./src/on1builder/integrations/__init__.py ./src/on1builder/integrations/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/integrations/__init__.py`.
    *   [ ] `mv ./src/on1builder/integrations/abi_registry.py ./src/on1builder/integrations/abi_registry.py` (stays)
    *   [ ] Create `src/on1builder/integrations/external_apis.py`.
        *   [ ] Move `APIConfig` class from old `config/config.py` here. Rename it to `ExternalAPIManager` or similar.
        *   [ ] Refactor it to remove direct config attribute access; it should be initialized with API keys/settings.
16. [ ] **Migrate `monitoring` Module:**
    *   [ ] `mv ./src/on1builder/monitoring/__init__.py ./src/on1builder/monitoring/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/monitoring/__init__.py`.
    *   [ ] `mv ./src/on1builder/monitoring/market_monitor.py ./src/on1builder/monitoring/market_data_feed.py`
    *   [ ] `mv ./src/on1builder/monitoring/txpool_monitor.py ./src/on1builder/monitoring/txpool_scanner.py`
17. [ ] **Migrate `persistence` Module:**
    *   [ ] `mv ./src/on1builder/persistence/__init__.py ./src/on1builder/persistence/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/persistence/__init__.py`.
    *   [ ] `mv ./src/on1builder/persistence/db_manager.py ./src/on1builder/persistence/db_interface.py`
    *   [ ] Create `src/on1builder/persistence/db_models.py`.
        *   [ ] Move SQLAlchemy models (`Transaction`, `ProfitRecord`) from `db_interface.py` here.
18. [ ] **Migrate `utils` Module:**
    *   [ ] `mv ./src/on1builder/utils/__init__.py ./src/on1builder/utils/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/utils/__init__.py`.
    *   [ ] `mv ./src/on1builder/utils/logger.py ./src/on1builder/utils/logging_config.py`
    *   [ ] `mv ./src/on1builder/utils/notifications.py ./src/on1builder/utils/notification_service.py`
    *   [ ] `mv ./src/on1builder/utils/container.py ./src/on1builder/utils/container.py` (stays)
    *   [ ] Create `src/on1builder/utils/custom_exceptions.py`.
        *   [ ] Move `StrategyExecutionError` from `utils/strategyexecutionerror.py` here.
        *   [ ] Delete `src/on1builder/utils/strategyexecutionerror.py`.
    *   [ ] Create `src/on1builder/utils/path_helpers.py` (for BASE_DIR, config paths, resource paths).
19. [ ] **Migrate `cli` Module:**
    *   [ ] `mv ./src/on1builder/cli/__init__.py ./src/on1builder/cli/__init__.py_old` (if exists)
    *   [ ] Create `src/on1builder/cli/__init__.py`.
    *   [ ] `mv ./src/on1builder/cli/config.py ./src/on1builder/cli/config_cmd.py`
    *   [ ] Create `src/on1builder/cli/run_cmd.py`.
        *   [ ] Extract `run_command` logic from `src/on1builder/__main__.py`.
    *   [ ] Create `src/on1builder/cli/status_cmd.py`.
        *   [ ] Extract `status_command` logic from `src/on1builder/__main__.py`.
    *   [ ] Refactor `src/on1builder/__main__.py` to import and register these command modules with its main Typer app.
20. [ ] **Update `__init__.py` Files:**
    *   [ ] Review and update all `__init__.py` files in `src/on1builder` and its subdirectories to reflect new module names and desired public exports.
    *   [ ] Specifically, `src/on1builder/__init__.py` should expose the main application object and key classes for external use if any.

**Phase 3: Resource and Configuration File Migration**

21. [ ] **Consolidate Token Data:**
    *   [ ] Create `src/on1builder/resources/tokens/all_chains_tokens.json`.
    *   [ ] Design a unified schema for this file (e.g., a list of token objects, each with `symbol`, `name`, and a dictionary of `addresses: {<chain_id>: <address>}`, `decimals`).
    *   [ ] Merge data from all `resources/tokens/chainid-1/*.json` files into `all_chains_tokens.json`.
    *   [ ] Update `integrations/abi_registry.py` (or a new `TokenRegistry` class) to load from this consolidated file and provide necessary lookup methods.
    *   [ ] `rm -rf ./resources/tokens/chainid-1` (or old token paths).
22. [ ] **Refine ABI Files:**
    *   [ ] Move ABIs from `./resources/abi/` to `src/on1builder/resources/abi/`.
    *   [ ] Ensure `uniswap_abi.json` only contains the `abi` array.
    *   [ ] Verify/correct `aave_pool_abi.json` to be the actual Aave V3 Pool ABI (not a proxy). If it's a proxy, rename it (e.g., `aave_v3_pool_proxy.json`). Get the implementation ABI too.
    *   [ ] Verify/correct `aave_flashloan_abi.json`. If it's for a custom receiver, rename it. The Aave V3 Pool ABI will have the `flashLoan` function.
23. [ ] **Migrate Strategy Weights:**
    *   [ ] Move `resources/ml_data/strategy_weights.json` (if this is the file used by `StrategyNet`) to `src/on1builder/resources/ml_models/strategy_weights.json`.
    *   [ ] Update `engines/strategy_executor.py` (formerly `StrategyNet`) to load weights from this new path, using `path_helpers.py` for robust path construction.
24. [ ] **Standardize YAML Configurations (`./configs/`):**
    *   [ ] Define a clear, consistent structure for `configs/common_settings.yaml` (for global defaults, API key *placeholders* to be filled by env vars).
    *   [ ] Define a structure for chain-specific configs in `configs/chains/` (e.g., `ethereum_mainnet.yaml`). This should primarily contain RPC endpoints, chain ID, specific contract addresses for that chain.
    *   [ ] Refactor `config/loaders.py` to load `common_settings.yaml` first, then the specified chain config(s), then override with environment variables.
    *   [ ] Migrate settings from old `configs/chains/config.yaml`, `config_multi_chain.yaml`, and `example_config.yaml` into the new structure.
    *   [ ] `rm ./configs/chains/config.yaml ./configs/chains/config_multi_chain.yaml ./configs/chains/example_config.yaml`
25. [ ] **Update `Dockerfile` and `docker-compose.yml`:**
    *   [ ] Adjust paths for copied files (e.g., `configs`, `src`).
    *   [ ] Change `docker-compose.yml` `command` from `python ignition.py` to `on1builder run --config /app/configs/chains/your_prod_config.yaml ...` or the appropriate command to run the main application.
    *   [ ] Ensure `PYTHONPATH` is correctly set if needed (e.g., `PYTHONPATH=/app/src`).

**Phase 4: Code Refactoring & Fixes (Iterative)**

26. [ ] **Update All Import Statements:** This is a major, systematic task. Go through every Python file and update imports to reflect the new structure and filenames.
    *   Example: `from on1builder.core.main_core import MainCore` -> `from on1builder.core.main_orchestrator import MainOrchestrator`
    *   Example: `from src.on1builder import ...` -> `from on1builder import ...` (assuming `src` is added to `PYTHONPATH` or handled by Poetry).
27. [ ] **Address `ignition_launcher.py` Issues:**
    *   [ ] Fix console usage (global vs. instance).
    *   [ ] Ensure NOP fallbacks for logger/container if `ON1BUILDER_AVAILABLE` is false.
    *   [ ] Make launch command use `on1builder` entry point: `cmd = ["on1builder", "run", ...]`.
    *   [ ] Make `stty size` cross-platform or use a library like `shutil.get_terminal_size()`.
    *   [ ] Remove dependency self-installation (`install_required_packages`); this is handled by `setup_dev_environment.sh` / Poetry.
28. [ ] **Address `ABIRegistry` (`integrations/abi_registry.py`):**
    *   [ ] Refactor to avoid module-level global state for instances/caches. If a singleton is desired, the `get_registry()` function should manage it properly.
    *   [ ] Fix synchronous file I/O in async methods (`get_token_address`, `get_token_symbol`) using `asyncio.to_thread` or by loading all token data into memory at initialization.
    *   [ ] Ensure robust handling of non-ABI JSON files in the ABI directory (e.g., by stricter naming conventions or content checks).
29. [ ] **Address `TransactionManager` (formerly `TransactionCore`):**
    *   [ ] Ensure `simulate_transaction` checksums `tx["to"]`.
    *   [ ] Make Aave contract addresses configurable per chain.
    *   [ ] Implement actual flashloan deployment/availability checks or clearly mark them as placeholders.
30. [ ] **Address `MainOrchestrator` (formerly `MainCore`):**
    *   [ ] Simplify ABI registry path logic; rely on `ABIRegistry` itself or `path_helpers.py`.
    *   [ ] Simplify token loading for `TxPoolScanner` (use `TokenRegistry`/`AbiRegistry`).
31. [ ] **Address `ExternalAPIManager` (formerly `APIConfig`):**
    *   [ ] Refactor `_create_api_id_mappings` to be less hardcoded if possible, or document it as needing manual updates.
    *   [ ] Ensure token mappings are loaded consistently (sync or async, not both).
32. [ ] **Address `StrategyExecutor` (formerly `StrategyNet`):**
    *   [ ] Resolve missing attributes (`current_profit`, `last_gas_used`) by adding them to `TransactionManager` or changing how rewards are calculated.
    *   [ ] Ensure strategy weights path uses `path_helpers.py`.
33. [ ] **Path Management Centralization:**
    *   [ ] Implement `utils/path_helpers.py` to provide functions like `get_base_dir()`, `get_config_dir()`, `get_resource_path()`.
    *   [ ] Update all file path constructions throughout the codebase to use these helpers.
34. [ ] **Error Handling Review:**
    *   [ ] Replace overly broad `except Exception: pass` with specific exceptions and logging.
35. [ ] **Review and Fix Logic Issues:** Systematically go through the issues identified in the initial analysis and apply the planned fixes.

**Phase 5: Testing & Finalization**

36. [ ] **Run Linters and Formatters:** Use `black`, `isort`, `flake8` (as defined in `pyproject.toml`).
37. [ ] **Write/Update Unit Tests:** Create tests for new/refactored modules in the `tests/` directory. Ensure existing tests pass.
38. [ ] **Write/Update Integration Tests:** Verify interactions between components.
39. [ ] **Manual Testing:**
    *   [ ] Run `scripts/setup_dev_environment.sh`.
    *   [ ] Run `tools/ignition_launcher.py`.
    *   [ ] Test CLI commands: `on1builder run ...`, `on1builder status`, `on1builder config validate ...`.
40. [ ] **Update `README.md`:**
    *   [ ] Reflect new directory structure.
    *   [ ] Update setup and usage instructions.
41. [ ] **Update `.gitignore`:** Add any new build artifacts, cache files, or IDE files.
42. [ ] **Remove Old Files/Folders:**
    *   [ ] Delete any `*_old.py` files.
    *   [ ] Delete `merged_code_and_configs.txt`.
    *   [ ] `rm -rf ./src/on1builder/config` (old folder if new one is created alongside) and similar for other refactored modules, once content is fully migrated.
43. [ ] **Review GitHub Specific Files:**
    *   [ ] In `.github/dependabot.yml`, change `target-branch: "master"` to `main` if applicable.
44. [ ] **Final Code Review:** Review all changes on the refactoring branch.
45. [ ] **Merge Branch:** Merge the refactoring branch into the main development branch.

This checklist is extensive but aims to be comprehensive. It's best to tackle it in stages, committing changes frequently. Good luck!
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Multi-chain blockchain transaction execution framework
==================================================================

A high-performance framework for building, signing, simulating, and dispatching
blockchain transactions across multiple chains, with a focus on MEV strategies.

This package provides tools for:
- Multi-chain transaction management
- Mempool monitoring
- Market data analysis
- Price prediction and MEV opportunity detection
- Transaction safety verification
- Gas optimization
- Strategy execution
- Performance monitoring

==========================
License: MIT
==========================
"""

__title__ = "on1builder"
__description__ = "Multi-chain blockchain transaction execution framework"
__url__ = "https://github.com/john0n1/ON1Builder"
__version_info__ = (2, 1, 1)
__version__ = "2.1.2"
__author__ = "john0n1"
__author_email__ = "john@on1.no"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2025 John0n1"

# Expose top-level components
# CLI imports (require all dependencies)
try:
    from .__main__ import app as cli
    from .cli.config_cmd import app as config_cli
except ImportError:
    cli = None
    config_cli = None

from .config.loaders import load_configuration
from .config.settings import ChainSettings, GlobalSettings, MultiChainSettings
from .core.chain_worker import ChainWorker
from .core.main_orchestrator import MainOrchestrator
from .core.multi_chain_orchestrator import MultiChainOrchestrator
from .core.nonce_manager import NonceManager
from .core.transaction_manager import TransactionManager
from .engines.safety_guard import SafetyGuard
from .engines.strategy_executor import StrategyExecutor
from .integrations.abi_registry import ABIRegistry
from .integrations.external_apis import ExternalAPIManager
from .monitoring.market_data_feed import MarketDataFeed
from .monitoring.txpool_scanner import TxPoolScanner
from .persistence.db_interface import DatabaseInterface
from .persistence.db_models import ProfitRecord, Transaction
from .utils.container import Container
from .utils.custom_exceptions import StrategyExecutionError
from .utils.logging_config import get_logger, setup_logging
from .utils.notification_service import NotificationService
from .utils.path_helpers import get_base_dir, get_config_dir, get_resource_path

__all__ = [
    "cli",
    "config_cli",
    "GlobalSettings",
    "ChainSettings",
    "MultiChainSettings",
    "load_configuration",
    "MainOrchestrator",
    "MultiChainOrchestrator",
    "TransactionManager",
    "NonceManager",
    "ChainWorker",
    "SafetyGuard",
    "StrategyExecutor",
    "TxPoolScanner",
    "MarketDataFeed",
    "DatabaseInterface",
    "Transaction",
    "ProfitRecord",
    "ABIRegistry",
    "ExternalAPIManager",
    "setup_logging",
    "get_logger",
    "NotificationService",
    "StrategyExecutionError",
    "Container",
    "get_base_dir",
    "get_config_dir",
    "get_resource_path",
]

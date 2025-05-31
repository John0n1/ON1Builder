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
__version_info__ = (2, 1, 0)
__version__ = "2.1.0"
__author__ = "john0n1"
__author_email__ = "john@on1.no"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2025 John0n1"

# Expose top-level components
from on1builder.__main__ import app as cli
from on1builder.cli.config import app as config_cli
from on1builder.config.config import Configuration, MultiChainConfiguration, APIConfig
from on1builder.core.main_core import MainCore
from on1builder.core.multi_chain_core import MultiChainCore
from on1builder.core.transaction_core import TransactionCore
from on1builder.core.nonce_core import NonceCore
from on1builder.engines.chain_worker import ChainWorker
from on1builder.engines.safety_net import SafetyNet
from on1builder.engines.strategy_net import StrategyNet
from on1builder.monitoring.txpool_monitor import TxpoolMonitor
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.persistence.db_manager import DatabaseManager, get_db_manager
from on1builder.integrations.abi_registry import get_registry as get_abi_registry
from on1builder.utils.logger import setup_logging
from on1builder.utils.notifications import send_alert
from on1builder.utils.strategyexecutionerror import StrategyExecutionError

__all__ = [
    "cli",  
    "config_cli",
    "Configuration",
    "MultiChainConfiguration",
    "APIConfig",
    "MainCore",
    "MultiChainCore",
    "TransactionCore",
    "NonceCore",
    "ChainWorker",
    "SafetyNet",
    "StrategyNet",
    "TxpoolMonitor",
    "MarketMonitor",
    "DatabaseManager",
    "get_db_manager",
    "get_abi_registry",
    "setup_logging",
    "send_alert",
    "StrategyExecutionError",
]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Entry Point
========================
Main entry point for the ON1Builder application.
Loads configuration, bootstraps either single-chain or multi-chain cores,
and handles graceful shutdown on SIGINT/SIGTERM.

This module provides the primary CLI interface and application bootstrap process,
coordinating the loading of configurations, environment variables, and core components.

==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from dotenv import load_dotenv
# Load root .env early so Option defaults (e.g. LOG_LEVEL) can use it
load_dotenv()

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
from on1builder.integrations.abi_registry import ABIRegistry, get_registry
from on1builder.utils.logger import setup_logging, get_logger, bind_logger_context
from on1builder.utils.container import Container, get_container
from on1builder.utils.notifications import NotificationManager, get_notification_manager, send_alert
from on1builder.utils.strategyexecutionerror import StrategyExecutionError

# -----------------------------------------------------------------------------
# CLI setup
# -----------------------------------------------------------------------------
# Export the Typer app for use in other modules
app = typer.Typer(help="ON1Builder – blockchain transaction framework")

# Get main logger
logger = get_logger(__name__)


async def _run(
    config_path: Path,
    env_file: Path,
    multi_chain: bool,
) -> None:
    """
    Internal runner: loads env, constructs config & core, runs until signal.
    
    Args:
        config_path: Path to the configuration file
        env_file: Path to the .env file with environment variables
        multi_chain: Whether to use multi-chain mode
    """
    # 1) Load .env if present
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment from {env_file}")

    # 2) Setup container for dependency management
    container = get_container()
    logger.debug("Initialized dependency container")

    # 3) Instantiate configuration and core
    if multi_chain:
        logger.info("Starting in multi-chain mode")
        config = MultiChainConfiguration(str(config_path), str(env_file))
        core = MultiChainCore(config)
    else:
        logger.info("Starting in single-chain mode")
        config = Configuration(str(config_path), str(env_file))
        core = MainCore(config)
        
    # 4) Initialize database manager and ABI registry
    # Initialize database manager using config
    db_manager = get_db_manager(config)
    # Ensure DB schema is created
    await db_manager.initialize()
    container.register("db_manager", db_manager)
    logger.debug("Initialized and registered DatabaseManager")
    # Initialize ABI registry
    abi_registry = await get_registry()
    container.register("abi_registry", abi_registry)
    logger.debug("Initialized and registered ABIRegistry")

    # 5) Register core in container for shared access
    container.register_main_core(core)
    container.register("config", config)
    logger.debug("Registered core and config in dependency container")
    
    
    # 8) Setup notification manager
    notification_mgr = get_notification_manager(config, core)
    if notification_mgr:
        container.register("notification_manager", notification_mgr)
        logger.debug("Notification system initialized")

    # 9) Setup graceful shutdown
    loop = asyncio.get_running_loop()
    stop_evt = asyncio.Event()

    def _on_signal():
        logger.info("Shutdown signal received")
        # Send notification of shutdown if possible
        try:
            asyncio.create_task(
                notification_mgr.send_notification(
                    "ON1Builder shutting down", 
                    level="INFO", 
                    details={"reason": "Signal received"}
                )
            )
        except Exception:
            pass
        stop_evt.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    # 10) Run core until signal
    run_task = asyncio.create_task(core.run())
    await stop_evt.wait()
    
    # 11) Graceful shutdown of all components
    logger.info("Starting graceful shutdown sequence...")
    
    # Stop core first
    logger.info("Stopping core...")
    await core.stop()
    
    # Stop all registered components in reverse order
    logger.info("Stopping all components...")
    await container.stop_all_components()
    
    # Wait for run task to complete
    await run_task
    logger.info("Shutdown complete")


@app.command("run")
def run_command(
    config: Path = typer.Option(
        Path("configs/chains/config.yaml"),
        "--config",
        "-c",
        help="Path to configuration YAML",
    ),
    multi_chain: bool = typer.Option(
        False, "--multi-chain", "-m", help="Enable multi-chain mode"
    ),
    env_file: Path = typer.Option(
        Path(".env"), "--env", "-e", help="Path to .env file"
    ),
    log_level: str = typer.Option(
        os.getenv("LOG_LEVEL", "INFO"),
        "--log-level", "-l",
        help="Logging level (DEBUG, INFO, WARNING, ERROR), defaults to LOG_LEVEL env"
    ),
    metrics_enabled: bool = typer.Option(
        True, "--metrics/--no-metrics", help="Enable/disable metrics collection"
    ),
    json_logs: bool = typer.Option(
        False, "--json-logs", help="Output logs in JSON format for easier parsing"
    ),
    monitoring_enabled: bool = typer.Option(
        True, "--monitoring/--no-monitoring", help="Enable/disable monitoring components"
    ),
    notifications_enabled: bool = typer.Option(
        True, "--notifications/--no-notifications", help="Enable/disable notifications"
    ),
    strategy_validation: bool = typer.Option(
        True, "--validate-strategies/--no-validate-strategies", 
        help="Enable/disable strategy validation on startup"
    ),
):
    """
    Run the ON1Builder bot in either single or multi-chain mode.
    
    This is the main entry point for running the ON1Builder application.
    It loads configuration, sets up logging, initializes the core,
    and manages the application lifecycle.
    
    The application can run in single-chain mode (default) or multi-chain mode,
    with various components enabled or disabled based on configuration options.
    """
    # Adjust root logger level
    level = getattr(logging, log_level.upper(), None)
    if not isinstance(level, int):
        logger.warning(f"Unknown log level '{log_level}', defaulting to INFO")
        level = logging.INFO
    
    # Configure root logger and all ON1Builder loggers
    # Use JSON formatting if requested
    setup_logging("ON1Builder", level=level, use_json=json_logs)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Set log level for all on1builder loggers
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith('on1builder'):
            logging.getLogger(logger_name).setLevel(level)
    
    # Display startup banner
    logger.info("=" * 80)
    logger.info(f"Starting ON1Builder {'Multi-Chain' if multi_chain else 'Single-Chain'} Mode")
    logger.info(f"Config: {config}")
    logger.info(f"Environment: {env_file}")
    logger.info(f"Log Level: {log_level}")
    logger.info(f"JSON Logs: {'Enabled' if json_logs else 'Disabled'}")
    logger.info(f"Metrics: {'Enabled' if metrics_enabled else 'Disabled'}")
    logger.info(f"Monitoring: {'Enabled' if monitoring_enabled else 'Disabled'}")
    logger.info(f"Notifications: {'Enabled' if notifications_enabled else 'Disabled'}")
    logger.info(f"Strategy Validation: {'Enabled' if strategy_validation else 'Disabled'}")
    logger.info("=" * 80)
    
    # Ensure config path exists (warn, but proceed if not)
    if not config.exists():
        logger.warning(f"Configuration file not found: {config}")
        logger.warning("Will attempt to use default configuration")
    
    # Store settings in environment for components to access
    os.environ["ON1_METRICS_ENABLED"] = str(metrics_enabled).lower()
    os.environ["ON1_MONITORING_ENABLED"] = str(monitoring_enabled).lower()
    os.environ["ON1_NOTIFICATIONS_ENABLED"] = str(notifications_enabled).lower()
    os.environ["ON1_STRATEGY_VALIDATION"] = str(strategy_validation).lower()
    
    try:
        # Run the application
        asyncio.run(_run(config, env_file, multi_chain))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except StrategyExecutionError as e:
        logger.error(f"Strategy execution error: {e}")
        if hasattr(e, 'to_dict'):
            logger.error(f"Error details: {e.to_dict()}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        # Print exception details in debug mode
        if log_level.upper() == "DEBUG":
            import traceback
            logger.debug(traceback.format_exc())
        
        # Try to send error alert if notifications are enabled
        if notifications_enabled:
            try:
                asyncio.run(
                    send_alert(
                        f"CRITICAL ERROR: {e}", 
                        level="CRITICAL",
                        details={"error": str(e), "traceback": traceback.format_exc()}
                    )
                )
            except Exception:
                pass
        
        sys.exit(1)


@app.command("status")
def status_command(
    config: Path = typer.Option(
        Path("configs/chains/config.yaml"),
        "--config",
        "-c",
        help="Path to configuration YAML",
    ),
    env_file: Path = typer.Option(
        Path(".env"), "--env", "-e", help="Path to .env file"
    ),
):
    """
    Check the status of ON1Builder components and connections.
    
    This command performs a diagnostic check of all components,
    verifies connections to blockchain nodes, databases,
    and ensures all required dependencies are available.
    """
    logger.info("=" * 80)
    logger.info("ON1Builder Status Check")
    logger.info("=" * 80)
    
    # Load environment variables
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment from {env_file}")
    
    # Check config file
    if config.exists():
        logger.info(f"Configuration file found: {config}")
        try:
            # Attempt to load config to verify syntax
            cfg = Configuration(str(config), str(env_file))
            logger.info("Configuration file syntax is valid")
            
            # Display some basic config info
            logger.info(f"Chain ID: {cfg.chain_id}")
            logger.info(f"Web3 Provider: {cfg.web3_provider}")
        except Exception as e:
            logger.error(f"Configuration file has errors: {e}")
    else:
        logger.error(f"Configuration file not found: {config}")
    
    # Check database connections
    try:
        # Use loaded cfg for database manager
        db_manager = get_db_manager(cfg)
        db_status = db_manager.check_connection()
        logger.info(f"Database connection: {'OK' if db_status else 'FAILED'}")
    except Exception as e:
        logger.error(f"Database manager error: {e}")
    
    # Check ABI registry
    try:
        # get_registry is async; run in event loop
        abi_registry = asyncio.run(get_registry())
        # Count loaded ABIs
        abi_count = len(getattr(abi_registry, 'abis', {}))
        logger.info(f"ABI Registry: OK ({abi_count} ABIs available)")
    except Exception as e:
        logger.error(f"ABI Registry error: {e}")
    
    # Strategy listing not implemented in CLI status
    logger.debug("Strategy listing not available in status command")
    
    logger.info("=" * 80)
    logger.info("Status check complete")
    logger.info("=" * 80)


def main():
    """
    Main entry point when executed directly from the command line.
    
    This is the function that gets called by the console_scripts entry point
    defined in setup.py. It initializes the CLI application and passes control
    to the Typer framework.
    """
    # Set package version in Typer app
    from on1builder import __version__
    app.info.version = __version__
    
    # Run the Typer app
    app()


if __name__ == "__main__":
    main()

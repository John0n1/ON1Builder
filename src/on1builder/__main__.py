#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Entry Point
========================
Main entry point for the ON1Builder application.
Loads configuration, bootstraps either single-chain or multi-chain cores,
and handles graceful shutdown on SIGINT/SIGTERM.
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv

from on1builder.config.config import Configuration, MultiChainConfiguration
from on1builder.core.main_core import MainCore
from on1builder.core.multi_chain_core import MultiChainCore
from on1builder.utils.logger import setup_logging

# -----------------------------------------------------------------------------
# CLI setup
# -----------------------------------------------------------------------------
# Export the Typer app for use in other modules
app = typer.Typer(help="ON1Builder – blockchain transaction framework")

logger = setup_logging("ON1Builder", level="INFO")


async def _run(
    config_path: Path,
    env_file: Path,
    multi_chain: bool,
) -> None:
    """
    Internal runner: loads env, constructs config & core, runs until signal.
    """
    # 1) Load .env if present
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment from {env_file}")

    # 2) Instantiate config
    if multi_chain:
        logger.info("Starting in multi-chain mode")
        config = MultiChainConfiguration(str(config_path), str(env_file))
        core: Any = MultiChainCore(config)
    else:
        logger.info("Starting in single-chain mode")
        config = Configuration(str(config_path), str(env_file))
        core = MainCore(config)

    # 3) Setup graceful shutdown
    loop = asyncio.get_running_loop()
    stop_evt = asyncio.Event()

    def _on_signal():
        logger.info("Shutdown signal received")
        stop_evt.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    # 4) Run core until signal
    run_task = asyncio.create_task(core.run())
    await stop_evt.wait()
    logger.info("Stopping core...")
    await core.stop()
    await run_task


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
        "INFO", "--log-level", "-l", help="Logging level (DEBUG, INFO, WARNING…)"),
):
    """
    Run the ON1Builder bot (single- or multi-chain).
    """
    # Adjust root logger level
    level = getattr(logging, log_level.upper(), None)
    if not isinstance(level, int):
        logger.warning(f"Unknown log level '{log_level}', defaulting to INFO")
        level = logging.INFO
    logging.getLogger().setLevel(level)

    # Ensure config path exists (warn, but proceed if not)
    if not config.exists():
        logger.warning(f"Configuration file not found: {config}")

    asyncio.run(_run(config, env_file, multi_chain))


def main():
    """
    Main entry point when executed directly from the command line.
    This is the function that gets called by the console_scripts entry point.
    """
    app()

if __name__ == "__main__":
    main()

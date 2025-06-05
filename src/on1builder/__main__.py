#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Main CLI Entry Point
==================================

Main command-line interface for the ON1Builder application.
Provides commands for running, configuring, and monitoring ON1Builder.

License: MIT
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

# Import CLI modules
from .cli.config_cmd import app as config_app
from .cli.run_cmd import app as run_app
from .cli.status_cmd import status_command
from .utils.logging_config import get_logger, setup_logging

# Create main app
app = typer.Typer(
    name="on1builder",
    help="ON1Builder - Multi-chain blockchain transaction execution framework",
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
)

# Add sub-commands
app.add_typer(config_app, name="config")
app.add_typer(run_app, name="run")
app.command(name="status")(status_command)


@app.callback()
def main(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    log_file: Optional[Path] = typer.Option(None, "--log-file", help="Log file path"),
) -> None:
    """ON1Builder - Multi-chain blockchain transaction execution framework."""
    # Setup logging
    log_level = "DEBUG" if debug else ("INFO" if verbose else "WARNING")
    log_dir = str(log_file.parent) if log_file else None
    setup_logging(name="on1builder", level=log_level, log_dir=log_dir)

    logger = get_logger(__name__)
    logger.debug(f"ON1Builder CLI started with log level: {log_level}")


@app.command()
def version() -> None:
    """Show version information."""
    from . import __description__, __title__, __version__

    typer.echo(f"{__title__} v{__version__}")
    typer.echo(__description__)


def cli() -> None:
    """Entry point for the CLI when installed as a package."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\nOperation cancelled by user.", err=True)
        sys.exit(1)
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Unexpected error: {e}")
        typer.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()

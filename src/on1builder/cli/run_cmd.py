#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import asyncio

import typer

from on1builder.core.main_orchestrator import MainOrchestrator
from on1builder.utils.cli_helpers import handle_cli_errors, info_message
from on1builder.utils.logging_config import get_logger

logger = get_logger(__name__)
app = typer.Typer(help="Commands to run the ON1Builder bot.")


@app.command(name="start")
@handle_cli_errors(show_traceback=True)
def start_bot():
    """
    Initializes and starts the ON1Builder main application.
    This command boots the orchestrator and runs until interrupted.
    """
    logger.info("CLI: 'start' command invoked.")

    orchestrator = MainOrchestrator()
    asyncio.run(orchestrator.run())

    logger.debug("ON1Builder has shut down.")
    info_message("Goodbye!")

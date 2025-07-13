# src/on1builder/cli/run_cmd.py
from __future__ import annotations

import asyncio
import sys

import typer

from on1builder.core.main_orchestrator import MainOrchestrator
from on1builder.utils.custom_exceptions import InitializationError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.cli_helpers import handle_cli_errors, info_message

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
    
    logger.info("ON1Builder has shut down.")
    info_message("Goodbye!")
# src/on1builder/cli/run_cmd.py
from __future__ import annotations

import asyncio
import sys

import typer

from on1builder.core.main_orchestrator import MainOrchestrator
from on1builder.utils.custom_exceptions import InitializationError
from on1builder.utils.logging_config import get_logger

logger = get_logger(__name__)
app = typer.Typer(help="Commands to run the ON1Builder bot.")

@app.command(name="start")
def start_bot():
    """
    Initializes and starts the ON1Builder main application.
    This command boots the orchestrator and runs until interrupted.
    """
    logger.info("CLI: 'start' command invoked.")
    
    try:
        orchestrator = MainOrchestrator()
        asyncio.run(orchestrator.run())
    except InitializationError as e:
        logger.critical(f"A critical component failed to initialize, which prevents the application from starting: {e}", exc_info=True)
        typer.secho(f"FATAL ERROR: Could not start the application. {e}", fg=typer.colors.RED, err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Application shutdown requested by user (Ctrl+C).")
        typer.echo("\nShutting down gracefully...")
    except Exception as e:
        logger.critical(f"An unexpected fatal error occurred during startup or runtime: {e}", exc_info=True)
        typer.secho(f"UNEXPECTED FATAL ERROR: {e}", fg=typer.colors.RED, err=True)
        sys.exit(1)
        
    logger.info("ON1Builder has shut down.")
    typer.echo("Goodbye!")
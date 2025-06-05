"""
Run command for ON1Builder CLI.
"""

import asyncio
from typing import Optional

import typer

from ..config.loaders import load_configuration
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

app = typer.Typer()


@app.command()
def run(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Configuration file path"
    ),
    chain: Optional[str] = typer.Option(None, "--chain", help="Chain to run on"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
):
    """Run the ON1Builder main application."""
    logger.info(
        f"Starting ON1Builder with config: {config}, chain: {chain}, debug: {debug}"
    )

    try:
        # Load configuration
        config_data = load_configuration(config_path=config, chain=chain)

        # Import and use the main orchestrator
        if config_data.get("multi_chain", False):
            from ..core.multi_chain_orchestrator import MultiChainOrchestrator

            orchestrator = MultiChainOrchestrator(config=config_data)
        else:
            from ..core.main_orchestrator import MainOrchestrator

            orchestrator = MainOrchestrator(config=config_data)

        # Run the orchestrator
        asyncio.run(orchestrator.run())

    except Exception as e:
        logger.error(f"Failed to run ON1Builder: {e}")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

"""
Status command for ON1Builder CLI.
"""

from typing import Optional

import typer

from ..config.loaders import load_configuration
from ..persistence.db_interface import DatabaseInterface
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

app = typer.Typer()


@app.command()
def status(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Configuration file path"
    ),
    chain: Optional[str] = typer.Option(
        None, "--chain", help="Chain to check status for"
    ),
):
    """Check the status of ON1Builder components."""
    logger.info(f"Checking status with config: {config}, chain: {chain}")

    try:
        # Load configuration
        config_data = load_configuration(config_path=config, chain=chain)

        typer.echo("=== ON1Builder Status ===")

        # Check database connectivity
        try:
            db = DatabaseInterface(config_data.get("database", {}))
            typer.echo("✓ Database: Connected")
        except Exception as e:
            typer.echo(f"✗ Database: Failed ({e})")

        # Check RPC endpoints
        rpc_url = config_data.get("rpc_url")
        if rpc_url:
            typer.echo(f"✓ RPC URL: {rpc_url}")
            # TODO: Actually test the RPC connection
        else:
            typer.echo("✗ RPC URL: Not configured")

        # Show chain info
        chain_id = config_data.get("chain_id")
        if chain_id:
            typer.echo(f"✓ Chain ID: {chain_id}")
        else:
            typer.echo("✗ Chain ID: Not configured")

        typer.echo("Status check completed")

    except Exception as e:
        logger.error(f"Failed to check status: {e}")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

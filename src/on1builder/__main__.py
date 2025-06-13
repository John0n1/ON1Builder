# src/on1builder/__main__.py
from __future__ import annotations

import typer
import sys

from on1builder.cli.config_cmd import app as config_app
from on1builder.cli.run_cmd import app as run_app
from on1builder.cli.status_cmd import app as status_app
from on1builder.utils.logging_config import get_logger, setup_logging

app = typer.Typer(
    name="on1builder",
    help="A high-performance, multi-chain MEV and trading bot framework.",
    add_completion=False,
    no_args_is_help=True
)

app.add_typer(run_app, name="run")
app.add_typer(config_app, name="config")
app.add_typer(status_app, name="status")

@app.command(name="version")
def show_version():
    """Displays the application version."""
    from on1builder import __version__
    typer.echo(f"ON1Builder Version: {__version__}")

def cli():
    """Main function to run the Typer application."""
    try:
        # The logger is initialized when the logging_config module is imported.
        # This ensures logging is set up before any command runs.
        app()
    except Exception as e:
        # This is a final catch-all for unexpected errors.
        logger = get_logger("main")
        logger.critical(f"CLI terminated with an unhandled exception: {e}", exc_info=True)
        typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED, err=True)
        sys.exit(1)

if __name__ == "__main__":
    cli()
# src/on1builder/cli/config_cmd.py
# flake8: noqa E501
from __future__ import annotations

import json
import typer
from rich.console import Console
from rich.syntax import Syntax

from on1builder.config.loaders import settings, load_settings
from on1builder.utils.custom_exceptions import ConfigurationError
from on1builder.utils.config_redactor import ConfigRedactor
from on1builder.utils.cli_helpers import handle_cli_errors, success_message

app = typer.Typer(help="Commands to inspect and validate configuration.")
console = Console()


@app.command(name="show")
@handle_cli_errors()
def show_config(
    show_keys: bool = typer.Option(
        False, "--show-keys", "-s", help="Show sensitive keys like WALLET_KEY."
    )
):
    """
    Displays the currently loaded configuration, redacting sensitive values by default.
    """
    # Pydantic models have a method to dump to a dict
    config_dict = settings.model_dump(mode="json")

    # Use the ConfigRedactor utility to handle sensitive data redaction
    redacted_config = ConfigRedactor.redact_config(config_dict, show_sensitive=show_keys)

    # Pretty print the JSON using rich
    json_str = json.dumps(redacted_config, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(syntax)


@app.command(name="validate")
@handle_cli_errors()
def validate_config():
    """
    Validates the current .env configuration by attempting to load it.
    Reports any validation errors found by Pydantic.
    """
    console.print("Validating configuration from .env file...")
    # The act of loading the settings performs the validation
    load_settings()
    success_message("Configuration is valid!")

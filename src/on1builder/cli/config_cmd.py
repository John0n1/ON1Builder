# src/on1builder/cli/config_cmd.py
from __future__ import annotations

import json
import typer
from rich.console import Console
from rich.syntax import Syntax

from on1builder.config.loaders import settings, load_settings
from on1builder.utils.custom_exceptions import ConfigurationError

app = typer.Typer(help="Commands to inspect and validate configuration.")
console = Console()

@app.command(name="show")
def show_config(
    show_keys: bool = typer.Option(False, "--show-keys", "-s", help="Show sensitive keys like WALLET_KEY.")
):
    """
    Displays the currently loaded configuration, redacting sensitive values by default.
    """
    try:
        # Pydantic models have a method to dump to a dict
        config_dict = settings.model_dump(mode='json')
        
        if not show_keys:
            if "wallet_key" in config_dict:
                config_dict["wallet_key"] = "[REDACTED]"
            if "api" in config_dict:
                for key in config_dict["api"]:
                    if "key" in key or "token" in key:
                         config_dict["api"][key] = "[REDACTED]"
            if "notifications" in config_dict and "smtp_password" in config_dict["notifications"]:
                config_dict["notifications"]["smtp_password"] = "[REDACTED]"

        # Pretty print the JSON using rich
        json_str = json.dumps(config_dict, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
        console.print(syntax)

    except Exception as e:
        console.print(f"[bold red]Error displaying configuration:[/] {e}")
        raise typer.Exit(code=1)

@app.command(name="validate")
def validate_config():
    """
    Validates the current .env configuration by attempting to load it.
    Reports any validation errors found by Pydantic.
    """
    console.print("🔍 Validating configuration from .env file...")
    try:
        # The act of loading the settings performs the validation
        load_settings()
        console.print("[bold green]✅ Configuration is valid![/]")
    except (ConfigurationError, ValueError) as e:
        console.print(f"[bold red]❌ Configuration validation failed![/]")
        console.print(f"   [red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]❌ An unexpected error occurred during validation:[/] {e}")
        raise typer.Exit(code=1)
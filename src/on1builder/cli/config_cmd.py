#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.syntax import Syntax

from on1builder.config.loaders import load_settings, settings
from on1builder.utils.cli_helpers import (
    confirm_action,
    handle_cli_errors,
    info_message,
    resolve_editor_command,
    success_message,
)
from on1builder.utils.config_redactor import ConfigRedactor
from on1builder.utils.custom_exceptions import ConfigurationError

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
    redacted_config = ConfigRedactor.redact_config(
        config_dict, show_sensitive=show_keys
    )

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


@app.command(name="init-env")
@handle_cli_errors()
def init_env(
    edit: bool = typer.Option(
        True,
        "--edit/--no-edit",
        help="Open the .env file in an editor after creation.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite an existing .env file."
    ),
    editor: str | None = typer.Option(
        None,
        "--editor",
        help="Editor command (defaults to $VISUAL/$EDITOR, nano, or notepad on Windows).",
    ),
):
    """
    Create a .env from .env.example and optionally open it for editing.
    """
    cwd = Path.cwd()
    env_example = cwd / ".env.example"
    env_path = cwd / ".env"

    if not env_example.exists():
        raise ConfigurationError(
            "Could not find .env.example in the current directory."
        )

    if env_path.exists() and not force:
        overwrite = confirm_action(
            ".env already exists. Overwrite it with .env.example?", default=False
        )
        if overwrite:
            shutil.copyfile(env_example, env_path)
            success_message("Overwrote .env from .env.example.")
        else:
            info_message("Keeping existing .env.")
    else:
        shutil.copyfile(env_example, env_path)
        success_message("Created .env from .env.example.")

    if edit:
        command = resolve_editor_command(editor)
        try:
            subprocess.run([*command, str(env_path)], check=False)
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"Editor '{command[0]}' not found. Set --editor or $EDITOR."
            ) from exc

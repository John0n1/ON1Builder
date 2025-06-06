#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – CLI Configuration Management
=========================================
Configuration management commands for ON1Builder.
==========================
License: MIT
==========================
This module provides commands to validate, show, and manage configurations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import typer
import yaml

from ..utils.logging_config import get_logger

logger = get_logger(__name__)
app = typer.Typer(name="config", help="Configuration management commands")


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file and return its contents as a dict."""
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        typer.secho(f"❌ YAML parsing error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("validate")
def validate_command(
    config_path: Path = typer.Argument(
        Path("configs/common_settings.yaml"),
        exists=True,
        readable=True,
        help="Path to the YAML configuration file to validate",
    ),
    chain_config: Optional[Path] = typer.Option(
        None, "--chain", "-c", help="Path to chain-specific configuration file"
    ),
    multi_chain: bool = typer.Option(
        False, "--multi-chain", "-m", help="Validate as multi-chain configuration"
    ),
) -> None:
    """
    Validate ON1Builder YAML configuration files.

    Checks:
      - File exists and is valid YAML
      - Top-level structure is a mapping
      - Required fields are present
      - Chain-specific configurations are valid
    """
    try:
        # Load main configuration
        config = _load_yaml(config_path)

        if not isinstance(config, dict):
            typer.secho(
                "❌ Configuration root must be a mapping (dictionary).",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        # Load chain configuration if provided
        if chain_config:
            chain_cfg = _load_yaml(chain_config)
            if not isinstance(chain_cfg, dict):
                typer.secho(
                    "❌ Chain configuration root must be a mapping (dictionary).",
                    fg=typer.colors.RED,
                )
                raise typer.Exit(code=1)

        errors: list[str] = []

        # Validate main configuration structure
        if multi_chain:
            # Multi-chain validation
            chains = config("chains", [])
            if not chains:
                errors.append("Multi-chain config must have 'chains' section")

            for i, chain in enumerate(chains):
                if not isinstance(chain, dict):
                    errors.append(f"Chain #{i}: must be a dictionary")
                    continue

                # Check required fields for each chain
                required_fields = ["chain_id", "rpc_url"]
                for field in required_fields:
                    if field not in chain:
                        errors.append(f"Chain #{i}: missing required field '{field}'")
        else:
            # Single chain validation
            if chain_config:
                # Validate chain-specific config
                required_fields = ["chain_id", "rpc_url"]
                for field in required_fields:
                    if field not in chain_cfg:
                        errors.append(f"Chain config: missing required field '{field}'")

        if errors:
            for err in errors:
                typer.secho(f"❌ {err}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        typer.secho(f"✅ Configuration is valid.", fg=typer.colors.GREEN)

    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        typer.secho(f"❌ Validation failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@app.command("show")
def show_command(
    config_path: Path = typer.Argument(
        Path("configs/common_settings.yaml"),
        exists=True,
        readable=True,
        help="Path to the configuration file to display",
    )
) -> None:
    """Display configuration file contents."""
    try:
        config = _load_yaml(config_path)
        typer.echo(yaml.dump(config, default_flow_style=False, indent=2))
    except Exception as e:
        logger.error(f"Failed to show configuration: {e}")
        typer.secho(f"❌ Failed to show config: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

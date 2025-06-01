#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – CLI Configuration Validation
=========================================
Validate ON1Builder YAML configuration files.
==========================
License: MIT
==========================
This module provides a `validate` command to check the syntax and
required sections/keys of your ON1Builder config.
"""

from __future__ import annotations
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import yaml
import typer

# Import the ON1Builder configuration if available
try:
    from on1builder.config.config import Configuration
except ImportError:
    # Handle case where module imports are not available
    pass

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
        Path("configs/chains/config.yaml"),
        exists=True,
        readable=True,
        help="Path to the YAML configuration file to validate",
    ),
    multi_chain: bool = typer.Option(
        False, "--multi-chain", "-m", help="Validate as multi-chain configuration"
    )
) -> None:
    """
    Validate an ON1Builder YAML configuration file.

    Checks:
      - File exists and is valid YAML
      - Top-level structure is a mapping
      - Required endpoints are present (HTTP_ENDPOINT or WEBSOCKET_ENDPOINT)
      - If multi-chain, validates the chains section structure
    """
    config = _load_yaml(config_path)

    if not isinstance(config, dict):
        typer.secho("❌ Configuration root must be a mapping (dictionary).", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    # Check if this is a multi-chain config
    if multi_chain or "chains" in config:
        # Validate multi-chain structure
        raw_chains = config.get("chains")
        if raw_chains is None:
            typer.secho("❌ Missing required top-level section: 'chains' for multi-chain config.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        if not isinstance(raw_chains, list) or not raw_chains:
            typer.secho("❌ 'chains' must be a non-empty list.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        errors: list[str] = []
        for i, chain_cfg in enumerate(raw_chains):
            if not isinstance(chain_cfg, dict):
                errors.append(f"Chain #{i}: configuration must be a mapping.")
                continue
                
            # Check for required endpoints
            has_endpoint = False
            for key in ("HTTP_ENDPOINT", "WEBSOCKET_ENDPOINT", "IPC_ENDPOINT"):
                if key in chain_cfg and chain_cfg[key]:
                    has_endpoint = True
                    break
                    
            if not has_endpoint:
                errors.append(f"Chain #{i}: missing required endpoint (HTTP_ENDPOINT, WEBSOCKET_ENDPOINT, or IPC_ENDPOINT)")
                
            # Check for CHAIN_ID
            if "CHAIN_ID" not in chain_cfg:
                errors.append(f"Chain #{i}: missing required CHAIN_ID.")

    if errors:
        for err in errors:
            typer.secho(f"❌ {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"✅ Configuration file '{config_path}' is valid.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()

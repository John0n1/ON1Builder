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
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
import typer

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
    )
) -> None:
    """
    Validate an ON1Builder YAML configuration file.

    Checks:
      - File exists and is valid YAML
      - Top-level structure is a mapping
      - Contains a non-empty `chains` section (or `CHAINS`)
      - Each chain entry is a mapping with required keys `rpc_url` and `chain_id`
    """
    config = _load_yaml(config_path)

    if not isinstance(config, dict):
        typer.secho("❌ Configuration root must be a mapping (dictionary).", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Accept either 'chains' or uppercase 'CHAINS'
    raw_chains = config.get("chains") or config.get("CHAINS")
    if raw_chains is None:
        typer.secho("❌ Missing required top-level section: 'chains'.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not isinstance(raw_chains, dict) or not raw_chains:
        typer.secho("❌ 'chains' must be a non-empty mapping.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    errors: list[str] = []
    for name, chain_cfg in raw_chains.items():
        if not isinstance(chain_cfg, dict):
            errors.append(f"Chain '{name}': configuration must be a mapping.")
            continue
        for key in ("rpc_url", "chain_id"):
            if key not in chain_cfg:
                errors.append(f"Chain '{name}': missing required key '{key}'.")

    if errors:
        for err in errors:
            typer.secho(f"❌ {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"✅ Configuration file '{config_path}' is valid.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()

# CLI Tools Module

This directory contains utility tools for the ON1Builder command line interface.

## Contents

- `config.py`: Configuration validation tools and commands
- `__init__.py`: Module exports

## Usage

The main command-line interface for the application is implemented in `src/on1builder/__main__.py` using Typer.
This CLI module provides additional utility tools that can be used by the main CLI.

To validate a configuration:

```python
from on1builder.cli import validate_command
validate_command("/path/to/config.yaml")
```

Or via the CLI:

```bash
python -m on1builder config validate /path/to/config.yaml
```

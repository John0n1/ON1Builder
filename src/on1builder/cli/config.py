"""
CLI configuration validation module
"""

import os
import sys
import yaml
from typing import Optional

try:
    import typer
    HAS_TYPER = True
    app = typer.Typer(help="Configuration management commands")
except ImportError:
    HAS_TYPER = False


def validate_config(config_path: str) -> bool:
    """
    Validate a configuration file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        True if the configuration is valid, False otherwise
    """
    if not os.path.exists(config_path):
        print(f"Error: Configuration file {config_path} not found")
        return False
        
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Validate basic structure
        if not isinstance(config, dict):
            print("Error: Configuration must be a dictionary")
            return False
            
        # Check for required sections
        required_sections = ["chains"]
        for section in required_sections:
            if section not in config:
                print(f"Error: Required section '{section}' not found in configuration")
                return False
                
        # Check chains section
        chains = config.get("chains", {})
        if not isinstance(chains, dict) or not chains:
            print("Error: 'chains' section must be a non-empty dictionary")
            return False
            
        # Validate each chain config
        for chain_name, chain_config in chains.items():
            if not isinstance(chain_config, dict):
                print(f"Error: Configuration for chain '{chain_name}' must be a dictionary")
                return False
                
            # Check for required chain configuration keys
            required_chain_keys = ["rpc_url", "chain_id"]
            for key in required_chain_keys:
                if key not in chain_config:
                    print(f"Error: Required key '{key}' not found in configuration for chain '{chain_name}'")
                    return False
        
        print(f"✅ Configuration file {config_path} is valid")
        return True
        
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {str(e)}")
        return False
    except Exception as e:
        print(f"Error validating configuration: {str(e)}")
        return False


if HAS_TYPER:
    @app.command("validate")
    def validate_command(config_path: str = typer.Argument(..., help="Path to configuration file")):
        """Validate a configuration file."""
        valid = validate_config(config_path)
        if not valid:
            sys.exit(1)
else:
    def validate_command_legacy(args):
        """Legacy validation command handling."""
        config_path = args[0] if args else "configs/chains/config.yaml"
        valid = validate_config(config_path)
        if not valid:
            sys.exit(1)

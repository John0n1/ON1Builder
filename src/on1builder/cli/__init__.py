"""
Command-line interface module for ON1Builder.

This module provides the CLI functionality for the application.
"""

from typing import Dict, Any, List, Optional
import argparse
import sys
import os

__all__ = ["parse_args", "run_command", "monitor_command"]


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="ON1Builder - Multi-chain transaction framework")
    
    # Main command groups
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the ON1Builder system")
    run_parser.add_argument("--config", "-c", help="Path to config file", default="config/config.yaml")
    run_parser.add_argument("--multi-chain", "-m", action="store_true", help="Use multi-chain mode")
    run_parser.add_argument("--dry-run", "-d", action="store_true", help="Run in simulation mode without executing transactions")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Start the monitoring system only")
    monitor_parser.add_argument("--chain", help="Chain ID to monitor", required=True)
    monitor_parser.add_argument("--config", "-c", help="Path to config file", default="config/config.yaml")
    
    return parser.parse_args(args)


async def run_command(args: argparse.Namespace) -> int:
    """Run the ON1Builder system."""
    # Import here to avoid circular imports
    from on1builder.__main__ import run_async
    
    try:
        config_path = args.config
        multi_chain = args.multi_chain
        dry_run = args.dry_run
        
        # Run the bot with the specified configuration
        await run_async(config_path=config_path, 
                      multi_chain=multi_chain, 
                      dry_run=dry_run)
        return 0
    except Exception as e:
        print(f"Error running ON1Builder: {str(e)}")
        return 1


async def monitor_command(args: argparse.Namespace) -> int:
    """Start the monitoring system only."""
    # Import here to avoid circular imports
    from on1builder.__main__ import monitor_async
    
    try:
        config_path = args.config
        chain = args.chain
        
        # Start the monitoring system only
        await monitor_async(config_path=config_path, chain=chain)
        return 0
    except Exception as e:
        print(f"Error starting monitoring system: {str(e)}")
        return 1
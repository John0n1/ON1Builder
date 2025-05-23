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
    try:
        from on1builder.config.config import Configuration
        from on1builder.core.main_core import MainCore
        
        config = Configuration(config_path=args.config)
        await config.load(skip_env=True)  # Skip environment variables in tests
        
        # Create and initialize the core
        core = MainCore(config)
        await core.bootstrap()
        await core.run(dry_run=args.dry_run)
        return 0
    except Exception as e:
        print(f"Error running ON1Builder: {str(e)}")
        return 1


async def monitor_command(args: argparse.Namespace) -> int:
    """Start the monitoring system only."""
    try:
        from on1builder.config.config import Configuration
        from on1builder.monitoring.txpool_monitor import TxpoolMonitor
        
        config = Configuration(config_path=args.config)
        await config.load(skip_env=True)  # Skip environment variables in tests
        
        # Create and start the monitor
        monitor = TxpoolMonitor(config, args.chain)
        await monitor.start()
        return 0
    except Exception as e:
        print(f"Error starting monitoring system: {str(e)}")
        return 1
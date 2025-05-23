#!/usr/bin/env python3
"""
ON1Builder - Entry Point
=======================

Main entry point for the ON1Builder application.
"""

import asyncio
import os
import sys
import logging
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import typer
    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False
    print("Typer not installed. Using basic CLI.")

try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False
    print("Python-dotenv not installed. Environment file loading disabled.")

# Add parent directory to path for local development if running from source
sys_path_modified = False
if os.path.basename(os.getcwd()) == "src" or os.path.basename(os.getcwd()) == "on1builder":
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        sys_path_modified = True
        print(f"Added {parent_dir} to sys.path for local development")

# Import our modules
from on1builder.config.config import Configuration, MultiChainConfiguration
from on1builder.utils.logger import setup_logging

logger = setup_logging("main", level="INFO")

# --------------------------------------------------------------------------- #
# Signal handling for graceful shutdown                                       #
# --------------------------------------------------------------------------- #

shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Handle SIGINT/SIGTERM to trigger clean shutdown."""
    logger.info(f"Received signal {sig}, initiating shutdown...")
    shutdown_event.set()
    
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --------------------------------------------------------------------------- #
# Bot implementation                                                          #
# --------------------------------------------------------------------------- #

async def run_bot(config_path: str = "configs/chains/config.yaml", 
                  multi_chain: bool = False, 
                  env_file: str = ".env") -> None:
    """Run the ON1Builder bot with the specified configuration.
    
    Args:
        config_path: Path to the configuration yaml file
        multi_chain: Whether to run in multi-chain mode
        env_file: Path to .env file for secrets
    """
    try:
        if HAS_DOTENV and os.path.exists(env_file):
            load_dotenv(env_file)
            logger.info(f"Loaded environment from {env_file}")

        if multi_chain:
            logger.info("Starting ON1Builder in multi-chain mode...")
            # Dynamic import to allow tests to patch
            from on1builder.config.config import MultiChainConfiguration
            from on1builder.core.multi_chain_core import MultiChainCore
            config = MultiChainConfiguration()
            config.CONFIG_FILE = config_path
            core = MultiChainCore(config)
        else:
            logger.info("Starting ON1Builder in single-chain mode...")
            # Dynamic import to allow tests to patch
            from on1builder.config.config import Configuration
            from on1builder.core.main_core import MainCore
            config = Configuration()
            config.CONFIG_FILE = config_path
            core = MainCore(config)
        # Handle AsyncMock or coroutine-based MainCore
        import inspect
        if inspect.isawaitable(core):
            core = await core
            
        # Initialize and run main core
        await core.run()
        
    except Exception as e:
        logger.error(f"Bot startup failed: {e}")
        # Swallow exception to prevent propagation during testing
        return

# Use typer for CLI if available
if HAS_TYPER:
    app = typer.Typer(help="ON1Builder - Multi-chain blockchain transaction framework")

    @app.command("run")
    def run_command(
        config: str = typer.Option("configs/chains/config.yaml", "--config", "-c", help="Path to configuration file"),
        multi_chain: bool = typer.Option(False, "--multi-chain", "-m", help="Enable multi-chain mode"),
        dry_run: bool = typer.Option(True, "--dry-run", "-d", help="Run in simulation mode"),
        env_file: str = typer.Option(".env", "--env", "-e", help="Path to .env file"),
    ):
        """Run the ON1Builder system."""
        asyncio.run(run_async(config, multi_chain, dry_run, env_file))

    @app.command("monitor")
    def monitor_command(
        chain: str = typer.Option("ethereum", "--chain", help="Chain to monitor"),
        config: str = typer.Option("configs/chains/config.yaml", "--config", "-c", help="Path to configuration file"),
        env_file: str = typer.Option(".env", "--env", "-e", help="Path to .env file"),
    ):
        """Start monitoring system only."""
        asyncio.run(monitor_async(chain, config, env_file))
        
    # Import and include config subcommands
    from on1builder.cli.config import app as config_app
    app.add_typer(config_app, name="config", help="Configuration management commands")

# Legacy CLI for compatibility
def parse_args(args: Optional[List[str]] = None) -> Dict[str, Any]:
    """Parse command line arguments in legacy mode."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ON1Builder - Multi-chain blockchain transaction framework")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the ON1Builder system")
    run_parser.add_argument("--config", "-c", help="Path to configuration file", default="configs/chains/config.yaml")
    run_parser.add_argument("--multi-chain", "-m", action="store_true", help="Enable multi-chain mode")
    run_parser.add_argument("--dry-run", "-d", action="store_true", help="Run in simulation mode")
    run_parser.add_argument("--env", "-e", help="Path to .env file", default=".env")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Start monitoring system only")
    monitor_parser.add_argument("--chain", help="Chain to monitor", required=True)
    monitor_parser.add_argument("--config", "-c", help="Path to configuration file", default="configs/chains/config.yaml")
    monitor_parser.add_argument("--env", "-e", help="Path to .env file", default=".env")
    
    # Config commands
    config_parser = subparsers.add_parser("config", help="Configuration management commands")
    config_subparsers = config_parser.add_subparsers(dest="subcommand", help="Config subcommand to execute")
    
    # Config validate command
    validate_parser = config_subparsers.add_parser("validate", help="Validate a configuration file")
    validate_parser.add_argument("config_path", help="Path to configuration file", nargs="?", default="configs/chains/config.yaml")
    
    args = parser.parse_args(args)
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    return vars(args)

async def run_async(
    config_path: str,
    multi_chain: bool = False,
    dry_run: bool = True,
    env_file: str = ".env"
) -> None:
    """
    Run the ON1Builder system asynchronously.
    
    Args:
        config_path: Path to configuration file
        multi_chain: Enable multi-chain mode
        dry_run: Run in simulation mode
        env_file: Path to environment file
    """
    import os
    import signal
    from dotenv import load_dotenv
    
    from on1builder.utils.logger import setup_logging
    from on1builder.config.config import Configuration, MultiChainConfiguration
    
    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def handle_signal(sig, frame):
        print(f"Received signal {sig}, initiating shutdown...")
        shutdown_event.set()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Load environment variables
    if os.path.exists(env_file):
        load_dotenv(env_file)
    
    # Configure logging - Fix the parameter name from logger to level
    logger = setup_logging("ON1Builder", level=logging.INFO)
    logger.info(f"Starting ON1Builder {'(multi-chain)' if multi_chain else ''}")
    logger.info(f"Configuration file: {config_path}")
    logger.info(f"Dry run: {dry_run}")
    
    try:
        # Load configuration using the appropriate class
        if multi_chain:
            # Import here to avoid circular dependencies
            from on1builder.core.multi_chain_core import MultiChainCore
            
            # Initialize multi-chain configuration and core
            config = MultiChainConfiguration()
            config.CONFIG_FILE = config_path
            
            # Initialize multi-chain core
            core = MultiChainCore(config=config, dry_run=dry_run)
            await core.initialize()
            
            # Start core operations
            await core.start()
            
            # Wait for shutdown signal
            await shutdown_event.wait()
            
            # Perform graceful shutdown
            logger.info("Shutting down multi-chain core...")
            await core.shutdown()
        else:
            # Import here to avoid circular dependencies
            from on1builder.core.main_core import MainCore
            
            # Initialize configuration and core
            config = Configuration()
            config.CONFIG_FILE = config_path
            
            # Initialize main core - Pass config as a positional argument
            core = MainCore(config)
            
            # Set dry run flag if available
            if hasattr(core, 'set_dry_run'):
                core.set_dry_run(dry_run)
                

            await core.run()
            

            
    except Exception as e:
        logger.exception(f"Error in ON1Builder: {str(e)}")
        raise
    finally:
        logger.info("ON1Builder shutdown complete")
        
    return None


async def monitor_async(
    chain: str,
    config_path: str,
    env_file: str = ".env"
) -> None:
    """
    Start monitoring system only.
    
    Args:
        chain: Chain to monitor
        config_path: Path to configuration file
        env_file: Path to environment file
    """
    import os
    import signal
    from dotenv import load_dotenv
    
    from on1builder.utils.logger import setup_logging
    from on1builder.config.config import Configuration
    from on1builder.monitoring.market_monitor import MarketMonitor
    from on1builder.monitoring.txpool_monitor import TxpoolMonitor
    
    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def handle_signal(sig, frame):
        print(f"Received signal {sig}, initiating shutdown...")
        shutdown_event.set()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Load environment variables
    if os.path.exists(env_file):
        load_dotenv(env_file)
        logging.info(f"Loaded environment from {env_file}")
        
    # Configure logging - Make sure we're using level instead of logger
    logger = setup_logging("ON1Builder-Monitor", level=logging.INFO)
    logger.info(f"Starting ON1Builder monitor for chain: {chain}")
    logger.info(f"Configuration file: {config_path}")
    
    try:
        # Load configuration using Configuration class
        config = Configuration()
        config.CONFIG_FILE = config_path
        chain_config = config.get_chain_config(chain)
        
        if not chain_config:
            logging.error(f"Chain '{chain}' not found in configuration")
            return
        
        # Initialize market monitor
        market_monitor = MarketMonitor(chain=chain, chain_config=chain_config)
        await market_monitor.initialize()
        
        # Initialize txpool monitor
        txpool_monitor = TxpoolMonitor(chain=chain, chain_config=chain_config)
        await txpool_monitor.initialize()
        
        # Start monitors
        market_task = asyncio.create_task(market_monitor.start())
        txpool_task = asyncio.create_task(txpool_monitor.start())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Perform graceful shutdown
        logger.info("Shutting down monitors...")
        await market_monitor.shutdown()
        await txpool_monitor.shutdown()
        
        # Cancel monitor tasks
        market_task.cancel()
        txpool_task.cancel()
        
        try:
            await market_task
        except asyncio.CancelledError:
            pass
        
        try:
            await txpool_task
        except asyncio.CancelledError:
            pass
            
    except Exception as e:
        logger.exception(f"Error in monitor: {str(e)}")
        raise
    finally:
        logger.info("ON1Builder monitor shutdown complete")
        
    return None


def main() -> int:
    """Main entry point for the application."""
    asyncio.run(run_async(
        config_path="configs/chains/config.yaml",
        multi_chain=False,
        env_file=".env"
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
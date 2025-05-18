#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import signal
import sys
import os
import traceback

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

from logger_on1 import setup_logging
from main_core import MainCore
from configuration import Configuration

# Configure logging
logger = setup_logging("Main", level=logging.INFO)

# Global variables
_core = None

async def shutdown(sig):
    """Shutdown gracefully."""
    logger.info(f"Received exit signal {sig.name}...")
    
    # Stop all tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    for task in tasks:
        task.cancel()
        
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Clean-up resources
    global _core
    if _core:
        await _core.stop()
    
    logger.info("Shutdown complete.")
    

async def main():
    """Main entry point."""
    global _core
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(shutdown(s))
        )
    
    try:
        # Initialize components
        logger.info("Starting ON1Builder...")
        
        # Load configuration
        config = Configuration()
        await config.load()
        
        # Initialize core
        _core = MainCore(config)
        await _core.run()
        
        return 0
    
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        logger.debug(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))  

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ON1Builder – Multi-Chain Main Entry Point
=======================================
Loads configuration, creates MultiChainCore, and runs it.
"""

import asyncio
import logging
import sys
import traceback
from configuration_multi_chain import MultiChainConfiguration
from multi_chain_core import MultiChainCore
from logger_on1 import setup_logging

logger = setup_logging("MultiChainMain", level="DEBUG")

async def main() -> int:
    """Main entry point.
    
    Returns:
        Exit code
    """
    try:
        # Load configuration
        logger.info("Loading configuration...")
        cfg = MultiChainConfiguration()
        await cfg.load()
        
        # Log configured chains
        chains = cfg.get_chains()
        logger.info(f"Configured {len(chains)} chains:")
        for chain in chains:
            chain_id = chain.get("CHAIN_ID", "Unknown")
            chain_name = chain.get("CHAIN_NAME", f"Chain {chain_id}")
            http_endpoint = chain.get("HTTP_ENDPOINT", "Not configured")
            wallet_address = chain.get("WALLET_ADDRESS", "Not configured")
            logger.info(f"  - {chain_name} (ID: {chain_id})")
            logger.info(f"    HTTP Endpoint: {http_endpoint}")
            logger.info(f"    Wallet Address: {wallet_address}")
        
        # Create and initialize MultiChainCore
        logger.info("Creating MultiChainCore...")
        core = MultiChainCore(cfg)
        
        logger.info("Initializing MultiChainCore...")
        success = await core.initialize()
        if not success:
            logger.error("Failed to initialize MultiChainCore")
            return 1
        
        # Run MultiChainCore
        logger.info("Running MultiChainCore...")
        await core.run()
        
        return 0
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting...")
        return 0
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        return 1

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:
        logger.critical("Unhandled exception: %s", exc)
        traceback.print_exc()
        sys.exit(1)

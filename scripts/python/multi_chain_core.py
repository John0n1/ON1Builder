#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ON1Builder – Multi-Chain Core
============================
Manages multiple chain workers and coordinates operations across chains.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from python.chain_worker import ChainWorker

logger = logging.getLogger("MultiChainCore")


class MultiChainCore:
    """Core class for managing multiple blockchain operations."""

    def __init__(self, config):
        """Initialize the multi-chain core.

        Args:
            config: The global configuration
        """
        self.config = config
        self.running = False
        self.workers = {}  # Chain ID -> ChainWorker

        # Parse chains configuration
        self.chains_config = self._parse_chains_config()

        # Global execution control
        self.dry_run = getattr(config, "DRY_RUN", True)
        self.go_live = getattr(config, "GO_LIVE", False)

        # Global metrics
        self.metrics = {
            "total_chains": len(self.chains_config),
            "active_chains": 0,
            "total_transactions": 0,
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0,
            "start_time": time.time(),
            "uptime_seconds": 0,
        }

        logger.info(
            f"Initialized MultiChainCore with {len(self.chains_config)} chains")
        for chain in self.chains_config:
            logger.info(
                f"Configured chain: {chain.get('CHAIN_NAME', 'Unknown')} (ID: {chain.get('CHAIN_ID', 'Unknown')})")

    def _parse_chains_config(self) -> List[Dict[str, Any]]:
        """Parse the chains configuration from the global config.

        Returns:
            A list of chain configurations
        """
        chains = []

        # Check if CHAINS is defined in the config
        chains_config = getattr(self.config, "CHAINS", None)
        if chains_config:
            # If it's a list, use it directly
            if isinstance(chains_config, list):
                chains = chains_config
            # If it's a string, try to parse it as a comma-separated list of chain IDs
            elif isinstance(chains_config, str):
                chain_ids = [c.strip() for c in chains_config.split(",")]
                for chain_id in chain_ids:
                    # Look for chain-specific config
                    chain_prefix = f"CHAIN_{chain_id}_"
                    chain_config = {
                        "CHAIN_ID": chain_id,
                    }

                    # Extract chain-specific config from global config
                    for key in dir(self.config):
                        if key.startswith(chain_prefix):
                            config_key = key[len(chain_prefix):]
                            chain_config[config_key] = getattr(
                                self.config, key)

                    # Add default chain name if not specified
                    if "CHAIN_NAME" not in chain_config:
                        chain_config["CHAIN_NAME"] = f"Chain {chain_id}"

                    chains.append(chain_config)

        # If no chains were configured, use the global config as a single chain
        if not chains:
            # Default to Ethereum mainnet if not specified
            chain_id = getattr(self.config, "CHAIN_ID", "1")
            chain_name = getattr(self.config, "CHAIN_NAME", "Ethereum")

            chains.append({
                "CHAIN_ID": chain_id,
                "CHAIN_NAME": chain_name,
                "HTTP_ENDPOINT": getattr(self.config, "HTTP_ENDPOINT", ""),
                "WEBSOCKET_ENDPOINT": getattr(self.config, "WEBSOCKET_ENDPOINT", ""),
                "WALLET_ADDRESS": getattr(self.config, "WALLET_ADDRESS", ""),
                "WALLET_KEY": getattr(self.config, "WALLET_KEY", ""),
            })

        return chains

    async def initialize(self) -> bool:
        """Initialize all chain workers.

        Returns:
            True if all workers were initialized successfully, False otherwise
        """
        logger.info("Initializing chain workers...")

        # Create global config dictionary
        global_config = {
            "DRY_RUN": self.dry_run,
            "GO_LIVE": self.go_live,
        }

        # Initialize workers for each chain
        for chain_config in self.chains_config:
            chain_id = chain_config.get("CHAIN_ID")
            chain_name = chain_config.get("CHAIN_NAME", f"chain-{chain_id}")

            logger.info(
                f"Initializing worker for {chain_name} (ID: {chain_id})")

            # Create and initialize worker
            worker = ChainWorker(chain_config, global_config)
            success = await worker.initialize()

            if success:
                self.workers[chain_id] = worker
                logger.info(
                    f"Worker for {chain_name} initialized successfully")
            else:
                logger.error(f"Failed to initialize worker for {chain_name}")

        # Update active chains count
        self.metrics["active_chains"] = len(self.workers)

        # Return success if at least one worker was initialized
        return len(self.workers) > 0

    async def run(self) -> None:
        """Run all chain workers."""
        if not self.workers:
            logger.error("No chain workers initialized, cannot run")
            return

        self.running = True
        logger.info(f"Starting {len(self.workers)} chain workers")

        # Start all workers
        worker_tasks = []
        for chain_id, worker in self.workers.items():
            task = asyncio.create_task(worker.start())
            worker_tasks.append(task)

        # Start metrics update task
        metrics_task = asyncio.create_task(self._update_metrics())

        # Wait for all tasks to complete
        try:
            await asyncio.gather(*worker_tasks, metrics_task)
        except asyncio.CancelledError:
            logger.info("MultiChainCore tasks cancelled")
            self.running = False
            # Stop all workers
            for chain_id, worker in self.workers.items():
                await worker.stop()
        except Exception as e:
            logger.error(f"Error in MultiChainCore: {e}")
            self.running = False
            # Stop all workers
            for chain_id, worker in self.workers.items():
                await worker.stop()

    async def stop(self) -> None:
        """Stop all chain workers."""
        self.running = False
        logger.info("Stopping all chain workers")

        # Stop all workers
        for chain_id, worker in self.workers.items():
            await worker.stop()

    async def _update_metrics(self) -> None:
        """Update global metrics based on worker metrics."""
        while self.running:
            try:
                # Update uptime
                self.metrics["uptime_seconds"] = int(
                    time.time() - self.metrics["start_time"])

                # Reset aggregated metrics
                self.metrics["total_transactions"] = 0
                self.metrics["total_profit_eth"] = 0.0
                self.metrics["total_gas_spent_eth"] = 0.0

                # Aggregate metrics from all workers
                for chain_id, worker in self.workers.items():
                    worker_metrics = worker.get_metrics()
                    self.metrics["total_transactions"] += worker_metrics.get(
                        "transaction_count", 0)
                    self.metrics["total_profit_eth"] += worker_metrics.get(
                        "total_profit_eth", 0.0)
                    self.metrics["total_gas_spent_eth"] += worker_metrics.get(
                        "total_gas_spent_eth", 0.0)

                # Sleep for a bit
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Error updating metrics: {e}")
                await asyncio.sleep(30)

    def get_metrics(self) -> Dict[str, Any]:
        """Get global metrics and metrics for all chains.

        Returns:
            A dictionary of metrics
        """
        # Get global metrics
        metrics = {
            "global": self.metrics,
            "chains": {}
        }

        # Add metrics for each chain
        for chain_id, worker in self.workers.items():
            metrics["chains"][chain_id] = worker.get_metrics()

        return metrics

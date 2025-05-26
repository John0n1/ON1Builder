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
from typing import Dict, Any, List
from on1builder.engines.chain_worker import ChainWorker
from contextlib import suppress

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
        self._tasks = set()  # Track all running tasks

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
            "errors": {},  # Chain ID -> list of recent errors
            "initialization_failures": 0,
        }

        # Health check interval
        self.health_check_interval = getattr(
            config, "HEALTH_CHECK_INTERVAL", 60
        )  # seconds
        self._health_check_task = None
        self._shutdown_event = asyncio.Event()

        logger.info(
            f"Initialized MultiChainCore with {len(self.chains_config)} chains")
        for chain in self.chains_config:
            logger.info(
                f"Configured chain: {
                    chain.get(
                        'CHAIN_NAME',
                        'Unknown')} (ID: {
                    chain.get(
                        'CHAIN_ID',
                        'Unknown')})"
            )

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
            # If it's a string, try to parse it as a comma-separated list of
            # chain IDs
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

            chains.append(
                {
                    "CHAIN_ID": chain_id,
                    "CHAIN_NAME": chain_name,
                    "HTTP_ENDPOINT": getattr(self.config, "HTTP_ENDPOINT", ""),
                    "WEBSOCKET_ENDPOINT": getattr(
                        self.config, "WEBSOCKET_ENDPOINT", ""
                    ),
                    "WALLET_ADDRESS": getattr(self.config, "WALLET_ADDRESS", ""),
                    "WALLET_KEY": getattr(self.config, "WALLET_KEY", ""),
                }
            )

        # Validate required fields for each chain
        validated_chains = []
        for chain in chains:
            required_fields = ["CHAIN_ID", "HTTP_ENDPOINT"]
            missing_fields = [
                field for field in required_fields if not chain.get(field)
            ]

            if missing_fields:
                logger.error(
                    f"Chain config missing required fields: {
                        ', '.join(missing_fields)}"
                )
                continue

            validated_chains.append(chain)

        return validated_chains

    async def initialize(self) -> bool:
        """Initialize the multi-chain core and all chain workers.

        Returns:
            True if at least one chain was successfully initialized, False otherwise
        """
        try:
            logger.info(
                f"Initializing multi-chain core with {len(self.chains_config)} chains"
            )

            # Initialize chain workers
            success_count = 0
            initialization_tasks = []

            # Create tasks for parallel initialization
            for chain_config in self.chains_config:
                chain_id = chain_config.get("CHAIN_ID")
                task = asyncio.create_task(
                    self._init_chain_worker(chain_id, chain_config),
                    name=f"init_chain_{chain_id}",
                )
                initialization_tasks.append(task)
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

            # Wait for all initialization tasks to complete
            results = await asyncio.gather(
                *initialization_tasks, return_exceptions=True
            )

            # Process results
            for i, result in enumerate(results):
                chain_id = self.chains_config[i].get("CHAIN_ID")
                if isinstance(result, Exception):
                    logger.error(
                        f"Failed to initialize chain worker for {
                            self.chains_config[i].get(
                                'CHAIN_NAME', chain_id)}: {result}"
                    )
                    # Detailed error tracking
                    import datetime
                    import traceback as _tb

                    error_entry = {
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                        "error": str(result),
                        "traceback": _tb.format_exception(
                            type(result), result, result.__traceback__
                        ),
                    }
                    self.metrics["errors"].setdefault(
                        chain_id, []).append(error_entry)
                    self.metrics["initialization_failures"] += 1
                elif result:  # True means success
                    success_count += 1

            # Continue if at least one chain initialized successfully
            if success_count > 0:
                logger.info(
                    f"Successfully initialized {success_count}/{
                        len(
                            self.chains_config)} chains"
                )

                # Setup metrics update task
                metrics_task = asyncio.create_task(self._update_metrics())
                self._tasks.add(metrics_task)
                metrics_task.add_done_callback(self._tasks.discard)

                # Setup health check task
                self._health_check_task = asyncio.create_task(
                    self._periodic_health_check()
                )
                self._tasks.add(self._health_check_task)
                self._health_check_task.add_done_callback(self._tasks.discard)

                return True
            else:
                logger.error("Failed to initialize any chains")
                return False

        except Exception as e:
            logger.exception(f"Error in multi-chain initialization: {e}")
            return False

    async def _init_chain_worker(
        self, chain_id: str, chain_config: Dict[str, Any]
    ) -> bool:
        """Initialize a single chain worker.

        Args:
            chain_id: Chain ID
            chain_config: Chain configuration

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            worker = ChainWorker(chain_config, self.config)
            if await worker.initialize():
                self.workers[chain_id] = worker
                logger.info(
                    f"Initialized chain worker for {
                        chain_config.get(
                            'CHAIN_NAME', chain_id)}"
                )
                return True
            else:
                logger.error(
                    f"Failed to initialize chain worker for {
                        chain_config.get(
                            'CHAIN_NAME', chain_id)}"
                )
                return False
        except Exception as e:
            logger.exception(
                f"Exception initializing chain worker for {
                    chain_config.get(
                        'CHAIN_NAME', chain_id)}: {e}"
            )
            raise

    async def check_health(self) -> Dict[str, Any]:
        """Check health of all chain workers and core components.

        Returns:
            Dict with health status information
        """
        import datetime

        health = {
            "status": "healthy",
            "chains": {},
            "total_chains": len(self.workers),
            "active_chains": 0,
            "timestamp": datetime.datetime.now().isoformat(),
            "uptime_seconds": int(time.time() - self.metrics["start_time"]),
            "initialization_failures": self.metrics["initialization_failures"],
        }

        # Check each chain
        chain_check_tasks = []
        for chain_id, worker in self.workers.items():
            task = asyncio.create_task(
                self._check_chain_health(chain_id, worker),
                name=f"health_check_{chain_id}",
            )
            chain_check_tasks.append(task)

        # Wait for all health checks to complete
        chain_results = await asyncio.gather(*chain_check_tasks, return_exceptions=True)

        # Process results
        for i, (chain_id, result) in enumerate(
                zip(self.workers.keys(), chain_results)):
            if isinstance(result, Exception):
                health["chains"][chain_id] = {
                    "status": "unhealthy",
                    "errors": [f"Health check failed: {str(result)}"],
                    "metrics": {},
                }
            else:
                health["chains"][chain_id] = result
                if result["status"] == "healthy":
                    health["active_chains"] += 1

        # Update overall status
        if health["active_chains"] == 0:
            health["status"] = "critical"
        elif health["active_chains"] < health["total_chains"]:
            health["status"] = "degraded"

        return health

    async def _check_chain_health(
        self, chain_id: str, worker: ChainWorker
    ) -> Dict[str, Any]:
        """Check health of a single chain worker.

        Args:
            chain_id: Chain ID
            worker: Chain worker instance

        Returns:
            Dict with chain health information
        """
        chain_status = "healthy"
        chain_errors = []

        # Set timeout for health checks
        try:
            # Run health checks with a timeout
            async with asyncio.timeout(10):  # 10-second timeout
                # Check connection
                try:
                    balance = await worker.get_wallet_balance()
                    if balance is None:
                        chain_status = "degraded"
                        chain_errors.append(
                            "Failed to retrieve wallet balance")

                    # Check gas price availability
                    gas_price = await worker.get_gas_price()
                    if gas_price is None:
                        chain_status = "degraded"
                        chain_errors.append("Failed to retrieve gas price")

                    # Check block sync status
                    is_syncing = await worker.is_syncing()
                    if is_syncing:
                        chain_status = "degraded"
                        chain_errors.append("Node is still syncing")

                except Exception as e:
                    chain_status = "unhealthy"
                    chain_errors.append(f"Connection error: {str(e)}")
        except asyncio.TimeoutError:
            chain_status = "unhealthy"
            chain_errors.append("Health check timed out after 10 seconds")

        return {
            "status": chain_status,
            "errors": chain_errors,
            "metrics": worker.get_metrics(),
        }

    async def _periodic_health_check(self) -> None:
        """Periodically check health of all chain workers."""
        while not self._shutdown_event.is_set():
            try:
                health = await self.check_health()

                # Log health issues
                if health["status"] != "healthy":
                    logger.warning(
                        f"Health check: System status is {health['status']}. "
                        f"Active chains: {
                            health['active_chains']}/{
                            health['total_chains']}"
                    )

                    # Log specific chain issues
                    for chain_id, chain_health in health["chains"].items():
                        if chain_health["status"] != "healthy":
                            logger.warning(
                                f"Chain {chain_id} status: {
                                    chain_health['status']}"
                            )
                            for error in chain_health["errors"]:
                                logger.warning(
                                    f"Chain {chain_id} error: {error}")

                # Update metrics with health info
                self.metrics["active_chains"] = health["active_chains"]

                # Attempt recovery for unhealthy chains
                for chain_id, chain_health in health["chains"].items():
                    if (
                        chain_health["status"] == "unhealthy"
                        and chain_id in self.workers
                    ):
                        logger.info(
                            f"Attempting to recover unhealthy chain {chain_id}")
                        await self.workers[chain_id].reconnect()

                # Wait before next check
                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.error(f"Error in health check: {e}")
                await asyncio.sleep(self.health_check_interval)

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
            task = asyncio.create_task(
                worker.start(), name=f"worker_{chain_id}")
            worker_tasks.append(task)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        # Wait for all tasks to complete or for shutdown
        try:
            # This will run until stop() is called and sets the shutdown event
            await self._shutdown_event.wait()
            logger.info("Shutdown event received, stopping workers...")
        except asyncio.CancelledError:
            logger.info("MultiChainCore tasks cancelled")
        except Exception as e:
            logger.error(f"Error in MultiChainCore: {e}")
        finally:
            self.running = False
            # Stop all workers
            await self.stop()

    async def stop(self) -> None:
        """Stop all chain workers and cleanup."""
        self.running = False
        logger.info("Stopping all chain workers")

        # Signal shutdown
        self._shutdown_event.set()

        # Cancel health check task
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._health_check_task

        # Stop all workers
        stop_tasks = []
        for chain_id, worker in self.workers.items():
            task = asyncio.create_task(worker.stop(), name=f"stop_{chain_id}")
            stop_tasks.append(task)

        # Wait for all workers to stop with timeout
        try:
            async with asyncio.timeout(30):  # 30-second timeout for shutdown
                await asyncio.gather(*stop_tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            logger.warning(
                "Some chain workers did not stop gracefully within timeout")

        # Cancel any remaining tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        logger.info("MultiChainCore stopped")

    async def _update_metrics(self) -> None:
        """Update global metrics based on worker metrics."""
        while self.running and not self._shutdown_event.is_set():
            try:
                # Update uptime
                self.metrics["uptime_seconds"] = int(
                    time.time() - self.metrics["start_time"]
                )

                # Aggregate metrics from all workers
                total_transactions = 0
                total_profit = 0.0
                total_gas = 0.0

                for chain_id, worker in self.workers.items():
                    worker_metrics = worker.get_metrics()
                    total_transactions += worker_metrics.get("transactions", 0)
                    total_profit += worker_metrics.get("profit_eth", 0.0)
                    total_gas += worker_metrics.get("gas_spent_eth", 0.0)

                self.metrics["total_transactions"] = total_transactions
                self.metrics["total_profit_eth"] = total_profit
                self.metrics["total_gas_spent_eth"] = total_gas

                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                logger.error(f"Error updating metrics: {e}")
                await asyncio.sleep(5)

    def get_metrics(self) -> Dict[str, Any]:
        """Get global metrics.

        Returns:
            Dict with global metrics
        """
        return self.metrics.copy()  # Return a copy to prevent modification

    async def start(self) -> None:
        """Start the MultiChainCore (alias for run).

        This method exists for API compatibility with __main__.py.
        """
        await self.run()

    async def shutdown(self) -> None:
        """Shutdown the MultiChainCore (alias for stop).

        This method exists for API compatibility with __main__.py.
        """
        await self.stop()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Multi-Chain Core
============================
Manages multiple chain workers and coordinates operations across chains.
License: MIT
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any, Dict, List, Optional

from on1builder.config.config import MultiChainConfiguration
from on1builder.engines.chain_worker import ChainWorker
from on1builder.utils.logger import setup_logging

logger = setup_logging("MultiChainCore", level="INFO")


class MultiChainCore:
    """Core class for managing multiple blockchain operations across chains."""

    def __init__(self, config: MultiChainConfiguration) -> None:
        """
        Args:
            config: MultiChainConfiguration instance
        """
        self.config = config
        self.workers: Dict[str, ChainWorker] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_event = asyncio.Event()

        # Execution flags
        self.dry_run: bool = getattr(config, "DRY_RUN", True)
        self.go_live: bool = getattr(config, "GO_LIVE", False)

        # Metrics
        now = time.time()
        self.metrics: Dict[str, Any] = {
            "total_chains": 0,
            "active_chains": 0,
            "total_transactions": 0,
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0,
            "start_time": now,
            "uptime_seconds": 0,
            "errors": {},  # chain_id -> list of error entries
            "initialization_failures": 0,
        }

        # Health check interval
        self.health_check_interval: float = getattr(
            config, "HEALTH_CHECK_INTERVAL", 60.0
        )
        self._health_check_task: Optional[asyncio.Task[Any]] = None

        logger.info("MultiChainCore initialized")

    async def initialize(self) -> bool:
        """
        Load chain configurations and initialize ChainWorker for each.
        Returns True if at least one chain succeeds.
        """
        # Load config (populates config.chains)
        await self.config.load()
        chains = getattr(self.config, "chains", []) or []
        self.metrics["total_chains"] = len(chains)

        if not chains:
            logger.error("No chains defined in multi-chain configuration")
            return False

        # Parallel initialization of workers
        init_tasks: List[asyncio.Task[bool]] = []
        for chain_cfg in chains:
            chain_id = str(chain_cfg.get("CHAIN_ID"))
            task = asyncio.create_task(
                self._init_chain_worker(chain_id, chain_cfg),
                name=f"init_chain_{chain_id}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            init_tasks.append(task)

        results = await asyncio.gather(*init_tasks, return_exceptions=True)
        success_count = 0

        for cfg, result in zip(chains, results):
            chain_id = str(cfg.get("CHAIN_ID"))
            if isinstance(result, Exception) or result is False:
                logger.error(f"Chain {chain_id} initialization failed: {result}")
                self.metrics["initialization_failures"] += 1
                entry = {
                    "timestamp": time.time(),
                    "chain_id": chain_id,
                    "error": str(result),
                }
                self.metrics["errors"].setdefault(chain_id, []).append(entry)
            else:
                success_count += 1

        if success_count == 0:
            logger.error("No chains initialized successfully")
            return False

        logger.info(
            f"Initialized {success_count}/{len(chains)} chain workers"
        )

        # Schedule periodic health check
        self._health_check_task = asyncio.create_task(
            self._periodic_health_check()
        )
        self._tasks.add(self._health_check_task)
        self._health_check_task.add_done_callback(self._tasks.discard)

        # Schedule metrics updater
        metrics_task = asyncio.create_task(self._update_metrics())
        self._tasks.add(metrics_task)
        metrics_task.add_done_callback(self._tasks.discard)

        return True

    async def _init_chain_worker(
        self, chain_id: str, chain_cfg: Dict[str, Any]
    ) -> bool:
        """Initialize a single ChainWorker."""
        try:
            worker = ChainWorker(chain_cfg, self.config)
            ok = await worker.initialize()
            if ok:
                self.workers[chain_id] = worker
                logger.info(f"ChainWorker {chain_id} initialized")
                return True
            logger.error(f"ChainWorker {chain_id} failed to initialize")
            return False
        except Exception as e:
            logger.exception(f"Error initializing worker {chain_id}: {e}")
            return False

    async def run(self) -> None:
        """Start all chain workers and run until shutdown."""
        if not self.workers:
            logger.error("No chain workers to run")
            return

        logger.info(f"Starting {len(self.workers)} chain workers")
        # Launch each worker.start()
        for chain_id, worker in self.workers.items():
            task = asyncio.create_task(worker.start(), name=f"worker_{chain_id}")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        # Wait for shutdown signal
        await self._shutdown_event.wait()
        logger.info("Shutdown event received; stopping workers...")
        await self.stop()

    async def stop(self) -> None:
        """Signal all workers to stop and cleanup tasks."""
        logger.info("Stopping MultiChainCore and all workers")
        self._shutdown_event.set()

        # Cancel health check
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._health_check_task

        # Stop each worker
        stop_tasks = [
            asyncio.create_task(worker.stop(), name=f"stop_{cid}")
            for cid, worker in self.workers.items()
        ]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        # Cancel any remaining tasks
        for task in list(self._tasks):
            if not task.done():
                task.cancel()

        logger.info("MultiChainCore stopped")

    async def _periodic_health_check(self) -> None:
        """Periodically check health of each worker and attempt recovery."""
        while not self._shutdown_event.is_set():
            try:
                for chain_id, worker in self.workers.items():
                    healthy = await worker.is_healthy()
                    if not healthy:
                        logger.warning(f"Worker {chain_id} unhealthy; reconnecting")
                        await worker.reconnect()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(self.health_check_interval)

    async def _update_metrics(self) -> None:
        """Aggregate worker metrics into global metrics."""
        while not self._shutdown_event.is_set():
            try:
                now = time.time()
                self.metrics["uptime_seconds"] = int(now - self.metrics["start_time"])

                total_txs = total_profit = total_gas = 0.0
                active = 0
                for cid, worker in self.workers.items():
                    m = worker.get_metrics()
                    total_txs += m.get("transactions", 0)
                    total_profit += m.get("profit_eth", 0.0)
                    total_gas += m.get("gas_spent_eth", 0.0)
                    if await worker.is_healthy():
                        active += 1

                self.metrics.update({
                    "total_transactions": total_txs,
                    "total_profit_eth": total_profit,
                    "total_gas_spent_eth": total_gas,
                    "active_chains": active,
                })

                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics update error: {e}")
                await asyncio.sleep(5.0)

    def get_metrics(self) -> Dict[str, Any]:
        """Return a shallow copy of current global metrics."""
        return dict(self.metrics)

    async def start(self) -> None:
        """Alias for run(), for API compatibility."""
        await self.run()

    async def shutdown(self) -> None:
        """Alias for stop(), for API compatibility."""
        await self.stop()

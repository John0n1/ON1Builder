# src/on1builder/core/main_orchestrator.py
# flake8: noqa E501
from __future__ import annotations

import asyncio
import signal
from decimal import Decimal
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from on1builder.config.manager import get_config_manager, initialize_global_config
from on1builder.core.chain_worker import ChainWorker
from on1builder.core.balance_manager import BalanceManager
from on1builder.core.multi_chain_orchestrator import MultiChainOrchestrator
from on1builder.utils.custom_exceptions import InitializationError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService
from on1builder.utils.web3_factory import create_web3_instance
from on1builder.utils.error_recovery import get_error_recovery_manager, with_error_recovery
from on1builder.utils.constants import PERFORMANCE_MONITORING_INTERVAL
from on1builder.persistence.db_interface import DatabaseInterface

logger = get_logger(__name__)


class MainOrchestrator:
    """
    The main orchestrator for the ON1Builder application. It initializes,
    starts, and gracefully shuts down all components and chain workers.
    Enhanced with balance management, cross-chain coordination, and advanced monitoring.
    """

    def __init__(self):
        # Initialize configuration first
        self._config_manager = get_config_manager()
        self._config = None  # Will be set during initialization

        self._workers: List[ChainWorker] = []
        self._balance_managers: Dict[int, BalanceManager] = {}
        self._multi_chain_orchestrator: Optional[MultiChainOrchestrator] = None
        self._is_running = False
        self._shutdown_event = asyncio.Event()
        self._notification_service: Optional[NotificationService] = None
        self._db_interface: Optional[DatabaseInterface] = None
        self._error_recovery_manager = get_error_recovery_manager()
        self._performance_monitor_task: Optional[asyncio.Task] = None
        self._last_profit_report = datetime.now()
        self._startup_time = datetime.now()
        self._error_count = 0
        self._max_consecutive_errors = 5
        logger.info("MainOrchestrator initialized successfully")

    async def _setup_signal_handlers(self):
        """Sets up signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.stop(s)))
            logger.debug("Signal handlers configured successfully")
        except Exception as e:
            logger.warning(f"Could not set up signal handlers: {e}")
            # Continue without signal handlers - user can still stop manually

    async def run(self):
        """
        The main entry point to start the application.
        Initializes workers and runs them until a shutdown signal is received.
        """
        if self._is_running:
            logger.warning("MainOrchestrator is already running")
            return

        try:
            # Initialize configuration first
            initialize_global_config()
            self._config = self._config_manager.get_config()
            logger.info("Configuration loaded and validated")
            self._notification_service = NotificationService()
            self._db_interface = DatabaseInterface()

        except Exception as e:
            logger.critical(f"Failed to initialize configuration: {e}")
            raise InitializationError(f"Configuration initialization failed: {e}", cause=e)

        self._is_running = True
        logger.info("Starting ON1Builder Orchestrator...")

        try:
            await self._setup_signal_handlers()
            await self._initialize_database()
            await self._initialize_workers()
            await self._start_services()

            await self._send_alert(
                title="ON1Builder Started",
                message=f"Application is now running and monitoring {len(self._workers)} chain(s)",
                level="INFO",
                details=self._get_startup_details(),
            )

            # Main loop - wait for shutdown
            await self._shutdown_event.wait()

        except Exception as e:
            logger.critical(f"Fatal error in MainOrchestrator: {e}", exc_info=True)
            await self._handle_critical_error(e)
        finally:
            logger.info("MainOrchestrator run loop exiting...")
            await self._shutdown()

    async def _initialize_database(self):
        """Initialize the database with error handling."""
        if not self._db_interface:
            raise InitializationError("Database interface is not initialized", "database")

        try:
            await self._db_interface.initialize_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            raise InitializationError(f"Database initialization failed: {e}", "database", e)

    async def _initialize_workers(self):
        """Initialize all chain workers with comprehensive error handling."""
        if not self._config.chains:
            raise InitializationError("No chains configured")

        successful_workers = 0
        failed_chains = []

        for chain_id in self._config.chains:
            try:
                await self._initialize_chain_worker(chain_id)
                successful_workers += 1
                logger.info(f"Successfully initialized worker for chain {chain_id}")

            except Exception as e:
                failed_chains.append(chain_id)
                logger.error(f"Failed to initialize worker for chain {chain_id}: {e}")
                await self._send_alert(
                    title=f"Chain {chain_id} Initialization Failed",
                    message=f"Could not initialize worker for chain {chain_id}",
                    level="ERROR",
                    details={"chain_id": chain_id, "error": str(e)},
                )

        if successful_workers == 0:
            raise InitializationError("No workers were initialized successfully")

        if failed_chains:
            logger.warning(f"Failed to initialize workers for chains: {failed_chains}")

    async def _initialize_chain_worker(self, chain_id: int):
        """Initialize a single chain worker and its balance manager."""
        worker = ChainWorker(chain_id)
        await worker.initialize()
        self._workers.append(worker)

        # Create balance manager for the chain
        web3 = await create_web3_instance(chain_id)
        balance_manager = BalanceManager(web3, self._config.wallet_address)
        await balance_manager.update_balance()
        self._balance_managers[chain_id] = balance_manager

    async def _start_services(self):
        """Start all services and background tasks."""
        # Initialize multi-chain orchestrator if we have multiple chains
        if len(self._workers) >= 2:
            self._multi_chain_orchestrator = MultiChainOrchestrator(self._workers)
            logger.info("Multi-chain orchestrator initialized")

        # Start all workers
        worker_tasks = [asyncio.create_task(worker.start()) for worker in self._workers]

        # Start multi-chain orchestrator if available
        if self._multi_chain_orchestrator:
            worker_tasks.append(asyncio.create_task(self._multi_chain_orchestrator.start()))

        # Start performance monitoring
        self._performance_monitor_task = asyncio.create_task(self._performance_monitor_loop())

    def _get_startup_details(self) -> Dict[str, Any]:
        """Get startup details for notifications."""
        return {
            "active_chains": self._config.chains,
            "multi_chain_enabled": self._multi_chain_orchestrator is not None,
            "balance_managers": len(self._balance_managers),
            "startup_time": self._startup_time.isoformat(),
            "version": "2.2.0",
        }

    async def _handle_critical_error(self, error: Exception):
        """Handle critical errors with proper notifications."""
        self._error_count += 1

        await self._send_alert(
            title="Critical Orchestrator Failure",
            message="A fatal error occurred, shutting down the application",
            level="CRITICAL",
            details={
                "error": str(error),
                "error_count": self._error_count,
                "uptime_seconds": (datetime.now() - self._startup_time).total_seconds(),
            },
        )

        if self._error_count >= self._max_consecutive_errors:
            logger.critical(f"Maximum consecutive errors ({self._max_consecutive_errors}) reached")
            # Additional emergency shutdown logic could go here

    async def _send_alert(
        self,
        *,
        title: str,
        message: str,
        level: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Safely dispatch a notification if the service is ready."""
        if not self._notification_service:
            logger.debug("Notification service not initialized; skipping alert '%s'.", title)
            return

        try:
            await self._notification_service.send_alert(
                title=title,
                message=message,
                level=level,
                details=details,
            )
        except Exception as exc:
            logger.error("Failed to send alert '%s': %s", title, exc, exc_info=True)

    async def stop(self, sig: Optional[signal.Signals] = None):
        """Initiates the graceful shutdown of the application."""
        if not self._shutdown_event.is_set():
            signal_name = f" received signal {sig.name}" if sig else ""
            logger.info(f"Shutdown sequence initiated{signal_name}.")
            self._shutdown_event.set()

    async def _shutdown(self):
        """Performs the actual shutdown of all workers and services."""
        logger.info(f"Stopping {len(self._workers)} chain workers...")

        # Stop performance monitoring
        if self._performance_monitor_task:
            self._performance_monitor_task.cancel()
            try:
                await self._performance_monitor_task
            except asyncio.CancelledError:
                pass

        # Stop multi-chain orchestrator
        if self._multi_chain_orchestrator:
            await self._multi_chain_orchestrator.stop()

        # Stop all workers
        shutdown_tasks = [worker.stop() for worker in self._workers]
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        # Generate final profit report
        await self._generate_final_report()

        logger.info("Closing database connection...")
        if self._db_interface:
            await self._db_interface.close()

        logger.info("Closing notification service session...")
        if self._notification_service:
            await self._notification_service.close()

        logger.info("ON1Builder has been shut down gracefully.")

    async def _performance_monitor_loop(self):
        """Monitors overall system performance and generates periodic reports."""
        while self._is_running:
            try:
                await asyncio.sleep(PERFORMANCE_MONITORING_INTERVAL)

                # Generate performance report every hour
                if datetime.now() - self._last_profit_report >= timedelta(hours=1):
                    await self._generate_performance_report()
                    self._last_profit_report = datetime.now()

                # Check system health
                await self._check_system_health()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance monitor loop: {e}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes before retrying

    async def _generate_performance_report(self):
        """Generates comprehensive performance and profit reports."""
        try:
            total_profit = Decimal("0")
            total_trades = 0
            chain_performances = {}

            for chain_id, worker in enumerate(self._workers):
                balance_manager = self._balance_managers.get(worker.chain_id)
                if balance_manager:
                    await balance_manager.update_balance()
                    chain_profit = balance_manager.get_total_profit()
                    total_profit += chain_profit

                    chain_performances[worker.chain_id] = {
                        "profit_usd": float(chain_profit),
                        "balance_eth": float(balance_manager.get_balance("ETH")),
                        "successful_trades": getattr(worker.tx_manager, "successful_trades", 0),
                        "failed_trades": getattr(worker.tx_manager, "failed_trades", 0),
                    }
                    total_trades += chain_performances[worker.chain_id]["successful_trades"]

            # Calculate success rate
            total_failed = sum(perf["failed_trades"] for perf in chain_performances.values())
            success_rate = (
                (total_trades / (total_trades + total_failed)) * 100
                if (total_trades + total_failed) > 0
                else 0
            )

            await self._send_alert(
                title="Hourly Performance Report",
                message=f"System generated ${total_profit:.2f} profit from {total_trades} successful trades",
                level="INFO",
                details={
                    "total_profit_usd": float(total_profit),
                    "total_trades": total_trades,
                    "success_rate_percent": round(success_rate, 2),
                    "chain_performances": chain_performances,
                    "multi_chain_active": self._multi_chain_orchestrator is not None,
                },
            )

        except Exception as e:
            logger.error(f"Error generating performance report: {e}", exc_info=True)

    async def _check_system_health(self):
        """Performs system health checks and alerts on issues."""
        try:
            unhealthy_chains = []

            for worker in self._workers:
                # Check if worker is responsive
                if (
                    not hasattr(worker, "last_heartbeat")
                    or (datetime.now() - getattr(worker, "last_heartbeat", datetime.min)).seconds
                    > 300
                ):
                    unhealthy_chains.append(worker.chain_id)

                # Check balance manager health
                balance_manager = self._balance_managers.get(worker.chain_id)
                if balance_manager:
                    eth_balance = balance_manager.get_balance("ETH")
                    if eth_balance < Decimal("0.01"):  # Low ETH balance warning
                        await self._send_alert(
                            title=f"Low ETH Balance Warning - Chain {worker.chain_id}",
                            message=f"ETH balance is critically low: {eth_balance:.6f} ETH",
                            level="WARNING",
                            details={
                                "chain_id": worker.chain_id,
                                "eth_balance": float(eth_balance),
                            },
                        )

            if unhealthy_chains:
                await self._send_alert(
                    title="System Health Alert",
                    message=f"Detected unresponsive workers on chains: {unhealthy_chains}",
                    level="ERROR",
                    details={"unhealthy_chains": unhealthy_chains},
                )

        except Exception as e:
            logger.error(f"Error in system health check: {e}", exc_info=True)

    async def _generate_final_report(self):
        """Generates a comprehensive final report on system shutdown."""
        try:
            await self._generate_performance_report()

            # Additional shutdown metrics
            uptime = datetime.now() - self._startup_time

            await self._send_alert(
                title="ON1Builder Shutdown Complete",
                message=f"System operated for {uptime} and is now offline",
                level="INFO",
                details={
                    "uptime_hours": round(uptime.total_seconds() / 3600, 2),
                    "workers_count": len(self._workers),
                    "shutdown_time": datetime.now().isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error generating final report: {e}", exc_info=True)

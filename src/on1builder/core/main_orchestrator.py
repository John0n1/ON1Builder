# src/on1builder/core/main_orchestrator.py
from __future__ import annotations

import asyncio
import signal
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from on1builder.config.loaders import settings
from on1builder.core.chain_worker import ChainWorker
from on1builder.core.balance_manager import BalanceManager
from on1builder.core.multi_chain_orchestrator import MultiChainOrchestrator
from on1builder.utils.custom_exceptions import InitializationError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService
from on1builder.utils.web3_factory import create_web3_instance
from on1builder.persistence.db_interface import DatabaseInterface

logger = get_logger(__name__)

class MainOrchestrator:
    """
    The main orchestrator for the ON1Builder application. It initializes,
    starts, and gracefully shuts down all components and chain workers.
    Enhanced with balance management, cross-chain coordination, and advanced monitoring.
    """

    def __init__(self):
        self._workers: List[ChainWorker] = []
        self._balance_managers: Dict[int, BalanceManager] = {}
        self._multi_chain_orchestrator: Optional[MultiChainOrchestrator] = None
        self._is_running = False
        self._shutdown_event = asyncio.Event()
        self._notification_service = NotificationService()
        self._db_interface = DatabaseInterface()
        self._performance_monitor_task: Optional[asyncio.Task] = None
        self._last_profit_report = datetime.now()
        logger.info("MainOrchestrator created with enhanced features.")

    async def _setup_signal_handlers(self):
        """Sets up signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.stop(s)))

    async def run(self):
        """
        The main entry point to start the application.
        Initializes workers and runs them until a shutdown signal is received.
        """
        if self._is_running:
            logger.warning("MainOrchestrator is already running.")
            return

        self._is_running = True
        logger.info("Starting ON1Builder Orchestrator...")
        
        await self._setup_signal_handlers()

        try:
            await self._db_interface.initialize_db()
            
            # Initialize workers and balance managers
            for chain_id in settings.chains:
                try:
                    worker = ChainWorker(chain_id)
                    await worker.initialize()
                    self._workers.append(worker)
                    
                    # Create balance manager for each chain
                    web3 = await create_web3_instance(chain_id)
                    balance_manager = BalanceManager(web3, settings.wallet_address)
                    await balance_manager.update_balance()
                    self._balance_managers[chain_id] = balance_manager
                    
                    logger.info(f"Initialized worker and balance manager for chain {chain_id}")
                    
                except InitializationError as e:
                    logger.critical(f"Failed to initialize worker for chain {chain_id}: {e}")
                    await self._notification_service.send_alert(
                        title=f"Critical Initialization Failure",
                        message=f"Could not initialize worker for chain {chain_id}. The application may not function correctly.",
                        level="CRITICAL",
                        details={"error": str(e)}
                    )
            
            if not self._workers:
                logger.critical("No workers were initialized successfully. Shutting down.")
                return

            # Initialize multi-chain orchestrator if we have multiple chains
            if len(self._workers) >= 2:
                self._multi_chain_orchestrator = MultiChainOrchestrator(self._workers)
                logger.info("Multi-chain orchestrator initialized for cross-chain operations.")

            # Start all workers
            worker_tasks = [asyncio.create_task(worker.start()) for worker in self._workers]
            
            # Start multi-chain orchestrator if available
            if self._multi_chain_orchestrator:
                worker_tasks.append(asyncio.create_task(self._multi_chain_orchestrator.start()))
            
            # Start performance monitoring
            self._performance_monitor_task = asyncio.create_task(self._performance_monitor_loop())
            
            await self._notification_service.send_alert(
                title="ON1Builder Started",
                message=f"Application is now running and monitoring {len(self._workers)} chain(s).",
                level="INFO",
                details={
                    "active_chains": settings.chains,
                    "multi_chain_enabled": self._multi_chain_orchestrator is not None,
                    "balance_managers": len(self._balance_managers)
                }
            )

            await self._shutdown_event.wait()

        except Exception as e:
            logger.critical(f"An unhandled error occurred in the MainOrchestrator: {e}", exc_info=True)
            await self._notification_service.send_alert(
                title="Critical Orchestrator Failure",
                message="A fatal error occurred, and the application is shutting down.",
                level="CRITICAL",
                details={"error": str(e)}
            )
        finally:
            logger.info("MainOrchestrator run loop exiting. Final cleanup...")
            await self._shutdown()

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
        await self._db_interface.close()

        logger.info("Closing notification service session...")
        await self._notification_service.close()
        
        logger.info("ON1Builder has been shut down gracefully.")

    async def _performance_monitor_loop(self):
        """Monitors overall system performance and generates periodic reports."""
        while self._is_running:
            try:
                await asyncio.sleep(settings.performance_report_interval)
                
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
            total_profit = Decimal('0')
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
                        "balance_eth": float(balance_manager.get_balance('ETH')),
                        "successful_trades": getattr(worker.tx_manager, 'successful_trades', 0),
                        "failed_trades": getattr(worker.tx_manager, 'failed_trades', 0)
                    }
                    total_trades += chain_performances[worker.chain_id]["successful_trades"]
            
            # Calculate success rate
            total_failed = sum(perf["failed_trades"] for perf in chain_performances.values())
            success_rate = (total_trades / (total_trades + total_failed)) * 100 if (total_trades + total_failed) > 0 else 0
            
            await self._notification_service.send_alert(
                title="Hourly Performance Report",
                message=f"System generated ${total_profit:.2f} profit from {total_trades} successful trades",
                level="INFO",
                details={
                    "total_profit_usd": float(total_profit),
                    "total_trades": total_trades,
                    "success_rate_percent": round(success_rate, 2),
                    "chain_performances": chain_performances,
                    "multi_chain_active": self._multi_chain_orchestrator is not None
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating performance report: {e}", exc_info=True)

    async def _check_system_health(self):
        """Performs system health checks and alerts on issues."""
        try:
            unhealthy_chains = []
            
            for worker in self._workers:
                # Check if worker is responsive
                if not hasattr(worker, 'last_heartbeat') or \
                   (datetime.now() - getattr(worker, 'last_heartbeat', datetime.min)).seconds > 300:
                    unhealthy_chains.append(worker.chain_id)
                
                # Check balance manager health
                balance_manager = self._balance_managers.get(worker.chain_id)
                if balance_manager:
                    eth_balance = balance_manager.get_balance('ETH')
                    if eth_balance < Decimal('0.01'):  # Low ETH balance warning
                        await self._notification_service.send_alert(
                            title=f"Low ETH Balance Warning - Chain {worker.chain_id}",
                            message=f"ETH balance is critically low: {eth_balance:.6f} ETH",
                            level="WARNING",
                            details={"chain_id": worker.chain_id, "eth_balance": float(eth_balance)}
                        )
            
            if unhealthy_chains:
                await self._notification_service.send_alert(
                    title="System Health Alert",
                    message=f"Detected unresponsive workers on chains: {unhealthy_chains}",
                    level="ERROR",
                    details={"unhealthy_chains": unhealthy_chains}
                )
                
        except Exception as e:
            logger.error(f"Error in system health check: {e}", exc_info=True)

    async def _generate_final_report(self):
        """Generates a comprehensive final report on system shutdown."""
        try:
            await self._generate_performance_report()
            
            # Additional shutdown metrics
            uptime = datetime.now() - getattr(self, '_start_time', datetime.now())
            
            await self._notification_service.send_alert(
                title="ON1Builder Shutdown Complete",
                message=f"System operated for {uptime} and is now offline",
                level="INFO",
                details={
                    "uptime_hours": round(uptime.total_seconds() / 3600, 2),
                    "workers_count": len(self._workers),
                    "shutdown_time": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating final report: {e}", exc_info=True)
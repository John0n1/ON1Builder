#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import asyncio
from typing import Any, cast

from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3
from web3.types import TxParams

from on1builder.config.loaders import settings
from on1builder.core.balance_manager import BalanceManager
from on1builder.core.nonce_manager import NonceManager
from on1builder.core.transaction_manager import TransactionManager
from on1builder.engines.safety_guard import SafetyGuard
from on1builder.engines.strategy_executor import StrategyExecutor
from on1builder.monitoring.market_data_feed import MarketDataFeed
from on1builder.monitoring.txpool_scanner import TxPoolScanner
from on1builder.utils.custom_exceptions import InitializationError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.memory_optimizer import get_memory_optimizer
from on1builder.utils.web3_factory import Web3ConnectionFactory

logger = get_logger(__name__)


class ChainWorker:
    """
    ON1Builder chain worker with balance management and comprehensive monitoring.
    Manages all operations for a single blockchain with balance-aware strategies.
    """

    def __init__(self, chain_id: int):
        self.chain_id = chain_id
        self.is_running = False
        self._tasks: list[asyncio.Task[Any]] = []

        # Core components
        self.web3: AsyncWeb3 | None = None
        self.account: LocalAccount | None = None
        self.balance_manager: BalanceManager | None = None

        # Managers
        self.market_feed: MarketDataFeed | None = None
        self.tx_scanner: TxPoolScanner | None = None
        self.tx_manager: TransactionManager | None = None
        self.strategy_executor: StrategyExecutor | None = None
        self.safety_guard: SafetyGuard | None = None
        self.nonce_manager: NonceManager | None = None

        # Performance tracking with ON1Builder metrics
        self._performance_stats = {
            "opportunities_detected": 0,
            "opportunities_executed": 0,
            "total_profit_eth": 0.0,
            "uptime_seconds": 0,
            "memory_cleanups": 0,
            "balance_updates": 0,
            "error_count": 0,
            "last_heartbeat": 0,
        }
        self._start_time = 0
        self._memory_optimizer = get_memory_optimizer()

        logger.debug("ChainWorker created for chain ID: %s", self.chain_id)

    async def initialize(self):
        """
        ON1Builder initialization with balance management and comprehensive validation.
        """
        try:
            logger.debug(
                f"[Chain {self.chain_id}] Initializing ON1Builder worker components..."
            )

            # Initialize Web3 connection
            self.web3 = await Web3ConnectionFactory.create_connection(self.chain_id)

            # Initialize account
            from eth_account import Account

            wallet_key = settings.wallet_keys.get(self.chain_id, settings.wallet_key)
            wallet_address = settings.wallet_addresses.get(
                self.chain_id, settings.wallet_address
            )

            self.account = Account.from_key(wallet_key)

            if (
                wallet_address
                and self.account.address.lower() != wallet_address.lower()
            ):
                raise InitializationError(
                    "WALLET_KEY does not correspond to WALLET_ADDRESS.",
                    component="ChainWorker",
                )

            # Initialize balance manager first (other components depend on it)
            self.balance_manager = BalanceManager(self.web3, self.account.address)
            await self.balance_manager.update_balance()

            # Check initial balance requirements
            balance_summary = await self.balance_manager.get_balance_summary()
            if balance_summary["balance"] < settings.emergency_balance_threshold:
                logger.debug(
                    f"[Chain {self.chain_id}] Very low balance detected: {balance_summary['balance']:.6f} ETH"
                )

            # Initialize other components
            self.market_feed = MarketDataFeed(self.web3)
            self.safety_guard = SafetyGuard(self.web3)
            self.nonce_manager = NonceManager(self.web3, self.account.address)

            # Initialize transaction manager with balance manager
            self.tx_manager = TransactionManager(
                web3=self.web3,
                account=self.account,
                chain_id=self.chain_id,
                balance_manager=self.balance_manager,
            )
            await self.tx_manager.initialize()  # Initialize gas optimizer and other components

            # Initialize strategy executor with balance manager
            self.strategy_executor = StrategyExecutor(
                transaction_manager=self.tx_manager,
                balance_manager=self.balance_manager,
            )

            # Initialize transaction pool scanner
            self.tx_scanner = TxPoolScanner(
                web3=self.web3,
                strategy_executor=self.strategy_executor,
                chain_id=self.chain_id,
            )

            # Register memory cleanup callbacks
            self._memory_optimizer.register_cleanup_callback(
                self._cleanup_worker_caches
            )

            logger.info(f"[Chain {self.chain_id}] ChainWorker initialized!")
            logger.debug(
                f"[Chain {self.chain_id}] Balance tier: {balance_summary['balance_tier']}, "
                f"Max investment: {balance_summary['max_investment']:.6f} ETH"
            )

        except Exception as e:
            logger.critical(f"[Chain {self.chain_id}] Node offline or syncing")
            raise InitializationError(
                f"ChainWorker {self.chain_id} Execution Client initialization failed"
            ) from e

    async def start(self):
        """startup with performance tracking and monitoring."""
        if self.is_running:
            logger.warning(f"[Chain {self.chain_id}] Worker is already running.")
            return

        if not all(
            [
                self.web3,
                self.account,
                self.market_feed,
                self.tx_scanner,
                self.balance_manager,
            ]
        ):
            logger.error(
                f"[Chain {self.chain_id}] Cannot start, worker not initialized."
            )
            return

        self.is_running = True
        self._start_time = asyncio.get_event_loop().time()

        logger.debug(f"[Chain {self.chain_id}] Starting ON1Builder background tasks...")

        # Start core monitoring tasks
        self._tasks.append(asyncio.create_task(self.market_feed.start()))
        self._tasks.append(asyncio.create_task(self.tx_scanner.start()))
        self._tasks.append(asyncio.create_task(self._ON1Builder_heartbeat()))
        self._tasks.append(asyncio.create_task(self._balance_monitoring_loop()))
        self._tasks.append(asyncio.create_task(self._performance_reporting_loop()))
        self._tasks.append(asyncio.create_task(self._run_startup_test_transaction()))

        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        """stop with comprehensive cleanup and final reporting."""
        if not self.is_running:
            return

        logger.debug(f"[Chain {self.chain_id}] Stopping ON1Builder worker...")
        self.is_running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(
            *[t for t in self._tasks if not t.done()], return_exceptions=True
        )
        self._tasks.clear()

        # Stop components
        if self.market_feed:
            await self.market_feed.stop()
        if self.tx_scanner:
            await self.tx_scanner.stop()

        # Final performance report
        await self._generate_final_report()

        logger.info("Closing ChainWorker...")

    async def _run_startup_test_transaction(self) -> None:
        """Attempt a startup test transaction for diagnostics."""
        if not getattr(settings, "startup_test_transaction", False):
            return
        if not getattr(settings, "allow_insufficient_funds_tests", False):
            logger.warning(
                "[Chain %s] Startup test transaction skipped; "
                "ALLOW_INSUFFICIENT_FUNDS_TESTS is disabled.",
                self.chain_id,
            )
            return
        if not self.tx_manager or not self.web3 or not self.account:
            return

        logger.warning(
            "[Chain %s] Running startup test transaction (diagnostics only).",
            self.chain_id,
        )

        try:
            gas_price = await self.web3.eth.gas_price
            max_allowed = self.web3.to_wei(settings.max_gas_price_gwei, "gwei")
            if gas_price > max_allowed:
                gas_price = max_allowed

            nonce = (
                await self.nonce_manager.get_next_nonce() if self.nonce_manager else 0
            )
            tx_params = cast(
                TxParams,
                {
                    "from": self.account.address,
                    "to": self.account.address,
                    "value": 0,
                    "gas": 21000,
                    "gasPrice": gas_price,
                    "nonce": nonce,
                    "chainId": self.chain_id,
                },
            )

            try:
                await self.tx_manager._simulate_transaction(tx_params)
            except Exception as exc:
                logger.debug(
                    "[Chain %s] Startup test simulation failed: %s",
                    self.chain_id,
                    exc,
                )

            result = await self.tx_manager.execute_and_confirm(
                tx_params,
                "startup_test",
                allow_recovery_retry=False,
            )
            if not result.get("success") and self.nonce_manager:
                await self.nonce_manager.resync_nonce()
        except Exception as exc:
            logger.warning(
                "[Chain %s] Startup test transaction failed: %s",
                self.chain_id,
                exc,
            )

    def _cleanup_worker_caches(self) -> None:
        """Memory cleanup callback for worker-specific caches."""
        try:
            cleanup_count = 0

            # Clean transaction scanner caches
            if self.tx_scanner:
                cache_stats = self.tx_scanner.get_cache_stats()
                if cache_stats["tx_analysis_cache_size"] > 500:
                    # Force cache cleanup in scanner
                    self.tx_scanner._manage_cache_size()
                    cleanup_count += 1

            # Clean transaction manager caches
            if self.tx_manager:
                # Transaction manager specific cleanup can be added here
                pass

            # Clean strategy executor memory
            if self.strategy_executor:
                # Strategy executor specific cleanup can be added here
                pass

            self._performance_stats["memory_cleanups"] += cleanup_count
            logger.debug(f"[Chain {self.chain_id}] Worker cache cleanup completed")

        except Exception as e:
            logger.error(f"[Chain {self.chain_id}] Error in worker cache cleanup: {e}")

    async def _ON1Builder_heartbeat(self):
        """heartbeat with comprehensive status reporting."""
        while self.is_running:
            try:
                # Update performance stats
                current_time = asyncio.get_event_loop().time()
                self._performance_stats["uptime_seconds"] = int(
                    current_time - self._start_time
                )
                self._performance_stats["last_heartbeat"] = current_time

                # Get comprehensive status
                balance_summary = await self.balance_manager.get_balance_summary()
                tx_manager_stats = await self.tx_manager.get_performance_stats()
                await self.strategy_executor.get_strategy_report()

                # Get memory metrics
                memory_metrics = self._memory_optimizer.get_current_metrics()

                logger.info(
                    f"[Chain {self.chain_id} ON1Builder Heartbeat] "
                    f"Status: Running | "
                    f"Balance: {balance_summary['balance']:.6f} ETH ({balance_summary['balance_tier']}) | "
                    f"Pending TXs: {self.tx_scanner.get_pending_tx_count()} | "
                    f"Success Rate: {tx_manager_stats['success_rate_percentage']:.1f}% | "
                    f"Net Profit: {tx_manager_stats['net_profit_eth']:.6f} ETH | "
                    f"Opportunities: {self._performance_stats['opportunities_detected']} | "
                    f"Memory: {memory_metrics.process_memory_mb:.1f}MB"
                )

                # Emergency balance warning
                if balance_summary["emergency_mode"]:
                    logger.debug(
                        f"[Chain {self.chain_id}] EMERGENCY MODE: Very low balance!"
                    )

                await asyncio.sleep(settings.heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._performance_stats["error_count"] += 1
                logger.error(f"[Chain {self.chain_id} ON1Builder Heartbeat] Error: {e}")
                await asyncio.sleep(settings.heartbeat_interval)

    async def _balance_monitoring_loop(self):
        """Dedicated balance monitoring and tier adjustment loop."""
        while self.is_running:
            try:
                # Update balance and check for tier changes
                old_summary = await self.balance_manager.get_balance_summary()
                await self.balance_manager.update_balance(force=True)
                new_summary = await self.balance_manager.get_balance_summary()

                # Log significant balance changes
                balance_change = new_summary["balance"] - old_summary["balance"]
                if abs(balance_change) > 0.001:  # More than 0.001 ETH change
                    logger.info(
                        f"[Chain {self.chain_id}] Balance change: {balance_change:+.6f} ETH"
                    )
                    self._performance_stats["balance_updates"] += 1

                # Emergency stop if balance too low
                if (
                    new_summary["emergency_mode"]
                    and old_summary["balance_tier"] != "emergency"
                ):
                    logger.critical(
                        f"[Chain {self.chain_id}] Emergency balance threshold reached! "
                        f"Current balance: {new_summary['balance']:.6f} ETH"
                    )
                    # Could implement emergency stop here if needed

                await asyncio.sleep(30)  # Check balance every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Chain {self.chain_id}] Balance monitoring error: {e}")
                await asyncio.sleep(30)

    async def _performance_reporting_loop(self):
        """Periodic performance reporting and optimization."""
        while self.is_running:
            try:
                # Generate performance report every 10 minutes
                await asyncio.sleep(600)

                if not self.is_running:
                    break

                # Get comprehensive performance data
                balance_summary = await self.balance_manager.get_balance_summary()
                tx_stats = await self.tx_manager.get_performance_stats()
                strategy_report = await self.strategy_executor.get_strategy_report()

                # Calculate profitability metrics
                roi = 0.0
                if tx_stats["total_gas_spent_eth"] > 0:
                    roi = (
                        tx_stats["net_profit_eth"] / tx_stats["total_gas_spent_eth"]
                    ) * 100

                performance_report = {
                    "chain_id": self.chain_id,
                    "uptime_hours": self._performance_stats["uptime_seconds"] / 3600,
                    "balance_summary": balance_summary,
                    "transaction_stats": tx_stats,
                    "strategy_performance": strategy_report["strategy_performance"],
                    "roi_percentage": roi,
                    "opportunities_per_hour": (
                        self._performance_stats["opportunities_detected"]
                        / max(1, self._performance_stats["uptime_seconds"] / 3600)
                    ),
                }

                logger.info(
                    f"[Chain {self.chain_id}] Performance Report: "
                    f"ROI: {roi:.2f}%, "
                    f"Opportunities/hr: {performance_report['opportunities_per_hour']:.1f}, "
                    f"Success Rate: {tx_stats['success_rate_percentage']:.1f}%"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"[Chain {self.chain_id}] Performance reporting error: {e}"
                )

    async def _generate_final_report(self):
        """Generate final performance report on shutdown."""
        try:
            # Get final stats
            balance_summary = await self.balance_manager.get_balance_summary()
            tx_stats = await self.tx_manager.get_performance_stats()
            await self.strategy_executor.get_strategy_report()

            total_time_hours = self._performance_stats["uptime_seconds"] / 3600

            final_report = {
                "chain_id": self.chain_id,
                "total_runtime_hours": total_time_hours,
                "final_balance_eth": balance_summary["balance"],
                "total_transactions": tx_stats["total_transactions"],
                "successful_transactions": tx_stats["successful_transactions"],
                "total_profit_eth": tx_stats["total_profit_eth"],
                "total_gas_spent_eth": tx_stats["total_gas_spent_eth"],
                "net_profit_eth": tx_stats["net_profit_eth"],
                "opportunities_detected": self._performance_stats[
                    "opportunities_detected"
                ],
                "opportunities_executed": self._performance_stats[
                    "opportunities_executed"
                ],
            }

            logger.info(
                f"[Chain {self.chain_id}] FINAL REPORT: "
                f"Runtime: {total_time_hours:.2f}h, "
                f"Net Profit: {final_report['net_profit_eth']:.6f} ETH, "
                f"Transactions: {final_report['successful_transactions']}/{final_report['total_transactions']}"
            )

        except Exception as e:
            logger.error(
                f"[Chain {self.chain_id}] Failed to generate final report: {e}"
            )

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive worker status."""
        if not self.is_running:
            return {"status": "stopped", "chain_id": self.chain_id}

        try:
            assert self.balance_manager is not None
            assert self.tx_manager is not None
            assert self.strategy_executor is not None
            assert self.tx_scanner is not None

            balance_summary = await self.balance_manager.get_balance_summary()
            tx_stats = await self.tx_manager.get_performance_stats()
            strategy_report = await self.strategy_executor.get_strategy_report()

            return {
                "status": "running",
                "chain_id": self.chain_id,
                "uptime_seconds": self._performance_stats["uptime_seconds"],
                "balance_summary": balance_summary,
                "transaction_stats": tx_stats,
                "strategy_summary": {
                    "execution_count": strategy_report["execution_count"],
                    "recent_performance": strategy_report["recent_performance"],
                    "ml_parameters": strategy_report["ml_parameters"],
                },
                "performance_stats": self._performance_stats,
                "pending_transactions": self.tx_scanner.get_pending_tx_count(),
            }
        except Exception as e:
            logger.error(f"[Chain {self.chain_id}] Failed to get status: {e}")
            return {"status": "error", "chain_id": self.chain_id, "error": str(e)}

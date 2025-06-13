# src/on1builder/core/chain_worker.py
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3

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
from on1builder.utils.web3_factory import Web3ConnectionFactory

logger = get_logger(__name__)

class ChainWorker:
    """
    Enhanced chain worker with balance management and comprehensive monitoring.
    Manages all operations for a single blockchain with balance-aware strategies.
    """

    def __init__(self, chain_id: int):
        self.chain_id = chain_id
        self.is_running = False
        self._tasks = []

        # Core components
        self.web3: Optional[AsyncWeb3] = None
        self.account: Optional[LocalAccount] = None
        self.balance_manager: Optional[BalanceManager] = None
        
        # Managers
        self.market_feed: Optional[MarketDataFeed] = None
        self.tx_scanner: Optional[TxPoolScanner] = None
        self.tx_manager: Optional[TransactionManager] = None
        self.strategy_executor: Optional[StrategyExecutor] = None
        self.safety_guard: Optional[SafetyGuard] = None
        self.nonce_manager: Optional[NonceManager] = None
        
        # Performance tracking
        self._performance_stats = {
            "opportunities_detected": 0,
            "opportunities_executed": 0,
            "total_profit_eth": 0.0,
            "uptime_seconds": 0
        }
        self._start_time = 0
        
        logger.info(f"Enhanced ChainWorker created for chain ID: {self.chain_id}")

    async def initialize(self):
        """
        Enhanced initialization with balance management and comprehensive validation.
        """
        try:
            logger.info(f"[Chain {self.chain_id}] Initializing enhanced worker components...")

            # Initialize Web3 connection
            self.web3 = await Web3ConnectionFactory.create_connection(self.chain_id)
            
            # Initialize account
            from eth_account import Account
            self.account = Account.from_key(settings.wallet_key)

            if self.account.address.lower() != settings.wallet_address.lower():
                raise InitializationError(
                    "WALLET_KEY does not correspond to WALLET_ADDRESS.",
                    component="ChainWorker"
                )

            # Initialize balance manager first (other components depend on it)
            self.balance_manager = BalanceManager(self.web3, self.account.address)
            await self.balance_manager.update_balance()
            
            # Check initial balance requirements
            balance_summary = await self.balance_manager.get_balance_summary()
            if balance_summary["balance"] < settings.emergency_balance_threshold:
                logger.warning(f"[Chain {self.chain_id}] Very low balance detected: {balance_summary['balance']:.6f} ETH")
            
            # Initialize other components
            self.market_feed = MarketDataFeed(self.web3)
            self.safety_guard = SafetyGuard(self.web3)
            self.nonce_manager = NonceManager(self.web3, self.account.address)
            
            # Initialize transaction manager with balance manager
            self.tx_manager = TransactionManager(
                web3=self.web3,
                account=self.account,
                chain_id=self.chain_id,
                balance_manager=self.balance_manager
            )
            await self.tx_manager.initialize()  # Initialize gas optimizer and other components
            
            # Initialize strategy executor with balance manager
            self.strategy_executor = StrategyExecutor(
                transaction_manager=self.tx_manager,
                balance_manager=self.balance_manager
            )
            
            # Initialize transaction pool scanner
            self.tx_scanner = TxPoolScanner(
                web3=self.web3,
                strategy_executor=self.strategy_executor
            )
            
            logger.info(f"[Chain {self.chain_id}] Enhanced worker initialized successfully.")
            logger.info(f"[Chain {self.chain_id}] Balance tier: {balance_summary['balance_tier']}, "
                       f"Max investment: {balance_summary['max_investment']:.6f} ETH")

        except Exception as e:
            logger.critical(f"[Chain {self.chain_id}] Failed to initialize: {e}", exc_info=True)
            raise InitializationError(f"ChainWorker {self.chain_id} failed to initialize.") from e

    async def start(self):
        """Enhanced startup with performance tracking and monitoring."""
        if self.is_running:
            logger.warning(f"[Chain {self.chain_id}] Worker is already running.")
            return

        if not all([self.web3, self.account, self.market_feed, self.tx_scanner, self.balance_manager]):
            logger.error(f"[Chain {self.chain_id}] Cannot start, worker not initialized.")
            return
            
        self.is_running = True
        self._start_time = asyncio.get_event_loop().time()
        
        logger.info(f"[Chain {self.chain_id}] Starting enhanced background tasks...")

        # Start core monitoring tasks
        self._tasks.append(asyncio.create_task(self.market_feed.start()))
        self._tasks.append(asyncio.create_task(self.tx_scanner.start()))
        self._tasks.append(asyncio.create_task(self._enhanced_heartbeat()))
        self._tasks.append(asyncio.create_task(self._balance_monitoring_loop()))
        self._tasks.append(asyncio.create_task(self._performance_reporting_loop()))

        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        """Enhanced stop with comprehensive cleanup and final reporting."""
        if not self.is_running:
            return

        logger.info(f"[Chain {self.chain_id}] Stopping enhanced worker...")
        self.is_running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*[t for t in self._tasks if not t.done()], return_exceptions=True)
        self._tasks.clear()

        # Stop components
        if self.market_feed:
            await self.market_feed.stop()
        if self.tx_scanner:
            await self.tx_scanner.stop()

        # Final performance report
        await self._generate_final_report()

        logger.info(f"[Chain {self.chain_id}] Enhanced worker stopped.")
        
    async def _enhanced_heartbeat(self):
        """Enhanced heartbeat with comprehensive status reporting."""
        while self.is_running:
            try:
                # Update performance stats
                current_time = asyncio.get_event_loop().time()
                self._performance_stats["uptime_seconds"] = int(current_time - self._start_time)
                
                # Get comprehensive status
                balance_summary = await self.balance_manager.get_balance_summary()
                tx_manager_stats = await self.tx_manager.get_performance_stats()
                strategy_report = await self.strategy_executor.get_strategy_report()
                
                logger.info(
                    f"[Chain {self.chain_id} Enhanced Heartbeat] "
                    f"Status: Running | "
                    f"Balance: {balance_summary['balance']:.6f} ETH ({balance_summary['balance_tier']}) | "
                    f"Pending TXs: {self.tx_scanner.get_pending_tx_count()} | "
                    f"Success Rate: {tx_manager_stats['success_rate_percentage']:.1f}% | "
                    f"Net Profit: {tx_manager_stats['net_profit_eth']:.6f} ETH | "
                    f"Opportunities: {self._performance_stats['opportunities_detected']}"
                )
                
                # Emergency balance warning
                if balance_summary["emergency_mode"]:
                    logger.warning(f"[Chain {self.chain_id}] EMERGENCY MODE: Very low balance!")
                
                await asyncio.sleep(settings.heartbeat_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Chain {self.chain_id} Enhanced Heartbeat] Error: {e}")
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
                    logger.info(f"[Chain {self.chain_id}] Balance change: {balance_change:+.6f} ETH")
                
                # Emergency stop if balance too low
                if new_summary["emergency_mode"] and old_summary["balance_tier"] != "emergency":
                    logger.critical(f"[Chain {self.chain_id}] Emergency balance threshold reached! "
                                  f"Current balance: {new_summary['balance']:.6f} ETH")
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
                    roi = (tx_stats["net_profit_eth"] / tx_stats["total_gas_spent_eth"]) * 100
                
                performance_report = {
                    "chain_id": self.chain_id,
                    "uptime_hours": self._performance_stats["uptime_seconds"] / 3600,
                    "balance_summary": balance_summary,
                    "transaction_stats": tx_stats,
                    "strategy_performance": strategy_report["strategy_performance"],
                    "roi_percentage": roi,
                    "opportunities_per_hour": (
                        self._performance_stats["opportunities_detected"] / 
                        max(1, self._performance_stats["uptime_seconds"] / 3600)
                    )
                }
                
                logger.info(f"[Chain {self.chain_id}] Performance Report: "
                           f"ROI: {roi:.2f}%, "
                           f"Opportunities/hr: {performance_report['opportunities_per_hour']:.1f}, "
                           f"Success Rate: {tx_stats['success_rate_percentage']:.1f}%")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Chain {self.chain_id}] Performance reporting error: {e}")

    async def _generate_final_report(self):
        """Generate final performance report on shutdown."""
        try:
            # Get final stats
            balance_summary = await self.balance_manager.get_balance_summary()
            tx_stats = await self.tx_manager.get_performance_stats()
            strategy_report = await self.strategy_executor.get_strategy_report()
            
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
                "opportunities_detected": self._performance_stats["opportunities_detected"],
                "opportunities_executed": self._performance_stats["opportunities_executed"]
            }
            
            logger.info(f"[Chain {self.chain_id}] FINAL REPORT: "
                       f"Runtime: {total_time_hours:.2f}h, "
                       f"Net Profit: {final_report['net_profit_eth']:.6f} ETH, "
                       f"Transactions: {final_report['successful_transactions']}/{final_report['total_transactions']}")
            
        except Exception as e:
            logger.error(f"[Chain {self.chain_id}] Failed to generate final report: {e}")

    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive worker status."""
        if not self.is_running:
            return {"status": "stopped", "chain_id": self.chain_id}
        
        try:
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
                    "ml_parameters": strategy_report["ml_parameters"]
                },
                "performance_stats": self._performance_stats,
                "pending_transactions": self.tx_scanner.get_pending_tx_count()
            }
        except Exception as e:
            logger.error(f"[Chain {self.chain_id}] Failed to get status: {e}")
            return {"status": "error", "chain_id": self.chain_id, "error": str(e)}
# src/on1builder/monitoring/performance_monitor.py
# flake8: noqa E501
"""Performance monitoring and metrics collection for ON1Builder."""

from __future__ import annotations

import asyncio
import psutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""

    timestamp: datetime = field(default_factory=datetime.now)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    active_connections: int = 0
    total_transactions: int = 0
    successful_transactions: int = 0
    failed_transactions: int = 0
    total_profit_eth: Decimal = field(default_factory=lambda: Decimal("0"))
    gas_used_eth: Decimal = field(default_factory=lambda: Decimal("0"))
    average_execution_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate transaction success rate."""
        if self.total_transactions == 0:
            return 0.0
        return (self.successful_transactions / self.total_transactions) * 100

    @property
    def net_profit_eth(self) -> Decimal:
        """Calculate net profit after gas costs."""
        return self.total_profit_eth - self.gas_used_eth


@dataclass
class ChainMetrics:
    """Performance metrics for a specific chain."""

    chain_id: int
    is_healthy: bool = True
    connection_status: str = "connected"
    last_block_number: int = 0
    block_lag: int = 0
    transactions_per_minute: float = 0.0
    average_gas_price_gwei: float = 0.0
    pending_transactions: int = 0
    last_update: datetime = field(default_factory=datetime.now)


class PerformanceMonitor:
    """Monitors system and application performance metrics."""

    def __init__(self, collection_interval: int = 60):
        self.collection_interval = collection_interval
        self._metrics_history: List[PerformanceMetrics] = []
        self._chain_metrics: Dict[int, ChainMetrics] = {}
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._max_history_size = 1440  # 24 hours of minute-by-minute data
        self._transaction_times: List[float] = []
        self._last_cleanup = datetime.now()

    async def start(self):
        """Start the performance monitoring loop."""
        if self._is_running:
            logger.warning("Performance monitor is already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"Performance monitor started with {self.collection_interval}s interval")

    async def stop(self):
        """Stop the performance monitoring."""
        self._is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Performance monitor stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._is_running:
            try:
                await self._collect_metrics()
                await self._cleanup_old_data()
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance monitoring loop: {e}")
                await asyncio.sleep(self.collection_interval)

    async def _collect_metrics(self):
        """Collect current performance metrics."""
        try:
            # System metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()

            # Application metrics (these would be updated by other components)
            metrics = PerformanceMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                average_execution_time_ms=self._calculate_average_execution_time(),
            )

            self._metrics_history.append(metrics)

            # Trim history if too large
            if len(self._metrics_history) > self._max_history_size:
                self._metrics_history = self._metrics_history[-self._max_history_size :]

            logger.debug(f"Collected metrics: CPU {cpu_percent:.1f}%, Memory {memory.percent:.1f}%")

        except Exception as e:
            logger.error(f"Error collecting performance metrics: {e}")

    def _calculate_average_execution_time(self) -> float:
        """Calculate average execution time from recent transactions."""
        if not self._transaction_times:
            return 0.0

        # Keep only recent execution times (last 100)
        self._transaction_times = self._transaction_times[-100:]
        return sum(self._transaction_times) / len(self._transaction_times)

    async def _cleanup_old_data(self):
        """Clean up old performance data."""
        now = datetime.now()
        if now - self._last_cleanup < timedelta(hours=1):
            return

        # Remove metrics older than 24 hours
        cutoff_time = now - timedelta(hours=24)
        self._metrics_history = [m for m in self._metrics_history if m.timestamp > cutoff_time]

        # Clean up chain metrics
        for chain_id, chain_metrics in list(self._chain_metrics.items()):
            if now - chain_metrics.last_update > timedelta(hours=1):
                chain_metrics.is_healthy = False
                chain_metrics.connection_status = "stale"

        self._last_cleanup = now
        logger.debug("Cleaned up old performance data")

    def record_transaction(
        self,
        chain_id: int,
        success: bool,
        execution_time_ms: float,
        profit_eth: Optional[Decimal] = None,
        gas_used_eth: Optional[Decimal] = None,
    ):
        """Record a transaction for performance tracking."""
        try:
            # Update latest metrics
            if self._metrics_history:
                latest = self._metrics_history[-1]
                latest.total_transactions += 1
                if success:
                    latest.successful_transactions += 1
                else:
                    latest.failed_transactions += 1

                if profit_eth:
                    latest.total_profit_eth += profit_eth
                if gas_used_eth:
                    latest.gas_used_eth += gas_used_eth

            # Record execution time
            self._transaction_times.append(execution_time_ms)

            # Update chain metrics
            if chain_id in self._chain_metrics:
                chain_metrics = self._chain_metrics[chain_id]
                chain_metrics.last_update = datetime.now()

        except Exception as e:
            logger.error(f"Error recording transaction metrics: {e}")

    def update_chain_metrics(
        self, chain_id: int, block_number: int, gas_price_gwei: float, pending_tx_count: int
    ):
        """Update metrics for a specific chain."""
        try:
            if chain_id not in self._chain_metrics:
                self._chain_metrics[chain_id] = ChainMetrics(chain_id=chain_id)

            chain_metrics = self._chain_metrics[chain_id]

            # Calculate block lag (simplified)
            if chain_metrics.last_block_number > 0:
                chain_metrics.block_lag = max(0, chain_metrics.last_block_number - block_number + 1)

            chain_metrics.last_block_number = block_number
            chain_metrics.average_gas_price_gwei = gas_price_gwei
            chain_metrics.pending_transactions = pending_tx_count
            chain_metrics.last_update = datetime.now()
            chain_metrics.is_healthy = True
            chain_metrics.connection_status = "connected"

        except Exception as e:
            logger.error(f"Error updating chain metrics for {chain_id}: {e}")

    def mark_chain_unhealthy(self, chain_id: int, reason: str):
        """Mark a chain as unhealthy."""
        if chain_id in self._chain_metrics:
            self._chain_metrics[chain_id].is_healthy = False
            self._chain_metrics[chain_id].connection_status = reason
            logger.warning(f"Chain {chain_id} marked as unhealthy: {reason}")

    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Get the most recent performance metrics."""
        return self._metrics_history[-1] if self._metrics_history else None

    def get_metrics_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Get a summary of performance metrics for the specified time period."""
        if not self._metrics_history:
            return {"error": "No metrics available"}

        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_metrics = [m for m in self._metrics_history if m.timestamp > cutoff_time]

        if not recent_metrics:
            return {"error": f"No metrics available for the last {hours} hour(s)"}

        # Calculate averages and totals
        avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
        avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
        total_transactions = sum(m.total_transactions for m in recent_metrics)
        total_successful = sum(m.successful_transactions for m in recent_metrics)
        total_profit = sum(m.total_profit_eth for m in recent_metrics)
        total_gas = sum(m.gas_used_eth for m in recent_metrics)

        success_rate = (
            (total_successful / total_transactions * 100) if total_transactions > 0 else 0
        )

        return {
            "time_period_hours": hours,
            "metrics_count": len(recent_metrics),
            "system": {
                "avg_cpu_percent": round(avg_cpu, 2),
                "avg_memory_percent": round(avg_memory, 2),
            },
            "trading": {
                "total_transactions": total_transactions,
                "successful_transactions": total_successful,
                "success_rate_percent": round(success_rate, 2),
                "total_profit_eth": float(total_profit),
                "total_gas_eth": float(total_gas),
                "net_profit_eth": float(total_profit - total_gas),
            },
            "chains": {
                chain_id: {
                    "healthy": metrics.is_healthy,
                    "status": metrics.connection_status,
                    "last_block": metrics.last_block_number,
                    "gas_price_gwei": metrics.average_gas_price_gwei,
                    "pending_tx": metrics.pending_transactions,
                }
                for chain_id, metrics in self._chain_metrics.items()
            },
        }

    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status."""
        current_metrics = self.get_current_metrics()

        if not current_metrics:
            return {"status": "unknown", "reason": "No metrics available"}

        issues = []

        # Check system resources
        if current_metrics.cpu_percent > 80:
            issues.append(f"High CPU usage: {current_metrics.cpu_percent:.1f}%")

        if current_metrics.memory_percent > 85:
            issues.append(f"High memory usage: {current_metrics.memory_percent:.1f}%")

        # Check chain health
        unhealthy_chains = [
            chain_id for chain_id, metrics in self._chain_metrics.items() if not metrics.is_healthy
        ]

        if unhealthy_chains:
            issues.append(f"Unhealthy chains: {unhealthy_chains}")

        # Check success rate
        if current_metrics.total_transactions > 10 and current_metrics.success_rate < 50:
            issues.append(f"Low success rate: {current_metrics.success_rate:.1f}%")

        if issues:
            return {
                "status": "degraded" if len(issues) <= 2 else "unhealthy",
                "issues": issues,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

    async def generate_report(self, hours: int = 24) -> str:
        """Generate a comprehensive performance report."""
        summary = self.get_metrics_summary(hours)
        health = self.get_health_status()

        report_lines = [
            f"ON1Builder Performance Report ({hours}h)",
            "=" * 50,
            "",
            f"System Health: {health['status'].upper()}",
        ]

        if "issues" in health:
            report_lines.extend(["Issues:", *[f"  - {issue}" for issue in health["issues"]], ""])

        if "system" in summary:
            report_lines.extend(
                [
                    "System Metrics:",
                    f"  Average CPU: {summary['system']['avg_cpu_percent']}%",
                    f"  Average Memory: {summary['system']['avg_memory_percent']}%",
                    "",
                ]
            )

        if "trading" in summary:
            trading = summary["trading"]
            report_lines.extend(
                [
                    "Trading Performance:",
                    f"  Total Transactions: {trading['total_transactions']}",
                    f"  Success Rate: {trading['success_rate_percent']}%",
                    f"  Total Profit: {trading['total_profit_eth']} ETH",
                    f"  Gas Costs: {trading['total_gas_eth']} ETH",
                    f"  Net Profit: {trading['net_profit_eth']} ETH",
                    "",
                ]
            )

        if "chains" in summary:
            report_lines.append("Chain Status:")
            for chain_id, chain_data in summary["chains"].items():
                status = "[OK]" if chain_data["healthy"] else "[X]"
                report_lines.append(
                    f"  {status} Chain {chain_id}: {chain_data['status']} "
                    f"(Block: {chain_data['last_block']}, "
                    f"Gas: {chain_data['gas_price_gwei']} gwei)"
                )

        return "\n".join(report_lines)

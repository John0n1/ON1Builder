"""Behavioral tests for performance monitoring logic (no system dependency)."""
from datetime import datetime, timedelta
from decimal import Decimal

from on1builder.monitoring.performance_monitor import (
    ChainMetrics,
    PerformanceMetrics,
    PerformanceMonitor,
)


def test_record_transaction_updates_metrics_and_chains():
    monitor = PerformanceMonitor()
    # Seed metrics history with a baseline entry
    baseline = PerformanceMetrics(cpu_percent=10.0, memory_percent=20.0)
    monitor._metrics_history.append(baseline)
    monitor._chain_metrics[1] = ChainMetrics(chain_id=1)

    monitor.record_transaction(
        chain_id=1,
        success=True,
        execution_time_ms=120.0,
        profit_eth=Decimal("0.3"),
        gas_used_eth=Decimal("0.05"),
    )

    latest = monitor.get_current_metrics()
    assert latest.total_transactions == 1
    assert latest.successful_transactions == 1
    assert latest.total_profit_eth == Decimal("0.3")
    assert latest.gas_used_eth == Decimal("0.05")
    assert latest.net_profit_eth == Decimal("0.25")
    assert monitor._chain_metrics[1].is_healthy is True


def test_health_status_reflects_degradation_conditions():
    monitor = PerformanceMonitor()
    degraded = PerformanceMetrics(
        cpu_percent=90.0,
        memory_percent=70.0,
        total_transactions=20,
        successful_transactions=5,
        failed_transactions=15,
    )
    monitor._metrics_history.append(degraded)
    monitor._chain_metrics[42] = ChainMetrics(chain_id=42, is_healthy=False, connection_status="stale")
    monitor.mark_chain_unhealthy(42, "stale")

    health = monitor.get_health_status()
    assert health["status"] in {"degraded", "unhealthy"}
    assert any("CPU" in issue or "Low success rate" in issue for issue in health.get("issues", []))


def test_metrics_summary_aggregates_over_window():
    monitor = PerformanceMonitor()
    now = datetime.now()
    metrics1 = PerformanceMetrics(
        timestamp=now - timedelta(minutes=30),
        cpu_percent=20,
        memory_percent=30,
        total_transactions=2,
        successful_transactions=1,
        failed_transactions=1,
        total_profit_eth=Decimal("1.0"),
        gas_used_eth=Decimal("0.1"),
    )
    metrics2 = PerformanceMetrics(
        timestamp=now - timedelta(minutes=10),
        cpu_percent=40,
        memory_percent=50,
        total_transactions=3,
        successful_transactions=2,
        failed_transactions=1,
        total_profit_eth=Decimal("2.0"),
        gas_used_eth=Decimal("0.2"),
    )
    monitor._metrics_history.extend([metrics1, metrics2])

    summary = monitor.get_metrics_summary(hours=1)
    assert summary["metrics_count"] == 2
    assert summary["trading"]["total_transactions"] == 5
    assert summary["trading"]["successful_transactions"] == 3
    assert summary["trading"]["net_profit_eth"] == float(Decimal("3.0") - Decimal("0.3"))

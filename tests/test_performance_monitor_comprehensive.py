from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.monitoring import performance_monitor as perf_module
from on1builder.monitoring.performance_monitor import (
    ChainMetrics,
    PerformanceMetrics,
    PerformanceMonitor,
)


def test_performance_metrics_properties():
    metrics = PerformanceMetrics(
        total_transactions=4,
        successful_transactions=3,
        total_profit_eth=Decimal("2"),
        gas_used_eth=Decimal("0.5"),
    )
    assert metrics.success_rate == 75.0
    assert metrics.net_profit_eth == Decimal("1.5")


@pytest.mark.asyncio
async def test_start_stop_and_monitoring_loop(monkeypatch):
    monitor = PerformanceMonitor(collection_interval=1)

    class FakeTask:
        def cancel(self):
            self.cancelled = True

        def __await__(self):
            if False:
                yield None
            return None

    monkeypatch.setattr(perf_module.asyncio, "create_task", lambda coro: FakeTask())
    await monitor.start()
    assert monitor._is_running is True
    await monitor.start()
    await monitor.stop()
    assert monitor._is_running is False

    monitor._is_running = True
    monitor._collect_metrics = AsyncMock(
        side_effect=lambda: setattr(monitor, "_is_running", False)
    )
    monitor._cleanup_old_data = AsyncMock()
    monkeypatch.setattr(perf_module.asyncio, "sleep", AsyncMock())
    await monitor._monitoring_loop()
    monitor._collect_metrics.assert_awaited_once()


@pytest.mark.asyncio
async def test_collect_metrics_cleanup_and_chain_updates(monkeypatch):
    monitor = PerformanceMonitor()
    monkeypatch.setattr(perf_module.psutil, "cpu_percent", lambda interval=1: 20.0)
    monkeypatch.setattr(
        perf_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(percent=40.0, used=200 * 1024 * 1024),
    )
    monitor._transaction_times = [100, 200, 300]
    await monitor._collect_metrics()
    assert monitor.get_current_metrics().average_execution_time_ms == 200

    old = PerformanceMetrics(timestamp=datetime.now() - timedelta(days=2))
    recent = PerformanceMetrics(timestamp=datetime.now())
    monitor._metrics_history = [old, recent]
    monitor._chain_metrics = {
        1: ChainMetrics(chain_id=1, last_update=datetime.now() - timedelta(hours=2))
    }
    monitor._last_cleanup = datetime.now() - timedelta(hours=2)
    await monitor._cleanup_old_data()
    assert monitor._metrics_history == [recent]
    assert monitor._chain_metrics[1].connection_status == "stale"

    monitor.update_chain_metrics(
        1, block_number=10, gas_price_gwei=3.0, pending_tx_count=2
    )
    assert monitor._chain_metrics[1].last_block_number == 10
    monitor.mark_chain_unhealthy(1, "offline")
    assert monitor._chain_metrics[1].is_healthy is False


def test_record_transaction_summary_and_health():
    monitor = PerformanceMonitor()
    baseline = PerformanceMetrics(
        cpu_percent=90,
        memory_percent=90,
        total_transactions=11,
        successful_transactions=4,
        failed_transactions=7,
        total_profit_eth=Decimal("3"),
        gas_used_eth=Decimal("1"),
    )
    baseline.timestamp = datetime.now()
    monitor._metrics_history.append(baseline)
    monitor._chain_metrics[1] = ChainMetrics(
        chain_id=1,
        is_healthy=False,
        connection_status="down",
        last_block_number=10,
        average_gas_price_gwei=2.0,
        pending_transactions=1,
    )

    monitor.record_transaction(
        1, True, 120, profit_eth=Decimal("1"), gas_used_eth=Decimal("0.1")
    )
    summary = monitor.get_metrics_summary(hours=1)
    assert summary["trading"]["total_transactions"] >= 12

    health = monitor.get_health_status()
    assert health["status"] in {"degraded", "unhealthy"}


@pytest.mark.asyncio
async def test_generate_report_formats_output():
    monitor = PerformanceMonitor()
    metric = PerformanceMetrics(
        timestamp=datetime.now(),
        cpu_percent=20,
        memory_percent=30,
        total_transactions=2,
        successful_transactions=1,
        failed_transactions=1,
        total_profit_eth=Decimal("1"),
        gas_used_eth=Decimal("0.2"),
    )
    monitor._metrics_history.append(metric)
    monitor._chain_metrics[1] = ChainMetrics(
        chain_id=1,
        is_healthy=True,
        connection_status="connected",
        last_block_number=10,
        average_gas_price_gwei=2.0,
        pending_transactions=1,
    )

    report = await monitor.generate_report(hours=1)
    assert "Performance Report" in report
    assert "Chain 1" in report

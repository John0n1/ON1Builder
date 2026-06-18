from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.utils import memory_optimizer as memory_module
from on1builder.utils.memory_optimizer import (
    MemoryMetrics,
    MemoryOptimizer,
    cleanup_memory_optimization,
    get_memory_optimizer,
    initialize_memory_optimization,
)


@pytest.fixture(autouse=True)
def reset_global_optimizer():
    memory_module._memory_optimizer = None
    yield
    memory_module._memory_optimizer = None


def test_get_current_metrics_and_register_callback(monkeypatch):
    fake_process = MagicMock()
    fake_process.memory_info.return_value = SimpleNamespace(rss=50 * 1024 * 1024)
    monkeypatch.setattr(memory_module.psutil, "Process", lambda: fake_process)
    monkeypatch.setattr(
        memory_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            total=1024 * 1024 * 1024,
            available=512 * 1024 * 1024,
            used=256 * 1024 * 1024,
            percent=25.0,
        ),
    )
    monkeypatch.setattr(memory_module.gc, "get_objects", lambda: [1, 2, 3])

    optimizer = MemoryOptimizer(
        gc_threshold_mb=100, cleanup_interval_seconds=5, memory_warning_threshold=70
    )

    def callback():
        pass

    optimizer.register_cleanup_callback(callback)
    metrics = optimizer.get_current_metrics()

    assert metrics.process_memory_mb == 50
    assert metrics.memory_percent == 25.0
    assert metrics.python_objects_count == 3
    assert optimizer._cleanup_callbacks == [callback]


@pytest.mark.asyncio
async def test_force_cleanup_collects_stats(monkeypatch):
    optimizer = MemoryOptimizer()

    def good_callback():
        return None

    def bad_callback():
        raise RuntimeError("cleanup failed")

    optimizer.register_cleanup_callback(good_callback)
    optimizer.register_cleanup_callback(bad_callback)

    before = MemoryMetrics(datetime.now(), 0, 0, 0, 80, 120, 1000)
    after = MemoryMetrics(datetime.now(), 0, 0, 0, 40, 90, 700)
    metrics_iter = iter([before, after])
    monkeypatch.setattr(optimizer, "get_current_metrics", lambda: next(metrics_iter))
    monkeypatch.setattr(memory_module.gc, "collect", lambda generation: generation + 1)

    stats = await optimizer.force_cleanup()

    assert stats["memory_freed_mb"] == 30
    assert stats["objects_freed"] == 300
    assert stats["gc_collected"] == 6
    assert stats["gc_by_generation"] == [1, 2, 3]
    assert stats["callback_results"][0].startswith("Success")
    assert "Failed: bad_callback" in stats["callback_results"][1]


@pytest.mark.asyncio
async def test_start_and_stop_monitoring(monkeypatch):
    optimizer = MemoryOptimizer()

    class FakeTask:
        def __init__(self, coro):
            self.coro = coro
            self.cancel = MagicMock()

        def __await__(self):
            self.coro.close()
            if False:
                yield None
            return None

    monkeypatch.setattr(
        memory_module.asyncio, "create_task", lambda coro: FakeTask(coro)
    )

    await optimizer.start_monitoring()
    assert optimizer._is_running is True
    assert optimizer._monitor_task is not None

    await optimizer.start_monitoring()
    task = optimizer._monitor_task
    await optimizer.stop_monitoring()
    task.cancel.assert_called_once()
    assert optimizer._is_running is False


@pytest.mark.asyncio
async def test_monitoring_loop_triggers_cleanup_and_trims_history(monkeypatch):
    optimizer = MemoryOptimizer(
        gc_threshold_mb=100, cleanup_interval_seconds=0, memory_warning_threshold=70
    )
    optimizer._is_running = True
    optimizer._metrics_history = [
        MemoryMetrics(datetime.now(), 0, 0, 0, 10, 1, 1) for _ in range(1001)
    ]
    optimizer.force_cleanup = AsyncMock()

    metric = MemoryMetrics(datetime.now(), 0, 0, 0, 90, 150, 5)
    monkeypatch.setattr(optimizer, "get_current_metrics", lambda: metric)

    async def fake_sleep(_seconds):
        optimizer._is_running = False

    monkeypatch.setattr(memory_module.asyncio, "sleep", fake_sleep)
    await optimizer._monitoring_loop()

    optimizer.force_cleanup.assert_awaited_once()
    assert len(optimizer._metrics_history) == 500


@pytest.mark.asyncio
async def test_monitoring_loop_handles_exceptions(monkeypatch):
    optimizer = MemoryOptimizer()
    optimizer._is_running = True

    def broken_metrics():
        raise RuntimeError("boom")

    monkeypatch.setattr(optimizer, "get_current_metrics", broken_metrics)

    async def fake_sleep(seconds):
        optimizer._is_running = False
        assert seconds == 60

    monkeypatch.setattr(memory_module.asyncio, "sleep", fake_sleep)
    await optimizer._monitoring_loop()


def test_get_memory_analytics_with_and_without_history():
    optimizer = MemoryOptimizer(
        gc_threshold_mb=50, cleanup_interval_seconds=15, memory_warning_threshold=75
    )
    assert optimizer.get_memory_analytics() == {"error": "No metrics available"}

    now = datetime.now()
    optimizer._is_running = True
    optimizer._metrics_history = [
        MemoryMetrics(now - timedelta(minutes=2), 0, 500, 0, 20, 50, 100),
        MemoryMetrics(now - timedelta(minutes=1), 0, 400, 0, 25, 60, 120),
        MemoryMetrics(now, 0, 300, 0, 30, 80, 140),
    ]
    analytics = optimizer.get_memory_analytics()

    assert analytics["current_metrics"]["process_memory_mb"] == 80
    assert analytics["trends"]["avg_memory_mb"] == pytest.approx((50 + 60 + 80) / 3)
    assert analytics["thresholds"]["gc_threshold_mb"] == 50
    assert analytics["cleanup_info"]["monitoring_active"] is True


@pytest.mark.asyncio
async def test_global_memory_optimizer_helpers(monkeypatch):
    optimizer = MemoryOptimizer()
    optimizer.start_monitoring = AsyncMock()
    optimizer.stop_monitoring = AsyncMock()
    memory_module._memory_optimizer = optimizer

    assert get_memory_optimizer() is optimizer
    await initialize_memory_optimization()
    optimizer.start_monitoring.assert_awaited_once()

    await cleanup_memory_optimization()
    optimizer.stop_monitoring.assert_awaited_once()
    assert memory_module._memory_optimizer is None

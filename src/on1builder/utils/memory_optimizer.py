# src/on1builder/utils/memory_optimizer.py
# flake8: noqa E501
"""Memory optimization utilities for ON1Builder."""

from __future__ import annotations

import gc
import sys
import psutil
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from dataclasses import dataclass

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryMetrics:
    """Memory usage metrics snapshot."""

    timestamp: datetime
    total_memory_mb: float
    available_memory_mb: float
    used_memory_mb: float
    memory_percent: float
    process_memory_mb: float
    python_objects_count: int


class MemoryOptimizer:
    """Advanced memory optimization manager for long-running MEV operations."""

    def __init__(
        self,
        gc_threshold_mb: float = 512.0,
        cleanup_interval_seconds: int = 300,
        memory_warning_threshold: float = 80.0,
    ):
        self._gc_threshold_mb = gc_threshold_mb
        self._cleanup_interval = cleanup_interval_seconds
        self._memory_warning_threshold = memory_warning_threshold

        # Memory tracking
        self._metrics_history: List[MemoryMetrics] = []
        self._cleanup_callbacks: List[Callable[[], None]] = []
        self._last_cleanup = datetime.now()
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # Process reference for memory monitoring
        self._process = psutil.Process()

        logger.info(f"MemoryOptimizer initialized with {gc_threshold_mb}MB GC threshold")

    async def start_monitoring(self):
        """Start background memory monitoring and optimization."""
        if self._is_running:
            logger.warning("Memory monitoring is already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Memory monitoring started")

    async def stop_monitoring(self):
        """Stop background memory monitoring."""
        if not self._is_running:
            return

        self._is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Memory monitoring stopped")

    def register_cleanup_callback(self, callback: Callable[[], None]):
        """Register a cleanup callback to be called during memory optimization."""
        self._cleanup_callbacks.append(callback)
        logger.debug(f"Registered cleanup callback: {callback.__name__}")

    def get_current_metrics(self) -> MemoryMetrics:
        """Get current memory usage metrics."""
        # System memory info
        memory = psutil.virtual_memory()

        # Process memory info
        process_memory = self._process.memory_info().rss / 1024 / 1024  # MB

        # Python object count
        objects_count = len(gc.get_objects())

        return MemoryMetrics(
            timestamp=datetime.now(),
            total_memory_mb=memory.total / 1024 / 1024,
            available_memory_mb=memory.available / 1024 / 1024,
            used_memory_mb=memory.used / 1024 / 1024,
            memory_percent=memory.percent,
            process_memory_mb=process_memory,
            python_objects_count=objects_count,
        )

    async def force_cleanup(self) -> Dict[str, Any]:
        """Force immediate memory cleanup and return statistics."""
        logger.info("Forcing memory cleanup")

        # Get metrics before cleanup
        before_metrics = self.get_current_metrics()

        # Run registered cleanup callbacks
        cleanup_results = []
        for callback in self._cleanup_callbacks:
            try:
                result = callback()
                cleanup_results.append(f"Success: {callback.__name__}")
            except Exception as e:
                cleanup_results.append(f"Failed: {callback.__name__} - {e}")
                logger.error(f"Cleanup callback {callback.__name__} failed: {e}")

        # Force garbage collection
        collected_objects = []
        for generation in range(3):
            collected = gc.collect(generation)
            collected_objects.append(collected)

        # Get metrics after cleanup
        after_metrics = self.get_current_metrics()

        # Calculate improvements
        memory_freed_mb = before_metrics.process_memory_mb - after_metrics.process_memory_mb
        objects_freed = before_metrics.python_objects_count - after_metrics.python_objects_count

        cleanup_stats = {
            "cleanup_time": datetime.now().isoformat(),
            "memory_freed_mb": memory_freed_mb,
            "objects_freed": objects_freed,
            "gc_collected": sum(collected_objects),
            "gc_by_generation": collected_objects,
            "callback_results": cleanup_results,
            "before_memory_mb": before_metrics.process_memory_mb,
            "after_memory_mb": after_metrics.process_memory_mb,
            "memory_percent_before": before_metrics.memory_percent,
            "memory_percent_after": after_metrics.memory_percent,
        }

        self._last_cleanup = datetime.now()
        logger.info(
            f"Memory cleanup completed. Freed: {memory_freed_mb:.2f}MB, {objects_freed} objects"
        )

        return cleanup_stats

    async def _monitoring_loop(self):
        """Background monitoring loop."""
        while self._is_running:
            try:
                # Get current metrics
                metrics = self.get_current_metrics()
                self._metrics_history.append(metrics)

                # Limit metrics history size
                if len(self._metrics_history) > 1000:
                    self._metrics_history = self._metrics_history[-500:]

                # Check if cleanup is needed
                cleanup_needed = False

                # Check process memory threshold
                if metrics.process_memory_mb > self._gc_threshold_mb:
                    logger.warning(f"Process memory usage high: {metrics.process_memory_mb:.2f}MB")
                    cleanup_needed = True

                # Check system memory threshold
                if metrics.memory_percent > self._memory_warning_threshold:
                    logger.warning(f"System memory usage high: {metrics.memory_percent:.1f}%")
                    cleanup_needed = True

                # Check cleanup interval
                if (datetime.now() - self._last_cleanup).seconds > self._cleanup_interval:
                    cleanup_needed = True

                # Perform cleanup if needed
                if cleanup_needed:
                    await self.force_cleanup()

                # Sleep for a bit before next check
                await asyncio.sleep(30)  # Check every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in memory monitoring loop: {e}")
                await asyncio.sleep(60)  # Back off on error

    def get_memory_analytics(self) -> Dict[str, Any]:
        """Get comprehensive memory analytics."""
        if not self._metrics_history:
            return {"error": "No metrics available"}

        current = self._metrics_history[-1]

        # Calculate trends over recent history
        recent_metrics = (
            self._metrics_history[-20:]
            if len(self._metrics_history) >= 20
            else self._metrics_history
        )

        if len(recent_metrics) > 1:
            memory_trend = (
                recent_metrics[-1].process_memory_mb - recent_metrics[0].process_memory_mb
            ) / len(recent_metrics)
            avg_memory = sum(m.process_memory_mb for m in recent_metrics) / len(recent_metrics)
            peak_memory = max(m.process_memory_mb for m in recent_metrics)
        else:
            memory_trend = 0.0
            avg_memory = current.process_memory_mb
            peak_memory = current.process_memory_mb

        return {
            "current_metrics": {
                "process_memory_mb": current.process_memory_mb,
                "system_memory_percent": current.memory_percent,
                "python_objects": current.python_objects_count,
                "available_memory_mb": current.available_memory_mb,
            },
            "trends": {
                "memory_trend_mb_per_sample": memory_trend,
                "avg_memory_mb": avg_memory,
                "peak_memory_mb": peak_memory,
                "samples_count": len(recent_metrics),
            },
            "thresholds": {
                "gc_threshold_mb": self._gc_threshold_mb,
                "memory_warning_percent": self._memory_warning_threshold,
                "cleanup_interval_seconds": self._cleanup_interval,
            },
            "cleanup_info": {
                "registered_callbacks": len(self._cleanup_callbacks),
                "last_cleanup": self._last_cleanup.isoformat() if self._last_cleanup else None,
                "monitoring_active": self._is_running,
            },
        }


# Global memory optimizer instance
_memory_optimizer: Optional[MemoryOptimizer] = None


def get_memory_optimizer() -> MemoryOptimizer:
    """Get the global memory optimizer instance."""
    global _memory_optimizer
    if _memory_optimizer is None:
        _memory_optimizer = MemoryOptimizer()
    return _memory_optimizer


async def initialize_memory_optimization():
    """Initialize global memory optimization."""
    optimizer = get_memory_optimizer()
    await optimizer.start_monitoring()
    logger.info("Global memory optimization initialized")


async def cleanup_memory_optimization():
    """Cleanup global memory optimization."""
    global _memory_optimizer
    if _memory_optimizer:
        await _memory_optimizer.stop_monitoring()
        _memory_optimizer = None
    logger.info("Global memory optimization cleaned up")

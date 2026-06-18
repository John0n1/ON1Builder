#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

"""
ON1Builder – Error Handling Utilities
====================================
Standardized error handling and recovery mechanisms.
License: MIT
"""

from __future__ import annotations

import asyncio
import functools
import traceback
from collections.abc import Callable
from typing import Any, TypeVar

from .custom_exceptions import InitializationError
from .logging_config import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RecoveryError(Exception):
    """Raised when error recovery attempts fail."""

    pass


# Use ComponentInitializationError as alias to maintain compatibility
ComponentInitializationError = InitializationError


def with_error_handling(
    component_name: str,
    critical: bool = False,
    retry_count: int = 0,
    retry_delay: float = 1.0,
    fallback: Any | None = None,
):
    """Decorator for standardized error handling."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(retry_count + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt < retry_count:
                        logger.warning(
                            f"[{component_name}] Attempt {attempt + 1}/{retry_count + 1} failed: {e}"
                        )
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(
                            f"[{component_name}] All attempts failed: {e}\n"
                            f"Traceback: {traceback.format_exc()}"
                        )

            if critical:
                raise InitializationError(
                    f"Critical component {component_name} failed to initialize: {last_exception}"
                )

            logger.warning(
                f"[{component_name}] Using fallback value due to initialization failure"
            )
            return fallback

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(retry_count + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt < retry_count:
                        logger.warning(
                            f"[{component_name}] Attempt {attempt + 1}/{retry_count + 1} failed: {e}"
                        )
                        import time

                        time.sleep(retry_delay)
                    else:
                        logger.error(
                            f"[{component_name}] All attempts failed: {e}\n"
                            f"Traceback: {traceback.format_exc()}"
                        )

            if critical:
                raise InitializationError(
                    f"Critical component {component_name} failed to initialize: {last_exception}"
                )

            logger.warning(
                f"[{component_name}] Using fallback value due to initialization failure"
            )
            return fallback

        async_wrapper.__doc__ = (func.__doc__ or "").strip()
        sync_wrapper.__doc__ = (func.__doc__ or "").strip()
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


async def safe_call(
    func: Callable,
    *args,
    component_name: str = "unknown",
    fallback: Any = None,
    log_errors: bool = True,
    **kwargs,
) -> Any:
    """Safely call a function with error handling."""
    try:
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"[{component_name}] Error in safe_call: {e}")
        return fallback


class ComponentHealthTracker:
    """Tracks component health and provides recovery suggestions."""

    def __init__(self):
        self._health_status: dict[str, dict[str, Any]] = {}
        self._failure_counts: dict[str, int] = {}
        self._recovery_strategies: dict[str, Callable] = {}

    def register_component(
        self, name: str, recovery_strategy: Callable | None = None
    ) -> None:
        """Register a component for health tracking."""
        self._health_status[name] = {
            "healthy": True,
            "last_check": None,
            "error_count": 0,
            "last_error": None,
        }
        self._failure_counts[name] = 0

        if recovery_strategy:
            self._recovery_strategies[name] = recovery_strategy

    def report_health(self, name: str, healthy: bool, error: str | None = None) -> None:
        """Report component health status."""
        if name not in self._health_status:
            self.register_component(name)

        import time

        self._health_status[name]["healthy"] = healthy
        self._health_status[name]["last_check"] = time.time()

        if not healthy:
            self._health_status[name]["error_count"] += 1
            self._health_status[name]["last_error"] = error
            self._failure_counts[name] += 1
        else:
            self._failure_counts[name] = 0

    def get_unhealthy_components(self) -> dict[str, dict[str, Any]]:
        """Get list of unhealthy components."""
        return {
            name: status
            for name, status in self._health_status.items()
            if not status["healthy"]
        }

    async def attempt_recovery(self, component_name: str) -> bool:
        """Attempt to recover a failed component."""
        if component_name not in self._recovery_strategies:
            logger.warning(f"No recovery strategy available for {component_name}")
            return False

        try:
            recovery_func = self._recovery_strategies[component_name]
            if asyncio.iscoroutinefunction(recovery_func):
                result = await recovery_func()
            else:
                result = recovery_func()

            if result:
                logger.info(f"Successfully recovered component: {component_name}")
                self.report_health(component_name, True)
                return True
            else:
                logger.warning(f"Recovery attempt failed for: {component_name}")
                return False

        except Exception as e:
            logger.error(f"Error during recovery of {component_name}: {e}")
            return False

    def get_failure_count(self, component_name: str) -> int:
        """Get failure count for a component."""
        return self._failure_counts.get(component_name, 0)

    def should_attempt_recovery(
        self, component_name: str, max_failures: int = 3
    ) -> bool:
        """Determine if recovery should be attempted."""
        return self.get_failure_count(component_name) < max_failures


# Global health tracker instance
_health_tracker = ComponentHealthTracker()


def get_health_tracker() -> ComponentHealthTracker:
    """Get the global health tracker instance."""
    return _health_tracker

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Dependency Injection Container
==========================================
A simple dependency injection container to manage component lifecycle and
resolve circular dependencies.
License: MIT
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional, TypeVar

from on1builder.utils.logger import setup_logging

T = TypeVar("T")

logger = setup_logging("Container", level="DEBUG")


class Container:
    """A simple DI container for ON1Builder components.

    Manages instances and factory functions, and supports graceful shutdown.
    """

    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[..., Any]] = {}
        self._resolving: Dict[str, bool] = {}

    def register(self, key: str, instance: Any) -> None:
        """Register a concrete instance under a key."""
        self._instances[key] = instance
        logger.debug("Registered instance '%s'", key)

    def register_factory(self, key: str, factory: Callable[..., T]) -> None:
        """Register a factory for lazy instantiation under a key."""
        self._factories[key] = factory
        logger.debug("Registered factory '%s'", key)

    def get(self, key: str) -> Any:
        """Resolve and return the component for `key`, instantiating if needed.

        Raises:
            KeyError: if neither instance nor factory is registered.
        """
        if self._resolving.get(key):
            logger.warning("Circular dependency detected for '%s'", key)
            return None  # break the cycle temporarily

        if key in self._instances:
            return self._instances[key]

        if key in self._factories:
            logger.debug("Creating '%s' via factory", key)
            self._resolving[key] = True
            try:
                factory = self._factories[key]
                sig = inspect.signature(factory)
                if "container" in sig.parameters:
                    instance = factory(container=self)
                else:
                    instance = factory()
                self._instances[key] = instance
                return instance
            finally:
                self._resolving[key] = False

        raise KeyError(f"Component not registered: '{key}'")

    def get_or_none(self, key: str) -> Optional[Any]:
        """Like `get`, but returns None if not registered."""
        try:
            return self.get(key)
        except KeyError:
            return None

    def has(self, key: str) -> bool:
        """Return True if `key` is registered (as instance or factory)."""
        return key in self._instances or key in self._factories

    async def close(self) -> None:
        """Call `.close()` on all registered instances that provide it."""
        for key, instance in list(self._instances.items()):
            close = getattr(instance, "close", None)
            if callable(close):
                logger.debug("Closing component '%s'", key)
                if inspect.iscoroutinefunction(close):
                    await close()
                else:
                    close()


# Global singleton container
_container: Container = Container()


def get_container() -> Container:
    """Retrieve the global DI container."""
    return _container

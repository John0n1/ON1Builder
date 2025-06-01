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

import asyncio
import inspect
from typing import Any, Callable, Dict, Optional, Set, TypeVar

from on1builder.utils.logger import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


class Container:
    """A simple DI container for ON1Builder components.

    Manages instances and factory functions, and supports graceful shutdown.
    """

    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[..., Any]] = {}
        self._resolving: Dict[str, bool] = {}
        self._dependencies: Dict[str, Set[str]] = {}  # Track component dependencies
        self._main_core: Optional[Any] = None  # Reference to MainCore

    def register(self, key: str, instance: Any) -> None:
        """Register a concrete instance under a key."""
        self._instances[key] = instance
        logger.debug(f"Registered instance '{key}'")

    def register_factory(self, key: str, factory: Callable[..., T]) -> None:
        """Register a factory for lazy instantiation under a key."""
        self._factories[key] = factory
        logger.debug(f"Registered factory '{key}'")
        
    def register_main_core(self, main_core: Any) -> None:
        """Register the MainCore instance for shared resource access."""
        self._main_core = main_core
        self.register("main_core", main_core)
        logger.debug("Registered MainCore instance")
        
    def get_main_core(self) -> Optional[Any]:
        """Get the registered MainCore instance if available."""
        return self._main_core

    def get(self, key: str) -> Any:
        """Resolve and return the component for `key`, instantiating if needed.

        Raises:
            KeyError: if neither instance nor factory is registered.
        """
        if self._resolving.get(key):
            logger.warning(f"Circular dependency detected for '{key}'")
            return None  # break the cycle temporarily

        if key in self._instances:
            return self._instances[key]

        if key in self._factories:
            logger.debug(f"Creating '{key}' via factory")
            self._resolving[key] = True
            try:
                factory = self._factories[key]
                sig = inspect.signature(factory)
                
                # Check if factory requires container or main_core params
                kwargs = {}
                if "container" in sig.parameters:
                    kwargs["container"] = self
                if "main_core" in sig.parameters and self._main_core:
                    kwargs["main_core"] = self._main_core
                    
                # Track dependencies
                if key not in self._dependencies:
                    self._dependencies[key] = set()
                    
                if kwargs:
                    instance = factory(**kwargs)
                    # Record dependencies
                    if "main_core" in kwargs:
                        self._dependencies[key].add("main_core")
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
        """Call `.close()` or `.stop()` on all registered instances that provide it.
        
        Components are closed in dependency-order to ensure proper cleanup.
        """
        # Process in reverse dependency order (least dependent components first)
        closed_components = set()
        
        # First pass: close any components that don't have stop/close methods
        # to prevent them from being repeatedly visited
        for key, instance in list(self._instances.items()):
            if not hasattr(instance, "close") and not hasattr(instance, "stop"):
                closed_components.add(key)
                
        # Continue until all components are closed
        while len(closed_components) < len(self._instances):
            for key, instance in list(self._instances.items()):
                if key in closed_components:
                    continue
                    
                # Check if this component depends on any unclosed components
                dependencies = self._dependencies.get(key, set())
                if not dependencies.issubset(closed_components):
                    # Some dependencies not closed yet, skip this one
                    continue
                
                # Close this component
                await self._close_component(key, instance)
                closed_components.add(key)
                
        logger.info(f"Closed {len(closed_components)} components")

    async def _close_component(self, key: str, instance: Any) -> None:
        """Close a single component using appropriate method."""
        try:
            # Try stop() first (standard for our components)
            if hasattr(instance, "stop") and callable(instance.stop):
                logger.debug(f"Stopping component '{key}'")
                if inspect.iscoroutinefunction(instance.stop):
                    await instance.stop()
                else:
                    instance.stop()
                return
                
            # Fall back to close() for compatibility
            if hasattr(instance, "close") and callable(instance.close):
                logger.debug(f"Closing component '{key}'")
                if inspect.iscoroutinefunction(instance.close):
                    await instance.close()
                else:
                    instance.close()
                return
        except Exception as e:
            logger.error(f"Error closing component '{key}': {e}")


# Global singleton container
_container: Container = Container()

def get_container() -> Container:
    """Get the global container singleton."""
    return _container

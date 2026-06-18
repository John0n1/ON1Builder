#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from .logging_config import get_logger

T = TypeVar("T")
logger = get_logger(__name__)


class Container:
    """A dependency injection container for managing component lifecycles with async support."""

    def __init__(self) -> None:
        self._instances: dict[str, Any] = {}
        self._providers: dict[str, Callable[[], T]] = {}
        self._resolving: set[str] = set()
        self._singleton_instances: dict[str, Any] = {}

    def register_instance(self, key: str, instance: Any) -> None:
        """Registers a pre-instantiated object in the container."""
        if not key:
            raise ValueError("Key cannot be empty")
        logger.debug(
            f"Registering instance for key: '{key}' (type: {type(instance).__name__})"
        )
        self._instances[key] = instance

    def register_provider(self, key: str, provider: Callable[[], T]) -> None:
        """Registers a provider (factory function) for lazy instantiation."""
        if not key:
            raise ValueError("Key cannot be empty")
        if not callable(provider):
            raise TypeError("Provider must be callable")
        logger.debug(f"Registering provider for key: '{key}'")
        self._providers[key] = provider

    def register_singleton(self, key: str, provider: Callable[[], T]) -> None:
        """Registers a singleton provider that will only be instantiated once."""
        if not key:
            raise ValueError("Key cannot be empty")
        if not callable(provider):
            raise TypeError("Provider must be callable")
        logger.debug(f"Registering singleton provider for key: '{key}'")

        def singleton_wrapper():
            if key not in self._singleton_instances:
                self._singleton_instances[key] = provider()
            return self._singleton_instances[key]

        self._providers[key] = singleton_wrapper

    def get(self, key: str) -> Any:
        """Resolves and returns a component by its key."""
        if key in self._instances:
            return self._instances[key]

        if key in self._resolving:
            raise RuntimeError(f"Circular dependency detected for key: '{key}'")

        if key not in self._providers:
            raise KeyError(f"No provider registered for key: '{key}'")

        logger.debug(f"Resolving component for key: '{key}' via provider.")
        self._resolving.add(key)

        try:
            provider = self._providers[key]
            instance = provider()
            self._instances[key] = instance
        finally:
            self._resolving.remove(key)

        return instance

    def get_or_none(self, key: str) -> Any | None:
        """Safely resolves a component, returning None if not registered."""
        try:
            return self.get(key)
        except (KeyError, RuntimeError):
            return None

    async def shutdown(self) -> None:
        """Gracefully shuts down all registered instances that have a 'stop' or 'close' method."""
        logger.info("Shutting down all containerized components...")
        for key, instance in reversed(list(self._instances.items())):
            shutdown_method = None
            if hasattr(instance, "stop") and callable(instance.stop):
                shutdown_method = instance.stop
            elif hasattr(instance, "close") and callable(instance.close):
                shutdown_method = instance.close

            if shutdown_method:
                logger.debug(f"Shutting down component: '{key}'")
                try:
                    if inspect.iscoroutinefunction(shutdown_method):
                        await shutdown_method()
                    else:
                        shutdown_method()
                except Exception as e:
                    logger.error(
                        f"Error shutting down component '{key}': {e}", exc_info=True
                    )

        self._instances.clear()
        self._providers.clear()
        logger.info("All containerized components have been shut down.")


# Global instance of the container
_container = Container()


def get_container() -> Container:
    """Provides access to the global DI container."""
    return _container

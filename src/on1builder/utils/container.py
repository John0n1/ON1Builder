# src/on1builder/utils/container.py
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional, TypeVar

from .logging_config import get_logger

T = TypeVar("T")
logger = get_logger(__name__)

class Container:
    """A dependency injection container for managing component lifecycles with async support."""

    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}
        self._providers: Dict[str, Callable[[], T]] = {}
        self._resolving: set[str] = set()
        self._singleton_instances: Dict[str, Any] = {}

    def register_instance(self, key: str, instance: Any) -> None:
        """
        Registers a pre-instantiated object in the container.
        
        Args:
            key: The unique identifier for the component
            instance: The already-created instance to register
        """
        if not key:
            raise ValueError("Key cannot be empty")
        
        logger.debug(f"Registering instance for key: '{key}' (type: {type(instance).__name__})")
        self._instances[key] = instance

    def register_provider(self, key: str, provider: Callable[[], T]) -> None:
        """
        Registers a provider (factory function) for lazy instantiation.
        
        Args:
            key: The unique identifier for the component
            provider: A zero-argument function that returns an instance of the component
        """
        if not key:
            raise ValueError("Key cannot be empty")
        if not callable(provider):
            raise TypeError("Provider must be callable")
            
        logger.debug(f"Registering provider for key: '{key}'")
        self._providers[key] = provider

    def register_singleton(self, key: str, provider: Callable[[], T]) -> None:
        """
        Registers a singleton provider that will only be instantiated once.
        
        Args:
            key: The unique identifier for the singleton
            provider: A zero-argument function that returns an instance
        """
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
        """
        Resolves and returns a component by its key.
        Instantiates the component using its provider if it hasn't been already.
        
        Args:
            key: The unique identifier for the component.
            
        Returns:
            The resolved component instance.
            
        Raises:
            KeyError: If the key is not registered.
            RuntimeError: If a circular dependency is detected.
        """
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

    def get_or_none(self, key: str) -> Optional[Any]:
        """
        Safely resolves a component, returning None if not registered.
        
        Args:
            key: The unique identifier for the component.
            
        Returns:
            The resolved component instance or None.
        """
        try:
            return self.get(key)
        except (KeyError, RuntimeError):
            return None

    async def shutdown(self) -> None:
        """
        Gracefully shuts down all registered instances that have a 'stop' or 'close' method.
        This is typically called once when the application is exiting.
        """
        logger.info("Shutting down all containerized components...")
        
        # We shut down in the reverse order of creation, which is a simple and
        # effective way to handle dependencies (e.g., TransactionManager before DB).
        for key, instance in reversed(list(self._instances.items())):
            shutdown_method = None
            if hasattr(instance, 'stop') and callable(instance.stop):
                shutdown_method = instance.stop
            elif hasattr(instance, 'close') and callable(instance.close):
                shutdown_method = instance.close

            if shutdown_method:
                logger.debug(f"Shutting down component: '{key}'")
                try:
                    if inspect.iscoroutinefunction(shutdown_method):
                        await shutdown_method()
                    else:
                        shutdown_method()
                except Exception as e:
                    logger.error(f"Error shutting down component '{key}': {e}", exc_info=True)
        
        self._instances.clear()
        self._providers.clear()
        logger.info("All containerized components have been shut down.")


# Global instance of the container
_container = Container()

def get_container() -> Container:
    """Provides access to the global DI container."""
    return _container
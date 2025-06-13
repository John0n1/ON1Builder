# src/on1builder/utils/singleton.py
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, TypeVar

from .logging_config import get_logger

T = TypeVar("T")
logger = get_logger(__name__)

class SingletonMeta(type):
    """A thread-safe singleton metaclass."""
    _instances: Dict[type, Any] = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs) -> T:
        if cls not in cls._instances:
            with cls._lock:
                # Double-check locking
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]

    def reset_instance(cls) -> None:
        """For testing purposes, allows resetting the singleton instance."""
        with cls._lock:
            if cls in cls._instances:
                del cls._instances[cls]
                logger.debug(f"Singleton instance for {cls.__name__} has been reset.")


class SingletonRegistry:
    """A registry for managing named singleton instances, often created via factories."""
    _instances: Dict[str, Any] = {}
    _factories: Dict[str, Callable[..., Any]] = {}
    _lock: threading.Lock = threading.Lock()

    def register_factory(self, key: str, factory: Callable[..., T]) -> None:
        """
        Registers a factory function for lazy singleton creation.
        If a factory for the key already exists, it will be overwritten.
        """
        with self._lock:
            self._factories[key] = factory
            logger.debug(f"Registered singleton factory for key: '{key}'")

    def get(self, key: str, *args, **kwargs) -> Any:
        """
        Gets or creates a singleton instance using its registered factory.
        If the instance does not exist, it's created, cached, and returned.
        """
        if key not in self._instances:
            with self._lock:
                # Double-check locking
                if key not in self._instances:
                    if key not in self._factories:
                        raise KeyError(f"No factory registered for singleton key: '{key}'")
                    
                    factory = self._factories[key]
                    instance = factory(*args, **kwargs)
                    self._instances[key] = instance
                    logger.debug(f"Created singleton instance for key: '{key}'")
        
        return self._instances[key]

    def has(self, key: str) -> bool:
        """Checks if a singleton (instance or factory) is registered for the key."""
        return key in self._instances or key in self._factories

    def reset(self, key: Optional[str] = None) -> None:
        """
        Resets one or all singleton instances. For testing purposes.
        If key is None, all instances are cleared.
        """
        with self._lock:
            if key:
                if key in self._instances:
                    del self._instances[key]
                    logger.debug(f"Singleton instance for key '{key}' has been reset.")
            else:
                self._instances.clear()
                logger.debug("All singleton instances have been reset.")

    async def shutdown_all(self) -> None:
        """
        Gracefully shuts down all singleton instances that have a 'stop' or 'close' method.
        """
        import inspect
        
        logger.info("Shutting down all managed singletons...")
        for key, instance in list(self._instances.items()):
            shutdown_method = None
            if hasattr(instance, 'stop') and callable(instance.stop):
                shutdown_method = instance.stop
            elif hasattr(instance, 'close') and callable(instance.close):
                shutdown_method = instance.close

            if shutdown_method:
                try:
                    if inspect.iscoroutinefunction(shutdown_method):
                        await shutdown_method()
                    else:
                        shutdown_method()
                    logger.info(f"Successfully shut down singleton: '{key}'")
                except Exception as e:
                    logger.error(f"Error shutting down singleton '{key}': {e}", exc_info=True)


# Global instance of the registry
_registry = SingletonRegistry()

def get_singleton_registry() -> SingletonRegistry:
    """Provides access to the global singleton registry."""
    return _registry
"""
ON1Builder - Dependency Injection Container
=========================================

A simple dependency injection container to manage component lifecycle and resolve circular dependencies.
"""

from typing import Any, Dict, TypeVar, Optional, Callable
import inspect
import logging

# Type variable for container types
T = TypeVar("T")

# Logger for container operations
logger = logging.getLogger("Container")


class Container:
    """A simple dependency injection container.

    This container helps manage component lifecycles and resolve
    circular dependencies by providing a centralized registry for
    component instances.
    """

    def __init__(self) -> None:
        """Initialize an empty container."""
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[..., Any]] = {}
        self._resolving: Dict[str, bool] = {}

    def register(self, key: str, instance: Any) -> None:
        """Register a component instance in the container.

        Args:
            key: Unique identifier for the component
            instance: Component instance
        """
        self._instances[key] = instance
        logger.debug(f"Registered instance: {key}")

    def register_factory(self, key: str, factory: Callable[..., T]) -> None:
        """Register a factory function for lazy instantiation.

        Args:
            key: Unique identifier for the component
            factory: Function that creates the component instance
        """
        self._factories[key] = factory
        logger.debug(f"Registered factory: {key}")

    def get(self, key: str) -> Any:
        """Get a component instance from the container.

        If the component is not yet instantiated but a factory exists,
        it will be created using the factory.

        Args:
            key: Unique identifier for the component

        Returns:
            Component instance

        Raises:
            KeyError: If the component is not registered
        """
        # Check for circular dependency
        if self._resolving.get(key, False):
            logger.warning(f"Circular dependency detected for: {key}")
            # Return None temporarily to break the cycle
            return None

        # Return existing instance if available
        if key in self._instances:
            return self._instances[key]

        # Create instance using factory if available
        if key in self._factories:
            logger.debug(f"Creating instance from factory: {key}")
            self._resolving[key] = True
            try:
                # Get factory function
                factory = self._factories[key]

                # Check if factory takes a container parameter
                sig = inspect.signature(factory)
                if "container" in sig.parameters:
                    instance = factory(container=self)
                else:
                    instance = factory()

                # Store instance
                self._instances[key] = instance
                return instance
            finally:
                self._resolving[key] = False

        raise KeyError(f"Component not registered: {key}")

    def get_or_none(self, key: str) -> Optional[Any]:
        """Get a component instance or None if not registered.

        Args:
            key: Unique identifier for the component

        Returns:
            Component instance or None
        """
        try:
            return self.get(key)
        except KeyError:
            return None

    def has(self, key: str) -> bool:
        """Check if a component is registered.

        Args:
            key: Unique identifier for the component

        Returns:
            True if component is registered, False otherwise
        """
        return key in self._instances or key in self._factories

    async def close(self) -> None:
        """Close all components that have a close method.

        This method is used for graceful shutdown of the container.
        """
        for key, instance in self._instances.items():
            if hasattr(instance, "close") and callable(
                    getattr(instance, "close")):
                logger.debug(f"Closing component: {key}")

                close_method = getattr(instance, "close")
                if inspect.iscoroutinefunction(close_method):
                    await close_method()
                else:
                    close_method()


# Global container instance
_container = Container()


def get_container() -> Container:
    """Get the global container instance.

    Returns:
        Global container instance
    """
    global _container
    return _container

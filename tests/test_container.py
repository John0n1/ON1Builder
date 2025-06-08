#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for ON1Builder dependency injection container
==================================================

This module contains comprehensive tests for the dependency injection container
defined in src/on1builder/utils/container.py.
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from on1builder.utils.container import Container, get_container


class TestContainer:
    """Test cases for the Container class."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.container = Container()

    def test_initialization(self):
        """Test container initialization."""
        assert self.container._instances == {}
        assert self.container._factories == {}
        assert self.container._resolving == {}
        assert self.container._dependencies == {}
        assert self.container._main_orchestrator is None

    def test_register_instance(self):
        """Test registering a concrete instance."""
        instance = "test_instance"
        self.container.register("test_key", instance)
        
        assert "test_key" in self.container._instances
        assert self.container._instances["test_key"] == instance

    def test_register_factory(self):
        """Test registering a factory function."""
        def test_factory():
            return "factory_result"
        
        self.container.register_factory("test_factory", test_factory)
        
        assert "test_factory" in self.container._factories
        assert self.container._factories["test_factory"] == test_factory

    def test_register_main_orchestrator(self):
        """Test registering main orchestrator."""
        mock_orchestrator = MagicMock()
        self.container.register_main_orchestrator(mock_orchestrator)
        
        assert self.container._main_orchestrator == mock_orchestrator
        assert self.container._instances["main_orchestrator"] == mock_orchestrator

    def test_get_main_orchestrator(self):
        """Test getting main orchestrator."""
        assert self.container.get_main_orchestrator() is None
        
        mock_orchestrator = MagicMock()
        self.container.register_main_orchestrator(mock_orchestrator)
        
        assert self.container.get_main_orchestrator() == mock_orchestrator

    def test_get_existing_instance(self):
        """Test getting an existing instance."""
        instance = "test_instance"
        self.container.register("test_key", instance)
        
        result = self.container.get("test_key")
        assert result == instance

    def test_get_via_factory(self):
        """Test getting instance via factory."""
        def test_factory():
            return "factory_result"
        
        self.container.register_factory("test_factory", test_factory)
        
        result = self.container.get("test_factory")
        assert result == "factory_result"
        
        # Should be cached as instance now
        assert "test_factory" in self.container._instances
        assert self.container._instances["test_factory"] == "factory_result"

    def test_get_factory_with_container_parameter(self):
        """Test factory that requires container parameter."""
        def test_factory(container):
            return f"factory_with_container_{id(container)}"
        
        self.container.register_factory("test_factory", test_factory)
        
        result = self.container.get("test_factory")
        assert result.startswith("factory_with_container_")
        assert str(id(self.container)) in result

    def test_get_factory_with_main_orchestrator_parameter(self):
        """Test factory that requires main_orchestrator parameter."""
        mock_orchestrator = MagicMock()
        self.container.register_main_orchestrator(mock_orchestrator)
        
        def test_factory(main_orchestrator):
            return f"factory_with_orchestrator_{id(main_orchestrator)}"
        
        self.container.register_factory("test_factory", test_factory)
        
        result = self.container.get("test_factory")
        assert result.startswith("factory_with_orchestrator_")
        assert str(id(mock_orchestrator)) in result

    def test_get_factory_with_both_parameters(self):
        """Test factory that requires both container and main_orchestrator."""
        mock_orchestrator = MagicMock()
        self.container.register_main_orchestrator(mock_orchestrator)
        
        def test_factory(container, main_orchestrator):
            return {
                "container_id": id(container),
                "orchestrator_id": id(main_orchestrator)
            }
        
        self.container.register_factory("test_factory", test_factory)
        
        result = self.container.get("test_factory")
        assert result["container_id"] == id(self.container)
        assert result["orchestrator_id"] == id(mock_orchestrator)

    def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist."""
        with pytest.raises(KeyError, match="Component not registered: 'nonexistent'"):
            self.container.get("nonexistent")

    def test_get_or_none_existing(self):
        """Test get_or_none with existing key."""
        instance = "test_instance"
        self.container.register("test_key", instance)
        
        result = self.container.get_or_none("test_key")
        assert result == instance

    def test_get_or_none_nonexistent(self):
        """Test get_or_none with nonexistent key."""
        result = self.container.get_or_none("nonexistent")
        assert result is None

    def test_has_instance(self):
        """Test has() with registered instance."""
        self.container.register("test_key", "test_instance")
        assert self.container.has("test_key") is True

    def test_has_factory(self):
        """Test has() with registered factory."""
        def test_factory():
            return "test"
        
        self.container.register_factory("test_factory", test_factory)
        assert self.container.has("test_factory") is True

    def test_has_nonexistent(self):
        """Test has() with nonexistent key."""
        assert self.container.has("nonexistent") is False

    def test_circular_dependency_detection(self):
        """Test circular dependency detection."""
        def factory_a():
            # This will trigger circular dependency
            return self.container.get("test_b")
        
        def factory_b():
            return self.container.get("test_a")
        
        self.container.register_factory("test_a", factory_a)
        self.container.register_factory("test_b", factory_b)
        
        # Should return None for circular dependency
        result = self.container.get("test_a")
        assert result is None

    def test_dependency_tracking(self):
        """Test that dependencies are tracked correctly."""
        mock_orchestrator = MagicMock()
        self.container.register_main_orchestrator(mock_orchestrator)
        
        def test_factory(main_orchestrator):
            return "test_instance"
        
        self.container.register_factory("test_key", test_factory)
        self.container.get("test_key")
        
        assert "test_key" in self.container._dependencies
        assert "main_orchestrator" in self.container._dependencies["test_key"]

    @pytest.mark.asyncio
    async def test_close_simple_components(self):
        """Test closing components without dependencies."""
        mock_component1 = MagicMock()
        mock_component2 = MagicMock()
        
        self.container.register("comp1", mock_component1)
        self.container.register("comp2", mock_component2)
        
        await self.container.close()
        
        mock_component1.stop.assert_called_once()
        mock_component2.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_async_stop(self):
        """Test closing components with async stop methods."""
        mock_component = MagicMock()
        mock_component.stop = AsyncMock()
        
        self.container.register("async_comp", mock_component)
        
        await self.container.close()
        
        mock_component.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_close_method(self):
        """Test closing components that use close() instead of stop()."""
        mock_component = MagicMock()
        del mock_component.stop  # Remove stop method
        
        self.container.register("close_comp", mock_component)
        
        await self.container.close()
        
        mock_component.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_async_close(self):
        """Test closing components with async close methods."""
        mock_component = MagicMock()
        del mock_component.stop  # Remove stop method
        mock_component.close = AsyncMock()
        
        self.container.register("async_close_comp", mock_component)
        
        await self.container.close()
        
        mock_component.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_methods(self):
        """Test closing components without stop/close methods."""
        simple_instance = "simple_string"
        
        self.container.register("simple", simple_instance)
        
        # Should not raise an error
        await self.container.close()

    @pytest.mark.asyncio
    async def test_close_with_error(self):
        """Test closing components when stop/close raises an error."""
        mock_component = MagicMock()
        mock_component.stop.side_effect = Exception("Stop error")
        
        self.container.register("error_comp", mock_component)
        
        with patch('on1builder.utils.container.logger') as mock_logger:
            await self.container.close()
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_respects_dependencies(self):
        """Test that components are closed in dependency order."""
        # Create mock orchestrator
        mock_orchestrator = MagicMock()
        self.container.register_main_orchestrator(mock_orchestrator)
        
        # Create a component that depends on orchestrator
        def dependent_factory(main_orchestrator):
            return MagicMock()
        
        self.container.register_factory("dependent", dependent_factory)
        dependent_instance = self.container.get("dependent")
        
        close_order = []
        
        def record_close(name):
            def closer():
                close_order.append(name)
            return closer
        
        dependent_instance.stop = record_close("dependent")
        mock_orchestrator.stop = record_close("main_orchestrator")
        
        await self.container.close()
        
        # Dependent should be closed before main_orchestrator
        assert close_order.index("dependent") < close_order.index("main_orchestrator")


class TestGlobalContainer:
    """Test cases for the global container singleton."""

    def test_get_container_singleton(self):
        """Test that get_container returns the same instance."""
        container1 = get_container()
        container2 = get_container()
        
        assert container1 is container2
        assert isinstance(container1, Container)

    def test_global_container_persistence(self):
        """Test that global container persists across calls."""
        container = get_container()
        container.register("test_persistence", "persistent_value")
        
        # Get container again and check value persists
        container2 = get_container()
        assert container2.get("test_persistence") == "persistent_value"


if __name__ == "__main__":
    pytest.main([__file__])

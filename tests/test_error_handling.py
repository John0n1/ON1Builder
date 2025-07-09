#!/usr/bin/env python3
"""
Tests for error handling utilities.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

def test_error_handling_imports():
    """Test that error handling modules can be imported."""
    from on1builder.utils.error_handling import (
        RecoveryError,
        ComponentInitializationError,
        with_error_handling,
        safe_call,
        get_health_tracker
    )
    
    assert RecoveryError is not None
    assert ComponentInitializationError is not None
    assert with_error_handling is not None
    assert safe_call is not None
    assert get_health_tracker is not None

def test_recovery_error():
    """Test RecoveryError exception."""
    from on1builder.utils.error_handling import RecoveryError
    
    error = RecoveryError("Recovery failed")
    assert "Recovery failed" in str(error)

def test_component_health_tracker():
    """Test ComponentHealthTracker basic functionality."""
    from on1builder.utils.error_handling import ComponentHealthTracker
    
    tracker = ComponentHealthTracker()
    
    # Register a component
    tracker.register_component("test_component")
    
    # Report healthy status
    tracker.report_health("test_component", True)
    
    # Check failure count
    assert tracker.get_failure_count("test_component") == 0
    
    # Report unhealthy status
    tracker.report_health("test_component", False, "Test error")
    assert tracker.get_failure_count("test_component") == 1
    
    # Get unhealthy components
    unhealthy = tracker.get_unhealthy_components()
    assert "test_component" in unhealthy
    
    # Should attempt recovery
    assert tracker.should_attempt_recovery("test_component")

@pytest.mark.asyncio
async def test_safe_call_async():
    """Test safe_call with async functions."""
    from on1builder.utils.error_handling import safe_call
    
    async def success_func():
        return "success"
    
    async def failing_func():
        raise ValueError("Test error")
    
    # Test successful call
    result = await safe_call(success_func, component_name="test")
    assert result == "success"
    
    # Test failing call with fallback
    result = await safe_call(failing_func, component_name="test", fallback="fallback")
    assert result == "fallback"

def test_safe_call_sync():
    """Test safe_call with sync functions."""
    from on1builder.utils.error_handling import safe_call
    import asyncio
    
    def success_func():
        return "success"
    
    def failing_func():
        raise ValueError("Test error")
    
    # Test successful call
    async def run_test():
        result = await safe_call(success_func, component_name="test")
        assert result == "success"
        
        # Test failing call with fallback
        result = await safe_call(failing_func, component_name="test", fallback="fallback")
        assert result == "fallback"
    
    asyncio.run(run_test())

def test_with_error_handling_decorator():
    """Test with_error_handling decorator with sync functions."""
    from on1builder.utils.error_handling import with_error_handling
    
    @with_error_handling("test_component", fallback="default")
    def test_function():
        return "success"
    
    @with_error_handling("test_component", fallback="default")
    def failing_function():
        raise ValueError("Test error")
    
    # Test successful function
    result = test_function()
    assert result == "success"
    
    # Test failing function with fallback
    result = failing_function()
    assert result == "default"

def test_global_health_tracker():
    """Test global health tracker instance."""
    from on1builder.utils.error_handling import get_health_tracker
    
    tracker1 = get_health_tracker()
    tracker2 = get_health_tracker()
    
    # Should be the same instance
    assert tracker1 is tracker2

if __name__ == "__main__":
    pytest.main([__file__])
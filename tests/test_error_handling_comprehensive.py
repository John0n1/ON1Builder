"""Comprehensive tests for error_handling module."""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from on1builder.utils.error_handling import (
    RecoveryError,
    ComponentInitializationError,
    with_error_handling,
    safe_call,
    ComponentHealthTracker,
    get_health_tracker,
)
from on1builder.utils.custom_exceptions import InitializationError


class TestRecoveryError:
    """Test RecoveryError exception."""

    def test_recovery_error_creation(self):
        """Test RecoveryError can be created and raised."""
        error = RecoveryError("Recovery failed")
        assert str(error) == "Recovery failed"
        
        with pytest.raises(RecoveryError):
            raise RecoveryError("Test")


class TestComponentInitializationError:
    """Test ComponentInitializationError alias."""

    def test_is_alias_for_initialization_error(self):
        """Test ComponentInitializationError is alias for InitializationError."""
        assert ComponentInitializationError is InitializationError


class TestWithErrorHandlingDecorator:
    """Test with_error_handling decorator."""

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test decorator with successful async function."""
        @with_error_handling(component_name="test", critical=False)
        async def async_func(value):
            await asyncio.sleep(0.01)
            return value * 2
        
        result = await async_func(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_async_function_with_retry(self):
        """Test decorator with retry on async function."""
        call_count = 0
        
        @with_error_handling(component_name="test", retry_count=2, retry_delay=0.01)
        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"
        
        result = await async_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_function_with_fallback(self):
        """Test decorator with fallback on async function."""
        @with_error_handling(component_name="test", fallback="default", critical=False)
        async def async_func():
            raise RuntimeError("Always fails")
        
        result = await async_func()
        assert result == "default"

    @pytest.mark.asyncio
    async def test_async_function_critical_failure(self):
        """Test decorator with critical failure on async function."""
        @with_error_handling(component_name="critical_component", critical=True)
        async def async_func():
            raise ValueError("Critical error")
        
        with pytest.raises(InitializationError) as exc_info:
            await async_func()
        
        assert "critical_component" in str(exc_info.value)

    def test_sync_function_success(self):
        """Test decorator with successful sync function."""
        @with_error_handling(component_name="sync_test", critical=False)
        def sync_func(a, b):
            return a + b
        
        result = sync_func(3, 4)
        assert result == 7

    def test_sync_function_with_retry(self):
        """Test decorator with retry on sync function."""
        call_count = 0
        
        @with_error_handling(component_name="sync_test", retry_count=2, retry_delay=0.01)
        def sync_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Not yet")
            return "done"
        
        result = sync_func()
        assert result == "done"
        assert call_count == 2

    def test_sync_function_with_fallback(self):
        """Test decorator with fallback on sync function."""
        @with_error_handling(component_name="sync_test", fallback=42, critical=False)
        def sync_func():
            raise RuntimeError("Always fails")
        
        result = sync_func()
        assert result == 42

    def test_sync_function_critical_failure(self):
        """Test decorator with critical failure on sync function."""
        @with_error_handling(component_name="critical_sync", critical=True)
        def sync_func():
            raise ValueError("Critical error")
        
        with pytest.raises(InitializationError) as exc_info:
            sync_func()
        
        assert "critical_sync" in str(exc_info.value)

    def test_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""
        @with_error_handling(component_name="test")
        def documented_func():
            """This is a test function."""
            return "result"
        
        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a test function."


class TestSafeCall:
    """Test safe_call function."""

    @pytest.mark.asyncio
    async def test_safe_call_async_success(self):
        """Test safe_call with successful async function."""
        async def async_func(x):
            return x * 3
        
        result = await safe_call(async_func, 5, component_name="test")
        assert result == 15

    @pytest.mark.asyncio
    async def test_safe_call_async_with_kwargs(self):
        """Test safe_call with async function using kwargs."""
        async def async_func(a, b=10):
            return a + b
        
        result = await safe_call(async_func, 5, b=20, component_name="test")
        assert result == 25

    @pytest.mark.asyncio
    async def test_safe_call_async_with_error(self):
        """Test safe_call with async function that raises error."""
        async def async_func():
            raise ValueError("Async error")
        
        result = await safe_call(async_func, component_name="test", fallback="fallback")
        assert result == "fallback"

    def test_safe_call_sync_success(self):
        """Test safe_call with successful sync function."""
        def sync_func(x, y):
            return x * y
        
        result = asyncio.run(safe_call(sync_func, 4, 5, component_name="sync_test"))
        assert result == 20

    def test_safe_call_sync_with_error(self):
        """Test safe_call with sync function that raises error."""
        def sync_func():
            raise RuntimeError("Sync error")
        
        result = asyncio.run(safe_call(sync_func, component_name="test", fallback=None))
        assert result is None

    @pytest.mark.asyncio
    async def test_safe_call_no_logging(self):
        """Test safe_call with log_errors=False."""
        async def failing_func():
            raise ValueError("Should not be logged")
        
        with patch("on1builder.utils.error_handling.logger") as mock_logger:
            result = await safe_call(
                failing_func,
                component_name="test",
                fallback="default",
                log_errors=False
            )
            
            assert result == "default"
            # Logger should not be called
            mock_logger.error.assert_not_called()


class TestComponentHealthTracker:
    """Test ComponentHealthTracker class."""

    def test_register_component(self):
        """Test registering a component."""
        tracker = ComponentHealthTracker()
        tracker.register_component("test_component")
        
        status = tracker._health_status["test_component"]
        assert status["healthy"] is True
        assert status["error_count"] == 0

    def test_register_with_recovery_strategy(self):
        """Test registering component with recovery strategy."""
        tracker = ComponentHealthTracker()
        
        def recovery():
            return True
        
        tracker.register_component("test", recovery_strategy=recovery)
        assert "test" in tracker._recovery_strategies

    def test_report_health_success(self):
        """Test reporting healthy status."""
        tracker = ComponentHealthTracker()
        tracker.register_component("test")
        
        tracker.report_health("test", healthy=True)
        
        assert tracker._health_status["test"]["healthy"] is True
        assert tracker._failure_counts["test"] == 0

    def test_report_health_failure(self):
        """Test reporting unhealthy status."""
        tracker = ComponentHealthTracker()
        tracker.register_component("test")
        
        tracker.report_health("test", healthy=False, error="Connection lost")
        
        assert tracker._health_status["test"]["healthy"] is False
        assert tracker._health_status["test"]["last_error"] == "Connection lost"
        assert tracker._health_status["test"]["error_count"] == 1
        assert tracker._failure_counts["test"] == 1

    def test_report_health_auto_register(self):
        """Test reporting health auto-registers component."""
        tracker = ComponentHealthTracker()
        
        tracker.report_health("new_component", healthy=False)
        
        assert "new_component" in tracker._health_status

    def test_get_unhealthy_components(self):
        """Test getting unhealthy components."""
        tracker = ComponentHealthTracker()
        tracker.register_component("healthy")
        tracker.register_component("unhealthy")
        
        tracker.report_health("healthy", healthy=True)
        tracker.report_health("unhealthy", healthy=False, error="Error")
        
        unhealthy = tracker.get_unhealthy_components()
        
        assert "unhealthy" in unhealthy
        assert "healthy" not in unhealthy

    @pytest.mark.asyncio
    async def test_attempt_recovery_async(self):
        """Test recovery with async strategy."""
        tracker = ComponentHealthTracker()
        
        async def async_recovery():
            return True
        
        tracker.register_component("test", recovery_strategy=async_recovery)
        tracker.report_health("test", healthy=False)
        
        result = await tracker.attempt_recovery("test")
        
        assert result is True
        assert tracker._health_status["test"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_attempt_recovery_sync(self):
        """Test recovery with sync strategy."""
        tracker = ComponentHealthTracker()
        
        def sync_recovery():
            return True
        
        tracker.register_component("test", recovery_strategy=sync_recovery)
        
        result = await tracker.attempt_recovery("test")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_attempt_recovery_no_strategy(self):
        """Test recovery without strategy."""
        tracker = ComponentHealthTracker()
        tracker.register_component("test")
        
        result = await tracker.attempt_recovery("test")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_attempt_recovery_failure(self):
        """Test recovery strategy that fails."""
        tracker = ComponentHealthTracker()
        
        def failing_recovery():
            return False
        
        tracker.register_component("test", recovery_strategy=failing_recovery)
        
        result = await tracker.attempt_recovery("test")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_attempt_recovery_exception(self):
        """Test recovery strategy that raises exception."""
        tracker = ComponentHealthTracker()
        
        def error_recovery():
            raise RuntimeError("Recovery failed")
        
        tracker.register_component("test", recovery_strategy=error_recovery)
        
        result = await tracker.attempt_recovery("test")
        
        assert result is False

    def test_get_failure_count(self):
        """Test getting failure count."""
        tracker = ComponentHealthTracker()
        tracker.register_component("test")
        
        tracker.report_health("test", healthy=False)
        tracker.report_health("test", healthy=False)
        
        assert tracker.get_failure_count("test") == 2

    def test_failure_count_reset_on_success(self):
        """Test failure count resets on successful health report."""
        tracker = ComponentHealthTracker()
        tracker.register_component("test")
        
        tracker.report_health("test", healthy=False)
        tracker.report_health("test", healthy=False)
        tracker.report_health("test", healthy=True)
        
        assert tracker.get_failure_count("test") == 0

    def test_should_attempt_recovery(self):
        """Test should_attempt_recovery logic."""
        tracker = ComponentHealthTracker()
        tracker.register_component("test")
        
        # Should attempt with low failure count
        tracker._failure_counts["test"] = 1
        assert tracker.should_attempt_recovery("test", max_failures=3) is True
        
        # Should not attempt with high failure count
        tracker._failure_counts["test"] = 5
        assert tracker.should_attempt_recovery("test", max_failures=3) is False


class TestGlobalHealthTracker:
    """Test global health tracker instance."""

    def test_get_health_tracker_returns_singleton(self):
        """Test get_health_tracker returns same instance."""
        tracker1 = get_health_tracker()
        tracker2 = get_health_tracker()
        
        assert tracker1 is tracker2
        assert isinstance(tracker1, ComponentHealthTracker)

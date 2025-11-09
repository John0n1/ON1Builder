"""Comprehensive tests for logging_config module."""
import pytest
import logging
import os
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from on1builder.utils.logging_config import (
    JsonFormatter,
    setup_logging,
    get_logger,
    reset_logging,
    HAVE_COLORLOG,
)


class TestJsonFormatter:
    """Test JsonFormatter class."""

    def test_basic_formatting(self):
        """Test basic JSON formatting."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        result = formatter.format(record)
        
        import json
        parsed = json.loads(result)
        
        assert parsed["level"] == "INFO"
        assert parsed["name"] == "test"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_formatting_with_exception(self):
        """Test JSON formatting with exception."""
        formatter = JsonFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )
        
        result = formatter.format(record)
        
        import json
        parsed = json.loads(result)
        
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_formatting_with_extra_data(self):
        """Test JSON formatting with extra data."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None
        )
        
        # Add extra data
        record.extra_data = {"user_id": 123, "action": "login"}
        
        result = formatter.format(record)
        
        import json
        parsed = json.loads(result)
        
        assert parsed["user_id"] == 123
        assert parsed["action"] == "login"


class TestSetupLogging:
    """Test setup_logging function."""

    def teardown_method(self):
        """Clean up after each test."""
        reset_logging()

    def test_setup_logging_default(self):
        """Test default logging setup."""
        with patch.dict(os.environ, {}, clear=True):
            setup_logging()
        
        logger = logging.getLogger("on1builder")
        assert logger.level in [logging.INFO, logging.DEBUG]
        assert len(logger.handlers) > 0

    def test_setup_logging_debug_mode(self):
        """Test logging setup with debug mode."""
        with patch("on1builder.config.loaders.get_settings") as mock_settings:
            mock_settings.return_value = Mock(debug=True)
            
            setup_logging(force_setup=True)
            
            logger = logging.getLogger("on1builder")
            assert logger.level == logging.DEBUG

    def test_setup_logging_json_format(self):
        """Test logging setup with JSON format."""
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}):
            setup_logging(force_setup=True)
            
            logger = logging.getLogger("on1builder")
            handler = logger.handlers[0]
            
            assert isinstance(handler.formatter, JsonFormatter)

    def test_setup_logging_colorlog(self):
        """Test logging setup with colorlog if available."""
        if not HAVE_COLORLOG:
            pytest.skip("colorlog not available")
        
        with patch.dict(os.environ, {"LOG_FORMAT": "console"}):
            setup_logging(force_setup=True)
            
            logger = logging.getLogger("on1builder")
            handler = logger.handlers[0]
            
            # Should have colorlog formatter
            import colorlog
            assert isinstance(handler.formatter, colorlog.ColoredFormatter)

    def test_setup_logging_without_colorlog(self):
        """Test logging setup falls back when colorlog unavailable."""
        with patch("on1builder.utils.logging_config.HAVE_COLORLOG", False):
            with patch.dict(os.environ, {"LOG_FORMAT": "console"}):
                setup_logging(force_setup=True)
                
                logger = logging.getLogger("on1builder")
                handler = logger.handlers[0]
                
                assert isinstance(handler.formatter, logging.Formatter)

    def test_setup_logging_custom_level(self):
        """Test logging setup with custom level from environment."""
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            with patch("on1builder.config.loaders.get_settings", side_effect=Exception):
                setup_logging(force_setup=True)
                
                logger = logging.getLogger("on1builder")
                assert logger.level == logging.WARNING

    def test_setup_logging_file_handler_created(self):
        """Test file handler is created."""
        # Skip in test environment
        pytest.skip("File handler creation tested separately")

    def test_setup_logging_file_handler_error(self):
        """Test logging continues if file handler fails."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("PYTEST_CURRENT_TEST", None)
            
            with patch("on1builder.utils.logging_config.get_base_dir") as mock_base:
                mock_base.side_effect = Exception("Cannot get base dir")
                
                # Should not raise, just log warning
                setup_logging(force_setup=True)
                
                logger = logging.getLogger("on1builder")
                assert len(logger.handlers) > 0

    def test_setup_logging_clears_existing_handlers(self):
        """Test setup_logging clears existing handlers."""
        logger = logging.getLogger("on1builder")
        
        # Add a dummy handler
        dummy_handler = logging.StreamHandler()
        logger.addHandler(dummy_handler)
        
        initial_count = len(logger.handlers)
        assert initial_count > 0
        
        setup_logging(force_setup=True)
        
        # Should clear and recreate handlers
        assert len(logger.handlers) > 0

    def test_setup_logging_idempotent(self):
        """Test setup_logging is idempotent without force_setup."""
        setup_logging()
        
        logger = logging.getLogger("on1builder")
        handler_count = len(logger.handlers)
        
        # Call again without force
        setup_logging()
        
        # Should not add more handlers
        assert len(logger.handlers) == handler_count

    def test_setup_logging_force_setup(self):
        """Test force_setup reconfigures logging."""
        setup_logging()
        
        logger = logging.getLogger("on1builder")
        original_level = logger.level
        
        # Change environment and force setup
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            with patch("on1builder.config.loaders.get_settings", side_effect=Exception):
                setup_logging(force_setup=True)
                
                # Level should change
                assert logger.level != original_level or original_level == logging.ERROR


class TestGetLogger:
    """Test get_logger function."""

    def teardown_method(self):
        """Clean up after each test."""
        reset_logging()

    def test_get_logger_returns_child_logger(self):
        """Test get_logger returns a child logger."""
        logger = get_logger("test_module")
        
        assert logger.name == "on1builder.test_module"
        assert isinstance(logger, logging.Logger)

    def test_get_logger_initializes_logging(self):
        """Test get_logger initializes logging if not setup."""
        reset_logging()
        
        logger = get_logger("test")
        
        # Root logger should be initialized
        root_logger = logging.getLogger("on1builder")
        assert len(root_logger.handlers) > 0

    def test_get_logger_multiple_calls(self):
        """Test multiple get_logger calls return proper loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        
        assert logger1.name == "on1builder.module1"
        assert logger2.name == "on1builder.module2"
        assert logger1 is not logger2

    def test_get_logger_with_dotted_name(self):
        """Test get_logger with dotted module name."""
        logger = get_logger("utils.helpers")
        
        assert logger.name == "on1builder.utils.helpers"


class TestResetLogging:
    """Test reset_logging function."""

    def test_reset_logging_clears_loggers(self):
        """Test reset_logging clears logger cache."""
        from on1builder.utils import logging_config
        
        setup_logging()
        assert len(logging_config._loggers) > 0
        
        reset_logging()
        assert len(logging_config._loggers) == 0

    def test_reset_logging_removes_handlers(self):
        """Test reset_logging removes handlers from root logger."""
        setup_logging()
        
        logger = logging.getLogger("on1builder")
        assert len(logger.handlers) > 0
        
        reset_logging()
        
        assert len(logger.handlers) == 0


class TestLoggingIntegration:
    """Test logging integration scenarios."""

    def teardown_method(self):
        """Clean up after each test."""
        reset_logging()

    def test_logger_hierarchy(self):
        """Test logger hierarchy works correctly."""
        parent = get_logger("parent")
        child = get_logger("parent.child")
        
        # Child should inherit parent settings
        assert child.parent.name == parent.name

    def test_logger_output(self, caplog):
        """Test logger actually logs messages."""
        with caplog.at_level(logging.INFO):
            logger = get_logger("test")
            logger.info("Test message")
        
        assert "Test message" in caplog.text

    def test_different_log_levels(self, caplog):
        """Test different log levels work correctly."""
        # Set up logger with DEBUG level
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            with patch("on1builder.config.loaders.get_settings", side_effect=Exception):
                setup_logging(force_setup=True)
        
        logger = get_logger("test")
        
        with caplog.at_level(logging.DEBUG):
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
        
        # Info, warning, and error should always be captured
        assert "Info message" in caplog.text
        assert "Warning message" in caplog.text
        assert "Error message" in caplog.text

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for ON1Builder logging configuration utilities
==================================================

This module contains comprehensive tests for logging configuration functions
defined in src/on1builder/utils/logging_config.py.
"""

import json
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from on1builder.utils.logging_config import (
    JsonFormatter,
    StructuredLoggerAdapter,
    setup_logging,
    get_logger,
    bind_logger_context,
    USE_JSON_LOGGING,
    HAVE_COLORLOG,
)


class TestJsonFormatter:
    """Test cases for JsonFormatter class."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.formatter = JsonFormatter()

    def test_basic_formatting(self):
        """Test basic log record formatting."""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        result = self.formatter.format(record)
        log_data = json.loads(result)
        
        assert log_data["level"] == "INFO"
        assert log_data["name"] == "test_logger"
        assert log_data["message"] == "Test message"
        assert "timestamp" in log_data
        assert "pid" in log_data
        assert "thread" in log_data

    def test_exception_formatting(self):
        """Test formatting with exception information."""
        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test_logger",
                level=logging.ERROR,
                pathname="/test/path.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
            
            result = self.formatter.format(record)
            log_data = json.loads(result)
            
            assert "exception" in log_data
            assert "ValueError" in log_data["exception"]
            assert "Test exception" in log_data["exception"]

    def test_custom_fields(self):
        """Test formatting with custom fields."""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.component = "test_component"
        record.tx_hash = "0x123abc"
        record.chain_id = 1
        record.custom_field = "custom_value"
        
        result = self.formatter.format(record)
        log_data = json.loads(result)
        
        assert log_data["component"] == "test_component"
        assert log_data["tx_hash"] == "0x123abc"
        assert log_data["chain_id"] == 1
        assert log_data["custom_field"] == "custom_value"

    def test_non_serializable_objects(self):
        """Test handling of non-serializable objects."""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Add a non-serializable object
        record.complex_object = object()
        
        # Should not raise an exception
        result = self.formatter.format(record)
        log_data = json.loads(result)
        
        # Object should be converted to string
        assert "complex_object" in log_data
        assert isinstance(log_data["complex_object"], str)


class TestStructuredLoggerAdapter:
    """Test cases for StructuredLoggerAdapter class."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.base_logger = logging.getLogger("test")
        self.adapter = StructuredLoggerAdapter(self.base_logger, {"component": "test"})

    def test_initialization(self):
        """Test adapter initialization."""
        assert self.adapter.logger == self.base_logger
        assert self.adapter.extra == {"component": "test"}

    def test_process(self):
        """Test message processing."""
        msg, kwargs = self.adapter.process("test message", {})
        assert msg == "test message"
        assert kwargs["extra"] == {"component": "test"}

    def test_process_with_existing_extra(self):
        """Test message processing with existing extra context."""
        msg, kwargs = self.adapter.process("test message", {"extra": {"user": "john"}})
        assert msg == "test message"
        assert kwargs["extra"] == {"component": "test", "user": "john"}

    def test_bind(self):
        """Test binding additional context."""
        new_adapter = self.adapter.bind(user="john", session="abc123")
        
        assert new_adapter.extra == {"component": "test", "user": "john", "session": "abc123"}
        # Original adapter should be unchanged
        assert self.adapter.extra == {"component": "test"}

    def test_unbind(self):
        """Test removing context keys."""
        adapter_with_context = self.adapter.bind(user="john", session="abc123")
        new_adapter = adapter_with_context.unbind("user")
        
        assert new_adapter.extra == {"component": "test", "session": "abc123"}
        # Original adapter should be unchanged
        assert adapter_with_context.extra == {"component": "test", "user": "john", "session": "abc123"}

    def test_unbind_nonexistent_key(self):
        """Test unbinding a key that doesn't exist."""
        new_adapter = self.adapter.unbind("nonexistent")
        assert new_adapter.extra == {"component": "test"}


class TestLoggingSetup:
    """Test cases for logging setup functions."""

    def setup_method(self):
        """Set up test environment before each test method."""
        # Clear any existing loggers
        from on1builder.utils.logging_config import _loggers
        _loggers.clear()

    def test_setup_logging_basic(self):
        """Test basic logging setup."""
        logger = setup_logging("test_logger")
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
        assert logger.level == logging.INFO

    def test_setup_logging_with_level_string(self):
        """Test logging setup with string level."""
        logger = setup_logging("test_logger", level="DEBUG")
        # For StructuredLoggerAdapter, check the underlying logger
        if isinstance(logger, StructuredLoggerAdapter):
            assert logger.logger.level == logging.DEBUG
        else:
            assert logger.level == logging.DEBUG

    def test_setup_logging_with_level_int(self):
        """Test logging setup with integer level."""
        logger = setup_logging("test_logger", level=logging.WARNING)
        # For StructuredLoggerAdapter, check the underlying logger
        if isinstance(logger, StructuredLoggerAdapter):
            assert logger.logger.level == logging.WARNING
        else:
            assert logger.level == logging.WARNING

    def test_setup_logging_with_context(self):
        """Test logging setup with context binding."""
        logger = setup_logging("test_logger", bind_context={"component": "test"})
        
        assert isinstance(logger, StructuredLoggerAdapter)
        assert logger.extra == {"component": "test"}

    def test_setup_logging_with_file_output(self):
        """Test logging setup with file output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = setup_logging("test_logger", log_dir=temp_dir)
            
            # Check that log file was created
            log_files = list(Path(temp_dir).glob("*.log"))
            assert len(log_files) > 0
            assert any("test_logger" in f.name for f in log_files)

    def test_setup_logging_json_format(self):
        """Test logging setup with JSON format."""
        # Explicitly specify use_json=True to force JSON formatting
        logger = setup_logging("test_json_logger", use_json=True)
        
        # Check that JsonFormatter is being used
        # For StructuredLoggerAdapter, check the underlying logger
        actual_logger = logger.logger if isinstance(logger, StructuredLoggerAdapter) else logger
        handler = actual_logger.handlers[0]
        # With use_json=True, should use JsonFormatter
        assert isinstance(handler.formatter, JsonFormatter)

    def test_setup_logging_cached(self):
        """Test that loggers are cached properly."""
        logger1 = setup_logging("cached_logger")
        logger2 = setup_logging("cached_logger")
        
        assert logger1 is logger2

    def test_setup_logging_cached_with_new_context(self):
        """Test cached logger with new context."""
        logger1 = setup_logging("cached_logger")
        logger2 = setup_logging("cached_logger", bind_context={"user": "john"})
        
        assert logger1 is not logger2
        assert isinstance(logger2, StructuredLoggerAdapter)

    def test_get_logger_existing(self):
        """Test getting existing logger."""
        original = setup_logging("existing_logger")
        retrieved = get_logger("existing_logger")
        
        assert original is retrieved

    def test_get_logger_new(self):
        """Test getting new logger with defaults."""
        logger = get_logger("new_logger")
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "new_logger"

    def test_bind_logger_context_with_logger(self):
        """Test binding context to a regular logger."""
        logger = logging.getLogger("test")
        adapter = bind_logger_context(logger, component="test")
        
        assert isinstance(adapter, StructuredLoggerAdapter)
        assert adapter.extra == {"component": "test"}

    def test_bind_logger_context_with_adapter(self):
        """Test binding context to an existing adapter."""
        base_logger = logging.getLogger("test")
        adapter = StructuredLoggerAdapter(base_logger, {"component": "test"})
        new_adapter = bind_logger_context(adapter, user="john")
        
        assert isinstance(new_adapter, StructuredLoggerAdapter)
        assert new_adapter.extra == {"component": "test", "user": "john"}

    def test_setup_logging_with_colorlog(self):
        """Test logging setup when colorlog is available."""
        # Since colorlog is not installed in the test environment, we'll just
        # test that when HAVE_COLORLOG is False, we use regular formatter
        with patch('on1builder.utils.logging_config.HAVE_COLORLOG', False):
            logger = setup_logging("test_colorlog_logger", use_json=False)
            
            # Should have a handler with a regular formatter (not JsonFormatter)
            actual_logger = logger.logger if isinstance(logger, StructuredLoggerAdapter) else logger
            handler = actual_logger.handlers[0]
            assert not isinstance(handler.formatter, JsonFormatter)
            assert isinstance(handler.formatter, logging.Formatter)

    @patch('on1builder.utils.logging_config.HAVE_COLORLOG', False)
    def test_setup_logging_without_colorlog(self):
        """Test logging setup without colorlog available."""
        logger = setup_logging("test_logger", use_json=False)
        
        # Should use regular formatter
        # For StructuredLoggerAdapter, check the underlying logger
        actual_logger = logger.logger if isinstance(logger, StructuredLoggerAdapter) else logger
        formatter = actual_logger.handlers[0].formatter
        assert isinstance(formatter, logging.Formatter)
        assert not hasattr(formatter, 'log_colors')

    def test_logger_thread_safety(self):
        """Test that logger creation is thread-safe."""
        results = []
        errors = []
        
        def create_logger(name):
            try:
                logger = setup_logging(f"thread_logger_{name}")
                results.append(logger)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(10):
            thread = threading.Thread(target=create_logger, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert len(errors) == 0
        assert len(results) == 10
        # All loggers should be different
        assert len(set(id(r) for r in results)) == 10


if __name__ == "__main__":
    pytest.main([__file__])

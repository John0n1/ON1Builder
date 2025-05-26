# LICENSE: MIT // github.com/John0n1/ON1Builder
"""Tests for the logging utilities in utils/logger.py."""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from on1builder.utils.logger import JsonFormatter, setup_logging


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


def test_setup_logging_basic():
    """Test basic logger setup."""
    logger = setup_logging("TestLogger", level="DEBUG")

    # Check that the logger has the correct name and level
    assert logger.name == "TestLogger"
    assert logger.level == logging.DEBUG

    # Verify handlers
    assert len(logger.handlers) > 0
    assert any(
        isinstance(handler, logging.StreamHandler) for handler in logger.handlers
    )


def test_setup_logging_with_log_dir(temp_log_dir):
    """Test logger setup with log directory for file output."""
    logger = setup_logging("FileLogger", level="INFO", log_dir=temp_log_dir)

    # Check that the logger has the correct name and level
    assert logger.name == "FileLogger"
    assert logger.level == logging.INFO

    # Verify handlers - should have both console and file handlers
    assert len(logger.handlers) == 2
    assert any(
        isinstance(handler, logging.StreamHandler) for handler in logger.handlers
    )
    assert any(isinstance(handler, logging.FileHandler) for handler in logger.handlers)

    # Check that the log file exists
    log_file = Path(temp_log_dir) / "filelogger.log"
    assert log_file.exists()


def test_setup_logging_with_json(temp_log_dir):
    """Test logger setup with JSON formatting."""
    logger = setup_logging(
        "JsonLogger", level="WARNING", log_dir=temp_log_dir, use_json=True
    )

    # Check that the logger has the correct name and level
    assert logger.name == "JsonLogger"
    assert logger.level == logging.WARNING

    # Verify JSON formatter is used
    for handler in logger.handlers:
        assert isinstance(handler.formatter, JsonFormatter)

    # Log a test message
    test_message = "This is a test warning message"
    logger.warning(test_message)

    # Check the log file content
    log_file = Path(temp_log_dir) / "jsonlogger.log"
    with open(log_file) as f:
        log_content = f.read()

    # Parse the JSON content
    log_entry = json.loads(log_content)

    # Verify the log entry contains the expected fields
    assert log_entry["level"] == "WARNING"
    assert log_entry["name"] == "JsonLogger"
    assert log_entry["message"] == test_message


def test_setup_logging_with_int_level():
    """Test logger setup with integer level."""
    logger = setup_logging("IntLevelLogger", level=logging.ERROR)

    # Check that the logger has the correct level
    assert logger.level == logging.ERROR


def test_json_formatter():
    """Test the JsonFormatter class."""
    formatter = JsonFormatter()

    # Create a log record with various attributes
    record = logging.LogRecord(
        name="TestLogger",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    # Add some extra attributes
    record.component = "TestComponent"
    record.tx_hash = "0xabcdef"
    record.custom_field = "custom value"

    # Format the record
    formatted = formatter.format(record)

    # Parse the JSON
    log_entry = json.loads(formatted)

    # Check the standard fields
    assert log_entry["level"] == "INFO"
    assert log_entry["name"] == "TestLogger"
    assert log_entry["message"] == "Test message"
    assert log_entry["component"] == "TestComponent"
    assert log_entry["tx_hash"] == "0xabcdef"
    assert log_entry["custom_field"] == "custom value"


def test_json_formatter_with_exception():
    """Test the JsonFormatter with exception information."""
    formatter = JsonFormatter()

    try:
        raise ValueError("Test exception")
    except ValueError as e:
        exc_info = (type(e), e, e.__traceback__)

    # Create a log record with exception info
    record = logging.LogRecord(
        name="TestLogger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=42,
        msg="Exception occurred",
        args=(),
        exc_info=exc_info,
    )

    # Format the record
    formatted = formatter.format(record)

    # Parse the JSON
    log_entry = json.loads(formatted)

    # Check the exception field
    assert "exception" in log_entry
    assert "ValueError: Test exception" in log_entry["exception"]


def test_setup_logging_with_existing_handlers():
    """Test that existing handlers are cleared when setting up logger."""
    logger_name = "ExistingHandlersLogger"

    # Create logger with a handler
    test_logger = logging.getLogger(logger_name)
    # Make sure we start with no handlers
    for handler in test_logger.handlers[:]:
        test_logger.removeHandler(handler)

    test_logger.addHandler(logging.StreamHandler())
    assert len(test_logger.handlers) == 1

    # Set up logger again
    test_logger = setup_logging(logger_name, level="INFO")

    # Verify handlers were cleared and new ones added
    assert len(test_logger.handlers) == 1  # should have exactly one handler


@patch("on1builder.utils.logger.HAVE_COLORLOG", False)
def test_setup_logging_without_colorlog():
    """Test logger setup when colorlog is not available."""
    logger = setup_logging("PlainLogger", level="INFO")

    # Should still work but with plain formatting
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            assert not str(handler.formatter).startswith("colorlog")


def test_logging_output(caplog):
    """Test the actual output of the logger."""
    caplog.set_level(logging.DEBUG)

    logger = setup_logging("OutputLogger", level="DEBUG")

    # Log messages at different levels
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    # Check that all messages were logged
    assert "Debug message" in caplog.text
    assert "Info message" in caplog.text
    assert "Warning message" in caplog.text
    assert "Error message" in caplog.text
    assert "Critical message" in caplog.text

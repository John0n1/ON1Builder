# src/on1builder/utils/logging_config.py
# flake8: noqa E501
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Dict

from on1builder.utils.path_helpers import get_base_dir

# Use colorlog if available for richer console output
try:
    import colorlog

    HAVE_COLORLOG = True
except ImportError:
    HAVE_COLORLOG = False

_loggers: Dict[str, logging.Logger] = {}


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON strings for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra context if available
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(force_setup: bool = False) -> None:
    """
    Configures the root logger for the application based on settings.
    This should be called once when the application starts.

    Args:
        force_setup: If True, will reconfigure logging even if already set up
    """
    if not force_setup and "on1builder" in _loggers:
        return

    # Import settings lazily to avoid circular imports
    try:
        from on1builder.config.loaders import get_settings

        settings = get_settings()
        log_level = "DEBUG" if settings.debug else "INFO"
    except Exception:
        # Fallback if settings not available
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    use_json = os.environ.get("LOG_FORMAT", "console").lower() == "json"

    root_logger = logging.getLogger("on1builder")
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Clear any existing handlers to prevent duplicate logging
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)

    if use_json:
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
    elif HAVE_COLORLOG:
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(name)s:%(levelname)s]%(reset)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s:%(levelname)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File Handler (only if not in test environment)
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            log_dir = get_base_dir() / "logs"
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / "on1builder.log"

            file_handler = logging.FileHandler(log_file, mode="a")
            file_formatter = logging.Formatter(
                "%(asctime)s [%(name)s:%(levelname)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            # Don't fail if we can't set up file logging
            root_logger.warning(f"Could not set up file logging: {e}")

    # Set the global logger instance
    _loggers["on1builder"] = root_logger
    root_logger.info(
        f"Logging initialized. Level: {log_level}, Format: {'JSON' if use_json else 'Console'}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Retrieves a logger instance. It will be a child of the root 'on1builder' logger.

    Args:
        name: The name for the logger, typically __name__

    Returns:
        A configured logger instance
    """
    if "on1builder" not in _loggers:
        setup_logging()

    # Create a child logger
    return logging.getLogger(f"on1builder.{name}")


def reset_logging() -> None:
    """Reset logging configuration. Mainly used for testing."""
    global _loggers
    _loggers.clear()

    # Clear all handlers from the root logger
    root_logger = logging.getLogger("on1builder")
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)


# Initialize logging as soon as this module is imported (unless in test mode)
if not os.environ.get("PYTEST_CURRENT_TEST") and "on1builder" not in _loggers:
    setup_logging()

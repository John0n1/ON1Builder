#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder - Logging Utilities
=============================

Provides logging configuration and utilities for the application.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Use colorlog if available, otherwise fallback to standard logging
try:
    import colorlog

    HAVE_COLORLOG = True
except ImportError:
    HAVE_COLORLOG = False

# Default to colorized console logging unless explicitly set to JSON
USE_JSON_LOGGING = False


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        standard_attrs = logging.LogRecord(
            "", "", "", "", "", "", "", ""
        ).__dict__.keys()
        extra_data = {
            k: v
            for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extra_data:
            log_entry.update(extra_data)

        log_entry["component"] = getattr(record, "component", None) or extra_data.get(
            "component", "N/A"
        )
        log_entry["tx_hash"] = getattr(record, "tx_hash", None) or extra_data.get(
            "tx_hash", None
        )

        if log_entry["component"] == "N/A" and "component" in log_entry:
            del log_entry["component"]
        if log_entry["tx_hash"] is None and "tx_hash" in log_entry:
            del log_entry["tx_hash"]

        return json.dumps(log_entry)


def setup_logging(
    name: str,
    level: Any = "INFO",
    log_dir: Optional[str] = None,
    use_json: Optional[bool] = None,
) -> logging.Logger:
    """Sets up logging with either colorized console output or JSON formatted
    output.

    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory to store log files, if None only console logging is used
        use_json: Whether to use JSON logging format, overrides global setting

    Returns:
        Configured logger instance
    """
    # Use parameter if provided, otherwise fall back to global setting
    use_json_logging = use_json if use_json is not None else USE_JSON_LOGGING

    # Determine numeric level from string or int
    if isinstance(level, int):
        numeric_level = level
    else:
        numeric_level = getattr(logging, str(level).upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with appropriate formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    if use_json_logging:
        formatter = JsonFormatter()
    elif HAVE_COLORLOG:
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
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
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Add file handler if log_dir provided
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path / f"{name.lower()}.log")
        file_handler.setLevel(numeric_level)

        if use_json_logging:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        logger.addHandler(file_handler)

    # ------------------------------------------------------------------
    # Expose module‐level helpers on the returned logger so that tests
    # doing logger.StreamHandler(), logger.getLogger() and logger.DEBUG
    # continue to work against this object:
    # ------------------------------------------------------------------
    logger.StreamHandler = logging.StreamHandler
    logger.getLogger = logging.getLogger
    logger.DEBUG = logging.DEBUG
    logger.INFO = logging.INFO
    logger.WARNING = logging.WARNING
    logger.ERROR = logging.ERROR
    logger.CRITICAL = logging.CRITICAL

    return logger

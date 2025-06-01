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
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Use colorlog if available, otherwise fallback to standard logging
try:
    import colorlog
    HAVE_COLORLOG = True
except ImportError:
    HAVE_COLORLOG = False

# Default to colorized console logging unless explicitly set to JSON
USE_JSON_LOGGING = os.environ.get("USE_JSON_LOGGING", "").lower() in ("true", "1", "yes")

# Global dictionary of configured loggers
_loggers: Dict[str, logging.Logger] = {}
_logger_lock = threading.RLock()


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        # Add custom fields from the record
        standard_attrs = set(["name", "msg", "args", "levelname", "levelno", "pathname",
                            "filename", "module", "exc_info", "exc_text", "stack_info",
                            "lineno", "funcName", "created", "asctime", "msecs", 
                            "relativeCreated", "thread", "threadName", "processName",
                            "process"])
        
        extra_data = {
            k: v
            for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        
        if extra_data:
            log_entry.update(extra_data)

        # Always include these fields if available
        log_entry["component"] = getattr(record, "component", None) or extra_data.get(
            "component", record.name
        )
        log_entry["tx_hash"] = getattr(record, "tx_hash", None) or extra_data.get(
            "tx_hash", None
        )
        log_entry["chain_id"] = getattr(record, "chain_id", None) or extra_data.get(
            "chain_id", None
        )

        # Clean up empty fields
        for key in list(log_entry.keys()):
            if log_entry[key] is None:
                del log_entry[key]
                
        # Handle non-serializable values
        try:
            return json.dumps(log_entry)
        except TypeError:
            # Try again with default=str for non-serializable objects
            return json.dumps(log_entry, default=str)


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """Adapter that allows adding structured context to all log messages."""
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        """Initialize with a logger and optional extra context.
        
        Args:
            logger: The underlying logger
            extra: Context data to include in all messages
        """
        super().__init__(logger, extra or {})
        
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Process the logging message and keyword arguments."""
        # Merge extra context from adapter with extra kwargs
        if 'extra' in kwargs:
            kwargs['extra'].update(self.extra)
        else:
            kwargs['extra'] = self.extra.copy()
        return msg, kwargs
    
    def bind(self, **new_context) -> 'StructuredLoggerAdapter':
        """Create a new adapter with additional context data."""
        merged_context = self.extra.copy()
        merged_context.update(new_context)
        return StructuredLoggerAdapter(self.logger, merged_context)
    
    def unbind(self, *keys) -> 'StructuredLoggerAdapter':
        """Create a new adapter with specified keys removed."""
        new_context = self.extra.copy()
        for key in keys:
            if key in new_context:
                del new_context[key]
        return StructuredLoggerAdapter(self.logger, new_context)


def setup_logging(
    name: str,
    level: Union[str, int] = "INFO",
    log_dir: Optional[str] = None,
    use_json: Optional[bool] = None,
    bind_context: Optional[Dict[str, Any]] = None,
) -> Union[logging.Logger, StructuredLoggerAdapter]:
    """Sets up logging with either colorized console output or JSON formatted
    output.

    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory to store log files, if None only console logging is used
        use_json: Whether to use JSON logging format, overrides global setting
        bind_context: Context data to bind to the logger

    Returns:
        Configured logger or LoggerAdapter if context is provided
    """
    global _loggers, _logger_lock
    
    # Check if we already have this logger configured
    with _logger_lock:
        if name in _loggers:
            logger = _loggers[name]
            # Apply any new context bindings
            if bind_context:
                if isinstance(logger, StructuredLoggerAdapter):
                    # Add to existing adapter
                    merged_context = logger.extra.copy()
                    merged_context.update(bind_context)
                    return StructuredLoggerAdapter(logger.logger, merged_context)
                else:
                    # Create new adapter with context
                    return StructuredLoggerAdapter(logger, bind_context)
            return logger
    
    # Use parameter if provided, otherwise fall back to global setting
    use_json_logging = use_json if use_json is not None else USE_JSON_LOGGING

    # Determine numeric level from string or int
    if isinstance(level, str):
        numeric_level = getattr(logging, level.upper(), logging.INFO)
    else:
        numeric_level = level

    # Get the base logger
    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)
    
    # Clear any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    # Add console handler with appropriate formatter
    console = logging.StreamHandler()
    console.setLevel(numeric_level)
    
    if use_json_logging:
        formatter = JsonFormatter()
    elif HAVE_COLORLOG:
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)8s] %(name)s: %(message)s%(reset)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                "DEBUG": "cyan", 
                "INFO": "green",
                "WARNING": "yellow", 
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    # Add file handler if log_dir is specified
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = log_path / f"{timestamp}_{name.lower()}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        
        if use_json_logging:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            
        logger.addHandler(file_handler)
    
    # Store in global dict
    with _logger_lock:
        _loggers[name] = logger
    
    # Apply any context bindings
    if bind_context:
        return StructuredLoggerAdapter(logger, bind_context)
        
    return logger


def get_logger(name: str) -> Union[logging.Logger, StructuredLoggerAdapter]:
    """Get an existing logger or create a new one with default settings.
    
    Args:
        name: Logger name
        
    Returns:
        Existing logger or newly created one
    """
    global _loggers, _logger_lock
    
    with _logger_lock:
        if name in _loggers:
            return _loggers[name]
    
    # Create a new logger with default settings
    return setup_logging(name)


def bind_logger_context(logger: Union[logging.Logger, StructuredLoggerAdapter], **context) -> StructuredLoggerAdapter:
    """Bind context data to a logger.
    
    Args:
        logger: Logger or LoggerAdapter to bind context to
        **context: Context key-value pairs
        
    Returns:
        StructuredLoggerAdapter with bound context
    """
    if isinstance(logger, StructuredLoggerAdapter):
        return logger.bind(**context)
    return StructuredLoggerAdapter(logger, context)

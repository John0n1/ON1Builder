# src/on1builder/utils/logging_config.py
import logging
import sys
from pathlib import Path

from on1builder.utils.path_helpers import get_base_dir

# Use colorlog if available for richer console output
try:
    import colorlog
    HAVE_COLORLOG = True
except ImportError:
    HAVE_COLORLOG = False

_loggers = {}
class JsonFormatter(logging.Formatter):
    """Formats log records as JSON strings for structured logging."""
    def format(self, record: logging.LogRecord) -> str:
        import json
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra context if available
        if hasattr(record, 'extra_data'):
            log_entry.update(record.extra_data)
            
        return json.dumps(log_entry)

def setup_logging():
    """
    Configures the root logger for the application based on settings.
    This should be called once when the application starts.
    """
    import os
    
    # Import settings lazily to avoid circular imports
    try:
        from on1builder.config.loaders import get_settings
        settings = get_settings()
        log_level = "DEBUG" if settings.debug else "INFO"
    except Exception:
        # Fallback if settings not available
        log_level = "INFO"
    
    use_json = os.environ.get("LOG_FORMAT", "console").lower() == "json"

    root_logger = logging.getLogger("on1builder")
    root_logger.setLevel(log_level)
    
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
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s:%(levelname)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File Handler
    log_dir = get_base_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "on1builder.log"
    
    file_handler = logging.FileHandler(log_file, mode='a')
    file_formatter = logging.Formatter(
        "%(asctime)s [%(name)s:%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Set the global logger instance
    _loggers["on1builder"] = root_logger
    root_logger.info(f"Logging initialized. Level: {log_level}, Format: {'JSON' if use_json else 'Console'}")

def get_logger(name: str) -> logging.Logger:
    """
    Retrieves a logger instance. It will be a child of the root 'on1builder' logger.
    """
    if "on1builder" not in _loggers:
        setup_logging()
        
    return logging.getLogger(f"on1builder.{name}")

# Initialize logging as soon as this module is imported
import os
if "on1builder" not in _loggers:
    setup_logging()
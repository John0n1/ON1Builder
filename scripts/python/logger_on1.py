import logging
import sys
import threading
import time
import colorlog
import json
from typing import Dict, Any, Optional

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

        log_entry["component"] = getattr(
            record, "component", None) or extra_data.get(
            "component", "N/A")
        log_entry["tx_hash"] = getattr(
            record, "tx_hash", None) or extra_data.get(
            "tx_hash", None)

        if log_entry["component"] == "N/A" and "component" in log_entry:
            del log_entry["component"]
        if log_entry["tx_hash"] is None and "tx_hash" in log_entry:
            del log_entry["tx_hash"]

        return json.dumps(log_entry)


class TaskSpinner:
    """Manages a simple spinner animation in a separate thread."""

    def __init__(self, message: str = "Working"):
        self._message = message
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._spinner_chars = ["◢", "◣", "◤", "◥"]
        self._idx = 0

    def _spin(self) -> None:
        """The function run by the spinner thread."""
        while not self._stop_event.is_set():
            try:
                char = self._spinner_chars[self._idx %
                                           len(self._spinner_chars)]

                sys.stderr.write(f"\r{self._message}... {char}")
                sys.stderr.flush()
                time.sleep(0.15)
                self._idx += 1
            except Exception:
                break

        try:
            sys.stderr.write("\r" + " " * (len(self._message) + 5) + "\r")
            sys.stderr.flush()
        except Exception:
            pass

    def start(self) -> None:
        """Starts the spinner thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._spin, daemon=True, name="SpinnerThread"
            )
            self._thread.start()

    def stop(self) -> None:
        """Stops the spinner thread."""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=0.5)
        self._thread = None


_global_spinner: Optional[TaskSpinner] = None


def setup_logging(
    name: str,
    level: int = logging.INFO,
    use_spinner: bool = False,
    spinner_message: str = "Loading",
) -> logging.Logger:
    """
    Configures and returns a logger instance. Supports color or JSON format.

    Args:
        name (str): The name for the logger.
        level (int): The logging level (e.g., logging.DEBUG, logging.INFO).
        use_spinner (bool): Display a loading spinner initially (only affects first setup call).
        spinner_message (str): Message to display with the spinner.

    Returns:
        logging.Logger: The configured logger instance.
    """
    global _global_spinner

    if use_spinner and _global_spinner is None:
        _global_spinner = TaskSpinner(spinner_message)
        _global_spinner.start()

    logger = logging.getLogger(name)

    if not logger.hasHandlers() or level < logger.level:
        logger.setLevel(level)

    if not logger.handlers:

        if USE_JSON_LOGGING:
            handler = logging.StreamHandler(sys.stdout)
            formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
        else:

            handler = colorlog.StreamHandler(sys.stdout)
            formatter = colorlog.ColoredFormatter(
                "%(log_color)s[%(levelname)-8s] %(name)s: %(message)s%(reset)s",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "red,bg_white",
                },
                secondary_log_colors={},
                style="%",  # Use %-style formatting
            )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if use_spinner and _global_spinner:
        _global_spinner.stop()
        _global_spinner = None

    return logger

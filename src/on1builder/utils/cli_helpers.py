# src/on1builder/utils/cli_helpers.py
"""CLI utility functions and decorators for ON1Builder."""

from __future__ import annotations
import functools
import sys
from typing import Any, Callable, TypeVar

import typer
from rich.console import Console

from .logging_config import get_logger
from .custom_exceptions import (
    ON1BuilderError,
    ConfigurationError,
    InitializationError,
    ConnectionError,
    ValidationError
)

F = TypeVar("F", bound=Callable[..., Any])

console = Console()
logger = get_logger(__name__)


def handle_cli_errors(
    exit_on_error: bool = True,
    show_traceback: bool = False
) -> Callable[[F], F]:
    """
    Decorator for standardized CLI error handling.
    
    Args:
        exit_on_error: Whether to exit the application on error
        show_traceback: Whether to show full traceback for debugging
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (ConfigurationError, ValidationError) as e:
                console.print(f"[bold red]❌ Configuration Error:[/] {e}")
                logger.error(f"Configuration error in {func.__name__}: {e}")
                if exit_on_error:
                    raise typer.Exit(code=1)
                return None
            except InitializationError as e:
                console.print(f"[bold red]❌ Initialization Error:[/] {e}")
                logger.critical(f"Initialization error in {func.__name__}: {e}", exc_info=show_traceback)
                if exit_on_error:
                    raise typer.Exit(code=2)
                return None
            except ConnectionError as e:
                console.print(f"[bold red]❌ Connection Error:[/] {e}")
                logger.error(f"Connection error in {func.__name__}: {e}")
                if exit_on_error:
                    raise typer.Exit(code=3)
                return None
            except ON1BuilderError as e:
                console.print(f"[bold red]❌ Application Error:[/] {e}")
                logger.error(f"Application error in {func.__name__}: {e}")
                if exit_on_error:
                    raise typer.Exit(code=4)
                return None
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠️ Operation cancelled by user[/]")
                logger.info(f"User cancelled operation in {func.__name__}")
                if exit_on_error:
                    raise typer.Exit(code=130)  # Standard SIGINT exit code
                return None
            except Exception as e:
                console.print(f"[bold red]❌ Unexpected Error:[/] {e}")
                logger.critical(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                if show_traceback:
                    console.print_exception()
                if exit_on_error:
                    raise typer.Exit(code=1)
                return None
        return wrapper
    return decorator


def success_message(message: str) -> None:
    """Display a success message with consistent formatting."""
    console.print(f"[bold green]✅ {message}[/]")


def info_message(message: str) -> None:
    """Display an info message with consistent formatting."""
    console.print(f"[blue]ℹ️ {message}[/]")


def warning_message(message: str) -> None:
    """Display a warning message with consistent formatting."""
    console.print(f"[yellow]⚠️ {message}[/]")


def error_message(message: str) -> None:
    """Display an error message with consistent formatting."""
    console.print(f"[bold red]❌ {message}[/]")


def confirm_action(message: str, default: bool = False) -> bool:
    """
    Prompt user for confirmation with consistent formatting.
    
    Args:
        message: The confirmation message
        default: Default response if user just presses Enter
        
    Returns:
        True if user confirms, False otherwise
    """
    return typer.confirm(f"🤔 {message}", default=default)

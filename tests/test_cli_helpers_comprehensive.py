from __future__ import annotations

import pytest
import typer

from on1builder.utils import cli_helpers as helpers
from on1builder.utils.custom_exceptions import (
    ConfigurationError,
    ConnectionError,
    InitializationError,
    ON1BuilderError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ConfigurationError("bad"), 1),
        (ValidationError("bad"), 1),
        (InitializationError("bad"), 2),
        (ConnectionError("bad"), 3),
        (ON1BuilderError("bad"), 4),
        (KeyboardInterrupt(), 130),
        (RuntimeError("bad"), 1),
    ],
)
def test_handle_cli_errors_exits_for_expected_error_types(monkeypatch, error, code):
    printed = []
    monkeypatch.setattr(
        helpers.console, "print", lambda *args, **kwargs: printed.append(args)
    )
    monkeypatch.setattr(
        helpers.console, "print_exception", lambda: printed.append(("traceback",))
    )

    @helpers.handle_cli_errors(exit_on_error=True, show_traceback=True)
    def boom():
        raise error

    with pytest.raises(typer.Exit) as exc:
        boom()

    assert exc.value.exit_code == code
    assert printed


def test_handle_cli_errors_can_return_none_without_exit(monkeypatch):
    monkeypatch.setattr(helpers.console, "print", lambda *args, **kwargs: None)

    @helpers.handle_cli_errors(exit_on_error=False)
    def boom():
        raise ConnectionError("offline")

    assert boom() is None


def test_handle_cli_errors_returns_function_result(monkeypatch):
    monkeypatch.setattr(helpers.console, "print", lambda *args, **kwargs: None)

    @helpers.handle_cli_errors()
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_message_helpers_and_confirm_action(monkeypatch):
    outputs = []
    monkeypatch.setattr(
        helpers.console, "print", lambda message: outputs.append(message)
    )
    monkeypatch.setattr(
        helpers.typer, "confirm", lambda message, default=False: (message, default)
    )

    helpers.success_message("saved")
    helpers.info_message("info")
    helpers.warning_message("warn")
    helpers.error_message("err")

    assert outputs == [
        "[bold green]✅ saved[/]",
        "[blue]ℹ️ info[/]",
        "[yellow]⚠️ warn[/]",
        "[bold red]❌ err[/]",
    ]
    assert helpers.confirm_action("Proceed?", default=True) == ("🤔 Proceed?", True)


def test_resolve_editor_command_prefers_argument_and_environment(monkeypatch):
    assert helpers.resolve_editor_command("code --wait") == ["code", "--wait"]

    monkeypatch.setenv("VISUAL", "vim -f")
    assert helpers.resolve_editor_command(None) == ["vim", "-f"]

    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "nano")
    assert helpers.resolve_editor_command(None) == ["nano"]

    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr(helpers.os, "name", "posix")
    assert helpers.resolve_editor_command(None) == ["nano"]

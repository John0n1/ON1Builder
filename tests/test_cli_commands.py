"""Tests for CLI commands: __main__, config_cmd, run_cmd."""
import pytest
import sys
from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner
import json

from on1builder.__main__ import app, cli, show_version
from on1builder.cli import config_cmd, run_cmd


runner = CliRunner()


class TestMainCLI:
    """Test main CLI entry point."""

    def test_version_command(self):
        """Test version command output."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ON1Builder Version:" in result.stdout

    def test_no_args_shows_help(self):
        """Test that running with no args shows help."""
        result = runner.invoke(app, [])
        # Exit code 2 means missing args with help shown (typer default)
        assert result.exit_code in [0, 2]
        assert "ON1Builder" in result.stdout or "Usage" in result.stdout

    def test_cli_exception_handling(self):
        """Test CLI exception handling in main function."""
        with patch("on1builder.__main__.app") as mock_app:
            mock_app.side_effect = RuntimeError("Test error")
            
            with pytest.raises(SystemExit) as exc_info:
                cli()
            
            assert exc_info.value.code == 1

    def test_show_version_function(self):
        """Test show_version function directly."""
        with patch("typer.echo") as mock_echo:
            show_version()
            mock_echo.assert_called_once()
            args = mock_echo.call_args[0][0]
            assert "ON1Builder Version:" in args


class TestConfigCommand:
    """Test config command functionality."""

    def test_show_config_default(self):
        """Test show config with redaction (default)."""
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        # Output should be JSON formatted
        assert "{" in result.stdout or "wallet" in result.stdout.lower()

    def test_show_config_with_keys(self):
        """Test show config with --show-keys flag."""
        result = runner.invoke(app, ["config", "show", "--show-keys"])
        assert result.exit_code == 0

    def test_validate_config(self):
        """Test config validation command."""
        result = runner.invoke(app, ["config", "validate"])
        # Should either succeed or fail gracefully
        assert result.exit_code in [0, 1]


class TestRunCommand:
    """Test run command functionality."""

    @patch("on1builder.cli.run_cmd.MainOrchestrator")
    @patch("asyncio.run")
    def test_start_bot_success(self, mock_asyncio_run, mock_orchestrator):
        """Test successful bot start."""
        mock_orch_instance = Mock()
        mock_orchestrator.return_value = mock_orch_instance
        
        result = runner.invoke(app, ["run", "start"])
        
        # Orchestrator should be instantiated
        mock_orchestrator.assert_called_once()
        # Run should be called
        mock_asyncio_run.assert_called_once()

    @patch("on1builder.cli.run_cmd.MainOrchestrator")
    def test_start_bot_initialization_error(self, mock_orchestrator):
        """Test bot start with initialization error."""
        from on1builder.utils.custom_exceptions import InitializationError
        
        mock_orchestrator.side_effect = InitializationError("Test init error")
        
        result = runner.invoke(app, ["run", "start"])
        # Should handle error gracefully - exit code 2 from cli_helpers decorator
        assert result.exit_code in [1, 2]


class TestConfigCmdModule:
    """Test config_cmd module functions directly."""

    @patch("on1builder.cli.config_cmd.settings")
    @patch("on1builder.cli.config_cmd.console")
    def test_show_config_function(self, mock_console, mock_settings):
        """Test show_config function directly."""
        mock_settings.model_dump.return_value = {
            "wallet_address": "0x1234",
            "wallet_key": "secret",
            "debug": True
        }
        
        from on1builder.cli.config_cmd import show_config
        
        # Should not raise
        show_config(show_keys=False)
        mock_console.print.assert_called()

    @patch("on1builder.cli.config_cmd.load_settings")
    @patch("on1builder.cli.config_cmd.console")
    def test_validate_config_function(self, mock_console, mock_load_settings):
        """Test validate_config function directly."""
        from on1builder.cli.config_cmd import validate_config
        
        # Should not raise
        validate_config()
        mock_load_settings.assert_called_once()
        mock_console.print.assert_called()


class TestRunCmdModule:
    """Test run_cmd module functions directly."""

    @patch("on1builder.cli.run_cmd.MainOrchestrator")
    @patch("asyncio.run")
    def test_start_bot_function(self, mock_asyncio_run, mock_orchestrator):
        """Test start_bot function directly."""
        mock_orch_instance = Mock()
        mock_orch_instance.run = Mock()
        mock_orchestrator.return_value = mock_orch_instance
        
        from on1builder.cli.run_cmd import start_bot
        
        start_bot()
        
        mock_orchestrator.assert_called_once()
        mock_asyncio_run.assert_called_once()

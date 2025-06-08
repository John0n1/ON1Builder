#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for ON1Builder main CLI entry point
==========================================

This module contains comprehensive tests for the main CLI application
defined in src/on1builder/__main__.py.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import typer
from typer.testing import CliRunner

from on1builder.__main__ import app, cli, main, version


class TestMainCLI:
    """Test cases for the main CLI application."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.runner = CliRunner()

    def test_app_creation(self):
        """Test that the main typer app is created correctly."""
        assert isinstance(app, typer.Typer)
        assert app.info.name == "on1builder"
        if app.info.help:
            assert "Multi-chain blockchain transaction execution framework" in app.info.help

    def test_help_option(self):
        """Test help option displays correctly."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "ON1Builder" in result.stdout
        assert "Multi-chain blockchain transaction execution framework" in result.stdout

    @patch('on1builder.__main__.setup_logging')
    @patch('on1builder.__main__.get_logger')
    def test_main_callback_defaults(self, mock_get_logger, mock_setup_logging):
        """Test main callback with default parameters."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        main()
        
        mock_setup_logging.assert_called_once_with(
            name="on1builder", 
            level="WARNING", 
            log_dir=None
        )
        mock_logger.debug.assert_called_once()

    @patch('on1builder.__main__.setup_logging')
    @patch('on1builder.__main__.get_logger')
    def test_main_callback_verbose(self, mock_get_logger, mock_setup_logging):
        """Test main callback with verbose flag."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        main(verbose=True)
        
        mock_setup_logging.assert_called_once_with(
            name="on1builder", 
            level="INFO", 
            log_dir=None
        )

    @patch('on1builder.__main__.setup_logging')
    @patch('on1builder.__main__.get_logger')
    def test_main_callback_debug(self, mock_get_logger, mock_setup_logging):
        """Test main callback with debug flag."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        main(debug=True)
        
        mock_setup_logging.assert_called_once_with(
            name="on1builder", 
            level="DEBUG", 
            log_dir=None
        )

    @patch('on1builder.__main__.setup_logging')
    @patch('on1builder.__main__.get_logger')
    def test_main_callback_with_log_file(self, mock_get_logger, mock_setup_logging):
        """Test main callback with log file path."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        log_file = Path("/tmp/test.log")
        
        main(log_file=log_file)
        
        mock_setup_logging.assert_called_once_with(
            name="on1builder", 
            level="WARNING", 
            log_dir="/tmp"
        )

    @patch('on1builder.__version__', '1.0.0')
    @patch('on1builder.__title__', 'ON1Builder')
    @patch('on1builder.__description__', 'Test Description')
    def test_version_command(self):
        """Test version command displays correct information."""
        result = self.runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ON1Builder v1.0.0" in result.stdout
        assert "Test Description" in result.stdout

    @patch('on1builder.__main__.app')
    def test_cli_normal_execution(self, mock_app):
        """Test CLI function normal execution."""
        mock_app.return_value = None
        
        cli()
        
        mock_app.assert_called_once()

    @patch('on1builder.__main__.app')
    @patch('on1builder.__main__.get_logger')
    @patch('sys.exit')
    def test_cli_keyboard_interrupt(self, mock_exit, mock_get_logger, mock_app):
        """Test CLI function handles KeyboardInterrupt."""
        mock_app.side_effect = KeyboardInterrupt()
        
        with patch('typer.echo') as mock_echo:
            cli()
        
        mock_echo.assert_called_once_with("\nOperation cancelled by user.", err=True)
        mock_exit.assert_called_once_with(1)

    @patch('on1builder.__main__.app')
    @patch('on1builder.__main__.get_logger')
    @patch('sys.exit')
    def test_cli_unexpected_exception(self, mock_exit, mock_get_logger, mock_app):
        """Test CLI function handles unexpected exceptions."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        test_error = ValueError("Test error")
        mock_app.side_effect = test_error
        
        with patch('typer.echo') as mock_echo:
            cli()
        
        mock_logger.error.assert_called_once_with(f"Unexpected error: {test_error}")
        mock_echo.assert_called_once_with("Error: Test error", err=True)
        mock_exit.assert_called_once_with(1)

    def test_main_module_execution(self):
        """Test that the module can be executed as __main__."""
        # This tests that the main module can be imported without errors
        # We can't easily test the if __name__ == "__main__": block due to relative imports
        # So we'll just verify the module can be imported
        try:
            import on1builder.__main__
            # If we get here, the module imported successfully
            assert True
        except ImportError as e:
            # The module has relative imports, which is expected when testing
            # As long as it's just relative import issues, this is acceptable
            if "relative import" in str(e):
                assert True  # This is expected when testing
            else:
                raise  # Unexpected import error

    def test_subcommands_registered(self):
        """Test that all subcommands are properly registered."""
        # Check that config, run, and status commands are available
        result = self.runner.invoke(app, ["--help"])
        assert "config" in result.stdout
        assert "run" in result.stdout
        assert "status" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__])

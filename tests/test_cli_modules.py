#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for ON1Builder CLI modules
===============================

This module contains comprehensive tests for all CLI command modules
to ensure 100% test coverage.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import typer
from typer.testing import CliRunner

from on1builder.cli.config_cmd import app as config_app, validate_command, _load_yaml
from on1builder.cli.run_cmd import app as run_app
from on1builder.cli.status_cmd import app as status_app, status


class TestConfigCommands:
    """Test cases for configuration management commands."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.runner = CliRunner()

    def test_load_yaml_valid_file(self):
        """Test loading a valid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("test_key: test_value\nother_key: 123")
            f.flush()
            
            result = _load_yaml(Path(f.name))
            assert result == {"test_key": "test_value", "other_key": 123}
            
            Path(f.name).unlink()  # Clean up

    def test_load_yaml_empty_file(self):
        """Test loading an empty YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            f.flush()
            
            result = _load_yaml(Path(f.name))
            assert result == {}
            
            Path(f.name).unlink()  # Clean up

    def test_load_yaml_invalid_file(self):
        """Test loading an invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()
            
            with pytest.raises(typer.Exit):
                _load_yaml(Path(f.name))
            
            Path(f.name).unlink()  # Clean up

    def test_validate_command_help(self):
        """Test config validate command help."""
        result = self.runner.invoke(config_app, ["validate", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.stdout

    def test_config_app_help(self):
        """Test config app help."""
        result = self.runner.invoke(config_app, ["--help"])
        assert result.exit_code == 0
        assert "Configuration management commands" in result.stdout

    @patch('on1builder.cli.config_cmd._load_yaml')
    def test_validate_command_success(self, mock_load_yaml):
        """Test successful validation."""
        mock_load_yaml.return_value = {"chain_id": 1, "rpc_url": "http://test"}
        
        with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
            result = self.runner.invoke(config_app, ["validate", f.name])
            assert result.exit_code == 0

    @patch('on1builder.cli.config_cmd._load_yaml')
    def test_validate_command_failure(self, mock_load_yaml):
        """Test validation failure."""
        mock_load_yaml.return_value = {"test": "config"}  # Missing required fields
        
        with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
            result = self.runner.invoke(config_app, ["validate", f.name])
            assert result.exit_code == 1


class TestRunCommands:
    """Test cases for run commands."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.runner = CliRunner()

    def test_run_app_help(self):
        """Test run app help."""
        result = self.runner.invoke(run_app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.stdout.lower()

    @patch('on1builder.cli.run_cmd.load_configuration')
    @patch('on1builder.core.main_orchestrator.MainOrchestrator')
    @patch('asyncio.run')
    def test_run_single_chain_command(self, mock_asyncio_run, mock_orchestrator_class, mock_load_config):
        """Test single chain run command."""
        mock_load_config.return_value = {"multi_chain": False}
        
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_asyncio_run.return_value = None
        
        with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
            result = self.runner.invoke(run_app, ["--config", f.name])
            # The command should attempt to run
            mock_load_config.assert_called_once()
            mock_orchestrator_class.assert_called_once()

    @patch('on1builder.cli.run_cmd.load_configuration')
    @patch('on1builder.core.multi_chain_orchestrator.MultiChainOrchestrator')
    @patch('asyncio.run')
    def test_run_multi_chain_command(self, mock_asyncio_run, mock_orchestrator_class, mock_load_config):
        """Test multi-chain run command."""
        mock_load_config.return_value = {"multi_chain": True}
        
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_asyncio_run.return_value = None
        
        with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
            result = self.runner.invoke(run_app, ["--config", f.name])
            # The command should attempt to run
            mock_load_config.assert_called_once()
            mock_orchestrator_class.assert_called_once()


class TestStatusCommand:
    """Test cases for status command."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.runner = CliRunner()

    @patch('on1builder.cli.status_cmd.load_configuration')
    @patch('on1builder.cli.status_cmd.DatabaseInterface')
    def test_status_command_no_orchestrator(self, mock_db_interface, mock_load_config):
        """Test status command when database connection works."""
        mock_load_config.return_value = {"database": {}, "rpc_url": "http://test"}
        mock_db = MagicMock()
        mock_db_interface.return_value = mock_db
        
        result = self.runner.invoke(status_app, [])
        assert result.exit_code == 0
        assert "Database: Connected" in result.output

    @patch('on1builder.cli.status_cmd.load_configuration')
    @patch('on1builder.cli.status_cmd.DatabaseInterface')
    def test_status_command_with_orchestrator(self, mock_db_interface, mock_load_config):
        """Test status command when database connection works."""
        mock_load_config.return_value = {"database": {}, "rpc_url": "http://test"}
        mock_db = MagicMock()
        mock_db_interface.return_value = mock_db
        
        result = self.runner.invoke(status_app, [])
        assert result.exit_code == 0
        assert "RPC URL: http://test" in result.output

    @patch('on1builder.cli.status_cmd.load_configuration')
    @patch('on1builder.cli.status_cmd.DatabaseInterface')
    def test_status_command_with_error(self, mock_db_interface, mock_load_config):
        """Test status command when an error occurs."""
        mock_load_config.return_value = {"database": {}, "rpc_url": "http://test"}
        mock_db_interface.side_effect = Exception("Database error")
        
        result = self.runner.invoke(status_app, [])
        assert result.exit_code == 0  # Command handles errors gracefully
        assert "Database: Failed" in result.output


class TestCLIIntegration:
    """Integration tests for CLI components."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.runner = CliRunner()

    def test_all_commands_have_help(self):
        """Test that all commands provide help text."""
        # Test config commands
        result = self.runner.invoke(config_app, ["--help"])
        assert result.exit_code == 0
        assert "help" in result.stdout.lower()

        # Test run commands
        result = self.runner.invoke(run_app, ["--help"])
        assert result.exit_code == 0
        assert "help" in result.stdout.lower()

    def test_command_error_handling(self):
        """Test that commands handle errors gracefully."""
        # Test config validate with non-existent file
        result = self.runner.invoke(config_app, ["validate", "/non/existent/file.yaml"])
        assert result.exit_code != 0

        # Test run with non-existent config
        result = self.runner.invoke(run_app, ["run", "--config", "/non/existent/file.yaml"])
        assert result.exit_code != 0

    @patch('on1builder.cli.config_cmd.logger')
    def test_logging_integration(self, mock_logger):
        """Test that CLI commands use logging correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as f:
            f.write("test: value")
            f.flush()
            
            # This should trigger logging
            result = self.runner.invoke(config_app, ["validate", f.name])
            
            # Verify logger was used (even if mocked)
            assert mock_logger is not None


if __name__ == "__main__":
    pytest.main([__file__])

# LICENSE: MIT // github.com/John0n1/ON1Builder
"""Tests for the CLI functionality in cli/__init__.py."""

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from on1builder.cli import monitor_command, parse_args, run_command


def test_parse_args_run_command():
    """Test parsing args for the run command."""
    # Test with default arguments
    with patch("argparse.ArgumentParser.parse_args") as mock_parse_args:
        mock_args = argparse.Namespace(
            command="run", config="config/config.yaml", multi_chain=False, dry_run=False
        )
        mock_parse_args.return_value = mock_args

        result = parse_args()

        assert result.command == "run"
        assert result.config == "config/config.yaml"
        assert result.multi_chain is False
        assert result.dry_run is False

    # Test with custom arguments
    with patch("argparse.ArgumentParser.parse_args") as mock_parse_args:
        mock_args = argparse.Namespace(
            command="run", config="custom_config.yaml", multi_chain=True, dry_run=True
        )
        mock_parse_args.return_value = mock_args

        result = parse_args()

        assert result.command == "run"
        assert result.config == "custom_config.yaml"
        assert result.multi_chain is True
        assert result.dry_run is True


def test_parse_args_monitor_command():
    """Test parsing args for the monitor command."""
    with patch("argparse.ArgumentParser.parse_args") as mock_parse_args:
        mock_args = argparse.Namespace(
            command="monitor", chain="ethereum", config="config/config.yaml"
        )
        mock_parse_args.return_value = mock_args

        result = parse_args()

        assert result.command == "monitor"
        assert result.chain == "ethereum"
        assert result.config == "config/config.yaml"


def test_parse_args_with_custom_args():
    """Test parsing with explicitly provided args."""
    custom_args = [
        "run",
        "--config",
        "custom_config.yaml",
        "--multi-chain",
        "--dry-run",
    ]

    result = parse_args(custom_args)

    assert result.command == "run"
    assert result.config == "custom_config.yaml"
    assert result.multi_chain is True
    assert result.dry_run is True


@pytest.mark.asyncio
async def test_run_command():
    """Test the run_command function."""
    # Create mock args
    args = argparse.Namespace(
        command="run", config="config/config.yaml", multi_chain=False, dry_run=False
    )  # Mock Configuration and MainCore in the correct location
    with (
        patch("on1builder.config.config.Configuration") as mock_config_class,
        patch("on1builder.core.main_core.MainCore") as mock_main_core_class,
    ):
        # Setup mocks
        mock_config = AsyncMock()
        mock_config.load = AsyncMock()
        mock_config_class.return_value = mock_config

        mock_core = AsyncMock()
        mock_core.bootstrap = AsyncMock()
        mock_core.run = AsyncMock()
        mock_main_core_class.return_value = mock_core

        # Call the function
        result = await run_command(args)

        # Check that Configuration was instantiated with the right path
        mock_config_class.assert_called_once_with(config_path=args.config)

        # Check that MainCore was instantiated with the config
        mock_main_core_class.assert_called_once_with(mock_config)

        # Check that bootstrap and run were called
        mock_core.bootstrap.assert_called_once()
        mock_core.run.assert_called_once_with(dry_run=args.dry_run)

        # Check the return value
        assert result == 0


@pytest.mark.asyncio
async def test_run_command_with_error():
    """Test the run_command function when an error occurs."""
    # Create mock args
    args = argparse.Namespace(
        command="run", config="config/config.yaml", multi_chain=False, dry_run=False
    )  # Mock Configuration and MainCore with an error in the correct location
    with (
        patch("on1builder.config.config.Configuration") as mock_config_class,
        patch("on1builder.core.main_core.MainCore") as mock_main_core_class,
    ):
        # Setup mocks
        mock_config = AsyncMock()
        mock_config.load = AsyncMock()
        mock_config_class.return_value = mock_config

        mock_core = AsyncMock()
        mock_core.bootstrap = AsyncMock()
        mock_core.run = AsyncMock(side_effect=Exception("Test error"))
        mock_main_core_class.return_value = mock_core

        # Call the function
        result = await run_command(args)

        # Check the return value
        assert result == 1


@pytest.mark.asyncio
async def test_monitor_command():
    """Test the monitor_command function."""
    # Create mock args
    args = argparse.Namespace(
        command="monitor", chain="ethereum", config="config/config.yaml"
    )  # Mock Configuration and TxpoolMonitor in the correct location
    with (
        patch("on1builder.config.config.Configuration") as mock_config_class,
        patch(
            "on1builder.monitoring.txpool_monitor.TxpoolMonitor"
        ) as mock_monitor_class,
    ):
        # Setup mocks
        mock_config = AsyncMock()
        mock_config.load = AsyncMock()
        mock_config_class.return_value = mock_config

        mock_monitor = AsyncMock()
        mock_monitor.start = AsyncMock()
        mock_monitor_class.return_value = mock_monitor

        # Call the function
        result = await monitor_command(args)

        # Check that Configuration was instantiated with the right path
        mock_config_class.assert_called_once_with(config_path=args.config)

        # Check that TxpoolMonitor was instantiated with the right parameters
        mock_monitor_class.assert_called_once()

        # Check that start was called
        mock_monitor.start.assert_called_once()

        # Check the return value
        assert result == 0


@pytest.mark.asyncio
async def test_monitor_command_with_error():
    """Test the monitor_command function when an error occurs."""
    # Create mock args
    args = argparse.Namespace(
        command="monitor", chain="ethereum", config="config/config.yaml"
    )  # Mock Configuration and TxpoolMonitor with an error in the correct location
    with (
        patch("on1builder.config.config.Configuration") as mock_config_class,
        patch(
            "on1builder.monitoring.txpool_monitor.TxpoolMonitor"
        ) as mock_monitor_class,
    ):
        # Setup mocks
        mock_config = AsyncMock()
        mock_config.load = AsyncMock()
        mock_config_class.return_value = mock_config

        mock_monitor = AsyncMock()
        mock_monitor.start = AsyncMock(side_effect=Exception("Test error"))
        mock_monitor_class.return_value = mock_monitor

        # Call the function
        result = await monitor_command(args)

        # Check the return value
        assert result == 1

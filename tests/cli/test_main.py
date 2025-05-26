"""Extended tests for the main module CLI functionality."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the main module
from on1builder.__main__ import *


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"
    config.WALLET_KEY = "test_wallet_key"
    return config


@pytest.mark.asyncio
async def test_handle_shutdown():
    """Test the handle_shutdown function."""
    core_instance = AsyncMock()

    # Test normal shutdown
    await handle_shutdown(core_instance)
    core_instance.stop.assert_called_once()


@pytest.mark.asyncio
async def test_run_single_chain(mock_config):
    """Test the run_single_chain function."""
    with (
        patch("on1builder.__main__.Configuration", return_value=mock_config),
        patch("on1builder.__main__.MainCore") as mock_main_core,
    ):
        mock_instance = AsyncMock()
        mock_main_core.return_value = mock_instance

        # Test running single chain mode
        await run_single_chain(config_path=None, env_file=None)

        # Check MainCore was instantiated correctly
        mock_main_core.assert_called_once_with(mock_config)
        # Check that run was called
        mock_instance.run.assert_called_once()


@pytest.mark.asyncio
async def test_run_multi_chain():
    """Test the run_multi_chain function."""
    mock_multi_config = MagicMock()

    with (
        patch(
            "on1builder.__main__.MultiChainConfiguration",
            return_value=mock_multi_config,
        ),
        patch("on1builder.__main__.MultiChainCore") as mock_multi_chain_core,
    ):
        mock_instance = AsyncMock()
        mock_multi_chain_core.return_value = mock_instance

        # Test running multi chain mode
        await run_multi_chain(config_path=None, env_file=None)

        # Check MultiChainCore was instantiated correctly
        mock_multi_chain_core.assert_called_once_with(mock_multi_config)
        # Check that initialize and run were called
        mock_instance.initialize.assert_called_once()
        mock_instance.run.assert_called_once()


@pytest.mark.asyncio
async def test_run_monitor(mock_config):
    """Test the run_monitor function."""
    with (
        patch("on1builder.__main__.Configuration", return_value=mock_config),
        patch("on1builder.__main__.TxpoolMonitor") as mock_monitor,
    ):
        mock_instance = AsyncMock()
        mock_monitor.return_value = mock_instance

        # Test running monitor mode
        await run_monitor(config_path=None, env_file=None)

        # Check TxpoolMonitor was instantiated correctly
        mock_monitor.assert_called_once()
        # Check that initialize and run were called
        mock_instance.initialize.assert_called_once()
        mock_instance.run.assert_called_once()


def test_signal_handler():
    """Test the signal handler function."""
    with patch("on1builder.__main__.shutdown_event") as mock_event:
        signal_handler(None, None)
        mock_event.set.assert_called_once()


def test_run_async():
    """Test the run_async function."""
    mock_coro = AsyncMock()
    with patch("on1builder.__main__.asyncio.run") as mock_run:
        run_async(mock_coro)
        mock_run.assert_called_once_with(mock_coro)


@pytest.mark.skipif(not hasattr(sys, "argv"), reason="sys.argv not available")
def test_main_with_args():
    """Test main function with command line arguments."""
    # Save original argv to restore later
    original_argv = sys.argv.copy()

    try:
        # Test with single chain command
        sys.argv = ["on1builder", "run", "--config", "test_config.yaml"]

        with (
            patch("on1builder.__main__.run_system_async") as mock_run_system_async,
            patch("on1builder.__main__.run_single_chain"),
        ):
            main()
            mock_run_system_async.assert_called_once()

        # Test with multi-chain command
        sys.argv = ["on1builder", "run-multi", "--config", "test_multi_config.yaml"]

        with (
            patch("on1builder.__main__.run_system_async") as mock_run_system_async,
            patch("on1builder.__main__.run_multi_chain"),
        ):
            main()
            mock_run_system_async.assert_called_once()

        # Test with monitor command
        sys.argv = ["on1builder", "monitor", "--config", "test_config.yaml"]

        with (
            patch("on1builder.__main__.run_system_async") as mock_run_system_async,
            patch("on1builder.__main__.run_monitor"),
        ):
            main()
            mock_run_system_async.assert_called_once()

    finally:
        # Restore original argv
        sys.argv = original_argv

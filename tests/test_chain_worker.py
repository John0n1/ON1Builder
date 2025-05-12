#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the ChainWorker class.
"""

from scripts.python.chain_worker import ChainWorker
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
import asyncio

# Add the project root to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import after path setup


@pytest.fixture
def chain_config():
    """Create a chain configuration."""
    return {
        "CHAIN_ID": "1",
        "CHAIN_NAME": "Ethereum Mainnet",
        "HTTP_ENDPOINT": "https://mainnet.infura.io/v3/your-infura-key",
        "WEBSOCKET_ENDPOINT": "wss://mainnet.infura.io/ws/v3/your-infura-key",
        "WALLET_ADDRESS": "0xYourMainnetWalletAddress",
        "WALLET_KEY": "0xYourMainnetWalletKey",
    }


@pytest.fixture
def global_config():
    """Create a global configuration."""
    return {
        "DRY_RUN": True,
        "GO_LIVE": False,
    }


@pytest.fixture
def chain_worker(chain_config, global_config):
    """Create a ChainWorker instance."""
    return ChainWorker(chain_config, global_config)


@pytest.mark.asyncio
async def test_initialize(chain_worker):
    """Test the initialize method."""
    # Mock the Web3 class
    with patch("python.chain_worker.Web3") as mock_web3:
        # Mock the Account class
        with patch("python.chain_worker.Account") as mock_account:
            # Set up the Web3 mock
            mock_web3_instance = MagicMock()
            mock_web3.return_value = mock_web3_instance
            mock_web3.HTTPProvider.return_value = "http_provider"
            mock_web3_instance.is_connected.return_value = True
            mock_web3_instance.eth.get_transaction_count.return_value = 10

            # Set up the Account mock
            mock_account_instance = MagicMock()
            mock_account.from_key.return_value = mock_account_instance

            # Mock the get_wallet_balance method
            with patch.object(chain_worker, "get_wallet_balance", new_callable=AsyncMock) as mock_get_wallet_balance:
                mock_get_wallet_balance.return_value = 1.5

                # Mock the get_gas_price method
                with patch.object(chain_worker, "get_gas_price", new_callable=AsyncMock) as mock_get_gas_price:
                    mock_get_gas_price.return_value = 25.0

                    # Call the initialize method
                    result = await chain_worker.initialize()

                    # Check that the result is True
                    assert result is True

                    # Check that the Web3 instance was created
                    mock_web3.HTTPProvider.assert_called_once_with(
                        chain_worker.http_endpoint)
                    mock_web3.assert_called_once()

                    # Check that the Account instance was created
                    mock_account.from_key.assert_called_once_with(
                        chain_worker.wallet_key)

                    # Check that the get_wallet_balance method was called
                    mock_get_wallet_balance.assert_called_once()

                    # Check that the get_gas_price method was called
                    mock_get_gas_price.assert_called_once()

                    # Check that the metrics were updated
                    assert chain_worker.metrics["wallet_balance_eth"] == 1.5
                    assert chain_worker.metrics["last_gas_price_gwei"] == 25.0
                    assert chain_worker.current_nonce == 10


@pytest.mark.asyncio
async def test_initialize_failure(chain_worker):
    """Test the initialize method when initialization fails."""
    # Mock the Web3 class
    with patch("python.chain_worker.Web3") as mock_web3:
        # Set up the Web3 mock
        mock_web3_instance = MagicMock()
        mock_web3.return_value = mock_web3_instance
        mock_web3.HTTPProvider.return_value = "http_provider"
        mock_web3_instance.is_connected.return_value = False

        # Call the initialize method
        result = await chain_worker.initialize()

        # Check that the result is False
        assert result is False


@pytest.mark.asyncio
async def test_start(chain_worker):
    """Test the start method."""
    # Mock the monitor_opportunities method
    with patch.object(chain_worker, "monitor_opportunities", new_callable=AsyncMock) as mock_monitor_opportunities:
        # Mock the update_metrics method
        with patch.object(chain_worker, "update_metrics", new_callable=AsyncMock) as mock_update_metrics:
            # Call the start method with a timeout to avoid hanging
            task = asyncio.create_task(chain_worker.start())

            # Wait a bit for the tasks to start
            await asyncio.sleep(0.1)

            # Stop the worker
            await chain_worker.stop()

            # Wait for the task to complete
            try:
                await asyncio.wait_for(task, timeout=1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # This is expected as we're cancelling the task
                pass

            # Check that the monitor_opportunities method was called
            assert mock_monitor_opportunities.called

            # Check that the update_metrics method was called
            assert mock_update_metrics.called


@pytest.mark.asyncio
async def test_stop(chain_worker):
    """Test the stop method."""
    # Set the running flag
    chain_worker.running = True

    # Call the stop method
    await chain_worker.stop()

    # Check that the running flag was set to False
    assert chain_worker.running is False


@pytest.mark.asyncio
async def test_get_wallet_balance(chain_worker):
    """Test the get_wallet_balance method."""
    # Mock the Web3 instance
    chain_worker.web3 = MagicMock()
    chain_worker.web3.eth.get_balance.return_value = 1500000000000000000  # 1.5 ETH in wei
    chain_worker.web3.from_wei.return_value = 1.5

    # Call the get_wallet_balance method
    balance = await chain_worker.get_wallet_balance()

    # Check that the balance is correct
    assert balance == 1.5

    # Check that the Web3 methods were called
    chain_worker.web3.eth.get_balance.assert_called_once_with(
        chain_worker.wallet_address)
    chain_worker.web3.from_wei.assert_called_once()


@pytest.mark.asyncio
async def test_get_gas_price(chain_worker):
    """Test the get_gas_price method."""
    # Mock the Web3 instance
    chain_worker.web3 = MagicMock()
    chain_worker.web3.eth.gas_price = 25000000000  # 25 Gwei in wei
    chain_worker.web3.from_wei.return_value = 25.0

    # Call the get_gas_price method
    gas_price = await chain_worker.get_gas_price()

    # Check that the gas price is correct
    assert gas_price == 25.0

    # Check that the Web3 methods were called
    chain_worker.web3.from_wei.assert_called_once()


@pytest.mark.asyncio
async def test_monitor_opportunities(chain_worker):
    """Test the monitor_opportunities method."""
    # Set the go_live flag
    chain_worker.go_live = True

    # Call the monitor_opportunities method
    await chain_worker.monitor_opportunities()

    # No assertions needed, just checking that it doesn't raise an exception


@pytest.mark.asyncio
async def test_update_metrics(chain_worker):
    """Test the update_metrics method."""
    # Mock the get_wallet_balance method
    with patch.object(chain_worker, "get_wallet_balance", new_callable=AsyncMock) as mock_get_wallet_balance:
        mock_get_wallet_balance.return_value = 1.5

        # Mock the get_gas_price method
        with patch.object(chain_worker, "get_gas_price", new_callable=AsyncMock) as mock_get_gas_price:
            mock_get_gas_price.return_value = 25.0

            # Mock the Web3 instance
            chain_worker.web3 = MagicMock()
            chain_worker.web3.eth.block_number = 12345678

            # Call the update_metrics method
            await chain_worker.update_metrics()

            # Check that the metrics were updated
            assert chain_worker.metrics["wallet_balance_eth"] == 1.5
            assert chain_worker.metrics["last_gas_price_gwei"] == 25.0
            assert chain_worker.metrics["last_block_number"] == 12345678

            # Check that the methods were called
            mock_get_wallet_balance.assert_called_once()
            mock_get_gas_price.assert_called_once()


def test_get_metrics(chain_worker):
    """Test the get_metrics method."""
    # Set up the metrics
    chain_worker.metrics = {
        "transaction_count": 10,
        "successful_transactions": 9,
        "failed_transactions": 1,
        "total_profit_eth": 0.05,
        "total_gas_spent_eth": 0.02,
        "last_gas_price_gwei": 25.0,
        "wallet_balance_eth": 1.5,
        "last_block_number": 12345678,
    }

    # Call the get_metrics method
    metrics = chain_worker.get_metrics()

    # Check that the metrics are correct
    assert metrics["chain_id"] == chain_worker.chain_id
    assert metrics["chain_name"] == chain_worker.chain_name
    for key, value in chain_worker.metrics.items():
        assert metrics[key] == value

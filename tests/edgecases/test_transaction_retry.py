#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# test_transaction_retry.py - Edge case tests for transaction retry logic
# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from web3.exceptions import TimeExhausted

from on1builder.core.transaction_core import TransactionCore
from on1builder.config.config import Configuration


@pytest.fixture
def config():
    config = Configuration()
    config.TRANSACTION_RETRY_COUNT = 3
    config.TRANSACTION_RETRY_DELAY = 0.1  # short delay for tests
    config.GAS_MULTIPLIER = 1.1
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WALLET_KEY = "0x" + "1" * 64  # Dummy private key
    config.MEMPOOL_MAX_RETRIES = 4
    config.MEMPOOL_RETRY_DELAY = 0.1
    config.MAX_GAS_PRICE_GWEI = 500
    return config
    
@pytest.fixture
def transaction_core(config):
        with patch("on1builder.core.transaction_core.AsyncWeb3") as mock_web3_class:
            # Set up the mock web3 instance
            mock_web3 = MagicMock()
            mock_web3.eth = MagicMock()
            mock_web3.eth.chain_id = 1  # Mock chain ID as a property, not a coroutine
            mock_web3.eth.estimate_gas = AsyncMock(return_value=21000)
            mock_web3.eth.send_raw_transaction = AsyncMock()
            mock_web3.eth.account = MagicMock()
            mock_web3.eth.account.sign_transaction = MagicMock(
                return_value=MagicMock(rawTransaction=b"mock_raw_tx")
            )
            mock_web3.to_wei = lambda amount, unit: amount * 10**9 if unit == "gwei" else amount  # Mock to_wei function
            mock_web3_class.return_value = mock_web3
            
            # Set up account
            mock_account = MagicMock(address="0xMockAddress")
            
            # Mock other dependencies
            mock_api_config = MagicMock()
            mock_market_monitor = MagicMock()
            mock_mempool_monitor = None
            mock_nonce_core = MagicMock()
            mock_nonce_core.get_nonce = AsyncMock(return_value=123)  # Mock async nonce getter
            mock_safety_net = MagicMock()
            
            tx_core = TransactionCore(
                mock_web3, 
                mock_account, 
                config, 
                mock_api_config, 
                mock_market_monitor, 
                mock_mempool_monitor, 
                mock_nonce_core, 
                mock_safety_net
            )
            yield tx_core


@pytest.mark.asyncio
async def test_transaction_retry_on_timeout(transaction_core):
    """Test that transactions are retried when they time out."""
    # Set up the transaction data
    tx_data = {
        "to": "0xDestinationAddress",
        "value": 1000000000000000000,  # 1 ETH
        "gas": 21000,
        "maxFeePerGas": 20000000000,  # 20 Gwei
        "maxPriorityFeePerGas": 1000000000,  # 1 Gwei
    }
    
    # Mock the web3 instance to raise TimeExhausted once, then succeed
    mock_web3 = transaction_core.web3
    
    # First call raises TimeExhausted, second succeeds
    tx_hash = "0x" + "a" * 64  # Dummy tx hash
    mock_send = AsyncMock(side_effect=[
        TimeExhausted("Transaction timed out"),
        tx_hash
    ])
    mock_web3.eth.send_raw_transaction = mock_send
    
    # Mock the transaction creation
    mock_web3.eth.account.sign_transaction.return_value = MagicMock(
        rawTransaction=b"mock_raw_tx"
    )
    
    # Mock gas estimation
    mock_web3.eth.estimate_gas.return_value = 21000

    # Mock simulation to always succeed
    transaction_core.simulate_transaction = AsyncMock(return_value=True)
    
    # Mock sign_transaction and send_signed to avoid chain_id issues
    transaction_core.sign_transaction = AsyncMock(return_value=b"mock_raw_tx")
    transaction_core.send_signed = AsyncMock(side_effect=[
        TimeExhausted("Transaction timed out"),
        tx_hash
    ])
    
    # Call the send transaction method
    result = await transaction_core.execute_transaction(tx_data)
    
    # Assert we got the transaction hash
    assert result == tx_hash
    
    # Assert send_signed was called twice
    assert transaction_core.send_signed.call_count == 2


@pytest.mark.asyncio
async def test_transaction_retry_max_exceeded(transaction_core):
    """Test that transactions fail after max retries."""
    # Set up the transaction data
    tx_data = {
        "to": "0xDestinationAddress",
        "value": 1000000000000000000,  # 1 ETH
        "gas": 21000,
        "maxFeePerGas": 20000000000,  # 20 Gwei
        "maxPriorityFeePerGas": 1000000000,  # 1 Gwei
    }
    
    # Mock the web3 instance to always raise TimeExhausted
    mock_web3 = transaction_core.web3
    mock_web3.eth.send_raw_transaction = AsyncMock(
        side_effect=TimeExhausted("Transaction timed out")
    )
    
    # Mock the transaction creation
    mock_web3.eth.account.sign_transaction.return_value = MagicMock(
        rawTransaction=b"mock_raw_tx"
    )
    
    # Mock gas estimation
    mock_web3.eth.estimate_gas.return_value = 21000

    # Mock simulation to always succeed
    transaction_core.simulate_transaction = AsyncMock(return_value=True)
    
    # Mock sign_transaction and send_signed to avoid chain_id issues
    transaction_core.sign_transaction = AsyncMock(return_value=b"mock_raw_tx")
    
    # Make send_signed always raise TimeExhausted
    transaction_core.send_signed = AsyncMock(side_effect=TimeExhausted("Transaction timed out"))
    
    # Call the send transaction method - should return None after max retries
    result = await transaction_core.execute_transaction(tx_data)
    assert result is None
    
    # Assert send_signed was called max retries + 1 times
    assert transaction_core.send_signed.call_count == transaction_core.config.MEMPOOL_MAX_RETRIES


@pytest.mark.asyncio
async def test_transaction_gas_price_increase_on_retry(transaction_core):
    """Test that gas price increases on each retry."""
    # Set up the transaction data with specific gas price
    tx_data = {
        "to": "0xDestinationAddress",
        "value": 1000000000000000000,  # 1 ETH
        "gas": 21000,
        "gasPrice": 20000000000,  # 20 Gwei initially
    }
    
    # Mock the web3 instance
    mock_web3 = transaction_core.web3
    
    # Track the gas prices used in each attempt
    gas_prices_used = []
    
    # Define tx_hash for later use
    tx_hash = "0x" + "a" * 64  # Dummy tx hash
    
    # Mock simulation to always succeed
    transaction_core.simulate_transaction = AsyncMock(return_value=True)
    
    # Create a custom side effect that captures the gas price
    async def mock_sign_tx(tx):
        gas_prices_used.append(tx.get("gasPrice"))
        return b"mock_raw_tx"
    
    # Mock sign_transaction and send_signed to avoid chain_id issues
    transaction_core.sign_transaction = mock_sign_tx
    transaction_core.send_signed = AsyncMock(side_effect=[
        TimeExhausted("Transaction timed out"),
        TimeExhausted("Transaction timed out"),
        tx_hash
    ])
    
    # Call the send transaction method
    result = await transaction_core.execute_transaction(tx_data)
    
    # Assert we got the transaction hash
    assert result == tx_hash
    
    # Assert send_signed was called 3 times
    assert transaction_core.send_signed.call_count == 3
    
    # Assert gas price increased on each retry
    assert len(gas_prices_used) == 3
    assert gas_prices_used[1] > gas_prices_used[0]
    assert gas_prices_used[2] > gas_prices_used[1]

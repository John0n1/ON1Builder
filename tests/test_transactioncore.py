# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from scripts.python.transaction_core import TransactionCore
from scripts.python.configuration import Configuration

@pytest.fixture
def configuration():
    config = Configuration()
    config.WALLET_KEY = "test_wallet_key"
    config.BASE_PATH = "test_base_path"
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"
    config.IPC_ENDPOINT = "/path/to/geth.ipc"
    return config

@pytest.fixture
def transaction_core(configuration):
    return TransactionCore(configuration)

@pytest.mark.asyncio
async def test_initialize(transaction_core):
    with patch.object(transaction_core, 'initialize', new_callable=AsyncMock) as mock_initialize:
        await transaction_core.initialize()
        mock_initialize.assert_called_once()

@pytest.mark.asyncio
async def test_build_transaction(transaction_core):
    function_call = AsyncMock()
    additional_params = {"param1": "value1"}
    with patch.object(transaction_core, 'build_transaction', new_callable=AsyncMock) as mock_build_transaction:
        await transaction_core.build_transaction(function_call, additional_params)
        mock_build_transaction.assert_called_once_with(function_call, additional_params)

@pytest.mark.asyncio
async def test_execute_transaction(transaction_core):
    tx = {"to": "0xAddress", "value": 1000}
    with patch.object(transaction_core, 'execute_transaction', new_callable=AsyncMock) as mock_execute_transaction:
        await transaction_core.execute_transaction(tx)
        mock_execute_transaction.assert_called_once_with(tx)

@pytest.mark.asyncio
async def test_handle_eth_transaction(transaction_core):
    target_tx = {"tx_hash": "0xHash", "value": 1000}
    with patch.object(transaction_core, 'handle_eth_transaction', new_callable=AsyncMock) as mock_handle_eth_transaction:
        await transaction_core.handle_eth_transaction(target_tx)
        mock_handle_eth_transaction.assert_called_once_with(target_tx)

@pytest.mark.asyncio
async def test_simulate_transaction(transaction_core):
    transaction = {"to": "0xAddress", "value": 1000}
    with patch.object(transaction_core, 'simulate_transaction', new_callable=AsyncMock) as mock_simulate_transaction:
        await transaction_core.simulate_transaction(transaction)
        mock_simulate_transaction.assert_called_once_with(transaction)

@pytest.mark.asyncio
async def test_prepare_flashloan_transaction(transaction_core):
    flashloan_asset = "0xAsset"
    flashloan_amount = 1000
    with patch.object(transaction_core, 'prepare_flashloan_transaction', new_callable=AsyncMock) as mock_prepare_flashloan_transaction:
        await transaction_core.prepare_flashloan_transaction(flashloan_asset, flashloan_amount)
        mock_prepare_flashloan_transaction.assert_called_once_with(flashloan_asset, flashloan_amount)

@pytest.mark.asyncio
async def test_send_bundle(transaction_core):
    transactions = [{"to": "0xAddress", "value": 1000}]
    with patch.object(transaction_core, 'send_bundle', new_callable=AsyncMock) as mock_send_bundle:
        await transaction_core.send_bundle(transactions)
        mock_send_bundle.assert_called_once_with(transactions)

@pytest.mark.asyncio
async def test_front_run(transaction_core):
    target_tx = {"tx_hash": "0xHash", "value": 1000}
    with patch.object(transaction_core, 'front_run', new_callable=AsyncMock) as mock_front_run:
        await transaction_core.front_run(target_tx)
        mock_front_run.assert_called_once_with(target_tx)

@pytest.mark.asyncio
async def test_back_run(transaction_core):
    target_tx = {"tx_hash": "0xHash", "value": 1000}
    with patch.object(transaction_core, 'back_run', new_callable=AsyncMock) as mock_back_run:
        await transaction_core.back_run(target_tx)
        mock_back_run.assert_called_once_with(target_tx)

@pytest.mark.asyncio
async def test_execute_sandwich_attack(transaction_core):
    target_tx = {"tx_hash": "0xHash", "value": 1000}
    strategy = "default"
    with patch.object(transaction_core, 'execute_sandwich_attack', new_callable=AsyncMock) as mock_execute_sandwich_attack:
        await transaction_core.execute_sandwich_attack(target_tx, strategy)
        mock_execute_sandwich_attack.assert_called_once_with(target_tx, strategy)

@pytest.mark.asyncio
async def test_cancel_transaction(transaction_core):
    nonce = 1
    with patch.object(transaction_core, 'cancel_transaction', new_callable=AsyncMock) as mock_cancel_transaction:
        await transaction_core.cancel_transaction(nonce)
        mock_cancel_transaction.assert_called_once_with(nonce)

@pytest.mark.asyncio
async def test_withdraw_eth(transaction_core):
    with patch.object(transaction_core, 'withdraw_eth', new_callable=AsyncMock) as mock_withdraw_eth:
        await transaction_core.withdraw_eth()
        mock_withdraw_eth.assert_called_once()

@pytest.mark.asyncio
async def test_transfer_profit_to_account(transaction_core):
    amount = 1000
    account = "0xAccount"
    with patch.object(transaction_core, 'transfer_profit_to_account', new_callable=AsyncMock) as mock_transfer_profit_to_account:
        await transaction_core.transfer_profit_to_account(amount, account)
        mock_transfer_profit_to_account.assert_called_once_with(amount, account)

@pytest.mark.asyncio
async def test_stop(transaction_core):
    with patch.object(transaction_core, 'stop', new_callable=AsyncMock) as mock_stop:
        await transaction_core.stop()
        mock_stop.assert_called_once()

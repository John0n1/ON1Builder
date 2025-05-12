# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from scripts.python.nonce_core import NonceCore
from scripts.python.configuration import Configuration
from web3 import AsyncWeb3

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
def nonce_core(configuration):
    web3 = AsyncWeb3()
    address = "0xYourEthereumAddress"
    return NonceCore(web3, address, configuration)

@pytest.mark.asyncio
async def test_initialize(nonce_core):
    with patch.object(nonce_core, 'initialize', new_callable=AsyncMock) as mock_initialize:
        await nonce_core.initialize()
        mock_initialize.assert_called_once()

@pytest.mark.asyncio
async def test_get_nonce(nonce_core):
    with patch.object(nonce_core, 'get_nonce', new_callable=AsyncMock) as mock_get_nonce:
        await nonce_core.get_nonce()
        mock_get_nonce.assert_called_once()

@pytest.mark.asyncio
async def test_refresh_nonce(nonce_core):
    with patch.object(nonce_core, 'refresh_nonce', new_callable=AsyncMock) as mock_refresh_nonce:
        await nonce_core.refresh_nonce()
        mock_refresh_nonce.assert_called_once()

@pytest.mark.asyncio
async def test_track_transaction(nonce_core):
    tx_hash = "0xTransactionHash"
    nonce = 1
    with patch.object(nonce_core, 'track_transaction', new_callable=AsyncMock) as mock_track_transaction:
        await nonce_core.track_transaction(tx_hash, nonce)
        mock_track_transaction.assert_called_once_with(tx_hash, nonce)

@pytest.mark.asyncio
async def test_sync_nonce_with_chain(nonce_core):
    with patch.object(nonce_core, 'sync_nonce_with_chain', new_callable=AsyncMock) as mock_sync_nonce_with_chain:
        await nonce_core.sync_nonce_with_chain()
        mock_sync_nonce_with_chain.assert_called_once()

@pytest.mark.asyncio
async def test_reset(nonce_core):
    with patch.object(nonce_core, 'reset', new_callable=AsyncMock) as mock_reset:
        await nonce_core.reset()
        mock_reset.assert_called_once()

@pytest.mark.asyncio
async def test_stop(nonce_core):
    with patch.object(nonce_core, 'stop', new_callable=AsyncMock) as mock_stop:
        await nonce_core.stop()
        mock_stop.assert_called_once()

@pytest.mark.asyncio
async def test_get_next_nonce(nonce_core):
    with patch.object(nonce_core, 'get_next_nonce', new_callable=AsyncMock) as mock_get_next_nonce:
        await nonce_core.get_next_nonce()
        mock_get_next_nonce.assert_called_once()

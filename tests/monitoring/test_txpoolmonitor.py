# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from on1builder.monitoring.txpool_monitor import TxpoolMonitor

@pytest.fixture
def configuration():
    from on1builder.config.config import Configuration
    config = Configuration()
    config.WALLET_KEY = "test_wallet_key"
    config.BASE_PATH = "test_base_path"
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"
    config.IPC_ENDPOINT = "/path/to/geth.ipc"
    return config

@pytest.fixture
def web3():
    from web3 import AsyncWeb3
    return AsyncWeb3()

@pytest.fixture
def account():
    from eth_account import Account
    return Account.create()

@pytest.fixture
def safety_net(web3, configuration, account):
    from on1builder.engines.safety_net import SafetyNet
    return SafetyNet(web3, configuration, account.address)

@pytest.fixture
def nonce_core(configuration, web3):
    from on1builder.core.nonce_core import NonceCore
    return NonceCore(web3, configuration)

@pytest.fixture
def api_config(configuration):
    from on1builder.config.config import APIConfig
    return APIConfig(configuration)

@pytest.fixture
def market_monitor(configuration, api_config):
    from on1builder.monitoring.market_monitor import MarketMonitor
    return MarketMonitor(configuration, api_config)

@pytest.fixture
def txpool_monitor(web3, safety_net, nonce_core, api_config, configuration, market_monitor):
    monitored_tokens = ["0xToken1", "0xToken2"]
    return TxpoolMonitor(web3, safety_net, nonce_core, api_config, monitored_tokens, configuration, market_monitor)

@pytest.mark.asyncio
async def test_handle_new_transactions(txpool_monitor):
    transactions = ["tx1", "tx2", "tx3"]
    with patch.object(txpool_monitor, '_process_transaction', new_callable=AsyncMock) as mock_process_transaction:
        await txpool_monitor._handle_new_transactions(transactions)
        assert mock_process_transaction.call_count == len(transactions)

@pytest.mark.asyncio
async def test_queue_transaction(txpool_monitor):
    transaction = "tx1"
    with patch.object(txpool_monitor, '_process_transaction', new_callable=AsyncMock) as mock_process_transaction:
        await txpool_monitor._queue_transaction(transaction)
        mock_process_transaction.assert_called_once_with(transaction)

@pytest.mark.asyncio
async def test_monitor_memory(txpool_monitor):
    with patch('on1builder.monitoring.txpool_monitor.psutil.virtual_memory') as mock_virtual_memory:
        mock_virtual_memory.return_value.percent = 50
        await txpool_monitor._monitor_memory()
        assert mock_virtual_memory.called

@pytest.mark.asyncio
async def test_get_dynamic_gas_price(txpool_monitor):
    with patch.object(txpool_monitor.web3.eth, 'get_block', new_callable=AsyncMock) as mock_get_block:
        mock_get_block.return_value = {'baseFeePerGas': 1000000000}
        gas_price = await txpool_monitor.get_dynamic_gas_price()
        assert mock_get_block.called

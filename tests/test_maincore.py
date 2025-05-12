# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from scripts.python.main_core import MainCore
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
def main_core(configuration):
    return MainCore(configuration)

@pytest.mark.asyncio
async def test_initialize_components(main_core):
    with patch.object(main_core, '_load_configuration', new_callable=AsyncMock) as mock_load_config, \
         patch.object(main_core, '_initialize_web3', new_callable=AsyncMock) as mock_init_web3, \
         patch.object(main_core, '_check_account_balance', new_callable=AsyncMock) as mock_check_balance, \
         patch('abi_registry.ABIRegistry.initialize', new_callable=AsyncMock) as mock_abi_init, \
         patch('api_config.APIConfig.initialize', new_callable=AsyncMock) as mock_api_config_init, \
         patch('nonce_core.NonceCore.initialize', new_callable=AsyncMock) as mock_nonce_init, \
         patch('safety_net.SafetyNet.initialize', new_callable=AsyncMock) as mock_safety_net_init, \
         patch('transaction_core.TransactionCore.initialize', new_callable=AsyncMock) as mock_txcore_init, \
         patch('market_monitor.MarketMonitor.initialize', new_callable=AsyncMock) as mock_market_monitor_init, \
         patch('txpool_monitor.TxpoolMonitor.initialize', new_callable=AsyncMock) as mock_txpool_monitor_init, \
         patch('strategy_net.StrategyNet.initialize', new_callable=AsyncMock) as mock_strategy_net_init:
        
        await main_core._initialize_components()

        mock_load_config.assert_called_once()
        mock_init_web3.assert_called_once()
        mock_check_balance.assert_called_once()
        mock_abi_init.assert_called_once()
        mock_api_config_init.assert_called_once()
        mock_nonce_init.assert_called_once()
        mock_safety_net_init.assert_called_once()
        mock_txcore_init.assert_called_once()
        mock_market_monitor_init.assert_called_once()
        mock_txpool_monitor_init.assert_called_once()
        mock_strategy_net_init.assert_called_once()

@pytest.mark.asyncio
async def test_initialize(main_core):
    with patch.object(main_core, '_initialize_components', new_callable=AsyncMock) as mock_init_components:
        await main_core.initialize()
        mock_init_components.assert_called_once()

@pytest.mark.asyncio
async def test_run(main_core):
    with patch.object(main_core.components['txpool_monitor'], 'start_monitoring', new_callable=AsyncMock) as mock_start_monitoring, \
         patch.object(main_core, '_process_profitable_transactions', new_callable=AsyncMock) as mock_process_tx, \
         patch.object(main_core, '_monitor_memory', new_callable=AsyncMock) as mock_monitor_memory, \
         patch.object(main_core, '_check_component_health', new_callable=AsyncMock) as mock_check_health:
        
        await main_core.run()

        mock_start_monitoring.assert_called_once()
        mock_process_tx.assert_called_once()
        mock_monitor_memory.assert_called_once()
        mock_check_health.assert_called_once()

@pytest.mark.asyncio
async def test_stop(main_core):
    with patch.object(main_core, '_stop_component', new_callable=AsyncMock) as mock_stop_component, \
         patch.object(main_core.web3.provider, 'disconnect', new_callable=AsyncMock) as mock_disconnect:
        
        await main_core.stop()

        mock_stop_component.assert_called()
        mock_disconnect.assert_called_once()

@pytest.mark.asyncio
async def test_emergency_shutdown(main_core):
    with patch('asyncio.all_tasks', return_value=[]), \
         patch.object(main_core.web3.provider, 'disconnect', new_callable=AsyncMock) as mock_disconnect:
        
        await main_core.emergency_shutdown()

        mock_disconnect.assert_called_once()

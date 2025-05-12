# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from scripts.python.safety_net import SafetyNet
from scripts.python.configuration import Configuration
from web3 import AsyncWeb3
from eth_account import Account

@pytest.fixture
def configuration():
    config = Configuration()
    config.SAFETYNET_CACHE_TTL = 60
    config.SAFETYNET_GAS_PRICE_TTL = 10
    config.MAX_GAS_PRICE_GWEI = 100
    config.MIN_PROFIT = 0.001
    return config

@pytest.fixture
def web3():
    return AsyncWeb3()

@pytest.fixture
def account():
    return Account.create()

@pytest.fixture
def safety_net(web3, configuration, account):
    return SafetyNet(web3, configuration=configuration, account=account)

@pytest.mark.asyncio
async def test_initialize(safety_net):
    with patch.object(safety_net.web3, 'is_connected', new_callable=AsyncMock) as mock_is_connected:
        mock_is_connected.return_value = True
        await safety_net.initialize()
        mock_is_connected.assert_called_once()

@pytest.mark.asyncio
async def test_get_balance(safety_net, account):
    with patch.object(safety_net.web3.eth, 'get_balance', new_callable=AsyncMock) as mock_get_balance:
        mock_get_balance.return_value = 1000000000000000000  # 1 ETH in wei
        balance = await safety_net.get_balance(account)
        assert balance == 1

@pytest.mark.asyncio
async def test_ensure_profit(safety_net):
    transaction_data = {
        'output_token': '0xTokenAddress',
        'amountOut': 100,
        'amountIn': 1,
        'gas_price': 50,
        'gas_used': 21000
    }
    with patch.object(safety_net.api_config, 'get_real_time_price', new_callable=AsyncMock) as mock_get_real_time_price, \
         patch.object(safety_net, '_calculate_gas_cost', return_value=0.001) as mock_calculate_gas_cost, \
         patch.object(safety_net, 'adjust_slippage_tolerance', return_value=0.1) as mock_adjust_slippage_tolerance, \
         patch.object(safety_net, '_calculate_profit', return_value=0.1) as mock_calculate_profit:
        mock_get_real_time_price.return_value = 0.01
        result = await safety_net.ensure_profit(transaction_data)
        assert result is True

@pytest.mark.asyncio
async def test_check_transaction_safety(safety_net):
    tx_data = {
        'output_token': '0xTokenAddress',
        'amountOut': 100,
        'amountIn': 1,
        'gas_price': 50,
        'gas_used': 21000
    }
    with patch.object(safety_net, 'get_dynamic_gas_price', return_value=50) as mock_get_dynamic_gas_price, \
         patch.object(safety_net.api_config, 'get_real_time_price', return_value=0.01) as mock_get_real_time_price, \
         patch.object(safety_net, 'adjust_slippage_tolerance', return_value=0.1) as mock_adjust_slippage_tolerance, \
         patch.object(safety_net, '_calculate_gas_cost', return_value=0.001) as mock_calculate_gas_cost, \
         patch.object(safety_net, '_calculate_profit', return_value=0.1) as mock_calculate_profit, \
         patch.object(safety_net, 'get_network_congestion', return_value=0.5) as mock_get_network_congestion:
        result, details = await safety_net.check_transaction_safety(tx_data)
        assert result is True
        assert details['is_safe'] is True
        assert details['gas_ok'] is True
        assert details['profit_ok'] is True
        assert details['congestion_ok'] is True

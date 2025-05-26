# LICENSE: MIT // github.com/John0n1/ON1Builder

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from eth_account import Account
from web3 import AsyncWeb3

from on1builder.config.config import Configuration
from on1builder.engines.safety_net import SafetyNet


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
    safety_net = SafetyNet(web3, configuration, account.address)
    # Add mock api_config for tests
    safety_net.api_config = MagicMock()
    safety_net.api_config.get_real_time_price = AsyncMock()
    return safety_net


@pytest.mark.asyncio
async def test_initialize(safety_net):
    with patch.object(
        safety_net.web3, "is_connected", new_callable=AsyncMock
    ) as mock_is_connected:
        mock_is_connected.return_value = True
        await safety_net.initialize()
        mock_is_connected.assert_called_once()


@pytest.mark.asyncio
async def test_get_balance(safety_net, account):
    with patch.object(
        safety_net.web3.eth, "get_balance", new_callable=AsyncMock
    ) as mock_get_balance:
        mock_get_balance.return_value = 1000000000000000000  # 1 ETH in wei
        balance = await safety_net.get_balance(account)
        assert balance == 1


@pytest.mark.asyncio
async def test_ensure_profit(safety_net):
    transaction_data = {
        "output_token": "0xTokenAddress",
        "amountOut": 100,
        "amountIn": 1,
        "gas_price": 50,
        "gas_used": 21000,
    }
    with (
        patch.object(
            safety_net.api_config, "get_real_time_price", new_callable=AsyncMock
        ) as mock_get_real_time_price,
        patch.object(
            safety_net, "_calculate_gas_cost", new_callable=AsyncMock
        ) as mock_calculate_gas_cost,
        patch.object(
            safety_net, "adjust_slippage_tolerance", new_callable=AsyncMock
        ) as mock_adjust_slippage_tolerance,
        patch.object(
            safety_net, "get_dynamic_gas_price", new_callable=AsyncMock
        ) as mock_dynamic_gas_price,
        patch.object(
            safety_net, "get_network_congestion", new_callable=AsyncMock
        ) as mock_network_congestion,
    ):
        mock_get_real_time_price.return_value = 0.01
        mock_calculate_gas_cost.return_value = 0.001
        mock_adjust_slippage_tolerance.return_value = 0.1
        mock_dynamic_gas_price.return_value = 50
        mock_network_congestion.return_value = 0.5

        result = await safety_net.ensure_profit(transaction_data)
        assert result is True


@pytest.mark.asyncio
async def test_check_transaction_safety(safety_net):
    tx_data = {
        "output_token": "0xTokenAddress",
        "amountOut": 100,
        "amountIn": 1,
        "gas_price": 50,
        "gas_used": 21000,
    }
    with (
        patch.object(
            safety_net, "get_dynamic_gas_price", new_callable=AsyncMock
        ) as mock_get_dynamic_gas_price,
        patch.object(
            safety_net.api_config, "get_real_time_price", new_callable=AsyncMock
        ) as mock_get_real_time_price,
        patch.object(
            safety_net, "adjust_slippage_tolerance", new_callable=AsyncMock
        ) as mock_adjust_slippage_tolerance,
        patch.object(
            safety_net, "_calculate_gas_cost", new_callable=AsyncMock
        ) as mock_calculate_gas_cost,
        patch.object(
            safety_net, "get_network_congestion", new_callable=AsyncMock
        ) as mock_get_network_congestion,
        patch.object(
            safety_net, "ensure_profit", new_callable=AsyncMock
        ) as mock_ensure_profit,
        patch.object(
            safety_net.web3.eth, "get_balance", new_callable=AsyncMock
        ) as mock_get_balance,
    ):
        # Set up mock returns
        mock_get_dynamic_gas_price.return_value = 50
        mock_get_real_time_price.return_value = 0.01
        mock_adjust_slippage_tolerance.return_value = 0.1
        mock_calculate_gas_cost.return_value = 0.001
        mock_get_network_congestion.return_value = 0.5
        mock_ensure_profit.return_value = True
        mock_get_balance.return_value = 10000000000000000000  # 10 ETH

        # Set up web3 from_wei method
        safety_net.web3.from_wei = lambda x, unit: x / 10**18 if unit == "ether" else x

        result, details = await safety_net.check_transaction_safety(tx_data)
        assert result is True
        assert "checks_passed" in details
        assert "checks_total" in details

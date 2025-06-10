#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for SafetyGuard"""
from on1builder.config.settings import GlobalSettings
from on1builder.engines.safety_guard import SafetyGuard
from on1builder.integrations.external_apis import ExternalAPIManager
import asyncio
import os

# Add the src directory to the path for imports
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestSafetyGuard:
    """Test cases for SafetyGuard class."""

    @pytest.fixture
    def mock_web3(self):
        """Mock AsyncWeb3 instance."""
        web3 = AsyncMock()
        web3.is_connected = AsyncMock(return_value=True)
        web3.eth.get_balance = AsyncMock(return_value=1000000000000000000)  # 1 ETH in wei
        
        # Use AsyncMock for gas_price and max_priority_fee 
        web3.eth.gas_price = AsyncMock(return_value=20000000000)  # 20 gwei
        web3.eth.max_priority_fee = AsyncMock(return_value=2000000000)  # 2 gwei
        
        web3.eth.get_block = AsyncMock(return_value={"gasUsed": 500000, "gasLimit": 1000000, "transactions": []})
        web3.eth.estimate_gas = AsyncMock(return_value=50000)
        web3.to_wei = lambda val, unit: (
            int(val * 10**18) if unit == "ether" else int(val * 10**9)
        )
        web3.from_wei = lambda val, unit: (
            val / 10**18 if unit == "ether" else val / 10**9
        )
        web3.to_checksum_address = lambda addr: addr
        
        # Mock contract creation
        mock_contract = MagicMock()
        mock_contract.functions.getLatestGasPrice.return_value.call = AsyncMock(return_value=25000000000)
        mock_contract.functions.latestAnswer.return_value.call = AsyncMock(return_value=25000000000)
        web3.eth.contract.return_value = mock_contract
        
        return web3

    @pytest.fixture
    def mock_config(self):
        """Mock GlobalSettings configuration."""
        config = MagicMock(spec=GlobalSettings)
        config.min_balance = 0.1  # 0.1 ETH
        config.max_gas_price = 50000000000  # 50 gwei
        config.min_gas_price_gwei = 1.0
        config.max_gas_price_gwei = 100.0
        config.default_gas_limit = 500000
        config.safetynet_cache_ttl = 300  # 5 minutes
        config.slippage_low_congestion = 0.5
        config.slippage_medium_congestion = 1.0
        config.slippage_high_congestion = 2.0
        config.slippage_extreme_congestion = 5.0
        config.slippage_default = 1.0
        config.min_slippage = 0.1
        config.max_slippage = 10.0
        config.max_network_congestion = 0.9
        config.profit_safety_margin = 0.95
        config.min_profit = 0.001
        config.primary_token = "ETH"
        config.profitability_threshold_eth = 0.01
        config.max_loss_threshold_eth = 0.005
        config.base_path = "/test/path"
        config.api_config = MagicMock()  # Add api_config attribute
        
        # Mock config() callable for dynamic settings
        def config_call(key, default=None):
            config_map = {
                "ALLOWED_TOKENS": ["ETH", "USDC", "DAI"],
                "MIN_PROFIT": 0.001,
                "MIN_SAFETY_PERCENTAGE": 85,
                "GAS_ESTIMATE_SAFETY_MARGIN": 1.1,
                "DEFAULT_GAS_LIMIT": 500000,
            }
            return config_map.get(key, default)
        
        config.side_effect = config_call
        config.__call__ = config_call
        
        return config

    @pytest.fixture
    def mock_account(self):
        """Mock Account instance."""
        account = MagicMock()
        account.address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        return account

    @pytest.fixture
    def mock_external_api_manager(self):
        """Mock ExternalAPIManager."""
        api_manager = AsyncMock(spec=ExternalAPIManager)
        api_manager.get_real_time_price = AsyncMock(return_value=2500.0)  # ETH price in USD
        return api_manager

    @pytest.fixture
    def mock_orchestrator(self):
        """Mock main orchestrator with components."""
        orchestrator = MagicMock()
        orchestrator.components = {
            "abi_registry": AsyncMock(),
        }

        # Mock ABI registry methods
        orchestrator.components["abi_registry"].get_abi.return_value = [
            {"name": "test"}
        ]

        return orchestrator

    @pytest.fixture
    def safety_guard(
        self,
        mock_web3,
        mock_config,
        mock_account,
        mock_external_api_manager,
        mock_orchestrator,
    ):
        """Create SafetyGuard instance."""
        return SafetyGuard(
            web3=mock_web3,
            config=mock_config,
            account=mock_account,
            external_api_manager=mock_external_api_manager,
            main_orchestrator=mock_orchestrator,
        )

    @pytest.fixture
    def safety_guard_minimal(self, mock_web3, mock_config, mock_account):
        """Create minimal SafetyGuard instance."""
        return SafetyGuard(web3=mock_web3, config=mock_config, account=mock_account)

    def test_init_with_orchestrator(
        self, safety_guard, mock_web3, mock_config, mock_account, mock_orchestrator
    ):
        """Test SafetyGuard initialization with orchestrator."""
        assert safety_guard.web3 == mock_web3
        assert safety_guard.config == mock_config
        assert safety_guard.account == mock_account
        assert safety_guard.account_address == mock_account.address
        assert safety_guard.main_orchestrator == mock_orchestrator
        assert safety_guard.circuit_broken is False
        assert safety_guard.circuit_break_reason is None
        assert isinstance(safety_guard.recent_txs, set)
        assert len(safety_guard._gas_price_history) == 0
        assert len(safety_guard._congestion_history) == 0

    def test_init_without_orchestrator(
        self, safety_guard_minimal, mock_web3, mock_config, mock_account
    ):
        """Test SafetyGuard initialization without orchestrator."""
        assert safety_guard_minimal.web3 == mock_web3
        assert safety_guard_minimal.config == mock_config
        assert safety_guard_minimal.account == mock_account
        assert safety_guard_minimal.main_orchestrator is None

    def test_init_with_string_account(self, mock_web3, mock_config):
        """Test SafetyGuard initialization with string account address."""
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        safety_guard = SafetyGuard(mock_web3, mock_config, address)

        assert safety_guard.account == address
        assert safety_guard.account_address == address

    @pytest.mark.asyncio
    async def test_initialize_success(self, safety_guard, mock_web3, mock_orchestrator):
        """Test successful initialization."""
        await safety_guard.initialize()

        mock_web3.is_connected.assert_called_once()
        assert safety_guard.abi_registry == mock_orchestrator.components["abi_registry"]

    @pytest.mark.asyncio
    async def test_initialize_web3_not_connected(self, safety_guard, mock_web3):
        """Test initialization when web3 is not connected."""
        mock_web3.is_connected.return_value = False

        await safety_guard.initialize()
        # Should complete without error but log warning

    @pytest.mark.asyncio
    async def test_initialize_without_orchestrator(self, safety_guard_minimal):
        """Test initialization without orchestrator."""
        await safety_guard_minimal.initialize()

        assert safety_guard_minimal.abi_registry is None

    @pytest.mark.asyncio
    async def test_close(self, safety_guard):
        """Test close method."""
        await safety_guard.close()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_stop_alias(self, safety_guard):
        """Test stop method as alias for close."""
        with patch.object(safety_guard, "close", new_callable=AsyncMock) as mock_close:
            await safety_guard.stop()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_balance_with_account_object(self, safety_guard, mock_web3):
        """Test getting balance with account object."""
        account = MagicMock()
        account.address = "0x123456"

        balance = await safety_guard.get_balance(account)

        assert balance == 1.0  # 1 ETH
        mock_web3.eth.get_balance.assert_called_once_with("0x123456")

    @pytest.mark.asyncio
    async def test_get_balance_with_address_string(self, safety_guard, mock_web3):
        """Test getting balance with address string."""
        balance = await safety_guard.get_balance("0x123456")

        assert balance == 1.0
        mock_web3.eth.get_balance.assert_called_once_with("0x123456")

    @pytest.mark.asyncio
    async def test_is_safe_to_proceed_circuit_broken(self, safety_guard):
        """Test is_safe_to_proceed when circuit is broken."""
        safety_guard.circuit_broken = True
        safety_guard.circuit_break_reason = "Test reason"

        result = await safety_guard.is_safe_to_proceed()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_safe_to_proceed_low_balance(
        self, safety_guard, mock_web3, mock_config
    ):
        """Test is_safe_to_proceed with low balance."""
        mock_web3.eth.get_balance = AsyncMock(return_value=50000000000000000)  # 0.05 ETH (below min_balance)

        result = await safety_guard.is_safe_to_proceed()

        assert result is False
        assert safety_guard.circuit_broken is True

    @pytest.mark.asyncio
    async def test_is_safe_to_proceed_high_gas_price(
        self, safety_guard, mock_web3, mock_config
    ):
        """Test is_safe_to_proceed with high gas price."""
        # Use AsyncMock for gas_price coroutine that returns high value
        web3.eth.gas_price = AsyncMock(return_value=60000000000)  # 60 gwei (above max_gas_price)

        result = await safety_guard.is_safe_to_proceed()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_safe_to_proceed_success(self, safety_guard, mock_web3):
        """Test successful is_safe_to_proceed."""
        result = await safety_guard.is_safe_to_proceed()

        assert result is True

    @pytest.mark.asyncio
    async def test_break_circuit(self, safety_guard):
        """Test circuit breaker activation."""
        reason = "Test circuit break"

        with patch(
            "on1builder.utils.notification_service.send_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await safety_guard.break_circuit(reason)

        assert safety_guard.circuit_broken is True
        assert safety_guard.circuit_break_reason == reason

    @pytest.mark.asyncio
    async def test_break_circuit_no_notification_service(self, safety_guard):
        """Test circuit breaker activation without notification service."""
        reason = "Test circuit break"

        # Simply test that the circuit breaks even if notification fails
        await safety_guard.break_circuit(reason)

        assert safety_guard.circuit_broken is True
        assert safety_guard.circuit_break_reason == reason

    @pytest.mark.asyncio
    async def test_reset_circuit(self, safety_guard):
        """Test circuit breaker reset."""
        # First break the circuit
        safety_guard.circuit_broken = True
        safety_guard.circuit_break_reason = "Test reason"

        await safety_guard.reset_circuit()

        assert safety_guard.circuit_broken is False
        assert safety_guard.circuit_break_reason is None

    @pytest.mark.asyncio
    async def test_reset_circuit_not_broken(self, safety_guard):
        """Test resetting circuit when not broken."""
        await safety_guard.reset_circuit()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_is_transaction_duplicate_new_tx(self, safety_guard):
        """Test duplicate detection with new transaction."""
        tx_hash = "0x123456"

        result = await safety_guard.is_transaction_duplicate(tx_hash)

        assert result is False
        assert tx_hash in safety_guard.recent_txs

    @pytest.mark.asyncio
    async def test_is_transaction_duplicate_existing_tx(self, safety_guard):
        """Test duplicate detection with existing transaction."""
        tx_hash = "0x123456"
        safety_guard.recent_txs.add(tx_hash)

        result = await safety_guard.is_transaction_duplicate(tx_hash)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_transaction_duplicate_cache_expiry(
        self, safety_guard, mock_config
    ):
        """Test duplicate detection with cache expiry."""
        tx_hash = "0x123456"
        safety_guard._cache_expiry = time.time() - 1  # Expired cache

        result = await safety_guard.is_transaction_duplicate(tx_hash)

        assert result is False
        assert len(safety_guard.recent_txs) == 1  # Cache was cleared and tx added

    @pytest.mark.asyncio
    async def test_validate_transaction_params_high_gas_price(
        self, safety_guard, mock_config
    ):
        """Test transaction validation with high gas price."""
        tx_params = {
            "gasPrice": 60000000000,  # 60 gwei (above max)
            "gas": 100000,
            "value": 1000000000000000,  # 0.001 ETH
        }

        result = await safety_guard.validate_transaction_params(tx_params)

        assert result is not None
        assert "Gas price" in result

    @pytest.mark.asyncio
    async def test_validate_transaction_params_high_gas_limit(
        self, safety_guard, mock_config
    ):
        """Test transaction validation with high gas limit."""
        tx_params = {
            "gasPrice": 20000000000,
            "gas": 600000,  # Above default_gas_limit
            "value": 1000000000000000,
        }

        result = await safety_guard.validate_transaction_params(tx_params)

        assert result is not None
        assert "Gas limit" in result

    @pytest.mark.asyncio
    async def test_validate_transaction_params_high_value(
        self, safety_guard, mock_web3
    ):
        """Test transaction validation with high value."""
        tx_params = {
            "gasPrice": 20000000000,
            "gas": 100000,
            "value": 990000000000000000,  # 99% of balance
        }

        result = await safety_guard.validate_transaction_params(tx_params)

        assert result is not None
        assert "Value" in result

    @pytest.mark.asyncio
    async def test_validate_transaction_params_success(self, safety_guard):
        """Test successful transaction validation."""
        tx_params = {
            "gasPrice": 20000000000,
            "gas": 100000,
            "value": 1000000000000000,  # 0.001 ETH
        }

        result = await safety_guard.validate_transaction_params(tx_params)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_oracle_success(
        self, safety_guard, mock_web3, mock_config, mock_orchestrator
    ):
        """Test dynamic gas price with oracle."""
        mock_config.gas_price_oracle = "0x123456"

        # Mock contract
        mock_contract = AsyncMock()
        mock_contract.functions.getLatestGasPrice.return_value.call.return_value = (
            25000000000  # 25 gwei
        )
        mock_web3.eth.contract.return_value = mock_contract

        gas_price = await safety_guard.get_dynamic_gas_price()

        assert gas_price == 25.0  # 25 gwei

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_oracle_error(
        self, safety_guard, mock_web3, mock_config
    ):
        """Test dynamic gas price when oracle fails."""
        mock_config.gas_price_oracle = "0x123456"
        mock_web3.eth.contract.side_effect = Exception("Oracle error")

        gas_price = await safety_guard.get_dynamic_gas_price()

        assert gas_price == 20.0  # Fallback to base gas price

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_eip1559(self, safety_guard, mock_web3):
        """Test dynamic gas price with EIP-1559."""
        mock_web3.eth.get_block.return_value = {
            "baseFeePerGas": 15000000000,  # 15 gwei
            "gasUsed": 500000,
            "gasLimit": 1000000,
        }

        with patch.object(safety_guard, "get_network_congestion", return_value=0.2):
            gas_price = await safety_guard.get_dynamic_gas_price()

        assert gas_price > 15.0  # Should be base fee + priority

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_legacy(self, safety_guard, mock_web3):
        """Test dynamic gas price with legacy."""
        mock_web3.eth.get_block.return_value = {"gasUsed": 500000, "gasLimit": 1000000}

        with patch.object(safety_guard, "get_network_congestion", return_value=0.3):
            gas_price = await safety_guard.get_dynamic_gas_price()

        assert gas_price > 20.0  # Should be adjusted for congestion

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_enforces_limits(
        self, safety_guard, mock_web3, mock_config
    ):
        """Test dynamic gas price enforces config limits."""
        mock_web3.eth.gas_price = 200000000000  # 200 gwei (above max)

        gas_price = await safety_guard.get_dynamic_gas_price()

        assert gas_price <= mock_config.max_gas_price_gwei

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_low_congestion(
        self, safety_guard, mock_config
    ):
        """Test slippage adjustment with low congestion."""
        slippage = await safety_guard.adjust_slippage_tolerance(congestion_level=0.2)

        assert slippage == mock_config.slippage_low_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_medium_congestion(
        self, safety_guard, mock_config
    ):
        """Test slippage adjustment with medium congestion."""
        slippage = await safety_guard.adjust_slippage_tolerance(congestion_level=0.5)

        assert slippage == mock_config.slippage_medium_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_high_congestion(
        self, safety_guard, mock_config
    ):
        """Test slippage adjustment with high congestion."""
        slippage = await safety_guard.adjust_slippage_tolerance(congestion_level=0.7)

        assert slippage == mock_config.slippage_high_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_extreme_congestion(
        self, safety_guard, mock_config
    ):
        """Test slippage adjustment with extreme congestion."""
        slippage = await safety_guard.adjust_slippage_tolerance(congestion_level=0.9)

        assert slippage == mock_config.slippage_extreme_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_auto_congestion(self, safety_guard):
        """Test slippage adjustment with automatic congestion detection."""
        with patch.object(safety_guard, "get_network_congestion", return_value=0.4):
            slippage = await safety_guard.adjust_slippage_tolerance()

        assert slippage > 0

    @pytest.mark.asyncio
    async def test_get_network_congestion(self, safety_guard, mock_web3):
        """Test network congestion calculation."""
        congestion = await safety_guard.get_network_congestion()

        assert 0 <= congestion <= 1
        mock_web3.eth.get_block.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_network_congestion_error(self, safety_guard, mock_web3):
        """Test network congestion calculation with error."""
        mock_web3.eth.get_block.side_effect = Exception("Block error")

        congestion = await safety_guard.get_network_congestion()

        assert congestion == 0.5  # Default fallback

    @pytest.mark.asyncio
    async def test_ensure_profit_profitable_tx(self, safety_guard, mock_config):
        """Test ensure_profit with profitable transaction."""
        tx_data = {
            "expected_profit_eth": 0.02,  # Above threshold
            "gas_cost_eth": 0.005,
        }

        result = await safety_guard.ensure_profit(tx_data)

        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_profit_unprofitable_tx(self, safety_guard, mock_config):
        """Test ensure_profit with unprofitable transaction."""
        tx_data = {
            "expected_profit_eth": 0.005,  # Below threshold
            "gas_cost_eth": 0.008,
        }

        result = await safety_guard.ensure_profit(tx_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_profit_high_loss(self, safety_guard):
        """Test ensure_profit with high loss."""
        tx_data = {
            "expected_profit_eth": -0.01,  # Loss above threshold
            "gas_cost_eth": 0.005,
        }

        result = await safety_guard.ensure_profit(tx_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_transaction_safety_success(self, safety_guard):
        """Test comprehensive transaction safety check."""
        tx_data = {
            "gas_price": 20.0,  # 20 gwei, below max
            "value": 1000000000000000,  # Small value
            "hash": "0x123456",
            "input_token": "ETH",
            "output_token": "USDC",
            "amountIn": 1.0,
            "amountOut": 2500.0,
            "gas_used": 100000,
        }

        # Mock the ensure_profit to return True
        with patch.object(safety_guard, "ensure_profit", return_value=True):
            result, details = await safety_guard.check_transaction_safety(tx_data)

        assert result is True
        assert "safety_percentage" in details
        assert details["checks_passed"] >= 3  # Should pass most checks

    @pytest.mark.asyncio
    async def test_check_transaction_safety_not_safe_to_proceed(self, safety_guard):
        """Test transaction safety check when gas price is too high."""
        tx_data = {
            "gas_price": 150.0,  # 150 gwei, above max of 100
            "value": 1000000000000000,
            "hash": "0x123456",
        }

        result, details = await safety_guard.check_transaction_safety(tx_data)

        assert result is False
        assert details["check_details"]["gas_check"]["passed"] is False

    @pytest.mark.asyncio
    async def test_check_transaction_safety_duplicate_tx(self, safety_guard):
        """Test transaction safety check with duplicate transaction."""
        tx_data = {
            "gas_price": 20.0,
            "value": 1000000000000000,
            "hash": "0x123456",
        }
        # Add the hash to recent transactions
        safety_guard.recent_txs.add("0x123456")

        result, details = await safety_guard.check_transaction_safety(tx_data)

        assert result is False
        assert details["check_details"]["duplicate_check"]["passed"] is False

    @pytest.mark.asyncio
    async def test_check_transaction_safety_validation_error(self, safety_guard):
        """Test transaction safety check with validation error."""
        tx_data = {
            "gas_price": 150.0,  # Too high (above 100 gwei max)
            "value": 1000000000000000,
            "hash": "0x123456",
        }

        result, details = await safety_guard.check_transaction_safety(tx_data)

        assert result is False
        # Should fail gas price check
        assert details["check_details"]["gas_check"]["passed"] is False

    @pytest.mark.asyncio
    async def test_estimate_gas_success(self, safety_guard, mock_web3):
        """Test gas estimation."""
        tx = {"to": "0x123456", "data": "0xabcdef"}
        mock_web3.eth.estimate_gas = AsyncMock(return_value=50000)

        gas = await safety_guard.estimate_gas(tx)

        assert gas == 55000  # 50000 * 1.1 safety margin
        mock_web3.eth.estimate_gas.assert_called_once_with({"to": "0x123456", "data": "0xabcdef", "value": 0})

    @pytest.mark.asyncio
    async def test_estimate_gas_error(self, safety_guard, mock_web3, mock_config):
        """Test gas estimation with error."""
        tx = {"to": "0x123456", "data": "0xabcdef"}
        mock_web3.eth.estimate_gas = AsyncMock(side_effect=Exception("Gas estimation failed"))

        gas = await safety_guard.estimate_gas(tx)

        assert gas == 500000  # DEFAULT_GAS_LIMIT fallback

    @pytest.mark.asyncio
    async def test_is_healthy_success(self, safety_guard, mock_web3):
        """Test health check success."""
        result = await safety_guard.is_healthy()

        assert result is True
        mock_web3.is_connected.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_healthy_circuit_broken(self, safety_guard):
        """Test health check with broken circuit."""
        safety_guard.circuit_broken = True

        result = await safety_guard.is_healthy()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_healthy_web3_error(self, safety_guard, mock_web3):
        """Test health check with web3 error."""
        mock_web3.is_connected = AsyncMock(side_effect=Exception("Connection error"))

        result = await safety_guard.is_healthy()

        assert result is False

    def test_safety_guard_attributes(self, safety_guard):
        """Test that all expected attributes are set."""
        assert hasattr(safety_guard, "web3")
        assert hasattr(safety_guard, "config")
        assert hasattr(safety_guard, "account")
        assert hasattr(safety_guard, "account_address")
        assert hasattr(safety_guard, "circuit_broken")
        assert hasattr(safety_guard, "circuit_break_reason")
        assert hasattr(safety_guard, "recent_txs")
        assert hasattr(safety_guard, "_gas_price_history")
        assert hasattr(safety_guard, "_congestion_history")

    def test_shared_components_access(self, safety_guard, mock_orchestrator):
        """Test access to shared components from orchestrator."""
        # After initialization, abi_registry should be set
        asyncio.run(safety_guard.initialize())
        assert safety_guard.abi_registry == mock_orchestrator.components["abi_registry"]

    # === Tests for missing coverage methods ===

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_legacy(self, safety_guard, mock_web3):
        """Test dynamic gas price calculation for legacy (non-EIP1559) network."""
        # Mock legacy block (no baseFeePerGas)
        mock_web3.eth.get_block = AsyncMock(return_value={"gasUsed": 500000, "gasLimit": 1000000, "transactions": []})
        
        with patch.object(safety_guard, "get_network_congestion", return_value=0.3):
            gas_price = await safety_guard.get_dynamic_gas_price()
        
        assert isinstance(gas_price, float)
        assert gas_price > 0

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_eip1559(self, safety_guard, mock_web3):
        """Test dynamic gas price calculation for EIP-1559 network."""
        # Mock EIP-1559 block with baseFeePerGas
        mock_web3.eth.get_block = AsyncMock(return_value={
            "gasUsed": 500000, 
            "gasLimit": 1000000, 
            "baseFeePerGas": 15000000000,  # 15 gwei
            "transactions": []
        })
        
        with patch.object(safety_guard, "get_network_congestion", return_value=0.5):
            gas_price = await safety_guard.get_dynamic_gas_price()
        
        assert isinstance(gas_price, float)
        assert gas_price > 0

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_oracle_success(self, safety_guard, mock_web3, mock_config):
        """Test dynamic gas price with oracle."""
        mock_config.gas_price_oracle = "0x1234567890abcdef"
        
        # Mock oracle contract
        mock_contract = MagicMock()
        mock_contract.functions.getLatestGasPrice.return_value.call = AsyncMock(return_value=25000000000)
        mock_web3.eth.contract.return_value = mock_contract
        
        gas_price = await safety_guard.get_dynamic_gas_price()
        
        assert gas_price == 25.0  # 25 gwei

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_oracle_error(self, safety_guard, mock_web3, mock_config):
        """Test dynamic gas price with oracle error fallback."""
        mock_config.gas_price_oracle = "0x1234567890abcdef"
        
        # Mock oracle contract that fails
        mock_web3.eth.contract.side_effect = Exception("Oracle error")
        
        gas_price = await safety_guard.get_dynamic_gas_price()
        
        assert isinstance(gas_price, float)
        assert gas_price > 0

    @pytest.mark.asyncio
    async def test_get_dynamic_gas_price_enforces_limits(self, safety_guard, mock_web3, mock_config):
        """Test that dynamic gas price enforces min/max limits."""
        # Set tight limits
        mock_config.min_gas_price_gwei = 50.0
        mock_config.max_gas_price_gwei = 60.0
        
        gas_price = await safety_guard.get_dynamic_gas_price()
        
        assert 50.0 <= gas_price <= 60.0

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_low_congestion(self, safety_guard, mock_config):
        """Test slippage adjustment for low congestion."""
        with patch.object(safety_guard, "get_network_congestion", return_value=0.2):
            slippage = await safety_guard.adjust_slippage_tolerance()
        
        assert slippage == mock_config.slippage_low_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_medium_congestion(self, safety_guard, mock_config):
        """Test slippage adjustment for medium congestion."""
        with patch.object(safety_guard, "get_network_congestion", return_value=0.5):
            slippage = await safety_guard.adjust_slippage_tolerance()
        
        assert slippage == mock_config.slippage_medium_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_high_congestion(self, safety_guard, mock_config):
        """Test slippage adjustment for high congestion."""
        with patch.object(safety_guard, "get_network_congestion", return_value=0.7):
            slippage = await safety_guard.adjust_slippage_tolerance()
        
        assert slippage == mock_config.slippage_high_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_extreme_congestion(self, safety_guard, mock_config):
        """Test slippage adjustment for extreme congestion."""
        with patch.object(safety_guard, "get_network_congestion", return_value=0.9):
            slippage = await safety_guard.adjust_slippage_tolerance()
        
        assert slippage == mock_config.slippage_extreme_congestion

    @pytest.mark.asyncio
    async def test_adjust_slippage_tolerance_auto_congestion(self, safety_guard, mock_config):
        """Test slippage adjustment with automatic congestion detection."""
        # Don't pass congestion_level parameter
        slippage = await safety_guard.adjust_slippage_tolerance()
        
        assert isinstance(slippage, float)
        assert mock_config.min_slippage <= slippage <= mock_config.max_slippage

    @pytest.mark.asyncio
    async def test_get_network_congestion(self, safety_guard, mock_web3):
        """Test network congestion calculation."""
        # Mock blocks for congestion calculation
        mock_web3.eth.get_block = AsyncMock(side_effect=[
            {"gasUsed": 800000, "gasLimit": 1000000, "transactions": []},  # latest
            {"gasUsed": 600000, "gasLimit": 1000000, "transactions": [1, 2, 3, 4, 5]},  # pending
        ])
        
        congestion = await safety_guard.get_network_congestion()
        
        assert isinstance(congestion, float)
        assert 0.0 <= congestion <= 1.0

    @pytest.mark.asyncio
    async def test_ensure_profit_profitable_tx(self, safety_guard, mock_external_api_manager):
        """Test ensure_profit with profitable token transaction."""
        tx_data = {
            "input_token": "ETH",
            "output_token": "USDC",
            "amountIn": 1.0,
            "amountOut": 2600.0,  # Good profit
            "gas_price": 20.0,
            "gas_used": 150000,
        }
        
        # Mock price feeds
        mock_external_api_manager.get_real_time_price = AsyncMock(side_effect=[
            1.0,      # ETH price in ETH (base)
            1.0,      # USDC price in ETH
        ])
        
        result = await safety_guard.ensure_profit(tx_data)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_profit_unprofitable_tx(self, safety_guard, mock_external_api_manager):
        """Test ensure_profit with unprofitable transaction."""
        tx_data = {
            "input_token": "ETH",
            "output_token": "USDC",
            "amountIn": 1.0,
            "amountOut": 0.5,  # Loss
            "gas_price": 20.0,
            "gas_used": 150000,
        }
        
        # Mock price feeds
        mock_external_api_manager.get_real_time_price = AsyncMock(side_effect=[
            1.0,      # ETH price in ETH
            1.0,      # USDC price in ETH
        ])
        
        result = await safety_guard.ensure_profit(tx_data)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_profit_no_api_manager(self, safety_guard):
        """Test ensure_profit without API manager."""
        safety_guard.external_api_manager = None
        
        tx_data = {"amountIn": 1.0, "amountOut": 2.0}
        
        result = await safety_guard.ensure_profit(tx_data)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_calculate_gas_cost(self, safety_guard):
        """Test gas cost calculation."""
        gas_cost = await safety_guard._calculate_gas_cost(20.0, 100000)  # 20 gwei, 100k gas
        
        assert isinstance(gas_cost, float)
        assert gas_cost > 0

    @pytest.mark.asyncio
    async def test_calculate_profit(self, safety_guard):
        """Test profit calculation with safety margin."""
        profit = await safety_guard._calculate_profit(1.0, 1.5, 0.1)  # amountIn, amountOut, gas_cost
        
        assert isinstance(profit, float)
        # Should be (1.5 - 1.0 - 0.1) * 0.95 = 0.38
        assert profit > 0

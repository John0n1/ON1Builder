#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for StrategyExecutor class.
"""

import pytest
import json
import tempfile
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from on1builder.config.settings import GlobalSettings
from on1builder.engines.strategy_executor import StrategyExecutor, StrategyPerformanceMetrics, StrategyGlobalSettings


@pytest.fixture
def mock_global_settings():
    """Create a mock GlobalSettings object."""
    settings = MagicMock(spec=GlobalSettings)
    settings.strategy_decay_factor = 0.95
    settings.strategy_learning_rate = 0.01
    settings.strategy_exploration_rate = 0.1
    settings.strategy_min_weight = 0.1
    settings.strategy_max_weight = 10.0
    settings.strategy_market_weight = 0.3
    settings.strategy_gas_weight = 0.2
    settings.strategy_save_interval = 100
    return settings


@pytest.fixture
def mock_web3():
    """Create a mock AsyncWeb3 instance."""
    web3 = MagicMock()
    web3.eth.get_block = AsyncMock(return_value={"number": 12345})
    return web3


@pytest.fixture
def mock_transaction_manager():
    """Create a mock TransactionManager instance."""
    txm = MagicMock()
    txm.handle_eth_transaction = AsyncMock(return_value=True)
    txm.front_run = AsyncMock(return_value=True)
    txm.back_run = AsyncMock(return_value=True)
    txm.execute_sandwich_attack = AsyncMock(return_value=True)
    txm.current_profit = 100.0
    return txm


@pytest.fixture
def mock_market_data_feed():
    """Create a mock MarketDataFeed instance."""
    feed = MagicMock()
    feed.get_token_price = AsyncMock(return_value=Decimal("100.0"))
    return feed


@pytest.fixture
def mock_safety_guard():
    """Create a mock SafetyGuard instance."""
    guard = MagicMock()
    guard.check_safety = AsyncMock(return_value=True)
    return guard


class TestStrategyPerformanceMetrics:
    """Test cases for StrategyPerformanceMetrics."""

    def test_init(self):
        """Test StrategyPerformanceMetrics initialization."""
        metrics = StrategyPerformanceMetrics()
        
        assert metrics.successes == 0
        assert metrics.failures == 0
        assert metrics.profit == Decimal("0")
        assert metrics.total_executions == 0
        assert metrics.avg_execution_time == 0.0

    def test_success_rate_zero_executions(self):
        """Test success rate calculation with zero executions."""
        metrics = StrategyPerformanceMetrics()
        assert metrics.success_rate == 0.0

    def test_success_rate_with_executions(self):
        """Test success rate calculation with executions."""
        metrics = StrategyPerformanceMetrics()
        metrics.successes = 7
        metrics.failures = 3
        metrics.total_executions = 10
        
        assert metrics.success_rate == 0.7


class TestStrategyGlobalSettings:
    """Test cases for StrategyGlobalSettings."""

    def test_init(self, mock_global_settings):
        """Test StrategyGlobalSettings initialization."""
        settings = StrategyGlobalSettings(mock_global_settings)
        
        assert settings.decay_factor == 0.95
        assert settings.base_learning_rate == 0.01
        assert settings.exploration_rate == 0.1
        assert settings.min_weight == 0.1
        assert settings.max_weight == 10.0
        assert settings.market_weight == 0.3
        assert settings.gas_weight == 0.2


class TestStrategyExecutor:
    """Test cases for StrategyExecutor."""

    @patch('on1builder.engines.strategy_executor.get_resource_path')
    def test_init(self, mock_get_resource_path, mock_global_settings, mock_web3, 
                  mock_transaction_manager, mock_safety_guard, mock_market_data_feed):
        """Test StrategyExecutor initialization."""
        # Mock the resource path
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file
        
        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed
        )
        
        assert executor.web3 == mock_web3
        assert executor.cfg == mock_global_settings
        assert executor.txc == mock_transaction_manager
        assert executor.safety_net == mock_safety_guard
        assert executor.market_monitor == mock_market_data_feed
        assert isinstance(executor.metrics, dict)
        assert isinstance(executor.weights, dict)
        assert isinstance(executor.learning_cfg, StrategyGlobalSettings)

    @patch('on1builder.engines.strategy_executor.get_resource_path')
    def test_get_strategies(self, mock_get_resource_path, mock_global_settings, mock_web3,
                           mock_transaction_manager, mock_safety_guard, mock_market_data_feed):
        """Test get_strategies method."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file
        
        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed
        )
        
        eth_strategies = executor.get_strategies("eth_transaction")
        assert len(eth_strategies) == 1
        assert eth_strategies[0] == mock_transaction_manager.handle_eth_transaction
        
        front_run_strategies = executor.get_strategies("front_run")
        assert len(front_run_strategies) == 1
        assert front_run_strategies[0] == mock_transaction_manager.front_run
        
        # Test non-existent strategy type
        empty_strategies = executor.get_strategies("non_existent")
        assert empty_strategies == []

    @patch('on1builder.engines.strategy_executor.get_resource_path')
    @pytest.mark.asyncio
    async def test_execute_best_strategy_success(self, mock_get_resource_path, mock_global_settings,
                                               mock_web3, mock_transaction_manager, mock_safety_guard,
                                               mock_market_data_feed):
        """Test successful strategy execution."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file
        
        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed
        )
        
        target_tx = {"hash": "0x123", "value": 1000}
        
        with patch.object(executor, '_select_strategy', return_value=mock_transaction_manager.handle_eth_transaction):
            with patch.object(executor, '_update_after_run') as mock_update:
                result = await executor.execute_best_strategy(target_tx, "eth_transaction")
                
                assert result is True
                mock_transaction_manager.handle_eth_transaction.assert_called_once_with(target_tx)
                mock_update.assert_called_once()

    @patch('on1builder.engines.strategy_executor.get_resource_path')
    @pytest.mark.asyncio
    async def test_execute_best_strategy_no_strategies(self, mock_get_resource_path, mock_global_settings,
                                                     mock_web3, mock_transaction_manager, mock_safety_guard,
                                                     mock_market_data_feed):
        """Test strategy execution with no available strategies."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file
        
        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed
        )
        
        target_tx = {"hash": "0x123", "value": 1000}
        result = await executor.execute_best_strategy(target_tx, "non_existent_strategy")
        
        assert result is False

    @patch('on1builder.engines.strategy_executor.get_resource_path')
    @pytest.mark.asyncio
    async def test_initialize(self, mock_get_resource_path, mock_global_settings,
                             mock_web3, mock_transaction_manager, mock_safety_guard,
                             mock_market_data_feed):
        """Test executor initialization."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file
        
        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed
        )
        
        # Test initialize method
        await executor.initialize()
        # Should complete without error

    @patch('on1builder.engines.strategy_executor.get_resource_path')
    @pytest.mark.asyncio
    async def test_stop(self, mock_get_resource_path, mock_global_settings,
                       mock_web3, mock_transaction_manager, mock_safety_guard,
                       mock_market_data_feed):
        """Test executor shutdown."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file
        
        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed
        )
        
        # Test stop method
        await executor.stop()
        # Should save weights and complete without error
        mock_weight_file.write_text.assert_called_once()

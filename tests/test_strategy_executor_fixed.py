#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for StrategyExecutor class.
"""

import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from on1builder.config.settings import GlobalSettings
from on1builder.engines.strategy_executor import (
    StrategyExecutor,
    StrategyGlobalSettings,
    StrategyPerformanceMetrics,
)


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

    @patch("on1builder.utils.path_helpers.get_resource_path")
    def test_init(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
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
            market_monitor=mock_market_data_feed,
        )

        assert executor.web3 == mock_web3
        assert executor.cfg == mock_global_settings
        assert executor.txc == mock_transaction_manager
        assert executor.safety_net == mock_safety_guard
        assert executor.market_monitor == mock_market_data_feed
        assert isinstance(executor.metrics, dict)
        assert isinstance(executor.weights, dict)
        assert isinstance(executor.learning_cfg, StrategyGlobalSettings)

    @patch("on1builder.utils.path_helpers.get_resource_path")
    def test_get_strategies(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test get_strategies method."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
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

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_execute_best_strategy_success(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test successful strategy execution."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        target_tx = {"hash": "0x123", "value": 1000}

        with patch.object(
            executor,
            "_select_strategy",
            return_value=mock_transaction_manager.handle_eth_transaction,
        ):
            with patch.object(executor, "_update_after_run") as mock_update:
                result = await executor.execute_best_strategy(
                    target_tx, "eth_transaction"
                )

                assert result is True
                mock_transaction_manager.handle_eth_transaction.assert_called_once_with(
                    target_tx
                )
                mock_update.assert_called_once()

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_execute_best_strategy_no_strategies(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test strategy execution with no available strategies."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        target_tx = {"hash": "0x123", "value": 1000}
        result = await executor.execute_best_strategy(
            target_tx, "non_existent_strategy"
        )

        assert result is False

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_initialize(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test executor initialization."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        # Test initialize method
        await executor.initialize()
        # Should complete without error

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_stop(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test executor shutdown."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        # Test stop method
        await executor.stop()
        # Should save weights and complete without error
        mock_weight_file.write_text.assert_called_once()

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_load_weights_with_existing_file(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test loading weights from existing file."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = True
        mock_weight_file.read_text.return_value = json.dumps(
            {"eth_transaction": [1.5, 2.0], "front_run": [0.8, 1.2]}
        )
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        # Check that weights were loaded correctly
        assert executor.weights["eth_transaction"][0] == 1.5
        assert executor.weights["front_run"][0] == 0.8

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_load_weights_invalid_json(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test loading weights with invalid JSON file."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = True
        mock_weight_file.read_text.return_value = "invalid json"
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )
        # Should handle error gracefully and use default weights

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_select_strategy_exploration(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test strategy selection with exploration."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        strategies = [mock_transaction_manager.handle_eth_transaction]

        with patch("random.random", return_value=0.05):  # Trigger exploration
            selected = await executor._select_strategy(strategies, "eth_transaction")
            assert selected == mock_transaction_manager.handle_eth_transaction

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_select_strategy_exploitation(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test strategy selection with exploitation."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        strategies = [mock_transaction_manager.handle_eth_transaction]

        # Mock gas price
        mock_web3.eth.gas_price = 50000000000  # 50 gwei

        with patch("random.random", return_value=0.5):  # Trigger exploitation
            selected = await executor._select_strategy(strategies, "eth_transaction")
            assert selected == mock_transaction_manager.handle_eth_transaction

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_update_after_run_success(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test updating metrics after successful run."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        await executor._update_after_run(
            "eth_transaction", "handle_eth_transaction", True, Decimal("10.5"), 1.2
        )

        metrics = executor.metrics["eth_transaction"]
        assert metrics.total_executions == 1
        assert metrics.successes == 1
        assert metrics.failures == 0
        assert metrics.profit == Decimal("10.5")

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_update_after_run_failure(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test updating metrics after failed run."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        await executor._update_after_run(
            "eth_transaction", "handle_eth_transaction", False, Decimal("0"), 2.5
        )

        metrics = executor.metrics["eth_transaction"]
        assert metrics.total_executions == 1
        assert metrics.successes == 0
        assert metrics.failures == 1
        assert metrics.profit == Decimal("0")

    @patch("on1builder.utils.path_helpers.get_resource_path")
    def test_calc_reward_success_with_profit(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test reward calculation for successful run with profit."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        reward = executor._calc_reward(True, Decimal("5.0"), 1.0)
        assert reward > 0  # Should be positive for successful profitable run

    @patch("on1builder.utils.path_helpers.get_resource_path")
    def test_calc_reward_failure(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test reward calculation for failed run."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        reward = executor._calc_reward(False, Decimal("0"), 1.0)
        assert reward < 0  # Should be negative for failed run

    @patch("on1builder.utils.path_helpers.get_resource_path")
    def test_strategy_index(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test finding strategy index by name."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        idx = executor._strategy_index("eth_transaction", "handle_eth_transaction")
        assert idx == 0  # Should find the first strategy

        idx = executor._strategy_index("eth_transaction", "nonexistent")
        assert idx == -1  # Should return -1 for non-existent strategy

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_is_healthy_success(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test health check with healthy executor."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        is_healthy = await executor.is_healthy()
        assert is_healthy is True

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_is_healthy_missing_dependencies(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test health check with missing dependencies."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=None,  # Missing transaction manager
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        is_healthy = await executor.is_healthy()
        assert is_healthy is False

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_get_market_condition_adjustment(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test market condition adjustment calculation."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        adjustment = await executor._get_market_condition_adjustment("eth_transaction")
        assert isinstance(adjustment, float)
        assert -1.0 <= adjustment <= 1.0

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_get_gas_condition_adjustment(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test gas condition adjustment calculation."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        # Mock gas price
        mock_web3.eth.gas_price = 50000000000  # 50 gwei

        adjustment = await executor._get_gas_condition_adjustment("front_run")
        assert isinstance(adjustment, float)

    @patch("on1builder.utils.path_helpers.get_resource_path")
    def test_get_strategy_performance(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test getting strategy performance metrics."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        performance = executor.get_strategy_performance()
        assert isinstance(performance, dict)
        assert "eth_transaction" in performance
        assert "front_run" in performance

    @patch("on1builder.utils.path_helpers.get_resource_path")
    @pytest.mark.asyncio
    async def test_reset_learning_state(
        self,
        mock_get_resource_path,
        mock_global_settings,
        mock_web3,
        mock_transaction_manager,
        mock_safety_guard,
        mock_market_data_feed,
    ):
        """Test resetting learning state."""
        mock_weight_file = MagicMock()
        mock_weight_file.exists.return_value = False
        mock_get_resource_path.return_value = mock_weight_file

        executor = StrategyExecutor(
            web3=mock_web3,
            config=mock_global_settings,
            transaction_core=mock_transaction_manager,
            safety_net=mock_safety_guard,
            market_monitor=mock_market_data_feed,
        )

        # Modify some metrics first
        executor.metrics["eth_transaction"].successes = 5
        executor.metrics["eth_transaction"].total_executions = 10

        await executor.reset_learning_state()

        # Check that metrics were reset
        assert executor.metrics["eth_transaction"].successes == 0
        assert executor.metrics["eth_transaction"].total_executions == 0
        assert executor._update_counter == 0

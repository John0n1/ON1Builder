#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for MultiChainOrchestrator"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add the src directory to the path for imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from on1builder.config.settings import MultiChainSettings
from on1builder.core.multi_chain_orchestrator import MultiChainOrchestrator


class TestMultiChainOrchestrator:
    """Test cases for MultiChainOrchestrator class."""

    @pytest.fixture
    def mock_chain_config(self):
        """Mock chain configuration."""
        return {
            "CHAIN_ID": 1,
            "RPC_URL": "https://mainnet.infura.io/v3/test",
            "WALLET_ADDRESS": "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6",
            "PRIVATE_KEY": "test_private_key",
        }

    @pytest.fixture
    def mock_config(self, mock_chain_config):
        """Mock MultiChainSettings configuration."""
        config = MagicMock(spec=MultiChainSettings)
        config.DRY_RUN = True
        config.GO_LIVE = False
        config.HEALTH_CHECK_INTERVAL = 10.0
        config.chains = [mock_chain_config]
        
        # Mock the load method
        config.load = AsyncMock(return_value=None)
        
        return config

    @pytest.fixture
    def orchestrator(self, mock_config):
        """Create MultiChainOrchestrator instance."""
        return MultiChainOrchestrator(mock_config)

    def test_init(self, orchestrator, mock_config):
        """Test MultiChainOrchestrator initialization."""
        assert orchestrator.config == mock_config
        assert orchestrator.workers == {}
        assert isinstance(orchestrator._tasks, set)
        assert orchestrator.dry_run is True
        assert orchestrator.go_live is False
        assert orchestrator.health_check_interval == 10.0
        
        # Check metrics initialization
        assert "total_chains" in orchestrator.metrics
        assert "active_chains" in orchestrator.metrics
        assert "total_transactions" in orchestrator.metrics
        assert orchestrator.metrics["total_chains"] == 0
        assert orchestrator.metrics["active_chains"] == 0

    def test_init_with_defaults(self, mock_config):
        """Test initialization with default values."""
        # Remove optional attributes
        delattr(mock_config, "DRY_RUN")
        delattr(mock_config, "GO_LIVE")
        delattr(mock_config, "HEALTH_CHECK_INTERVAL")
        
        orchestrator = MultiChainOrchestrator(mock_config)
        
        assert orchestrator.dry_run is True  # Default
        assert orchestrator.go_live is False  # Default
        assert orchestrator.health_check_interval == 60.0  # Default

    @pytest.mark.asyncio
    async def test_initialize_no_chains(self, orchestrator, mock_config):
        """Test initialization with no chains configured."""
        mock_config.chains = []
        
        result = await orchestrator.initialize()
        
        assert result is False
        assert orchestrator.metrics["total_chains"] == 0

    @pytest.mark.asyncio
    async def test_initialize_success(self, orchestrator, mock_config):
        """Test successful initialization with chains."""
        with patch.object(orchestrator, '_init_chain_worker', new_callable=AsyncMock) as mock_init:
            mock_init.return_value = True
            
            result = await orchestrator.initialize()
            
            assert result is True
            assert orchestrator.metrics["total_chains"] == 1
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_partial_failure(self, orchestrator, mock_config):
        """Test initialization with some chains failing."""
        mock_config.chains = [
            {"CHAIN_ID": 1, "RPC_URL": "url1"},
            {"CHAIN_ID": 2, "RPC_URL": "url2"}
        ]
        
        with patch.object(orchestrator, '_init_chain_worker', new_callable=AsyncMock) as mock_init:
            mock_init.side_effect = [True, False]  # First succeeds, second fails
            
            result = await orchestrator.initialize()
            
            assert result is True  # At least one succeeded
            assert orchestrator.metrics["total_chains"] == 2
            assert orchestrator.metrics["initialization_failures"] == 1

    @pytest.mark.asyncio
    async def test_initialize_all_failures(self, orchestrator, mock_config):
        """Test initialization with all chains failing."""
        with patch.object(orchestrator, '_init_chain_worker', new_callable=AsyncMock) as mock_init:
            mock_init.return_value = False
            
            result = await orchestrator.initialize()
            
            assert result is False
            assert orchestrator.metrics["initialization_failures"] == 1

    @pytest.mark.asyncio
    async def test_init_chain_worker_success(self, orchestrator, mock_config, mock_chain_config):
        """Test successful chain worker initialization."""
        with patch('src.on1builder.core.multi_chain_orchestrator.ChainWorker') as mock_worker_class:
            mock_worker = AsyncMock()
            mock_worker.initialize.return_value = True
            mock_worker_class.return_value = mock_worker
            
            result = await orchestrator._init_chain_worker("1", mock_chain_config)
            
            assert result is True
            assert "1" in orchestrator.workers
            mock_worker.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_chain_worker_failure(self, orchestrator, mock_config, mock_chain_config):
        """Test chain worker initialization failure."""
        with patch('src.on1builder.core.multi_chain_orchestrator.ChainWorker') as mock_worker_class:
            mock_worker = AsyncMock()
            mock_worker.initialize.return_value = False
            mock_worker_class.return_value = mock_worker
            
            result = await orchestrator._init_chain_worker("1", mock_chain_config)
            
            assert result is False
            assert "1" not in orchestrator.workers

    @pytest.mark.asyncio
    async def test_init_chain_worker_exception(self, orchestrator, mock_config, mock_chain_config):
        """Test chain worker initialization with exception."""
        with patch('src.on1builder.core.multi_chain_orchestrator.ChainWorker') as mock_worker_class:
            mock_worker_class.side_effect = Exception("Test error")
            
            result = await orchestrator._init_chain_worker("1", mock_chain_config)
            
            assert result is False
            assert "1" not in orchestrator.workers

    @pytest.mark.asyncio
    async def test_run_no_workers(self, orchestrator):
        """Test run with no workers."""
        await orchestrator.run()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_run_with_workers(self, orchestrator):
        """Test run with workers."""
        mock_worker = AsyncMock()
        mock_worker.start.return_value = None
        orchestrator.workers["1"] = mock_worker
        
        # Simulate shutdown immediately
        async def shutdown_soon():
            await asyncio.sleep(0.1)
            orchestrator._shutdown_event.set()
        
        shutdown_task = asyncio.create_task(shutdown_soon())
        
        await orchestrator.run()
        await shutdown_task
        
        mock_worker.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self, orchestrator):
        """Test stop functionality."""
        mock_worker = AsyncMock()
        orchestrator.workers["1"] = mock_worker
        
        # Add a mock health check task
        mock_task = AsyncMock()
        mock_task.done.return_value = False
        orchestrator._health_check_task = mock_task
        
        await orchestrator.stop()
        
        assert orchestrator._shutdown_event.is_set()
        mock_worker.stop.assert_called_once()
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_periodic_health_check(self, orchestrator):
        """Test periodic health check functionality."""
        mock_worker = AsyncMock()
        mock_worker.is_healthy.return_value = False
        orchestrator.workers["1"] = mock_worker
        
        # Start health check and then stop it quickly
        task = asyncio.create_task(orchestrator._periodic_health_check())
        await asyncio.sleep(0.1)
        orchestrator._shutdown_event.set()
        
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()
        
        mock_worker.is_healthy.assert_called()
        mock_worker.reconnect.assert_called()

    @pytest.mark.asyncio
    async def test_update_metrics(self, orchestrator):
        """Test metrics update functionality."""
        mock_worker = AsyncMock()
        mock_worker.get_metrics.return_value = {
            "transactions": 10,
            "profit_eth": 0.5,
            "gas_spent_eth": 0.1
        }
        mock_worker.is_healthy.return_value = True
        orchestrator.workers["1"] = mock_worker
        
        # Start metrics update and then stop it quickly
        task = asyncio.create_task(orchestrator._update_metrics())
        await asyncio.sleep(0.1)
        orchestrator._shutdown_event.set()
        
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()
        
        # Check that metrics were updated
        assert orchestrator.metrics["total_transactions"] == 10
        assert orchestrator.metrics["total_profit_eth"] == 0.5
        assert orchestrator.metrics["total_gas_spent_eth"] == 0.1
        assert orchestrator.metrics["active_chains"] == 1

    def test_get_metrics(self, orchestrator):
        """Test get_metrics returns a copy."""
        original_metrics = orchestrator.metrics
        metrics_copy = orchestrator.get_metrics()
        
        assert metrics_copy == original_metrics
        assert metrics_copy is not original_metrics  # Should be a copy

    @pytest.mark.asyncio
    async def test_start_alias(self, orchestrator):
        """Test start method as alias for run."""
        with patch.object(orchestrator, 'run', new_callable=AsyncMock) as mock_run:
            await orchestrator.start()
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_alias(self, orchestrator):
        """Test shutdown method as alias for stop."""
        with patch.object(orchestrator, 'stop', new_callable=AsyncMock) as mock_stop:
            await orchestrator.shutdown()
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_exception_handling(self, orchestrator):
        """Test health check handles exceptions gracefully."""
        mock_worker = AsyncMock()
        mock_worker.is_healthy.side_effect = Exception("Test error")
        orchestrator.workers["1"] = mock_worker
        
        # Mock sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            task = asyncio.create_task(orchestrator._periodic_health_check())
            await asyncio.sleep(0.01)  # Let it run once
            orchestrator._shutdown_event.set()
            
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()

    @pytest.mark.asyncio
    async def test_metrics_update_exception_handling(self, orchestrator):
        """Test metrics update handles exceptions gracefully."""
        mock_worker = AsyncMock()
        mock_worker.get_metrics.side_effect = Exception("Test error")
        orchestrator.workers["1"] = mock_worker
        
        # Mock sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            task = asyncio.create_task(orchestrator._update_metrics())
            await asyncio.sleep(0.01)  # Let it run once
            orchestrator._shutdown_event.set()
            
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()

    def test_metrics_structure(self, orchestrator):
        """Test that metrics have expected structure."""
        metrics = orchestrator.get_metrics()
        
        expected_keys = {
            "total_chains", "active_chains", "total_transactions",
            "total_profit_eth", "total_gas_spent_eth", "start_time",
            "uptime_seconds", "errors", "initialization_failures"
        }
        
        assert set(metrics.keys()) >= expected_keys
        assert isinstance(metrics["errors"], dict)
        assert isinstance(metrics["initialization_failures"], int)

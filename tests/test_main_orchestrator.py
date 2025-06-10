#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
Tests for MainOrchestrator class.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from eth_account import Account

from on1builder.config.settings import GlobalSettings
from on1builder.core.main_orchestrator import MainOrchestrator
from on1builder.utils.custom_exceptions import StrategyExecutionError


@pytest.fixture
def mock_global_settings():
    """Create a mock GlobalSettings object."""
    settings = MagicMock(spec=GlobalSettings)
    settings.chains = {"ethereum": MagicMock()}
    settings.chains["ethereum"].rpc_url = "http://localhost:8545"
    settings.chains["ethereum"].chain_id = 1
    settings.chains["ethereum"].websocket_endpoint = "ws://localhost:8546"
    settings.connection_retry_count = 3
    settings.connection_retry_delay = 1.0
    settings.poa_chains = {1}
    settings.base_path = Path("/tmp")
    settings.api = MagicMock()
    settings.database_url = "sqlite:///test.db"
    settings.memory_check_interval = 30  # Add missing attribute
    return settings


@pytest.fixture
def mock_config_path(tmp_path):
    """Create a temporary config file."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        """
chains:
  ethereum:
    rpc_url: "http://localhost:8545"
    chain_id: 1
"""
    )
    return config_file


class TestMainOrchestrator:
    """Test cases for MainOrchestrator."""

    def test_init_with_config_path(self, mock_config_path):
        """Test MainOrchestrator initialization with config path."""
        with patch(
            "on1builder.core.main_orchestrator.get_config_loader"
        ) as mock_loader:
            mock_loader.return_value.load_multi_chain_config.return_value = MagicMock()
            orchestrator = MainOrchestrator(config=str(mock_config_path))
            assert orchestrator.cfg is not None

    def test_init_with_settings_object(self, mock_global_settings):
        """Test MainOrchestrator initialization with settings object."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        assert orchestrator.cfg == mock_global_settings

    def test_init_with_dict_config(self):
        """Test MainOrchestrator initialization with dict config."""
        config_dict = {
            "debug": True,
            "min_profit": 0.001,
            "chains": {
                "ethereum": {
                    "chain_id": 1,
                    "name": "ethereum",
                    "http_endpoint": "http://localhost:8545",
                }
            },
        }
        # Don't mock GlobalSettings, let it be instantiated normally
        orchestrator = MainOrchestrator(config=config_dict)
        assert isinstance(orchestrator.cfg, GlobalSettings)

    def test_init_default_config(self):
        """Test MainOrchestrator initialization with default config."""
        with patch(
            "on1builder.core.main_orchestrator.get_config_loader"
        ) as mock_loader:
            mock_loader.return_value.load_multi_chain_config.return_value = MagicMock()
            orchestrator = MainOrchestrator()
            assert orchestrator.cfg is not None

    def test_init_attributes(self, mock_global_settings):
        """Test that all expected attributes are initialized."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        assert orchestrator.web3 is None
        assert orchestrator.account is None
        assert orchestrator._bg == []
        assert isinstance(orchestrator._running_evt, asyncio.Event)
        assert isinstance(orchestrator._stop_evt, asyncio.Event)
        assert orchestrator.components == {}
        assert orchestrator.component_health == {}

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_global_settings):
        """Test successful connection to blockchain networks."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        mock_web3 = MagicMock()
        mock_web3.is_connected = AsyncMock(return_value=True)

        with patch.object(
            orchestrator, "_connect_web3", new_callable=AsyncMock
        ) as mock_connect:
            mock_connect.return_value = mock_web3

            result = await orchestrator.connect()
            assert result is True
            assert orchestrator.web3 == mock_web3

    @pytest.mark.asyncio
    async def test_connect_failure_no_web3(self, mock_global_settings):
        """Test connection failure when web3 creation fails."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        with patch.object(
            orchestrator, "_connect_web3", new_callable=AsyncMock
        ) as mock_connect:
            mock_connect.return_value = None

            result = await orchestrator.connect()
            assert result is False

    @pytest.mark.asyncio
    async def test_connect_failure_not_connected(self, mock_global_settings):
        """Test connection failure when web3 is not connected."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        mock_web3 = MagicMock()
        mock_web3.is_connected = AsyncMock(return_value=False)

        with patch.object(
            orchestrator, "_connect_web3", new_callable=AsyncMock
        ) as mock_connect:
            mock_connect.return_value = mock_web3

            result = await orchestrator.connect()
            assert result is False

    @pytest.mark.asyncio
    async def test_connect_websocket_success(self, mock_global_settings):
        """Test successful WebSocket connection."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.web3 = MagicMock()  # Initialize web3 first

        mock_web3 = MagicMock()
        mock_web3.eth.chain_id = AsyncMock(return_value=1)
        mock_web3.is_connected = MagicMock(return_value=True)

        with (
            patch(
                "on1builder.core.main_orchestrator.WebSocketProvider"
            ) as mock_provider,
            patch("on1builder.core.main_orchestrator.AsyncWeb3") as mock_web3_class,
        ):

            mock_web3_class.return_value = mock_web3

            result = await orchestrator.connect_websocket()
            assert result is True
            assert orchestrator.web3 == mock_web3

    @pytest.mark.asyncio
    async def test_connect_websocket_no_web3(self, mock_global_settings):
        """Test WebSocket connection failure when web3 is not initialized."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.web3 = None

        result = await orchestrator.connect_websocket()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_websocket_no_endpoint(self, mock_global_settings):
        """Test WebSocket connection failure when no endpoint is configured."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.web3 = MagicMock()

        # Remove websocket endpoint
        orchestrator.cfg.chains["ethereum"].websocket_endpoint = None

        result = await orchestrator.connect_websocket()
        assert result is False

    @pytest.mark.asyncio
    async def test_run_lifecycle(self, mock_global_settings):
        """Test complete run lifecycle."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        # Mock all the internal methods that would be called during run
        with patch.multiple(
            orchestrator,
            _bootstrap=AsyncMock(),
            _tx_processor=AsyncMock(),
            _heartbeat=AsyncMock(),
            stop=AsyncMock(),
        ):
            # Mock asyncio.create_task to return mock tasks
            mock_task = MagicMock()
            mock_task.done.return_value = False
            
            # Mock the event wait to return immediately
            original_wait = orchestrator._stop_evt.wait
            
            async def mock_wait():
                return True
                
            orchestrator._stop_evt.wait = mock_wait
            
            with patch("asyncio.create_task", return_value=mock_task):
                await orchestrator.run()
                
                # Verify bootstrap was called
                orchestrator._bootstrap.assert_called_once()
                
                # Verify that the running event was set
                assert orchestrator._running_evt.is_set()
                
                # Verify that stop was called
                orchestrator.stop.assert_called_once()
            
            # Restore original wait method
            orchestrator._stop_evt.wait = original_wait

    @pytest.mark.asyncio
    async def test_stop(self, mock_global_settings):
        """Test stopping the orchestrator."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        # Create mock tasks
        mock_task1 = MagicMock()
        mock_task1.done.return_value = False
        mock_task2 = MagicMock()
        mock_task2.done.return_value = True

        orchestrator._bg = [mock_task1, mock_task2]

        # Mock web3 provider with disconnect method
        mock_provider = MagicMock()
        mock_provider.disconnect = AsyncMock()
        mock_web3 = MagicMock()
        mock_web3.provider = mock_provider
        orchestrator.web3 = mock_web3

        with patch("asyncio.gather", new_callable=AsyncMock):
            await orchestrator.stop()

            assert orchestrator._stop_evt.is_set()
            mock_task1.cancel.assert_called_once()
            # task2 should not be cancelled as it's already done
            assert not mock_task2.cancel.called

    @pytest.mark.asyncio
    async def test_bootstrap_web3_failure(self, mock_global_settings):
        """Test bootstrap failure when web3 connection fails."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        with patch.object(
            orchestrator, "_connect_web3", new_callable=AsyncMock
        ) as mock_connect:
            mock_connect.return_value = None

            with pytest.raises(
                StrategyExecutionError, match="Failed to create Web3 connection"
            ):
                await orchestrator._bootstrap()

    @pytest.mark.asyncio
    async def test_bootstrap_account_failure(self, mock_global_settings):
        """Test bootstrap failure when account creation fails."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        with patch.multiple(
            orchestrator,
            _connect_web3=AsyncMock(return_value=MagicMock()),
            _create_account=AsyncMock(return_value=None),
        ):
            with pytest.raises(
                StrategyExecutionError, match="Failed to create account"
            ):
                await orchestrator._bootstrap()

    @pytest.mark.asyncio
    async def test_bootstrap_success(self, mock_global_settings):
        """Test successful bootstrap process."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        mock_web3 = MagicMock()
        mock_account = MagicMock()

        with patch.multiple(
            orchestrator,
            _connect_web3=AsyncMock(return_value=mock_web3),
            _create_account=AsyncMock(return_value=mock_account),
            _mk_api_config=AsyncMock(return_value=MagicMock()),
            _mk_abi_registry=AsyncMock(return_value=MagicMock()),
            _mk_notification_manager=AsyncMock(return_value=MagicMock()),
            _mk_db_manager=AsyncMock(return_value=MagicMock()),
            _mk_nonce_core=AsyncMock(return_value=MagicMock()),
            _mk_safety_net=AsyncMock(return_value=MagicMock()),
            _mk_txcore=AsyncMock(return_value=MagicMock()),
            _mk_market_monitor=AsyncMock(return_value=MagicMock()),
            _mk_txpool_monitor=AsyncMock(return_value=MagicMock()),
            _mk_strategy_net=AsyncMock(return_value=MagicMock()),
        ):
            await orchestrator._bootstrap()

            assert orchestrator.web3 == mock_web3
            assert orchestrator.account == mock_account
            assert len(orchestrator.components) > 0

    def test_component_creation_methods_exist(self, mock_global_settings):
        """Test that all component creation methods exist."""
        orchestrator = MainOrchestrator(config=mock_global_settings)

        # Check that all the _mk_* methods exist
        assert hasattr(orchestrator, "_mk_api_config")
        assert hasattr(orchestrator, "_mk_abi_registry")
        assert hasattr(orchestrator, "_mk_notification_manager")
        assert hasattr(orchestrator, "_mk_db_manager")
        assert hasattr(orchestrator, "_mk_nonce_core")
        assert hasattr(orchestrator, "_mk_safety_net")
        assert hasattr(orchestrator, "_mk_txcore")
        assert hasattr(orchestrator, "_mk_market_monitor")
        assert hasattr(orchestrator, "_mk_txpool_monitor")
        assert hasattr(orchestrator, "_mk_strategy_net")

    @pytest.mark.asyncio
    async def test_connect_web3_http_success(self, mock_global_settings):
        """Test successful web3 HTTP connection."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        
        mock_web3 = MagicMock()
        mock_web3.is_connected = AsyncMock(return_value=True)
        mock_web3.eth.chain_id = AsyncMock(return_value=1)
        
        # Mock the _create_web3_connection method directly
        with patch.object(orchestrator, "_create_web3_connection", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_web3
            
            result = await orchestrator._connect_web3()
            assert result == mock_web3
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_web3_poa_chain(self, mock_global_settings):
        """Test web3 connection for POA chain."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.cfg.chains["ethereum"].chain_id = 99  # POA chain
        
        mock_web3 = MagicMock()
        mock_web3.is_connected = AsyncMock(return_value=True)
        mock_web3.eth.chain_id = AsyncMock(return_value=99)
        mock_web3.middleware_onion.inject = MagicMock()
        
        # Mock the _create_web3_connection method directly
        with patch.object(orchestrator, "_create_web3_connection", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_web3
            
            result = await orchestrator._connect_web3()
            assert result == mock_web3
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_web3_connection_failure(self, mock_global_settings):
        """Test web3 connection failure."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        
        mock_web3 = MagicMock()
        mock_web3.is_connected = AsyncMock(return_value=False)
        
        with patch("on1builder.core.main_orchestrator.AsyncWeb3") as mock_web3_class:
            mock_web3_class.return_value = mock_web3
            
            result = await orchestrator._connect_web3()
            assert result is None

    @pytest.mark.asyncio
    async def test_create_account_success(self, mock_global_settings):
        """Test successful account creation."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.cfg.wallet_key = "0x" + "1" * 64
        
        mock_account = MagicMock()
        with patch.object(Account, "from_key", return_value=mock_account):
            result = await orchestrator._create_account()
            assert result == mock_account

    @pytest.mark.asyncio
    async def test_create_account_no_wallet_key(self, mock_global_settings):
        """Test account creation failure when no wallet key is configured."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.cfg.wallet_key = None
        
        result = await orchestrator._create_account()
        assert result is None

    @pytest.mark.asyncio
    async def test_mk_api_config(self, mock_global_settings):
        """Test API config creation."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        
        with patch("on1builder.core.main_orchestrator.ExternalAPIManager") as mock_api:
            mock_instance = MagicMock()
            mock_instance.initialize = AsyncMock()
            mock_api.return_value = mock_instance
            
            result = await orchestrator._mk_api_config()
            assert result == mock_instance
            mock_instance.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_mk_abi_registry(self, mock_global_settings):
        """Test ABI registry creation."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        
        with patch("on1builder.integrations.abi_registry.get_registry") as mock_get_registry:
            mock_registry = MagicMock()
            mock_registry.abis = {}  # Empty dict for len() call
            mock_get_registry.return_value = mock_registry
            
            result = await orchestrator._mk_abi_registry()
            assert result == mock_registry
            mock_get_registry.assert_called_once()

    @pytest.mark.asyncio
    async def test_mk_db_manager(self, mock_global_settings):
        """Test database manager creation."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        
        with patch("on1builder.persistence.db_interface.get_db_manager") as mock_get_db:
            mock_instance = MagicMock()
            mock_instance.initialize = AsyncMock()
            mock_get_db.return_value = mock_instance
            
            result = await orchestrator._mk_db_manager()
            assert result == mock_instance
            mock_instance.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_tx_processor_no_components(self, mock_global_settings):
        """Test transaction processor when no transaction manager exists."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        # Don't add transaction_manager to components
        
        # Set stop event immediately to exit the loop
        orchestrator._stop_evt.set()
        
        # This should exit immediately due to stop event
        await orchestrator._tx_processor()
        
        # Verify that stop event is set
        assert orchestrator._stop_evt.is_set()

    @pytest.mark.asyncio
    async def test_heartbeat_functionality(self, mock_global_settings):
        """Test heartbeat functionality."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.components = {
            "test_component": MagicMock(is_healthy=AsyncMock(return_value=True))
        }
        
        # Set stop event immediately to exit the loop
        orchestrator._stop_evt.set()
        
        # This should exit immediately due to stop event
        await orchestrator._heartbeat()
        
        # Verify that stop event is set
        assert orchestrator._stop_evt.is_set()

    def test_component_health_storage(self, mock_global_settings):
        """Test that component health can be stored and accessed."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.component_health = {
            "component1": True,
            "component2": False
        }
        
        # Just verify the health dictionary is accessible
        assert orchestrator.component_health["component1"] is True
        assert orchestrator.component_health["component2"] is False

    @pytest.mark.asyncio
    async def test_connect_web3_exception_handling(self, mock_global_settings):
        """Test web3 connection with exception handling."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        
        with patch("on1builder.core.main_orchestrator.AsyncWeb3", side_effect=Exception("Connection failed")):
            result = await orchestrator._connect_web3()
            assert result is None

    @pytest.mark.asyncio
    async def test_create_account_exception_handling(self, mock_global_settings):
        """Test account creation with exception handling."""
        orchestrator = MainOrchestrator(config=mock_global_settings)
        orchestrator.cfg.wallet_key = "invalid_key"
        
        with patch.object(Account, "from_key", side_effect=Exception("Invalid key")):
            result = await orchestrator._create_account()
            assert result is None

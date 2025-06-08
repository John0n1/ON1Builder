"""
Tests for the chain_worker module.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from on1builder.core.chain_worker import ChainWorker
from on1builder.config.settings import GlobalSettings, APISettings


@pytest.fixture
def mock_global_settings():
    """Create a mock GlobalSettings instance."""
    settings = MagicMock(spec=GlobalSettings)
    settings.heartbeat_interval = 10
    settings.price_cache_ttl = 300  # Add missing attribute
    settings.api = MagicMock(spec=APISettings)
    return settings


@pytest.fixture
def chain_config():
    """Create a sample chain configuration."""
    return {
        "CHAIN_ID": 1,
        "CHAIN_NAME": "ethereum",
        "HTTP_ENDPOINT": "http://localhost:8545",
        "WEBSOCKET_ENDPOINT": "ws://localhost:8546",
        "IPC_ENDPOINT": "/tmp/geth.ipc",
        "WALLET_KEY": "0x" + "1" * 64,
        "WALLET_ADDRESS": "0x742d35Cc6634C0532925a3b8D0C55E749b5A2C4B",
    }


@pytest.fixture
def chain_worker(chain_config, mock_global_settings):
    """Create a ChainWorker instance for testing."""
    return ChainWorker(chain_config, mock_global_settings)


class TestChainWorker:
    """Test suite for ChainWorker class."""

    def test_init(self, chain_worker, chain_config, mock_global_settings):
        """Test ChainWorker initialization."""
        assert chain_worker.chain_cfg == chain_config
        assert chain_worker.config == mock_global_settings
        assert chain_worker.chain_id == "1"
        assert chain_worker.chain_name == "ethereum"
        assert chain_worker.http_endpoint == "http://localhost:8545"
        assert chain_worker.websocket_endpoint == "ws://localhost:8546"
        assert chain_worker.ipc_endpoint == "/tmp/geth.ipc"
        assert chain_worker.wallet_key == "0x" + "1" * 64
        assert chain_worker.wallet_address == "0x742d35Cc6634C0532925a3b8D0C55E749b5A2C4B"
        assert not chain_worker.initialized
        assert not chain_worker.running
        assert chain_worker.web3 is None
        assert chain_worker.account is None

    def test_default_chain_values(self, mock_global_settings):
        """Test ChainWorker with minimal configuration."""
        minimal_config = {}
        worker = ChainWorker(minimal_config, mock_global_settings)
        assert worker.chain_id == "unknown"
        assert worker.chain_name == "chain-unknown"
        assert worker.http_endpoint == ""
        assert worker.websocket_endpoint == ""
        assert worker.ipc_endpoint == ""

    def test_metrics_initialized(self, chain_worker):
        """Test that metrics are properly initialized."""
        assert "chain_id" in chain_worker.metrics
        assert "chain_name" in chain_worker.metrics
        assert "wallet_balance_eth" in chain_worker.metrics
        assert "health_status" in chain_worker.metrics
        assert chain_worker.metrics["chain_id"] == "1"
        assert chain_worker.metrics["chain_name"] == "ethereum"
        assert chain_worker.metrics["health_status"] == "initializing"

    @pytest.mark.asyncio
    @patch('on1builder.core.chain_worker.get_container')
    @patch('on1builder.core.chain_worker.get_notification_manager')
    @patch('on1builder.core.chain_worker.MarketDataFeed')
    @patch('on1builder.core.chain_worker.TxPoolScanner')
    async def test_initialize_success(self, mock_txpool, mock_market_feed, mock_get_notification, mock_get_container, chain_worker):
        """Test successful initialization."""
        # Add missing attributes to config mock
        chain_worker.config.monitored_tokens = ["ETH", "USDC"]
        chain_worker.config.api = MagicMock()
        
        # Mock container
        mock_container = MagicMock()
        mock_get_container.return_value = mock_container

        # Mock notification manager
        mock_notification = MagicMock()
        mock_get_notification.return_value = mock_notification

        # Mock MarketDataFeed
        mock_market = MagicMock()
        mock_market.initialize = AsyncMock()
        mock_market_feed.return_value = mock_market

        # Mock TxPoolScanner
        mock_scanner = MagicMock()
        mock_scanner.initialize = AsyncMock()
        mock_txpool.return_value = mock_scanner

        # Mock web3 initialization
        with patch.object(chain_worker, '_init_web3', new_callable=AsyncMock) as mock_init_web3, \
             patch('on1builder.core.chain_worker.Account') as mock_account_class, \
             patch('on1builder.core.chain_worker.ExternalAPIManager') as mock_api_manager, \
             patch('on1builder.core.chain_worker.get_db_manager') as mock_get_db, \
             patch('on1builder.core.chain_worker.NonceManager') as mock_nonce_manager, \
             patch('on1builder.core.chain_worker.SafetyGuard') as mock_safety_guard:

            # Setup mocks
            mock_init_web3.return_value = True
            
            # Mock web3 instance to ensure it's set during init
            mock_web3 = MagicMock()
            chain_worker.web3 = mock_web3
            
            mock_account = MagicMock()
            mock_account.address = chain_worker.wallet_address
            mock_account_class.from_key.return_value = mock_account

            # Mock API manager
            mock_api = MagicMock()
            mock_api.initialize = AsyncMock()
            mock_api_manager.return_value = mock_api

            # Mock database
            mock_db = MagicMock()
            mock_db.initialize = AsyncMock()
            mock_get_db.return_value = mock_db

            # Mock nonce manager
            mock_nonce = MagicMock()
            mock_nonce.initialize = AsyncMock()
            mock_nonce_manager.return_value = mock_nonce

            # Mock safety guard
            mock_safety = MagicMock()
            mock_safety.initialize = AsyncMock()
            mock_safety_guard.return_value = mock_safety

            result = await chain_worker.initialize()

            assert result is True
            assert chain_worker.initialized
            assert chain_worker.account == mock_account
            mock_init_web3.assert_called_once()
            mock_account_class.from_key.assert_called_once_with(chain_worker.wallet_key)

    @pytest.mark.asyncio
    async def test_initialize_no_wallet_key(self, chain_worker):
        """Test initialization failure when no wallet key is provided."""
        chain_worker.wallet_key = None
        
        with patch.object(chain_worker, '_init_web3', new_callable=AsyncMock) as mock_init_web3:
            mock_init_web3.return_value = True
            
            result = await chain_worker.initialize()
            
            assert result is False
            assert not chain_worker.initialized
            assert chain_worker.metrics["health_status"] == "error_account"

    @pytest.mark.asyncio
    async def test_initialize_web3_failure(self, chain_worker):
        """Test initialization failure when Web3 connection fails."""
        with patch.object(chain_worker, '_init_web3', new_callable=AsyncMock) as mock_init_web3:
            mock_init_web3.return_value = False
            
            result = await chain_worker.initialize()
            
            assert result is False
            assert not chain_worker.initialized
            assert chain_worker.metrics["health_status"] == "error_web3"

    @pytest.mark.asyncio
    async def test_start_worker_success(self, chain_worker):
        """Test starting the worker successfully."""
        chain_worker.initialized = True
        
        # Mock required components
        chain_worker.txpool_scanner = MagicMock()
        chain_worker.txpool_scanner.start_monitoring = AsyncMock()
        chain_worker.market_data_feed = MagicMock()
        chain_worker.market_data_feed.schedule_updates = AsyncMock()
        chain_worker.notification_manager = MagicMock()
        chain_worker.notification_manager.send_notification = AsyncMock()
        
        with patch.object(chain_worker, '_run_heartbeat', new_callable=AsyncMock):
            await chain_worker.start()
            
            assert chain_worker.running
            assert chain_worker.metrics["health_status"] == "running"
            chain_worker.notification_manager.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_worker_not_initialized(self, chain_worker):
        """Test starting worker when not initialized."""
        await chain_worker.start()
        assert not chain_worker.running

    @pytest.mark.asyncio
    async def test_start_worker_already_running(self, chain_worker):
        """Test starting worker when already running."""
        chain_worker.initialized = True
        chain_worker.running = True
        
        await chain_worker.start()
        # Should just log warning and return

    @pytest.mark.asyncio
    async def test_stop_worker(self, chain_worker):
        """Test stopping the worker."""
        chain_worker.running = True
        chain_worker._stop_event = asyncio.Event()
        
        # Mock some tasks
        mock_task1 = MagicMock()
        mock_task1.done.return_value = False
        mock_task1.cancelled.return_value = False
        mock_task1.get_name.return_value = "test_task_1"
        
        mock_task2 = MagicMock()
        mock_task2.done.return_value = False
        mock_task2.cancelled.return_value = False
        mock_task2.get_name.return_value = "test_task_2"
        
        chain_worker._tasks = [mock_task1, mock_task2]
        chain_worker.notification_manager = MagicMock()
        chain_worker.notification_manager.send_notification = AsyncMock()
        chain_worker.notification_manager.stop = AsyncMock()
        
        with patch.object(chain_worker, '_stop_component', new_callable=AsyncMock) as mock_stop_component:
            await chain_worker.stop()
            
            assert not chain_worker.running
            assert chain_worker._stop_event.is_set()
            assert chain_worker.metrics["health_status"] == "stopped"
            mock_task1.cancel.assert_called_once()
            mock_task2.cancel.assert_called_once()
            # _stop_component should be called for each component
            assert mock_stop_component.call_count >= 5

    @pytest.mark.asyncio
    async def test_stop_worker_not_running(self, chain_worker):
        """Test stopping worker when not running."""
        await chain_worker.stop()
        # Should return early without doing anything

    @pytest.mark.asyncio
    async def test_get_wallet_balance(self, chain_worker):
        """Test getting wallet balance."""
        mock_web3 = MagicMock()
        mock_web3.eth.get_balance = AsyncMock(return_value=1000000000000000000)  # 1 ETH in wei
        chain_worker.web3 = mock_web3
        chain_worker.account = MagicMock()
        chain_worker.account.address = "0x742d35Cc6634C0532925a3b8D0C55E749b5A2C4B"
        
        balance = await chain_worker.get_wallet_balance()
        
        assert balance == 1.0  # 1 ETH
        mock_web3.eth.get_balance.assert_called_once_with(chain_worker.account.address)

    @pytest.mark.asyncio
    async def test_get_gas_price(self, chain_worker):
        """Test getting gas price."""
        mock_web3 = MagicMock()
        # For AsyncWeb3, gas_price is awaitable
        async def mock_gas_price():
            return 20000000000  # 20 gwei in wei
            
        mock_web3.eth.gas_price = mock_gas_price()
        mock_web3.from_wei = MagicMock(return_value=20.0)
        chain_worker.web3 = mock_web3

        gas_price = await chain_worker.get_gas_price()

        assert gas_price == 20.0  # 20 gwei

    @pytest.mark.asyncio
    async def test_verify_connection_success(self, chain_worker):
        """Test successful connection verification."""
        mock_web3 = MagicMock()
        
        # Mock chain_id as a coroutine
        async def mock_chain_id():
            return 1
        mock_web3.eth.chain_id = mock_chain_id()
        
        mock_web3.eth.get_block = AsyncMock(return_value={"number": 12345})
        chain_worker.web3 = mock_web3
        chain_worker.chain_id = "1"

        result = await chain_worker._verify_connection()

        assert result is True
        assert chain_worker.metrics["last_block_number"] == 12345

    @pytest.mark.asyncio
    async def test_verify_connection_chain_id_mismatch(self, chain_worker):
        """Test connection verification with chain ID mismatch."""
        mock_web3 = MagicMock()
        
        # Mock chain_id as a coroutine returning different ID
        async def mock_chain_id():
            return 5
        mock_web3.eth.chain_id = mock_chain_id()
        
        chain_worker.web3 = mock_web3
        chain_worker.chain_id = "1"

        result = await chain_worker._verify_connection()

        assert result is False

    @pytest.mark.asyncio
    async def test_init_web3_http_success(self, chain_worker):
        """Test successful Web3 initialization with HTTP provider."""
        with patch('on1builder.core.chain_worker.AsyncWeb3') as mock_web3_class, \
             patch('on1builder.core.chain_worker.AsyncHTTPProvider') as mock_provider:

            mock_web3 = MagicMock()
            
            # Mock chain_id as a coroutine
            async def mock_chain_id():
                return 1
            mock_web3.eth.chain_id = mock_chain_id()
            
            mock_web3_class.return_value = mock_web3

            result = await chain_worker._init_web3()

            assert result is True
            assert chain_worker.web3 == mock_web3

    @pytest.mark.asyncio
    async def test_init_web3_no_endpoints(self, chain_worker):
        """Test Web3 initialization with no endpoints."""
        chain_worker.http_endpoint = ""
        chain_worker.websocket_endpoint = ""
        chain_worker.ipc_endpoint = ""
        
        result = await chain_worker._init_web3()
        
        assert result is False

    @pytest.mark.asyncio
    async def test_update_metrics(self, chain_worker):
        """Test metrics update."""
        # Mock required components
        chain_worker.web3 = MagicMock()
        chain_worker.account = MagicMock()
        chain_worker.account.address = "0x742d35Cc6634C0532925a3b8D0C55E749b5A2C4B"
        
        # Mock block_number as a coroutine
        async def mock_block_number():
            return 12345
        chain_worker.web3.eth.block_number = mock_block_number()
        
        with patch.object(chain_worker, 'get_wallet_balance', new_callable=AsyncMock) as mock_balance, \
             patch.object(chain_worker, 'get_gas_price', new_callable=AsyncMock) as mock_gas_price:
            
            mock_balance.return_value = 5.0
            mock_gas_price.return_value = 25.0
            
            # Call the method that exists in the actual implementation
            await chain_worker._update_metrics()
            
            # Check that the methods were called (the actual metrics update may depend on implementation details)
            mock_balance.assert_called()
            mock_gas_price.assert_called()

    @pytest.mark.asyncio
    async def test_run_heartbeat(self, chain_worker):
        """Test heartbeat functionality."""
        chain_worker.running = True
        chain_worker._stop_event = asyncio.Event()
        
        # Add missing config attributes that are used in _update_metrics
        chain_worker.config.min_wallet_balance = 0.1
        chain_worker.config.max_gas_price_gwei = 100
        
        # Mock web3 for metrics update
        mock_web3 = MagicMock()
        
        # Mock block_number as a coroutine  
        async def mock_block_number():
            return 12345
        mock_web3.eth.block_number = mock_block_number()
        
        chain_worker.web3 = mock_web3

        # Stop the event after a short delay to prevent infinite loop
        async def stop_after_delay():
            await asyncio.sleep(0.1)
            chain_worker._stop_event.set()

        with patch.object(chain_worker, '_update_metrics', new_callable=AsyncMock) as mock_update, \
             patch.object(chain_worker, '_check_component_health', new_callable=AsyncMock) as mock_health:

            mock_update.return_value = None
            mock_health.return_value = True

            # Start the stop task
            stop_task = asyncio.create_task(stop_after_delay())

            # Run heartbeat (should exit when stop event is set)
            await chain_worker._run_heartbeat()

            # Clean up
            await stop_task

            # Verify metrics update was called
            mock_update.assert_called()

    @pytest.mark.asyncio
    async def test_check_component_health(self, chain_worker):
        """Test component health checking."""
        # Mock components
        chain_worker.web3 = MagicMock()
        chain_worker.web3.is_connected = AsyncMock(return_value=True)

        # Mock safety guard with async health check
        chain_worker.safety_guard = MagicMock()
        chain_worker.safety_guard.is_healthy = AsyncMock(return_value=True)

        # Mock nonce manager with async health check
        chain_worker.nonce_manager = MagicMock()
        chain_worker.nonce_manager.is_healthy = AsyncMock(return_value=True)

        result = await chain_worker._check_component_health()

        # Should return True when all components are healthy
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_component(self, chain_worker):
        """Test stopping a component."""
        # Create a mock component with stop method
        mock_component = MagicMock()
        mock_component.stop = AsyncMock()
        chain_worker.txpool_scanner = mock_component
        
        await chain_worker._stop_component("txpool_scanner")
        
        mock_component.stop.assert_called_once()
        assert "txpool_scanner" in chain_worker._closed_components

    @pytest.mark.asyncio
    async def test_stop_component_not_exists(self, chain_worker):
        """Test stopping a component that doesn't exist."""
        # Should not raise an error
        await chain_worker._stop_component("nonexistent_component")


class TestChainWorkerErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_initialize_with_exception(self, chain_worker):
        """Test initialization with exception."""
        with patch.object(chain_worker, '_init_web3', new_callable=AsyncMock) as mock_init_web3:
            mock_init_web3.side_effect = Exception("Connection failed")
            
            result = await chain_worker.initialize()
            
            assert result is False
            assert chain_worker.metrics["health_status"] == "error"

    @pytest.mark.asyncio
    async def test_start_with_exception(self, chain_worker):
        """Test start with exception."""
        chain_worker.initialized = True
        chain_worker.txpool_scanner = MagicMock()
        chain_worker.txpool_scanner.start_monitoring = AsyncMock(side_effect=Exception("Start failed"))
        
        await chain_worker.start()
        
        assert chain_worker.metrics["health_status"] == "error_starting"

    @pytest.mark.asyncio
    async def test_get_wallet_balance_exception(self, chain_worker):
        """Test wallet balance with exception."""
        mock_web3 = MagicMock()
        mock_web3.eth.get_balance = AsyncMock(side_effect=Exception("Network error"))
        chain_worker.web3 = mock_web3
        chain_worker.account = MagicMock()
        chain_worker.account.address = "0x742d35Cc6634C0532925a3b8D0C55E749b5A2C4B"
        
        balance = await chain_worker.get_wallet_balance()
        
        assert balance == 0.0  # Should return 0 on error

    @pytest.mark.asyncio
    async def test_get_gas_price_exception(self, chain_worker):
        """Test gas price with exception."""
        mock_web3 = MagicMock()
        mock_web3.eth.gas_price = property(lambda self: (_ for _ in ()).throw(Exception("Network error")))
        chain_worker.web3 = mock_web3
        
        gas_price = await chain_worker.get_gas_price()
        
        assert gas_price == 0.0  # Should return 0 on error


class TestChainWorkerIntegration:
    """Integration tests for ChainWorker."""

    @pytest.mark.asyncio
    async def test_minimal_lifecycle(self, chain_config, mock_global_settings):
        """Test minimal worker lifecycle."""
        worker = ChainWorker(chain_config, mock_global_settings)
        
        # Test initialization (will fail due to missing dependencies, but that's expected)
        result = await worker.initialize()
        
        # Should not crash, even if initialization fails
        assert isinstance(result, bool)
        
        # Test stop (should work even if not started)
        await worker.stop()

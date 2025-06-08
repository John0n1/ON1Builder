"""
Tests for the txpool_scanner module.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from on1builder.monitoring.txpool_scanner import TxPoolScanner


@pytest.fixture
def mock_web3():
    """Create mock AsyncWeb3 instance."""
    return MagicMock()


@pytest.fixture
def mock_safety_net():
    """Create mock SafetyGuard instance."""
    return MagicMock()


@pytest.fixture
def mock_nonce_core():
    """Create mock NonceManager instance."""
    return MagicMock()


@pytest.fixture
def mock_api_config():
    """Create mock ExternalAPIManager instance."""
    return MagicMock()


@pytest.fixture
def mock_market_monitor():
    """Create mock MarketDataFeed instance."""
    return MagicMock()


@pytest.fixture
def mock_configuration():
    """Create mock configuration."""
    return {
        "MEMPOOL_MAX_PARALLEL_TASKS": 10,
        "MIN_GAS": 0,
        "MAX_QUEUE_SIZE": 1000,
        "USE_TXPOOL_API": False,
    }


@pytest.fixture
def monitored_tokens():
    """Create list of monitored tokens."""
    return ["ETH", "0x123456789abcdef", "USDT"]


@pytest.fixture
def txpool_scanner(
    mock_web3,
    mock_safety_net,
    mock_nonce_core,
    mock_api_config,
    monitored_tokens,
    mock_configuration,
    mock_market_monitor,
):
    """Create test TxPoolScanner instance."""
    # Mock the api_config_token_address function
    def mock_token_address(symbol):
        mappings = {
            "ETH": "0xETH_ADDRESS",
            "USDT": "0xUSDT_ADDRESS",
        }
        return mappings.get(symbol)
    
    with patch('on1builder.monitoring.txpool_scanner.api_config_token_address', side_effect=mock_token_address):
        return TxPoolScanner(
            mock_web3,
            mock_safety_net,
            mock_nonce_core,
            mock_api_config,
            monitored_tokens,
            mock_configuration,
            mock_market_monitor,
        )


class TestTxPoolScanner:
    """Test TxPoolScanner class."""

    def test_init(self, txpool_scanner, mock_web3, mock_safety_net, mock_nonce_core):
        """Test TxPoolScanner initialization."""
        assert txpool_scanner.web3 == mock_web3
        assert txpool_scanner.safety_net == mock_safety_net
        assert txpool_scanner.nonce_core == mock_nonce_core
        
        # Check monitored tokens normalization
        assert isinstance(txpool_scanner.monitored_tokens, set)
        assert "0x123456789abcdef" in txpool_scanner.monitored_tokens
        assert "0xeth_address" in txpool_scanner.monitored_tokens
        assert "0xusdt_address" in txpool_scanner.monitored_tokens
        
        # Check queues initialization
        assert isinstance(txpool_scanner._tx_hash_queue, asyncio.Queue)
        assert isinstance(txpool_scanner._tx_analysis_queue, asyncio.Queue)
        assert isinstance(txpool_scanner.profitable_transactions, asyncio.Queue)
        
        # Check configuration
        assert txpool_scanner.min_gas == 0
        assert txpool_scanner.max_queue_size == 1000
        assert txpool_scanner.use_txpool_api is False
        
        # Check initial state
        assert txpool_scanner._running is False
        assert len(txpool_scanner._tasks) == 0
        assert len(txpool_scanner._processed_hashes) == 0

    @pytest.mark.asyncio
    async def test_initialize(self, txpool_scanner):
        """Test TxPoolScanner initialization."""
        await txpool_scanner.initialize()
        
        # Check queues are reset
        assert txpool_scanner._tx_hash_queue.empty()
        assert txpool_scanner._tx_analysis_queue.empty()
        assert txpool_scanner.profitable_transactions.empty()
        
        # Check sets are cleared
        assert len(txpool_scanner._processed_hashes) == 0
        assert len(txpool_scanner._tx_cache) == 0
        assert txpool_scanner._running is False

    def test_monitored_tokens_with_invalid_symbol(self):
        """Test handling of invalid token symbols."""
        with patch('on1builder.monitoring.txpool_scanner.api_config_token_address', return_value=None):
            mock_web3 = MagicMock()
            mock_safety_net = MagicMock()
            mock_nonce_core = MagicMock()
            mock_api_config = MagicMock()
            mock_market_monitor = MagicMock()
            monitored_tokens = ["INVALID_TOKEN"]
            configuration = {"MEMPOOL_MAX_PARALLEL_TASKS": 10, "MIN_GAS": 0, "MAX_QUEUE_SIZE": 1000, "USE_TXPOOL_API": False}
            
            scanner = TxPoolScanner(
                mock_web3,
                mock_safety_net,
                mock_nonce_core,
                mock_api_config,
                monitored_tokens,
                configuration,
                mock_market_monitor,
            )
            
            # Should not add invalid token to monitored set
            assert len(scanner.monitored_tokens) == 0

    def test_queue_initialization(self, txpool_scanner):
        """Test that all queues are properly initialized."""
        assert hasattr(txpool_scanner, '_tx_hash_queue')
        assert hasattr(txpool_scanner, '_tx_analysis_queue')
        assert hasattr(txpool_scanner, 'profitable_transactions')
        assert hasattr(txpool_scanner, 'tx_queue')
        
        assert isinstance(txpool_scanner._tx_hash_queue, asyncio.Queue)
        assert isinstance(txpool_scanner._tx_analysis_queue, asyncio.Queue)
        assert isinstance(txpool_scanner.profitable_transactions, asyncio.Queue)
        assert isinstance(txpool_scanner.tx_queue, list)

    def test_semaphore_configuration(self, txpool_scanner):
        """Test semaphore is configured correctly."""
        assert hasattr(txpool_scanner, '_semaphore')
        assert isinstance(txpool_scanner._semaphore, asyncio.Semaphore)
        assert txpool_scanner._semaphore._value == 10  # MAX_PARALLEL_TASKS

    def test_stop_event_initialization(self, txpool_scanner):
        """Test stop event is initialized."""
        assert hasattr(txpool_scanner, '_stop_event')
        assert isinstance(txpool_scanner._stop_event, asyncio.Event)
        assert not txpool_scanner._stop_event.is_set()

    def test_task_list_initialization(self, txpool_scanner):
        """Test task list is initialized empty."""
        assert hasattr(txpool_scanner, '_tasks')
        assert isinstance(txpool_scanner._tasks, list)
        assert len(txpool_scanner._tasks) == 0

    def test_cache_initialization(self, txpool_scanner):
        """Test caches are initialized empty."""
        assert hasattr(txpool_scanner, '_processed_hashes')
        assert hasattr(txpool_scanner, '_tx_cache')
        assert hasattr(txpool_scanner, 'processed_txs')
        
        assert isinstance(txpool_scanner._processed_hashes, set)
        assert isinstance(txpool_scanner._tx_cache, dict)
        assert isinstance(txpool_scanner.processed_txs, set)
        
        assert len(txpool_scanner._processed_hashes) == 0
        assert len(txpool_scanner._tx_cache) == 0
        assert len(txpool_scanner.processed_txs) == 0

    def test_configuration_defaults(self):
        """Test default configuration values."""
        mock_web3 = MagicMock()
        mock_safety_net = MagicMock()
        mock_nonce_core = MagicMock()
        mock_api_config = MagicMock()
        mock_market_monitor = MagicMock()
        
        # Empty configuration - should use defaults
        configuration = {}
        
        with patch('on1builder.monitoring.txpool_scanner.api_config_token_address', return_value=None):
            scanner = TxPoolScanner(
                mock_web3,
                mock_safety_net,
                mock_nonce_core,
                mock_api_config,
                [],
                configuration,
                mock_market_monitor,
            )
            
            assert scanner.min_gas == 0  # Default MIN_GAS
            assert scanner.max_queue_size == 1000  # Default MAX_QUEUE_SIZE
            assert scanner.use_txpool_api is False  # Default USE_TXPOOL_API
            assert scanner._semaphore._value == 10  # Default MEMPOOL_MAX_PARALLEL_TASKS

    def test_address_normalization(self):
        """Test that addresses are normalized to lowercase."""
        mock_web3 = MagicMock()
        mock_safety_net = MagicMock()
        mock_nonce_core = MagicMock()
        mock_api_config = MagicMock()
        mock_market_monitor = MagicMock()
        
        # Mixed case addresses
        monitored_tokens = ["0xAbCdEf123456", "0X789ABC456DEF"]
        configuration = {"MEMPOOL_MAX_PARALLEL_TASKS": 10, "MIN_GAS": 0, "MAX_QUEUE_SIZE": 1000, "USE_TXPOOL_API": False}
        
        with patch('on1builder.monitoring.txpool_scanner.api_config_token_address', return_value=None):
            scanner = TxPoolScanner(
                mock_web3,
                mock_safety_net,
                mock_nonce_core,
                mock_api_config,
                monitored_tokens,
                configuration,
                mock_market_monitor,
            )
            
            assert "0xabcdef123456" in scanner.monitored_tokens
            assert "0x789abc456def" in scanner.monitored_tokens
            # Should not contain original case versions
            assert "0xAbCdEf123456" not in scanner.monitored_tokens
            assert "0X789ABC456DEF" not in scanner.monitored_tokens

    @pytest.mark.asyncio
    async def test_queue_operations(self, txpool_scanner):
        """Test basic queue operations."""
        await txpool_scanner.initialize()
        
        # Test putting items in queues
        await txpool_scanner._tx_hash_queue.put("0x123")
        await txpool_scanner._tx_analysis_queue.put((1, "0x456"))
        await txpool_scanner.profitable_transactions.put({"hash": "0x789"})
        
        # Test getting items from queues
        hash_item = await txpool_scanner._tx_hash_queue.get()
        analysis_item = await txpool_scanner._tx_analysis_queue.get()
        profit_item = await txpool_scanner.profitable_transactions.get()
        
        assert hash_item == "0x123"
        assert analysis_item == (1, "0x456")
        assert profit_item == {"hash": "0x789"}

    def test_client_session_attribute(self, txpool_scanner):
        """Test that client_session attribute is initialized."""
        assert hasattr(txpool_scanner, 'client_session')
        assert txpool_scanner.client_session is None

    def test_queue_event_initialization(self, txpool_scanner):
        """Test queue event is initialized."""
        assert hasattr(txpool_scanner, 'queue_event')
        assert isinstance(txpool_scanner.queue_event, asyncio.Event)
        assert not txpool_scanner.queue_event.is_set()

    @pytest.mark.asyncio 
    async def test_multiple_initialize_calls(self, txpool_scanner):
        """Test that multiple initialize calls work correctly."""
        # First initialization
        await txpool_scanner.initialize()
        
        # Add some data
        await txpool_scanner._tx_hash_queue.put("test")
        txpool_scanner._processed_hashes.add("hash1")
        txpool_scanner._tx_cache["key"] = "value"
        
        # Second initialization should clear everything
        await txpool_scanner.initialize()
        
        assert txpool_scanner._tx_hash_queue.empty()
        assert len(txpool_scanner._processed_hashes) == 0
        assert len(txpool_scanner._tx_cache) == 0

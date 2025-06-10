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
    """Create list of monitored tokens - only addresses."""
    return ["0x123456789abcdef"]  # Only valid addresses


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
        mock_web3 = MagicMock()
        mock_safety_net = MagicMock()
        mock_nonce_core = MagicMock()
        mock_api_config = MagicMock()
        mock_market_monitor = MagicMock()
        monitored_tokens = ["INVALID_TOKEN"]
        configuration = {
            "MEMPOOL_MAX_PARALLEL_TASKS": 10,
            "MIN_GAS": 0,
            "MAX_QUEUE_SIZE": 1000,
            "USE_TXPOOL_API": False,
        }

        scanner = TxPoolScanner(
            mock_web3,
            mock_safety_net,
            mock_nonce_core,
            mock_api_config,
            monitored_tokens,
            configuration,
            mock_market_monitor,
        )

        # Should not add invalid token to monitored set since it doesn't start with '0x'
        assert len(scanner.monitored_tokens) == 0

    def test_queue_initialization(self, txpool_scanner):
        """Test that all queues are properly initialized."""
        assert hasattr(txpool_scanner, "_tx_hash_queue")
        assert hasattr(txpool_scanner, "_tx_analysis_queue")
        assert hasattr(txpool_scanner, "profitable_transactions")
        assert hasattr(txpool_scanner, "tx_queue")

        assert isinstance(txpool_scanner._tx_hash_queue, asyncio.Queue)
        assert isinstance(txpool_scanner._tx_analysis_queue, asyncio.Queue)
        assert isinstance(txpool_scanner.profitable_transactions, asyncio.Queue)
        assert isinstance(txpool_scanner.tx_queue, list)

    def test_semaphore_configuration(self, txpool_scanner):
        """Test semaphore is configured correctly."""
        assert hasattr(txpool_scanner, "_semaphore")
        assert isinstance(txpool_scanner._semaphore, asyncio.Semaphore)
        assert txpool_scanner._semaphore._value == 10  # MAX_PARALLEL_TASKS

    def test_stop_event_initialization(self, txpool_scanner):
        """Test stop event is initialized."""
        assert hasattr(txpool_scanner, "_stop_event")
        assert isinstance(txpool_scanner._stop_event, asyncio.Event)
        assert not txpool_scanner._stop_event.is_set()

    def test_task_list_initialization(self, txpool_scanner):
        """Test task list is initialized empty."""
        assert hasattr(txpool_scanner, "_tasks")
        assert isinstance(txpool_scanner._tasks, list)
        assert len(txpool_scanner._tasks) == 0

    def test_cache_initialization(self, txpool_scanner):
        """Test caches are initialized empty."""
        assert hasattr(txpool_scanner, "_processed_hashes")
        assert hasattr(txpool_scanner, "_tx_cache")
        assert hasattr(txpool_scanner, "processed_txs")

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

    def test_address_normalization(self):
        """Test that addresses are normalized to lowercase."""
        mock_web3 = MagicMock()
        mock_safety_net = MagicMock()
        mock_nonce_core = MagicMock()
        mock_api_config = MagicMock()
        mock_market_monitor = MagicMock()

        # Mixed case addresses
        monitored_tokens = ["0xAbCdEf123456", "0X789ABC456DEF"]
        configuration = {
            "MEMPOOL_MAX_PARALLEL_TASKS": 10,
            "MIN_GAS": 0,
            "MAX_QUEUE_SIZE": 1000,
            "USE_TXPOOL_API": False,
        }

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
        assert hasattr(txpool_scanner, "client_session")
        assert txpool_scanner.client_session is None

    def test_queue_event_initialization(self, txpool_scanner):
        """Test queue event is initialized."""
        assert hasattr(txpool_scanner, "queue_event")
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

    # === Tests for missing coverage methods ===

    @pytest.mark.asyncio
    async def test_initialize_with_api_config(self):
        """Test initialize method with API config."""
        mock_web3 = AsyncMock()
        mock_web3.eth.block_number = 12345
        
        mock_safety_net = MagicMock()
        mock_nonce_core = MagicMock()
        mock_api_config = MagicMock()
        mock_market_monitor = MagicMock()
        
        # Mock successful node connection
        with patch.object(TxPoolScanner, '_check_txpool_support', return_value=True), \
             patch('on1builder.monitoring.txpool_scanner.psutil') as mock_psutil:
            
            mock_process = MagicMock()
            mock_process.memory_info.return_value.rss = 100 * 1024 * 1024  # 100MB
            mock_psutil.Process.return_value = mock_process
            
            scanner = TxPoolScanner(
                mock_web3,
                mock_safety_net,
                mock_nonce_core,
                mock_api_config,
                [],
                {},
                mock_market_monitor,
            )
            
            await scanner.initialize()
            
            assert scanner.use_txpool_api is True
            mock_web3.eth.block_number

    @pytest.mark.asyncio
    async def test_check_txpool_support(self):
        """Test txpool support checking."""
        mock_web3 = AsyncMock()
        mock_geth = MagicMock()
        mock_geth.txpool.status = AsyncMock(return_value=MagicMock(pending="0x5"))
        mock_web3.geth = mock_geth
        
        scanner = TxPoolScanner(
            mock_web3,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            [],
            {},
            MagicMock(),
        )
        
        # Test with geth support
        result = await scanner._check_txpool_support()
        assert result is True
        
        # Test without geth support
        mock_web3.geth = None
        result = await scanner._check_txpool_support()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_connected(self):
        """Test health check when connected."""
        mock_web3 = AsyncMock()
        mock_web3.is_connected.return_value = True
        
        scanner = TxPoolScanner(
            mock_web3,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            [],
            {},
            MagicMock(),
        )
        scanner._running = True
        scanner._tasks = [MagicMock(done=lambda: False, cancelled=lambda: False, get_name=lambda: "test")]
        
        result = await scanner.check_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_not_connected(self):
        """Test health check when not connected."""
        mock_web3 = AsyncMock()
        mock_web3.is_connected.return_value = False
        
        scanner = TxPoolScanner(
            mock_web3,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            [],
            {},
            MagicMock(),
        )
        
        result = await scanner.check_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_monitoring(self):
        """Test stopping monitoring tasks."""
        scanner = TxPoolScanner(
            AsyncMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            [],
            {},
            MagicMock(),
        )
        
        # Create mock tasks
        mock_task1 = MagicMock()
        mock_task1.done.return_value = False
        mock_task1.cancelled.return_value = False
        mock_task1.get_name.return_value = "task1"
        
        mock_task2 = MagicMock()
        mock_task2.done.return_value = True
        mock_task2.cancelled.return_value = False
        mock_task2.get_name.return_value = "task2"
        
        scanner._running = True
        scanner._tasks = [mock_task1, mock_task2]
        scanner._stop_event = asyncio.Event()
        
        # Mock queue operations
        scanner._tx_hash_queue = AsyncMock()
        scanner._tx_hash_queue.empty.return_value = True
        scanner._tx_analysis_queue = AsyncMock()
        scanner._tx_analysis_queue.empty.return_value = True
        scanner.profitable_transactions = AsyncMock()
        scanner.profitable_transactions.empty.return_value = True
        
        await scanner.stop()
        
        assert scanner._running is False
        assert scanner._stop_event.is_set()
        mock_task1.cancel.assert_called_once()

    @pytest.mark.asyncio  
    async def test_start_monitoring(self):
        """Test starting monitoring tasks."""
        mock_web3 = AsyncMock()
        scanner = TxPoolScanner(
            mock_web3,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            [],
            {},
            MagicMock(),
        )
        
        # Mock the background task methods
        scanner._collect_hashes = AsyncMock()
        scanner._analysis_dispatcher = AsyncMock()
        
        # Mock asyncio.create_task to return completed tasks
        mock_task1 = AsyncMock()
        mock_task1.done.return_value = True
        mock_task2 = AsyncMock() 
        mock_task2.done.return_value = True
        
        with patch('asyncio.create_task', side_effect=[mock_task1, mock_task2]):
            await scanner.start_monitoring()
            
        assert scanner._running is True
        assert len(scanner._tasks) == 2

    @pytest.mark.asyncio
    async def test_analyze_transaction_not_profitable(self):
        """Test transaction analysis for non-profitable transaction."""
        mock_web3 = AsyncMock()
        mock_safety_net = MagicMock()
        mock_safety_net.check_transaction_safety = AsyncMock(return_value=(False, {}))
        
        scanner = TxPoolScanner(
            mock_web3,
            mock_safety_net,
            MagicMock(),
            MagicMock(),
            [],
            {},
            MagicMock(),
        )
        
        tx_data = {
            "hash": "0x123",
            "to": "0x456",
            "value": 1000000000000000000,
            "gas": 21000,
            "gasPrice": 20000000000
        }
        
        result = await scanner._analyze_transaction(tx_data)
        assert result is None  # Should return None for non-profitable tx

    def test_token_filtering_valid_addresses(self):
        """Test that valid token addresses are properly filtered."""
        scanner = TxPoolScanner(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            ["0x123456789abcdef", "0xABCDEF123456789", "ETH", "USDC"],
            {},
            MagicMock(),
        )
        
        # Should only include valid addresses (starting with 0x)
        assert len(scanner.monitored_tokens) == 2
        assert "0x123456789abcdef" in scanner.monitored_tokens
        assert "0xabcdef123456789" in scanner.monitored_tokens  # normalized to lowercase

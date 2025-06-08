#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for NonceManager"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add the src directory to the path for imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from on1builder.config.settings import GlobalSettings
from on1builder.core.nonce_manager import NonceManager


class TestNonceManager:
    """Test cases for NonceManager class."""

    @pytest.fixture
    def mock_web3(self):
        """Mock AsyncWeb3 instance."""
        web3 = AsyncMock()
        web3.is_connected.return_value = True
        web3.eth.chain_id = 1
        web3.eth.get_transaction_count.return_value = 10
        web3.eth.get_transaction_receipt.return_value = None
        return web3

    @pytest.fixture
    def mock_config(self):
        """Mock GlobalSettings configuration."""
        config = MagicMock(spec=GlobalSettings)
        config.address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        config.WALLET_ADDRESS = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        config.get = MagicMock(side_effect=lambda key, default: {
            "NONCE_CACHE_TTL": 60,
            "NONCE_RETRY_DELAY": 1,
            "NONCE_MAX_RETRIES": 5,
            "NONCE_TRANSACTION_TIMEOUT": 120
        }.get(key, default))
        return config

    @pytest.fixture
    def mock_orchestrator(self):
        """Mock main orchestrator with components."""
        orchestrator = MagicMock()
        orchestrator.components = {
            "db_manager": AsyncMock(),
            "notification_manager": AsyncMock()
        }
        
        # Mock database methods
        orchestrator.components["db_manager"].load_nonce_state = AsyncMock(return_value={})
        orchestrator.components["db_manager"].store_nonce_state = AsyncMock()
        
        return orchestrator

    @pytest.fixture
    def nonce_manager(self, mock_web3, mock_config, mock_orchestrator):
        """Create NonceManager instance."""
        return NonceManager(mock_web3, mock_config, mock_orchestrator)

    @pytest.fixture
    def nonce_manager_no_orchestrator(self, mock_web3, mock_config):
        """Create NonceManager instance without orchestrator."""
        return NonceManager(mock_web3, mock_config, None)

    def test_init_with_orchestrator(self, nonce_manager, mock_web3, mock_config, mock_orchestrator):
        """Test NonceManager initialization with orchestrator."""
        assert nonce_manager.web3 == mock_web3
        assert nonce_manager.account == mock_config
        assert nonce_manager.config == mock_config
        assert nonce_manager.main_orchestrator == mock_orchestrator
        assert nonce_manager.db_interface is not None
        assert nonce_manager.notification_manager is not None
        assert nonce_manager._cache_ttl == 60
        assert nonce_manager._retry_delay == 1
        assert nonce_manager._max_retries == 5
        assert nonce_manager._tx_timeout == 120
        assert isinstance(nonce_manager._nonces, dict)
        assert isinstance(nonce_manager._last_refresh, dict)

    def test_init_without_orchestrator(self, nonce_manager_no_orchestrator, mock_web3, mock_config):
        """Test NonceManager initialization without orchestrator."""
        assert nonce_manager_no_orchestrator.web3 == mock_web3
        assert nonce_manager_no_orchestrator.account == mock_config
        assert nonce_manager_no_orchestrator.config == mock_config
        assert nonce_manager_no_orchestrator.main_orchestrator is None
        assert nonce_manager_no_orchestrator.db_interface is None
        assert nonce_manager_no_orchestrator.notification_manager is None

    def test_init_orchestrator_without_components(self, mock_web3, mock_config):
        """Test initialization with orchestrator that has no components."""
        orchestrator = MagicMock()
        orchestrator.components = {}
        
        nonce_manager = NonceManager(mock_web3, mock_config, orchestrator)
        
        assert nonce_manager.db_interface is None
        assert nonce_manager.notification_manager is None

    @pytest.mark.asyncio
    async def test_initialize_success(self, nonce_manager, mock_web3):
        """Test successful initialization."""
        await nonce_manager.initialize()
        
        mock_web3.is_connected.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_web3_not_connected(self, nonce_manager, mock_web3):
        """Test initialization when web3 is not connected."""
        mock_web3.is_connected.return_value = False
        
        await nonce_manager.initialize()
        # Should complete without error but log warning

    @pytest.mark.asyncio
    async def test_initialize_web3_error(self, nonce_manager, mock_web3):
        """Test initialization when web3 connection check fails."""
        mock_web3.is_connected.side_effect = Exception("Connection error")
        
        await nonce_manager.initialize()
        # Should complete without error but log error

    @pytest.mark.asyncio
    async def test_initialize_with_persisted_nonce_state(self, nonce_manager, mock_web3):
        """Test initialization with persisted nonce state."""
        nonce_data = {
            "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6": {
                "nonce": 15,
                "chain_id": 1,
                "last_update": time.time()
            }
        }
        nonce_manager.db_interface.load_nonce_state.return_value = nonce_data
        
        await nonce_manager.initialize()
        
        assert "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6" in nonce_manager._nonces
        assert nonce_manager._nonces["0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"] == 15

    @pytest.mark.asyncio
    async def test_initialize_persisted_nonce_different_chain(self, nonce_manager, mock_web3):
        """Test initialization ignores persisted nonce from different chain."""
        nonce_data = {
            "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6": {
                "nonce": 15,
                "chain_id": 137,  # Different chain
                "last_update": time.time()
            }
        }
        nonce_manager.db_interface.load_nonce_state.return_value = nonce_data
        
        await nonce_manager.initialize()
        
        assert "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6" not in nonce_manager._nonces

    @pytest.mark.asyncio
    async def test_initialize_db_load_error(self, nonce_manager):
        """Test initialization handles database load error gracefully."""
        nonce_manager.db_interface.load_nonce_state.side_effect = Exception("DB error")
        
        await nonce_manager.initialize()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_get_onchain_nonce_success(self, nonce_manager, mock_web3):
        """Test successful on-chain nonce retrieval."""
        mock_web3.eth.get_transaction_count.return_value = 42
        
        nonce = await nonce_manager.get_onchain_nonce("0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6")
        
        assert nonce == 42
        mock_web3.eth.get_transaction_count.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_onchain_nonce_no_address(self, nonce_manager):
        """Test get_onchain_nonce with no address provided."""
        with pytest.raises(ValueError, match="Address must be provided"):
            await nonce_manager.get_onchain_nonce(None)

    @pytest.mark.asyncio
    async def test_get_onchain_nonce_retry_success(self, nonce_manager, mock_web3):
        """Test get_onchain_nonce with retry logic."""
        mock_web3.eth.get_transaction_count.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            42
        ]
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            nonce = await nonce_manager.get_onchain_nonce("0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6")
        
        assert nonce == 42
        assert mock_web3.eth.get_transaction_count.call_count == 3

    @pytest.mark.asyncio
    async def test_get_onchain_nonce_permanent_failure(self, nonce_manager, mock_web3):
        """Test get_onchain_nonce permanent failure after retries."""
        mock_web3.eth.get_transaction_count.side_effect = Exception("Permanent error")
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(Exception, match="Permanent error"):
                await nonce_manager.get_onchain_nonce("0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6")
        
        assert mock_web3.eth.get_transaction_count.call_count == 5  # max retries

    @pytest.mark.asyncio
    async def test_get_next_nonce_cache_miss(self, nonce_manager, mock_web3):
        """Test get_next_nonce with cache miss."""
        mock_web3.eth.get_transaction_count.return_value = 50
        
        nonce = await nonce_manager.get_next_nonce("0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6")
        
        assert nonce == 50
        assert "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6" in nonce_manager._nonces

    @pytest.mark.asyncio
    async def test_get_next_nonce_cache_hit(self, nonce_manager):
        """Test get_next_nonce with cache hit."""
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        nonce_manager._nonces[address] = 50
        nonce_manager._last_refresh[address] = time.time()
        
        nonce = await nonce_manager.get_next_nonce(address)
        
        assert nonce == 51
        assert nonce_manager._nonces[address] == 51

    @pytest.mark.asyncio
    async def test_get_next_nonce_cache_expired(self, nonce_manager, mock_web3):
        """Test get_next_nonce with expired cache."""
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        nonce_manager._nonces[address] = 50
        nonce_manager._last_refresh[address] = time.time() - 3600  # 1 hour ago
        mock_web3.eth.get_transaction_count.return_value = 55
        
        nonce = await nonce_manager.get_next_nonce(address)
        
        assert nonce == 55
        assert nonce_manager._nonces[address] == 55

    @pytest.mark.asyncio
    async def test_get_next_nonce_no_address_with_account(self, nonce_manager, mock_web3):
        """Test get_next_nonce without address, using account.address."""
        mock_web3.eth.get_transaction_count.return_value = 30
        
        nonce = await nonce_manager.get_next_nonce()
        
        assert nonce == 30

    @pytest.mark.asyncio
    async def test_get_next_nonce_no_address_no_account(self, mock_web3, mock_config):
        """Test get_next_nonce without address and no account.address."""
        delattr(mock_config, "address")
        nonce_manager = NonceManager(mock_web3, mock_config, None)
        
        with pytest.raises(ValueError, match="No address provided"):
            await nonce_manager.get_next_nonce()

    @pytest.mark.asyncio
    async def test_get_nonce_alias(self, nonce_manager):
        """Test get_nonce as alias for get_next_nonce."""
        with patch.object(nonce_manager, 'get_next_nonce', new_callable=AsyncMock) as mock_get_next:
            mock_get_next.return_value = 42
            
            nonce = await nonce_manager.get_nonce("0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6")
            
            assert nonce == 42
            mock_get_next.assert_called_once_with("0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6")

    @pytest.mark.asyncio
    async def test_reset_nonce(self, nonce_manager, mock_web3):
        """Test reset_nonce functionality."""
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        nonce_manager._nonces[address] = 100
        mock_web3.eth.get_transaction_count.return_value = 105
        
        nonce = await nonce_manager.reset_nonce(address)
        
        assert nonce == 105
        assert nonce_manager._nonces[address] == 105

    @pytest.mark.asyncio
    async def test_reset_nonce_no_address(self, nonce_manager, mock_web3):
        """Test reset_nonce without address."""
        mock_web3.eth.get_transaction_count.return_value = 105
        
        nonce = await nonce_manager.reset_nonce()
        
        assert nonce == 105

    @pytest.mark.asyncio
    async def test_track_transaction(self, nonce_manager, mock_web3):
        """Test transaction tracking."""
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        tx_hash = "0x123456"
        
        with patch.object(nonce_manager, '_monitor_transaction', new_callable=AsyncMock):
            await nonce_manager.track_transaction(tx_hash, 50, address)
        
        assert hasattr(nonce_manager, '_tx_tracking')
        assert tx_hash in nonce_manager._tx_tracking
        assert nonce_manager._tx_tracking[tx_hash]["nonce"] == 50
        assert nonce_manager._tx_tracking[tx_hash]["address"] == address

    @pytest.mark.asyncio
    async def test_track_transaction_no_address(self, nonce_manager):
        """Test track_transaction without address."""
        tx_hash = "0x123456"
        
        with patch.object(nonce_manager, '_monitor_transaction', new_callable=AsyncMock):
            await nonce_manager.track_transaction(tx_hash, 50)
        
        assert tx_hash in nonce_manager._tx_tracking

    @pytest.mark.asyncio
    async def test_track_transaction_no_address_no_account(self, mock_web3, mock_config):
        """Test track_transaction without address and no account.address."""
        delattr(mock_config, "address")
        nonce_manager = NonceManager(mock_web3, mock_config, None)
        
        await nonce_manager.track_transaction("0x123456", 50)
        # Should complete without error but not track

    @pytest.mark.asyncio
    async def test_track_transaction_with_db_storage(self, nonce_manager, mock_web3):
        """Test transaction tracking with database storage."""
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        tx_hash = "0x123456"
        
        with patch.object(nonce_manager, '_monitor_transaction', new_callable=AsyncMock):
            await nonce_manager.track_transaction(tx_hash, 50, address)
        
        nonce_manager.db_interface.store_nonce_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_transaction_db_error(self, nonce_manager, mock_web3):
        """Test transaction tracking handles database error gracefully."""
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        tx_hash = "0x123456"
        nonce_manager.db_interface.store_nonce_state.side_effect = Exception("DB error")
        
        with patch.object(nonce_manager, '_monitor_transaction', new_callable=AsyncMock):
            await nonce_manager.track_transaction(tx_hash, 50, address)
        
        # Should complete without error

    @pytest.mark.asyncio
    async def test_monitor_transaction_confirmed(self, nonce_manager, mock_web3):
        """Test transaction monitoring with confirmed transaction."""
        tx_hash = "0x123456"
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        
        # Setup tracking
        nonce_manager._tx_tracking = {tx_hash: {"status": "pending"}}
        
        # Mock receipt with success status
        mock_web3.eth.get_transaction_receipt.return_value = {"status": 1}
        
        await nonce_manager._monitor_transaction(tx_hash, address)
        
        assert nonce_manager._tx_tracking[tx_hash]["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_monitor_transaction_failed(self, nonce_manager, mock_web3):
        """Test transaction monitoring with failed transaction."""
        tx_hash = "0x123456"
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        
        # Setup tracking
        nonce_manager._tx_tracking = {tx_hash: {"status": "pending"}}
        
        # Mock receipt with failure status
        mock_web3.eth.get_transaction_receipt.return_value = {"status": 0}
        
        with patch.object(nonce_manager, 'reset_nonce', new_callable=AsyncMock) as mock_reset:
            await nonce_manager._monitor_transaction(tx_hash, address)
        
        assert nonce_manager._tx_tracking[tx_hash]["status"] == "failed"
        mock_reset.assert_called_once_with(address)

    @pytest.mark.asyncio
    async def test_monitor_transaction_timeout(self, nonce_manager, mock_web3):
        """Test transaction monitoring with timeout."""
        tx_hash = "0x123456"
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        
        # Setup tracking with old start time
        nonce_manager._tx_tracking = {tx_hash: {"status": "pending"}}
        nonce_manager._tx_timeout = 0.1  # Very short timeout
        
        # Mock no receipt
        mock_web3.eth.get_transaction_receipt.return_value = None
        
        with patch.object(nonce_manager, 'reset_nonce', new_callable=AsyncMock) as mock_reset:
            with patch('time.time', return_value=time.time() + 1000):  # Simulate timeout
                await nonce_manager._monitor_transaction(tx_hash, address)
        
        assert nonce_manager._tx_tracking[tx_hash]["status"] == "timeout"
        mock_reset.assert_called_once_with(address)

    @pytest.mark.asyncio
    async def test_monitor_transaction_cancelled(self, nonce_manager):
        """Test transaction monitoring cancellation."""
        tx_hash = "0x123456"
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        
        nonce_manager._tx_tracking = {tx_hash: {"status": "pending"}}
        
        # Create and immediately cancel the task
        task = asyncio.create_task(nonce_manager._monitor_transaction(tx_hash, address))
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        assert nonce_manager._tx_tracking[tx_hash]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_monitor_transaction_error(self, nonce_manager, mock_web3):
        """Test transaction monitoring with repeated errors."""
        tx_hash = "0x123456"
        address = "0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6"
        
        nonce_manager._tx_tracking = {tx_hash: {"status": "pending"}}
        mock_web3.eth.get_transaction_receipt.side_effect = Exception("Network error")
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            await nonce_manager._monitor_transaction(tx_hash, address)
        
        assert nonce_manager._tx_tracking[tx_hash]["status"] == "error"

    @pytest.mark.asyncio
    async def test_wait_for_transaction_success(self, nonce_manager, mock_web3):
        """Test wait_for_transaction with successful transaction."""
        tx_hash = "0x123456"
        mock_web3.eth.get_transaction_receipt.return_value = {"status": 1}
        
        result = await nonce_manager.wait_for_transaction(tx_hash, timeout=1)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_transaction_timeout(self, nonce_manager, mock_web3):
        """Test wait_for_transaction with timeout."""
        tx_hash = "0x123456"
        mock_web3.eth.get_transaction_receipt.return_value = None
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await nonce_manager.wait_for_transaction(tx_hash, timeout=0.1)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_transaction_exception(self, nonce_manager, mock_web3):
        """Test wait_for_transaction handles exceptions."""
        tx_hash = "0x123456"
        mock_web3.eth.get_transaction_receipt.side_effect = Exception("Network error")
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await nonce_manager.wait_for_transaction(tx_hash, timeout=0.1)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_close_with_db_persistence(self, nonce_manager):
        """Test close with database persistence."""
        nonce_manager._nonces = {"0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6": 50}
        
        await nonce_manager.close()
        
        nonce_manager.db_interface.store_nonce_state.assert_called()
        assert len(nonce_manager._nonces) == 0

    @pytest.mark.asyncio
    async def test_close_db_error(self, nonce_manager):
        """Test close handles database error gracefully."""
        nonce_manager._nonces = {"0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6": 50}
        nonce_manager.db_interface.store_nonce_state.side_effect = Exception("DB error")
        
        await nonce_manager.close()
        
        # Should complete without error
        assert len(nonce_manager._nonces) == 0

    @pytest.mark.asyncio
    async def test_close_without_db(self, nonce_manager_no_orchestrator):
        """Test close without database interface."""
        nonce_manager_no_orchestrator._nonces = {"0x742d35Cc6635C0532925a3b8D8b5A8b3F3C4C7c6": 50}
        
        await nonce_manager_no_orchestrator.close()
        
        assert len(nonce_manager_no_orchestrator._nonces) == 0

    @pytest.mark.asyncio
    async def test_stop_alias(self, nonce_manager):
        """Test stop method as alias for close."""
        with patch.object(nonce_manager, 'close', new_callable=AsyncMock) as mock_close:
            await nonce_manager.stop()
            mock_close.assert_called_once()

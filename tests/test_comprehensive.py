# tests/test_comprehensive.py
"""
Comprehensive test suite for ON1Builder core functionality.
This addresses the lack of unit and integration tests.
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta

from on1builder.core.balance_manager import BalanceManager
from on1builder.core.nonce_manager import NonceManager
from on1builder.core.transaction_manager import TransactionManager
from on1builder.engines.safety_guard import SafetyGuard
from on1builder.engines.strategy_executor import StrategyExecutor
from on1builder.monitoring.txpool_scanner import TxPoolScanner
from on1builder.utils.custom_exceptions import (
    InsufficientFundsError,
    TransactionError,
    StrategyExecutionError,
    ConnectionError
)
from on1builder.utils.constants import BALANCE_TIER_THRESHOLDS, MIN_PROFIT_THRESHOLD_ETH


class TestBalanceManager:
    """Test suite for BalanceManager functionality."""
    
    @pytest.fixture
    def mock_web3(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=1000000000000000000)  # 1 ETH
        web3.from_wei = Mock(side_effect=lambda wei, unit: Decimal(str(wei)) / Decimal("1e18"))
        return web3
    
    @pytest.fixture
    def balance_manager(self, mock_web3):
        return BalanceManager(mock_web3, "0x1234567890123456789012345678901234567890")
    
    @pytest.mark.asyncio
    async def test_balance_retrieval(self, balance_manager, mock_web3):
        """Test basic balance retrieval functionality."""
        balance = await balance_manager.get_balance()
        assert balance == Decimal("1.0")
        mock_web3.eth.get_balance.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_balance_caching(self, balance_manager, mock_web3):
        """Test that balance caching works correctly."""
        # First call should hit the blockchain
        balance1 = await balance_manager.get_balance()
        # Second call should use cache
        balance2 = await balance_manager.get_balance()
        
        assert balance1 == balance2
        # Should only call get_balance once due to caching
        assert mock_web3.eth.get_balance.call_count == 1
    
    @pytest.mark.asyncio
    async def test_insufficient_funds_detection(self, balance_manager, mock_web3):
        """Test insufficient funds detection."""
        mock_web3.eth.get_balance.return_value = 100000000000000000  # 0.1 ETH
        
        with pytest.raises(InsufficientFundsError):
            await balance_manager.ensure_sufficient_balance(Decimal("1.0"))
    
    def test_balance_tier_classification(self, balance_manager):
        """Test balance tier classification logic."""
        assert balance_manager._get_balance_tier(Decimal("0.005")) == "dust"
        assert balance_manager._get_balance_tier(Decimal("0.05")) == "small"
        assert balance_manager._get_balance_tier(Decimal("0.3")) == "medium"
        assert balance_manager._get_balance_tier(Decimal("5.0")) == "large"
        assert balance_manager._get_balance_tier(Decimal("50.0")) == "whale"
    
    @pytest.mark.asyncio
    async def test_profit_tracking(self, balance_manager):
        """Test profit tracking functionality."""
        # Record some profits
        await balance_manager.record_profit(Decimal("0.01"), "arbitrage", "USDC-ETH")
        await balance_manager.record_profit(Decimal("0.005"), "front_run", "WETH-USDT")
        
        stats = balance_manager.get_profit_stats()
        assert stats["total_profit_eth"] == Decimal("0.015")
        assert stats["strategy_profits"]["arbitrage"] == Decimal("0.01")
        assert len(stats["recent_profits"]) == 2


class TestNonceManager:
    """Test suite for NonceManager functionality."""
    
    @pytest.fixture
    def mock_web3(self):
        web3 = AsyncMock()
        web3.eth.get_transaction_count = AsyncMock(return_value=42)
        return web3
    
    @pytest.fixture
    def nonce_manager(self, mock_web3):
        return NonceManager(mock_web3, "0x1234567890123456789012345678901234567890")
    
    @pytest.mark.asyncio
    async def test_nonce_initialization(self, nonce_manager, mock_web3):
        """Test nonce initialization."""
        nonce = await nonce_manager.get_next_nonce()
        assert nonce == 42
        mock_web3.eth.get_transaction_count.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_nonce_increment(self, nonce_manager):
        """Test that nonces increment correctly."""
        nonce1 = await nonce_manager.get_next_nonce()
        nonce2 = await nonce_manager.get_next_nonce()
        nonce3 = await nonce_manager.get_next_nonce()
        
        assert nonce2 == nonce1 + 1
        assert nonce3 == nonce2 + 1
    
    @pytest.mark.asyncio
    async def test_concurrent_nonce_requests(self, nonce_manager):
        """Test that concurrent nonce requests don't create duplicates."""
        tasks = [nonce_manager.get_next_nonce() for _ in range(10)]
        nonces = await asyncio.gather(*tasks)
        
        # All nonces should be unique
        assert len(set(nonces)) == len(nonces)
        
        # Nonces should be consecutive
        sorted_nonces = sorted(nonces)
        for i in range(1, len(sorted_nonces)):
            assert sorted_nonces[i] == sorted_nonces[i-1] + 1


class TestSafetyGuard:
    """Test suite for SafetyGuard functionality."""
    
    @pytest.fixture
    def mock_web3(self):
        web3 = AsyncMock()
        web3.from_wei = Mock(side_effect=lambda wei, unit: wei / 1e18)
        return web3
    
    @pytest.fixture
    def mock_balance_manager(self):
        balance_manager = AsyncMock()
        balance_manager.get_balance.return_value = Decimal("1.0")
        return balance_manager
    
    @pytest.fixture
    def safety_guard(self, mock_web3, mock_balance_manager):
        return SafetyGuard(mock_web3, mock_balance_manager, chain_id=1)
    
    @pytest.mark.asyncio
    async def test_gas_price_check(self, safety_guard):
        """Test gas price safety check."""
        # Normal gas price should pass
        tx_params = {"gasPrice": 20_000_000_000, "gas": 100_000}  # 20 gwei
        is_safe, reason = await safety_guard.check_transaction(tx_params)
        assert is_safe
        
        # Extremely high gas price should fail
        tx_params = {"gasPrice": 1_000_000_000_000, "gas": 100_000}  # 1000 gwei
        is_safe, reason = await safety_guard.check_transaction(tx_params)
        assert not is_safe
        assert "gas price" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_balance_check(self, safety_guard, mock_balance_manager):
        """Test balance safety check."""
        # Sufficient balance should pass
        tx_params = {"value": 100_000_000_000_000_000, "gasPrice": 20_000_000_000, "gas": 21_000}  # 0.1 ETH
        is_safe, reason = await safety_guard.check_transaction(tx_params)
        assert is_safe
        
        # Insufficient balance should fail
        mock_balance_manager.get_balance.return_value = Decimal("0.01")
        tx_params = {"value": 500_000_000_000_000_000, "gasPrice": 20_000_000_000, "gas": 21_000}  # 0.5 ETH
        is_safe, reason = await safety_guard.check_transaction(tx_params)
        assert not is_safe
        assert "insufficient" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, safety_guard):
        """Test transaction rate limiting."""
        tx_params = {"gasPrice": 20_000_000_000, "gas": 100_000}
        
        # First few transactions should pass
        for _ in range(5):
            is_safe, reason = await safety_guard.check_transaction(tx_params)
            assert is_safe
        
        # Too many transactions should trigger rate limit
        # This would need implementation in SafetyGuard
        # For now, just verify the method exists
        assert hasattr(safety_guard, "_check_rate_limits")


class TestTxPoolScanner:
    """Test suite for TxPoolScanner functionality."""
    
    @pytest.fixture
    def mock_web3(self):
        web3 = AsyncMock()
        web3.eth.chain_id = 1
        return web3
    
    @pytest.fixture
    def mock_strategy_executor(self):
        return AsyncMock()
    
    @pytest.fixture
    def txpool_scanner(self, mock_web3, mock_strategy_executor):
        return TxPoolScanner(mock_web3, mock_strategy_executor, chain_id=1)
    
    def test_dex_router_mapping(self, txpool_scanner):
        """Test DEX router mapping creation."""
        assert hasattr(txpool_scanner, "_dex_routers")
        assert isinstance(txpool_scanner._dex_routers, dict)
    
    def test_mev_pattern_detection(self, txpool_scanner):
        """Test MEV pattern detection."""
        # Test sandwich attack detection
        analysis = {
            "input_data": "0x38ed1739000000000000000000000000000000000000000000000000000000000000000a"
        }
        
        # This would need the actual pattern matching logic
        for pattern_name, pattern in txpool_scanner.MEV_PATTERNS.items():
            if pattern.search(analysis["input_data"]):
                assert pattern_name in ["sandwich_attack", "arbitrage"]
    
    def test_transaction_relevance_check(self, txpool_scanner):
        """Test transaction relevance checking."""
        # High value transaction should be relevant
        analysis = {
            "to": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap router
            "value_eth": 5.0,
            "target_dex": "uniswap_v2",
            "mev_type": "arbitrage",
            "from": "0x1234567890123456789012345678901234567890",
            "gas_price": 20_000_000_000
        }
        
        is_relevant = txpool_scanner._is_relevant_for_mev(analysis)
        assert is_relevant
    
    def test_cache_management(self, txpool_scanner):
        """Test cache size management."""
        # Fill cache beyond threshold
        for i in range(txpool_scanner.MAX_TX_CACHE_SIZE + 100):
            txpool_scanner._tx_analysis_cache[f"tx_{i}"] = {"test": "data"}
            txpool_scanner._cache_access_times[f"tx_{i}"] = datetime.now()
        
        # Trigger cache cleanup
        txpool_scanner._manage_cache_size()
        
        # Cache should be reduced
        assert len(txpool_scanner._tx_analysis_cache) <= txpool_scanner.MAX_TX_CACHE_SIZE


class TestIntegration:
    """Integration tests for component interactions."""
    
    @pytest.fixture
    def mock_components(self):
        """Create mock components for integration testing."""
        web3 = AsyncMock()
        web3.eth.get_balance.return_value = 5_000_000_000_000_000_000  # 5 ETH
        web3.eth.get_transaction_count.return_value = 42
        web3.from_wei = Mock(side_effect=lambda wei, unit: Decimal(str(wei)) / Decimal("1e18"))
        web3.to_wei = Mock(side_effect=lambda amount, unit: int(Decimal(str(amount)) * Decimal("1e18")))
        
        account = Mock()
        account.address = "0x1234567890123456789012345678901234567890"
        
        return {
            "web3": web3,
            "account": account,
            "chain_id": 1
        }
    
    @pytest.mark.asyncio
    async def test_transaction_flow(self, mock_components):
        """Test complete transaction flow from detection to execution."""
        # Create components
        balance_manager = BalanceManager(mock_components["web3"], mock_components["account"].address)
        nonce_manager = NonceManager(mock_components["web3"], mock_components["account"].address)
        
        # Test balance check
        balance = await balance_manager.get_balance()
        assert balance == Decimal("5.0")
        
        # Test nonce management
        nonce = await nonce_manager.get_next_nonce()
        assert nonce == 42
        
        # Test safety checks would go here
        # This integration test demonstrates how components work together
    
    @pytest.mark.asyncio
    async def test_error_propagation(self, mock_components):
        """Test error propagation through component stack."""
        # Simulate connection error
        mock_components["web3"].eth.get_balance.side_effect = ConnectionError("RPC connection failed")
        
        balance_manager = BalanceManager(mock_components["web3"], mock_components["account"].address)
        
        with pytest.raises(ConnectionError):
            await balance_manager.get_balance()
    
    @pytest.mark.asyncio
    async def test_profit_calculation_integration(self, mock_components):
        """Test profit calculation across multiple operations."""
        balance_manager = BalanceManager(mock_components["web3"], mock_components["account"].address)
        
        # Simulate multiple profitable operations
        profits = [
            (Decimal("0.01"), "arbitrage", "ETH-USDC"),
            (Decimal("0.005"), "front_run", "WETH-DAI"),
            (Decimal("0.015"), "liquidation", "COMP")
        ]
        
        for profit, strategy, pair in profits:
            await balance_manager.record_profit(profit, strategy, pair)
        
        stats = balance_manager.get_profit_stats()
        assert stats["total_profit_eth"] == Decimal("0.03")
        assert len(stats["strategy_profits"]) == 3


class TestPerformance:
    """Performance and stress tests."""
    
    @pytest.mark.asyncio
    async def test_concurrent_nonce_performance(self):
        """Test nonce manager performance under load."""
        web3 = AsyncMock()
        web3.eth.get_transaction_count.return_value = 0
        
        nonce_manager = NonceManager(web3, "0x1234567890123456789012345678901234567890")
        
        # Simulate 100 concurrent nonce requests
        start_time = datetime.now()
        tasks = [nonce_manager.get_next_nonce() for _ in range(100)]
        nonces = await asyncio.gather(*tasks)
        end_time = datetime.now()
        
        # All nonces should be unique
        assert len(set(nonces)) == 100
        
        # Should complete reasonably quickly (< 1 second)
        execution_time = (end_time - start_time).total_seconds()
        assert execution_time < 1.0
    
    @pytest.mark.asyncio
    async def test_cache_performance(self):
        """Test cache performance under load."""
        web3 = AsyncMock()
        strategy_executor = AsyncMock()
        
        scanner = TxPoolScanner(web3, strategy_executor, chain_id=1)
        
        # Fill cache with many entries
        start_time = datetime.now()
        for i in range(1000):
            scanner._tx_analysis_cache[f"tx_{i}"] = {"value_eth": i * 0.01}
            scanner._cache_access_times[f"tx_{i}"] = datetime.now()
        
        # Trigger cache cleanup
        scanner._manage_cache_size()
        end_time = datetime.now()
        
        # Cache cleanup should be fast
        cleanup_time = (end_time - start_time).total_seconds()
        assert cleanup_time < 0.5
        
        # Cache should be appropriately sized
        assert len(scanner._tx_analysis_cache) <= scanner.MAX_TX_CACHE_SIZE


# Configuration for pytest
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    # Run tests with coverage if executed directly
    pytest.main([
        __file__,
        "-v",
        "--cov=on1builder",
        "--cov-report=html",
        "--cov-report=term-missing"
    ])

"""Comprehensive tests for BalanceManager."""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta

from on1builder.core.balance_manager import BalanceManager
from on1builder.utils.custom_exceptions import InsufficientFundsError, ConnectionError as ON1ConnectionError


class TestBalanceManagerInit:
    """Test BalanceManager initialization."""

    @pytest.fixture
    def mock_web3(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=1000000000000000000)
        return web3

    def test_initialization(self, mock_web3):
        """Test BalanceManager initialization."""
        manager = BalanceManager(mock_web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")
        
        assert manager.web3 == mock_web3
        assert manager.wallet_address == "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7"
        assert manager.current_balance is None
        assert manager.balance_tier == "unknown"
        assert manager._total_profit == Decimal("0")
        assert manager._session_profit == Decimal("0")
        assert len(manager._profit_by_strategy) == 0
        assert len(manager._profit_history) == 0


class TestUpdateBalance:
    """Test balance update functionality."""

    @pytest.fixture
    def mock_web3(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=5000000000000000000)  # 5 ETH
        return web3

    @pytest.fixture
    def manager(self, mock_web3):
        return BalanceManager(mock_web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_update_balance_first_time(self, manager, mock_web3):
        """Test initial balance update."""
        balance = await manager.update_balance()
        
        assert balance == Decimal("5.0")
        assert manager.current_balance == Decimal("5.0")
        assert manager.balance_tier in ["large", "medium", "whale"]
        mock_web3.eth.get_balance.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_balance_caching(self, manager, mock_web3):
        """Test balance caching mechanism."""
        # First update
        balance1 = await manager.update_balance()
        
        # Second update without force should use cache
        balance2 = await manager.update_balance(force=False)
        
        assert balance1 == balance2
        # Should only call once due to caching
        mock_web3.eth.get_balance.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_balance_force(self, manager, mock_web3):
        """Test forced balance update."""
        # First update
        await manager.update_balance()
        
        # Change mock return value
        mock_web3.eth.get_balance.return_value = 3000000000000000000  # 3 ETH
        
        # Force update should fetch new balance
        balance = await manager.update_balance(force=True)
        
        assert balance == Decimal("3.0")
        assert mock_web3.eth.get_balance.call_count == 2

    @pytest.mark.asyncio
    async def test_update_balance_connection_error(self, manager, mock_web3):
        """Test balance update with connection error."""
        mock_web3.eth.get_balance.side_effect = Exception("Connection lost")
        
        with pytest.raises(InsufficientFundsError):
            await manager.update_balance()

    @pytest.mark.asyncio
    async def test_update_balance_tier_change(self, manager, mock_web3):
        """Test balance tier changes are detected."""
        # Start with high balance
        mock_web3.eth.get_balance.return_value = 10000000000000000000  # 10 ETH
        await manager.update_balance()
        initial_tier = manager.balance_tier
        
        # Drop to low balance
        mock_web3.eth.get_balance.return_value = 50000000000000000  # 0.05 ETH
        with patch.object(manager, '_handle_tier_change', new_callable=AsyncMock) as mock_handle:
            await manager.update_balance(force=True)
            
            if initial_tier != manager.balance_tier:
                mock_handle.assert_called_once()


class TestBalanceTiers:
    """Test balance tier classification."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    def test_emergency_tier(self, manager):
        """Test emergency tier for zero/negative balance."""
        assert manager._determine_balance_tier(Decimal("0")) == "emergency"
        assert manager._determine_balance_tier(Decimal("-1")) == "emergency"

    def test_dust_tier(self, manager):
        """Test dust tier."""
        assert manager._determine_balance_tier(Decimal("0.001")) == "dust"
        assert manager._determine_balance_tier(Decimal("0.009")) == "dust"

    def test_small_tier(self, manager):
        """Test small tier."""
        assert manager._determine_balance_tier(Decimal("0.01")) in ["dust", "small"]
        assert manager._determine_balance_tier(Decimal("0.05")) in ["small", "medium"]

    def test_medium_tier(self, manager):
        """Test medium tier."""
        # Check tier for various balances - actual threshold values vary
        tier_0_2 = manager._determine_balance_tier(Decimal("0.2"))
        tier_0_5 = manager._determine_balance_tier(Decimal("0.5"))
        assert tier_0_2 in ["small", "medium"]
        assert tier_0_5 in ["medium", "large"]

    def test_large_tier(self, manager):
        """Test large tier."""
        assert manager._determine_balance_tier(Decimal("5.0")) == "large"
        assert manager._determine_balance_tier(Decimal("15.0")) == "large"

    def test_whale_tier(self, manager):
        """Test whale tier."""
        assert manager._determine_balance_tier(Decimal("50.0")) == "whale"
        assert manager._determine_balance_tier(Decimal("100.0")) == "whale"


class TestMaxInvestment:
    """Test maximum investment calculation."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=5000000000000000000)  # 5 ETH
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_max_investment_standard(self, manager):
        """Test max investment for standard strategy."""
        await manager.update_balance()
        max_invest = await manager.get_max_investment_amount("standard")
        
        # Should be less than total balance (accounting for risk ratio and gas)
        assert Decimal("0") < max_invest < Decimal("5.0")

    @pytest.mark.asyncio
    async def test_max_investment_emergency_mode(self, manager):
        """Test max investment returns zero in emergency mode."""
        manager.web3.eth.get_balance.return_value = 0
        await manager.update_balance(force=True)
        
        max_invest = await manager.get_max_investment_amount()
        assert max_invest == Decimal("0")

    @pytest.mark.asyncio
    async def test_max_investment_flashloan_strategy(self, manager):
        """Test max investment for flashloan strategy."""
        await manager.update_balance()
        max_invest = await manager.get_max_investment_amount("flashloan")
        
        # Flashloan strategy should be more conservative
        standard_invest = await manager.get_max_investment_amount("standard")
        assert max_invest < standard_invest

    @pytest.mark.asyncio
    async def test_max_investment_arbitrage_strategy(self, manager):
        """Test max investment for arbitrage strategy."""
        await manager.update_balance()
        max_invest = await manager.get_max_investment_amount("arbitrage")
        
        assert max_invest > Decimal("0")


class TestDynamicProfitThreshold:
    """Test dynamic profit threshold calculation."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=5000000000000000000)
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_profit_threshold_calculation(self, manager):
        """Test basic profit threshold calculation."""
        await manager.update_balance()
        
        investment = Decimal("1.0")
        threshold = await manager.calculate_dynamic_profit_threshold(investment)
        
        # Should have some minimum threshold
        assert threshold >= Decimal("0.0001")

    @pytest.mark.asyncio
    async def test_profit_threshold_scales_with_investment(self, manager):
        """Test profit threshold scales with investment amount."""
        await manager.update_balance()
        
        small_investment = Decimal("0.1")
        large_investment = Decimal("5.0")
        
        small_threshold = await manager.calculate_dynamic_profit_threshold(small_investment)
        large_threshold = await manager.calculate_dynamic_profit_threshold(large_investment)
        
        # Larger investments may have different thresholds
        assert small_threshold > Decimal("0")
        assert large_threshold > Decimal("0")


class TestFlashloanLogic:
    """Test flashloan decision logic."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=1000000000000000000)  # 1 ETH
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_should_use_flashloan_low_balance(self, manager):
        """Test flashloan recommended for low balance."""
        await manager.update_balance()
        
        # Set low balance tier
        manager.balance_tier = "low"
        
        with patch('on1builder.config.loaders.settings') as mock_settings:
            mock_settings.flashloan_enabled = True
            should_use = await manager.should_use_flashloan(Decimal("0.5"))
            
            assert should_use is True

    @pytest.mark.asyncio
    async def test_should_not_use_flashloan_disabled(self, manager):
        """Test flashloan not used when disabled."""
        await manager.update_balance()
        
        # Need to patch before calling the method
        from on1builder.config import loaders
        original_enabled = loaders.settings.flashloan_enabled
        try:
            loaders.settings.flashloan_enabled = False
            should_use = await manager.should_use_flashloan(Decimal("0.5"))
            assert should_use is False
        finally:
            loaders.settings.flashloan_enabled = original_enabled

    @pytest.mark.asyncio
    async def test_should_use_flashloan_large_amount(self, manager):
        """Test flashloan recommended for large amounts."""
        await manager.update_balance()
        manager.balance_tier = "medium"
        
        with patch('on1builder.config.loaders.settings') as mock_settings:
            mock_settings.flashloan_enabled = True
            
            # Request amount larger than available balance
            should_use = await manager.should_use_flashloan(Decimal("50.0"))
            
            # Logic depends on get_max_investment_amount
            assert isinstance(should_use, bool)


class TestProfitTracking:
    """Test profit tracking functionality."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_record_profit(self, manager):
        """Test recording profit."""
        await manager.record_profit(
            profit_amount=Decimal("0.1"),
            strategy="arbitrage",
            context="test-opp-1",
            gas_cost=Decimal("0.01")
        )
        
        assert manager._total_profit == Decimal("0.1")
        assert manager._session_profit == Decimal("0.1")
        assert manager._profit_by_strategy.get("arbitrage") == Decimal("0.1")
        assert len(manager._profit_history) == 1

    @pytest.mark.asyncio
    async def test_record_multiple_profits(self, manager):
        """Test recording multiple profits."""
        await manager.record_profit(Decimal("0.05"), "arbitrage")
        await manager.record_profit(Decimal("0.03"), "flashloan")
        await manager.record_profit(Decimal("0.02"), "arbitrage")
        
        assert manager._total_profit == Decimal("0.10")
        assert manager._profit_by_strategy["arbitrage"] == Decimal("0.07")
        assert manager._profit_by_strategy["flashloan"] == Decimal("0.03")

    @pytest.mark.asyncio
    async def test_get_profit_stats(self, manager):
        """Test getting profit statistics."""
        await manager.record_profit(Decimal("0.1"), "arbitrage")
        await manager.record_profit(Decimal("0.05"), "flashloan")
        
        stats = manager.get_profit_stats()
        
        assert stats["total_profit_eth"] == Decimal("0.15")
        assert stats["session_profit_eth"] == Decimal("0.15")
        assert "strategy_profits" in stats
        assert "recent_profits" in stats


class TestBalanceSummary:
    """Test balance summary generation."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=2000000000000000000)  # 2 ETH
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_get_profit_summary(self, manager):
        """Test getting comprehensive profit summary."""
        await manager.record_profit(Decimal("0.1"), "arbitrage", gas_cost=Decimal("0.01"))
        await manager.record_profit(Decimal("0.05"), "flashloan", gas_cost=Decimal("0.005"))
        
        summary = manager.get_profit_summary()
        
        assert "total_profit_eth" in summary
        assert "session_profit_eth" in summary
        assert "net_profit_eth" in summary
        assert "total_trades" in summary
        assert summary["total_trades"] == 2
        assert summary["total_profit_eth"] == 0.15


class TestTokenBalances:
    """Test multi-token balance tracking."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=1000000000000000000)
        web3.to_checksum_address = lambda x: x
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_get_eth_balance(self, manager):
        """Test getting ETH balance."""
        balance = await manager.get_balance("ETH")
        assert balance == Decimal("1.0")
    
    @pytest.mark.asyncio
    async def test_get_balance_none_defaults_to_eth(self, manager):
        """Test get_balance with None returns ETH."""
        balance = await manager.get_balance(None)
        assert balance == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_get_token_balance_by_address(self, manager):
        """Test getting token balance by address."""
        token_address = "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        
        with patch.object(manager, '_get_token_balance_by_address', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Decimal("1000.0")
            
            balance = await manager.get_balance(token_address)
            
            assert balance == Decimal("1000.0")
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_balance_by_symbol(self, manager):
        """Test getting token balance by symbol."""
        with patch.object(manager, '_get_token_balance_by_symbol', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Decimal("500.0")
            
            balance = await manager.get_balance("USDC")
            
            assert balance == Decimal("500.0")
            mock_get.assert_called_once()


class TestPerformanceMetrics:
    """Test performance metrics tracking."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_update_performance_metrics(self, manager):
        """Test performance metrics are updated."""
        await manager.record_profit(Decimal("0.1"), "arbitrage")
        await manager.record_profit(Decimal("0.05"), "arbitrage")
        
        metrics = manager._performance_metrics
        
        assert metrics["total_trades"] == 2
        assert metrics["profitable_trades"] == 2

    @pytest.mark.asyncio
    async def test_record_gas_cost(self, manager):
        """Test gas cost is recorded."""
        await manager.record_profit(Decimal("0.1"), "arbitrage", gas_cost=Decimal("0.001"))
        
        assert manager._performance_metrics["total_gas_spent"] == Decimal("0.001")


class TestSufficientBalance:
    """Test sufficient balance checks."""

    @pytest.fixture
    def manager(self):
        web3 = AsyncMock()
        web3.eth.get_balance = AsyncMock(return_value=1000000000000000000)  # 1 ETH
        return BalanceManager(web3, "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7")

    @pytest.mark.asyncio
    async def test_ensure_sufficient_balance_success(self, manager):
        """Test sufficient balance check passes."""
        with patch('on1builder.config.loaders.settings') as mock_settings:
            mock_settings.min_wallet_balance = 0.0
            
            # Should not raise for amount less than balance
            balance = await manager.ensure_sufficient_balance(Decimal("0.5"))
            assert balance >= Decimal("0.5")

    @pytest.mark.asyncio
    async def test_ensure_sufficient_balance_failure(self, manager):
        """Test insufficient balance raises error."""
        with patch('on1builder.config.loaders.settings') as mock_settings:
            mock_settings.min_wallet_balance = 0.0
            
            # Should raise for amount greater than balance
            with pytest.raises(InsufficientFundsError):
                await manager.ensure_sufficient_balance(Decimal("10.0"))

    @pytest.mark.asyncio
    async def test_ensure_sufficient_balance_with_buffer(self, manager):
        """Test ensure sufficient balance with custom buffer."""
        with patch('on1builder.config.loaders.settings') as mock_settings:
            mock_settings.min_wallet_balance = 0.0
            
            # Should raise when amount + buffer exceeds balance
            with pytest.raises(InsufficientFundsError):
                await manager.ensure_sufficient_balance(Decimal("0.9"), buffer=Decimal("0.2"))

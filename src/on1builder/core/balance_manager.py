# src/on1builder/core/balance_manager.py
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta

from web3 import AsyncWeb3

from on1builder.config.loaders import settings
from on1builder.utils.custom_exceptions import InsufficientFundsError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService
from on1builder.utils.constants import (
    BALANCE_TIER_THRESHOLDS,
    MIN_PROFIT_THRESHOLD_ETH,
    BALANCE_CACHE_DURATION,
    LOW_BALANCE_THRESHOLD_ETH
)

logger = get_logger(__name__)

class BalanceManager:
    """
    Enhanced balance manager with sophisticated profit tracking, 
    multi-token support, and intelligent caching strategies.
    """
    
    # Investment percentage limits by tier
    TIER_INVESTMENT_LIMITS = {
        "dust": Decimal("0.3"),
        "small": Decimal("0.5"),
        "medium": Decimal("0.7"),
        "large": Decimal("0.8"),
        "whale": Decimal("0.9")
    }

    def __init__(self, web3: AsyncWeb3, wallet_address: str):
        self.web3 = web3
        self.wallet_address = wallet_address
        self.current_balance: Optional[Decimal] = None
        self.balance_tier: str = "unknown"
        self.notification_service = NotificationService()
        
        # Enhanced locking and caching
        self._balance_lock = asyncio.Lock()
        self._token_lock = asyncio.Lock()
        self._last_balance_check = 0
        self._token_balance_cache: Dict[str, Tuple[Decimal, float]] = {}
        
        # Enhanced profit tracking with granular metrics
        self._total_profit: Decimal = Decimal("0")
        self._session_profit: Decimal = Decimal("0")
        self._profit_by_strategy: Dict[str, Decimal] = {}
        self._profit_history: List[Dict] = []
        self._performance_metrics = {
            "total_trades": 0,
            "profitable_trades": 0,
            "avg_profit_per_trade": Decimal("0"),
            "max_profit": Decimal("0"),
            "total_gas_spent": Decimal("0")
        }
        
        # Multi-token balance tracking
        self.balances: Dict[str, Decimal] = {}
        
        logger.info(f"Enhanced BalanceManager initialized for wallet: {wallet_address}")

    async def update_balance(self, force: bool = False) -> Decimal:
        """Enhanced balance update with intelligent caching."""
        import time
        
        async with self._balance_lock:
            current_time = time.time()
            
            # Use cache if not forcing update and cache is fresh
            if not force and self.current_balance is not None:
                if current_time - self._last_balance_check < self.BALANCE_CACHE_DURATION:
                    return self.current_balance
            
            try:
                balance_wei = await self.web3.eth.get_balance(self.wallet_address)
                new_balance = Decimal(str(balance_wei)) / Decimal("1e18")
                
                # Update balance and cache timestamp
                old_balance = self.current_balance
                self.current_balance = new_balance
                self._last_balance_check = current_time
                
                # Update balance tier if changed
                old_tier = self.balance_tier
                self.balance_tier = self._determine_balance_tier(new_balance)
                
                # Handle tier changes
                if old_tier != self.balance_tier and old_tier != "unknown":
                    await self._handle_tier_change(old_tier, self.balance_tier)
                
                # Log significant balance changes
                if old_balance and abs(new_balance - old_balance) > Decimal("0.01"):
                    change = new_balance - old_balance
                    logger.info(f"Balance change: {change:+.6f} ETH (now: {new_balance:.6f} ETH)")
                
                logger.debug(f"Balance updated: {new_balance:.6f} ETH (tier: {self.balance_tier})")
                return new_balance
                
            except Exception as e:
                logger.error(f"Failed to update balance: {e}")
                if self.current_balance is None:
                    raise InsufficientFundsError("Unable to determine wallet balance")
                return self.current_balance

    def _determine_balance_tier(self, balance: Decimal) -> str:
        """Enhanced balance tier determination with configurable thresholds."""
        for tier, threshold in reversed(list(self.TIER_THRESHOLDS.items())):
            if balance >= threshold:
                return tier
        return "emergency"

    async def _handle_tier_change(self, old_tier: str, new_tier: str):
        """Handles balance tier changes and sends notifications."""
        level = "INFO"
        if new_tier == "emergency":
            level = "CRITICAL"
        elif new_tier == "low":
            level = "WARNING"
        
        await self.notification_service.send_alert(
            title=f"Balance Tier Changed: {old_tier} → {new_tier}",
            message=f"Wallet balance tier changed from {old_tier} to {new_tier}. Current balance: {self.current_balance:.6f} ETH",
            level=level,
            details={
                "old_tier": old_tier,
                "new_tier": new_tier,
                "balance": float(self.current_balance),
                "wallet": self.wallet_address
            }
        )

    async def get_max_investment_amount(self, strategy_type: str = "standard") -> Decimal:
        """
        Returns the maximum amount that can be safely invested based on current balance and strategy.
        """
        await self.update_balance()
        
        if self.balance_tier == "emergency":
            return Decimal("0")  # No trading in emergency mode
        
        base_risk_ratio = Decimal(str(settings.balance_risk_ratio))
        
        # Adjust risk ratio based on balance tier and strategy
        risk_multipliers = {
            "low": Decimal("0.5"),      # 50% of normal risk
            "medium": Decimal("1.0"),   # Normal risk
            "high": Decimal("1.2")      # 20% higher risk
        }
        
        strategy_multipliers = {
            "flashloan": Decimal("0.1"),    # Very conservative for flashloans
            "arbitrage": Decimal("0.8"),    # Conservative for arbitrage
            "mev": Decimal("1.0"),          # Normal for MEV
            "sandwich": Decimal("0.6")      # More conservative for sandwich attacks
        }
        
        tier_multiplier = risk_multipliers.get(self.balance_tier, Decimal("1.0"))
        strategy_multiplier = strategy_multipliers.get(strategy_type, Decimal("1.0"))
        
        max_investment = self.current_balance * base_risk_ratio * tier_multiplier * strategy_multiplier
        
        # Reserve gas money - estimate for 10 transactions
        gas_reserve = Decimal("0.01")  # 0.01 ETH gas reserve
        
        return max(Decimal("0"), max_investment - gas_reserve)

    async def calculate_dynamic_profit_threshold(self, investment_amount: Decimal) -> Decimal:
        """
        Calculates dynamic profit thresholds based on balance tier and investment amount.
        Lower balances need any profit, higher balances can afford to be pickier.
        """
        await self.update_balance()
        
        base_min_profit = Decimal(str(settings.min_profit_eth))
        percentage_threshold = Decimal(str(settings.min_profit_percentage)) / Decimal("100")
        
        if not settings.dynamic_profit_scaling:
            return base_min_profit
        
        # Calculate percentage-based threshold
        percentage_profit = investment_amount * percentage_threshold
        
        # Balance tier adjustments
        tier_adjustments = {
            "emergency": Decimal("0"),      # Any profit is good
            "low": Decimal("0.1"),          # 10% of base requirement
            "medium": Decimal("1.0"),       # Full requirement
            "high": Decimal("1.5")          # 50% higher requirement
        }
        
        tier_multiplier = tier_adjustments.get(self.balance_tier, Decimal("1.0"))
        adjusted_base = base_min_profit * tier_multiplier
        
        # Use the higher of percentage-based or adjusted base, but never below 0.0001 ETH
        final_threshold = max(
            Decimal("0.0001"),  # Minimum to cover gas
            min(adjusted_base, percentage_profit)
        )
        
        logger.debug(f"Dynamic profit threshold: {final_threshold:.6f} ETH for investment: {investment_amount:.6f} ETH")
        return final_threshold

    async def should_use_flashloan(self, required_amount: Decimal) -> bool:
        """
        Determines if a flashloan should be used based on balance and amount needed.
        """
        if not settings.flashloan_enabled:
            return False
        
        await self.update_balance()
        
        if self.balance_tier in ["emergency", "low"]:
            return True  # Use flashloans when balance is low
        
        available_amount = await self.get_max_investment_amount("flashloan")
        
        # Use flashloan if we need more than 80% of our available balance
        return required_amount > (available_amount * Decimal("0.8"))

    async def calculate_optimal_gas_price(self, expected_profit: Decimal) -> Tuple[int, bool]:
        """
        Calculates optimal gas price based on expected profit and balance tier.
        Returns (gas_price_gwei, should_proceed)
        """
        max_gas_percentage = Decimal(str(settings.max_gas_fee_percentage)) / Decimal("100")
        max_gas_fee = expected_profit * max_gas_percentage
        
        # Estimate gas cost at current market price
        try:
            current_gas_price = await self.web3.eth.gas_price
            gas_limit = settings.default_gas_limit
            estimated_gas_cost_wei = current_gas_price * gas_limit
            estimated_gas_cost_eth = Decimal(str(estimated_gas_cost_wei)) / Decimal("1e18")
            
            if estimated_gas_cost_eth > max_gas_fee:
                # Gas too expensive relative to profit
                if self.balance_tier == "emergency":
                    # In emergency mode, accept higher gas if profit still positive
                    return int(current_gas_price / 1e9), estimated_gas_cost_eth < expected_profit
                else:
                    return 0, False
            
            # Optimize gas price based on balance tier
            tier_gas_multipliers = {
                "emergency": 1.5,  # Pay more to ensure execution
                "low": 1.2,        # Slightly higher for faster execution
                "medium": 1.0,     # Market rate
                "high": 0.9        # Can afford to wait
            }
            
            multiplier = tier_gas_multipliers.get(self.balance_tier, 1.0)
            optimal_gas_price = int((current_gas_price * multiplier) / 1e9)
            
            # Cap at settings maximum
            optimal_gas_price = min(optimal_gas_price, settings.max_gas_price_gwei)
            
            return optimal_gas_price, True
            
        except Exception as e:
            logger.error(f"Failed to calculate optimal gas price: {e}")
            return settings.fallback_gas_price_gwei, True

    async def get_balance(self, token_identifier: Optional[str] = None, force_refresh: bool = False) -> Decimal:
        """
        Enhanced balance retrieval supporting both token symbols and addresses.
        
        Args:
            token_identifier: Token symbol (e.g., 'ETH', 'USDC') or contract address. 
                            If None, returns ETH balance.
            force_refresh: If True, bypasses cache and queries blockchain directly
        
        Returns:
            Token balance as Decimal
        """
        if token_identifier is None or token_identifier.upper() == 'ETH':
            await self.update_balance(force=force_refresh)
            return self.current_balance or Decimal("0")
        
        # Check if it's a contract address (starts with 0x and is 42 chars long)
        if token_identifier.startswith('0x') and len(token_identifier) == 42:
            return await self._get_token_balance_by_address(token_identifier, force_refresh)
        else:
            # Treat as token symbol
            return await self._get_token_balance_by_symbol(token_identifier.upper(), force_refresh)
    
    async def _get_token_balance_by_symbol(self, token_symbol: str, force_refresh: bool = False) -> Decimal:
        """Get token balance using symbol lookup."""
        import time
        
        # Check cache first
        if not force_refresh:
            cached_balance = self._token_balance_cache.get(token_symbol)
            if cached_balance:
                balance, timestamp = cached_balance
                if (time.time() - timestamp) < self.TOKEN_CACHE_DURATION:
                    return balance
        
        try:
            from on1builder.integrations.abi_registry import ABIRegistry
            abi_registry = ABIRegistry()
            
            # Get chain ID
            chain_id = await self._get_chain_id()
            
            # Get token contract address
            token_address = abi_registry.get_token_address(token_symbol, chain_id)
            if not token_address:
                logger.warning(f"Token {token_symbol} not found in registry for chain {chain_id}")
                self._cache_token_balance(token_symbol, Decimal("0"))
                return Decimal("0")
            
            return await self._get_token_balance_by_address(token_address, force_refresh, token_symbol)
            
        except Exception as e:
            logger.error(f"Failed to get balance for token {token_symbol}: {e}")
            self._cache_token_balance(token_symbol, Decimal("0"))
            return Decimal("0")
    
    async def _get_token_balance_by_address(self, token_address: str, force_refresh: bool = False, symbol: Optional[str] = None) -> Decimal:
        """Get token balance using contract address."""
        try:
            from on1builder.integrations.abi_registry import ABIRegistry
            abi_registry = ABIRegistry()
            
            # Get ERC-20 contract ABI
            erc20_abi = abi_registry.get_abi("ERC20") or abi_registry.get_abi("erc20_abi")
            if not erc20_abi:
                logger.error("ERC-20 ABI not found in registry")
                return Decimal("0")
            
            # Create contract instance
            contract = self.web3.eth.contract(
                address=self.web3.to_checksum_address(token_address),
                abi=erc20_abi
            )
            
            # Get balance and decimals concurrently
            balance_wei, decimals = await asyncio.gather(
                contract.functions.balanceOf(self.wallet_address).call(),
                self._get_token_decimals(contract),
                return_exceptions=True
            )
            
            if isinstance(balance_wei, Exception):
                raise balance_wei
            if isinstance(decimals, Exception):
                decimals = 18  # Default fallback
            
            # Convert to decimal
            balance = Decimal(str(balance_wei)) / Decimal(str(10 ** decimals))
            
            # Cache the result
            cache_key = symbol or token_address
            self._cache_token_balance(cache_key, balance)
            
            return balance
            
        except Exception as e:
            logger.error(f"Failed to get balance for token {token_address}: {e}")
            return Decimal("0")
    
    async def _get_token_decimals(self, contract) -> int:
        """Get token decimals with fallback."""
        try:
            return await contract.functions.decimals().call()
        except Exception:
            logger.warning("Could not get token decimals, using default 18")
            return 18
    
    async def _get_chain_id(self) -> int:
        """Get chain ID with proper async handling."""
        try:
            return await self.web3.eth.chain_id
        except TypeError:
            # Fallback for sync chain_id property
            return self.web3.eth.chain_id
    
    def _cache_token_balance(self, identifier: str, balance: Decimal) -> None:
        """Cache token balance with timestamp."""
        import time
        self._token_balance_cache[identifier] = (balance, time.time())
        if not identifier.startswith('0x'):  # Only update balances dict for symbols
            self.balances[identifier] = balance

    async def get_balances(self, token_identifiers: List[str]) -> Dict[str, Decimal]:
        """
        Enhanced method to get balances for multiple tokens efficiently using concurrent calls.
        
        Args:
            token_identifiers: List of token symbols or contract addresses
            
        Returns:
            Dictionary mapping token identifiers to their balances
        """
        if not token_identifiers:
            return {}
        
        # Use asyncio.gather for concurrent balance queries
        tasks = [self.get_balance(identifier) for identifier in token_identifiers]
        balances_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        result = {}
        for identifier, balance in zip(token_identifiers, balances_list):
            if isinstance(balance, Exception):
                logger.warning(f"Failed to get balance for {identifier}: {balance}")
                result[identifier] = Decimal("0")
            else:
                result[identifier] = balance
        
        return result
    
    def get_total_profit(self) -> Decimal:
        """Returns the total profit earned across all strategies."""
        return self._total_profit

    def get_session_profit(self) -> Decimal:
        """Returns the profit earned in the current session."""
        return self._session_profit

    def get_profit_by_strategy(self) -> Dict[str, Decimal]:
        """Returns profit breakdown by strategy."""
        return self._profit_by_strategy.copy()

    async def record_profit(self, profit_amount: Decimal, strategy: str, gas_cost: Decimal = Decimal("0")):
        """Enhanced profit recording with comprehensive analytics."""
        if profit_amount < self.MIN_PROFIT_THRESHOLD:
            return  # Don't track very small profits
        
        # Update profit tracking
        self._total_profit += profit_amount
        self._session_profit += profit_amount
        
        if strategy not in self._profit_by_strategy:
            self._profit_by_strategy[strategy] = Decimal("0")
        self._profit_by_strategy[strategy] += profit_amount
        
        # Update performance metrics
        self._performance_metrics["total_trades"] += 1
        if profit_amount > 0:
            self._performance_metrics["profitable_trades"] += 1
        self._performance_metrics["total_gas_spent"] += gas_cost
        
        # Calculate average profit per trade
        total_trades = self._performance_metrics["total_trades"]
        if total_trades > 0:
            self._performance_metrics["avg_profit_per_trade"] = self._total_profit / total_trades
        
        # Update max profit
        if profit_amount > self._performance_metrics["max_profit"]:
            self._performance_metrics["max_profit"] = profit_amount
        
        # Add to profit history
        import time
        profit_record = {
            "timestamp": time.time(),
            "strategy": strategy,
            "profit": float(profit_amount),
            "gas_cost": float(gas_cost),
            "net_profit": float(profit_amount - gas_cost),
            "balance_after": float(self.current_balance or 0)
        }
        self._profit_history.append(profit_record)
        
        # Keep only recent history (last 1000 trades)
        if len(self._profit_history) > 1000:
            self._profit_history = self._profit_history[-1000:]
        
        logger.info(f"Profit recorded: {profit_amount:.6f} ETH from {strategy} (net: {profit_amount - gas_cost:.6f} ETH)")
    
    def get_profit_summary(self) -> Dict[str, Any]:
        """Get comprehensive profit summary with enhanced metrics."""
        total_trades = self._performance_metrics["total_trades"]
        profitable_trades = self._performance_metrics["profitable_trades"]
        total_gas = self._performance_metrics["total_gas_spent"]
        
        # Calculate derived metrics
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0
        net_profit = self._total_profit - total_gas
        roi_percent = (net_profit / total_gas * 100) if total_gas > 0 else 0.0
        
        return {
            "total_profit_eth": float(self._total_profit),
            "session_profit_eth": float(self._session_profit),
            "net_profit_eth": float(net_profit),
            "total_trades": total_trades,
            "profitable_trades": profitable_trades,
            "win_rate_percent": round(win_rate, 2),
            "avg_profit_per_trade": float(self._performance_metrics["avg_profit_per_trade"]),
            "max_profit": float(self._performance_metrics["max_profit"]),
            "total_gas_spent": float(total_gas),
            "roi_percent": round(roi_percent, 2),
            "profit_by_strategy": {k: float(v) for k, v in self._profit_by_strategy.items()},
            "current_balance": float(self.current_balance or 0),
            "balance_tier": self.balance_tier
        }
    
    def get_recent_performance(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance metrics for recent period."""
        import time
        cutoff_time = time.time() - (hours * 3600)
        
        recent_trades = [
            trade for trade in self._profit_history 
            if trade["timestamp"] > cutoff_time
        ]
        
        if not recent_trades:
            return {
                "period_hours": hours,
                "trades": 0,
                "total_profit": 0.0,
                "avg_profit": 0.0,
                "win_rate": 0.0
            }
        
        total_profit = sum(trade["net_profit"] for trade in recent_trades)
        profitable_trades = sum(1 for trade in recent_trades if trade["net_profit"] > 0)
        
        return {
            "period_hours": hours,
            "trades": len(recent_trades),
            "total_profit": total_profit,
            "avg_profit": total_profit / len(recent_trades),
            "win_rate": (profitable_trades / len(recent_trades)) * 100,
            "strategy_breakdown": self._analyze_strategy_performance(recent_trades)
        }
    
    def _analyze_strategy_performance(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Analyze performance by strategy."""
        strategy_stats = {}
        
        for trade in trades:
            strategy = trade["strategy"]
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {
                    "trades": 0,
                    "total_profit": 0.0,
                    "profitable_trades": 0
                }
            
            stats = strategy_stats[strategy]
            stats["trades"] += 1
            stats["total_profit"] += trade["net_profit"]
            if trade["net_profit"] > 0:
                stats["profitable_trades"] += 1
        
        # Calculate additional metrics
        for strategy, stats in strategy_stats.items():
            if stats["trades"] > 0:
                stats["avg_profit"] = stats["total_profit"] / stats["trades"]
                stats["win_rate"] = (stats["profitable_trades"] / stats["trades"]) * 100
            else:
                stats["avg_profit"] = 0.0
                stats["win_rate"] = 0.0
        
        return strategy_stats

    def get_total_balance_usd(self) -> Decimal:
        """Calculate total portfolio value in USD (mock implementation)."""
        # In a real implementation, this would use current market prices
        # For now, return ETH balance as a proxy
        eth_balance = self.current_balance or Decimal("0")
        
        # Mock ETH price of $2000
        mock_eth_price = Decimal("2000")
        
        return eth_balance * mock_eth_price
    
    def get_balance_aware_investment_limit(self, strategy_type: str = "standard") -> Decimal:
        """
        Enhanced investment limit calculation with strategy-specific adjustments.
        
        Args:
            strategy_type: Type of strategy to adjust limits for
            
        Returns:
            Maximum safe investment amount
        """
        if not self.current_balance:
            return Decimal("0")
        
        # Base tier limit
        tier_limit = self.TIER_INVESTMENT_LIMITS.get(self.balance_tier, Decimal("0.5"))
        base_amount = self.current_balance * tier_limit
        
        # Strategy-specific adjustments
        strategy_multipliers = {
            "flashloan": Decimal("0.1"),     # Very conservative
            "arbitrage": Decimal("0.8"),     # Conservative  
            "front_run": Decimal("1.0"),     # Standard
            "back_run": Decimal("1.0"),      # Standard
            "sandwich": Decimal("0.6"),      # More conservative
            "mev": Decimal("0.9"),           # Slightly conservative
            "standard": Decimal("1.0")       # Default
        }
        
        strategy_multiplier = strategy_multipliers.get(strategy_type, Decimal("1.0"))
        adjusted_amount = base_amount * strategy_multiplier
        
        # Reserve gas for multiple transactions
        gas_reserve = Decimal("0.005") * max(5, int(self.current_balance))  # Scale with balance
        
        return max(Decimal("0"), adjusted_amount - gas_reserve)

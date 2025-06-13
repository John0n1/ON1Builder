# src/on1builder/core/balance_manager.py
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Dict, Optional, Tuple, List

from web3 import AsyncWeb3

from on1builder.config.loaders import settings
from on1builder.utils.custom_exceptions import InsufficientFundsError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService

logger = get_logger(__name__)

class BalanceManager:
    """
    Manages wallet balance and dynamically adjusts trading parameters based on available funds.
    Implements strategies for low-balance scenarios and profit compounding.
    """

    def __init__(self, web3: AsyncWeb3, wallet_address: str):
        self.web3 = web3
        self.wallet_address = wallet_address
        self.current_balance: Optional[Decimal] = None
        self.balance_tier: str = "unknown"
        self.notification_service = NotificationService()
        self._balance_lock = asyncio.Lock()
        self._last_balance_check = 0
        self._balance_cache_duration = 30  # seconds
        self._token_balance_cache: Dict[str, Tuple[Decimal, float]] = {}  # token -> (balance, timestamp)
        self._token_cache_duration = 60  # Token balance cache duration in seconds
        
        # Profit tracking
        self._total_profit: Decimal = Decimal("0")
        self._session_profit: Decimal = Decimal("0")
        self._profit_by_strategy: Dict[str, Decimal] = {}
        
        logger.info(f"BalanceManager initialized for wallet: {wallet_address}")

    async def update_balance(self, force: bool = False) -> Decimal:
        """Updates the current balance from the blockchain."""
        import time
        
        async with self._balance_lock:
            current_time = time.time()
            
            if not force and self.current_balance is not None:
                if current_time - self._last_balance_check < self._balance_cache_duration:
                    return self.current_balance
            
            try:
                balance_wei = await self.web3.eth.get_balance(self.wallet_address)
                self.current_balance = Decimal(str(balance_wei)) / Decimal("1e18")
                self._last_balance_check = current_time
                
                old_tier = self.balance_tier
                self.balance_tier = self._determine_balance_tier(self.current_balance)
                
                if old_tier != self.balance_tier and old_tier != "unknown":
                    await self._handle_tier_change(old_tier, self.balance_tier)
                
                logger.debug(f"Balance updated: {self.current_balance:.6f} ETH (tier: {self.balance_tier})")
                return self.current_balance
                
            except Exception as e:
                logger.error(f"Failed to update balance: {e}")
                if self.current_balance is None:
                    raise InsufficientFundsError("Unable to determine wallet balance")
                return self.current_balance

    def _determine_balance_tier(self, balance: Decimal) -> str:
        """Determines the balance tier for strategy selection."""
        balance_float = float(balance)
        
        if balance_float <= settings.emergency_balance_threshold:
            return "emergency"
        elif balance_float <= settings.low_balance_threshold:
            return "low"
        elif balance_float <= settings.high_balance_threshold:
            return "medium"
        else:
            return "high"

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

    async def get_balance(self, token_symbol: str, force_refresh: bool = False) -> Decimal:
        """
        Returns the balance for a specific token.
        For ETH, returns the current wallet balance.
        For ERC-20 tokens, queries the token contract for the actual balance.
        
        Args:
            token_symbol: The symbol of the token (e.g., 'ETH', 'USDC')
            force_refresh: If True, bypasses cache and queries blockchain directly
        """
        import time
        
        token_symbol_upper = token_symbol.upper()
        
        if token_symbol_upper == 'ETH':
            await self.update_balance(force=force_refresh)
            return self.current_balance or Decimal("0")
        
        # Check token balance cache (unless force refresh)
        if not force_refresh:
            cached_balance = self._token_balance_cache.get(token_symbol_upper)
            if cached_balance:
                balance, timestamp = cached_balance
                if (time.time() - timestamp) < self._token_cache_duration:
                    logger.debug(f"Using cached balance for {token_symbol_upper}: {balance}")
                    return balance
        
        # For ERC-20 tokens, query the contract
        try:
            from on1builder.integrations.abi_registry import ABIRegistry
            
            abi_registry = ABIRegistry()
            
            # Get chain ID (handle both sync and async versions)
            try:
                chain_id = await self.web3.eth.chain_id
            except TypeError:
                # Fallback for sync chain_id property
                chain_id = self.web3.eth.chain_id
            
            # Get token contract address
            token_address = abi_registry.get_token_address(token_symbol_upper, chain_id)
            if not token_address:
                logger.warning(f"Token {token_symbol_upper} not found in registry for chain {chain_id}")
                balance = Decimal("0")
                self._token_balance_cache[token_symbol_upper] = (balance, time.time())
                return balance
            
            # Get ERC-20 contract ABI
            erc20_abi = abi_registry.get_abi("ERC20")
            if not erc20_abi:
                logger.error("ERC-20 ABI not found in registry")
                balance = Decimal("0")
                self._token_balance_cache[token_symbol_upper] = (balance, time.time())
                return balance
            
            # Create contract instance
            contract = self.web3.eth.contract(
                address=self.web3.to_checksum_address(token_address),
                abi=erc20_abi
            )
            
            # Get token balance
            balance_wei = await contract.functions.balanceOf(self.wallet_address).call()
            
            # Get token decimals to convert to human-readable format
            try:
                decimals = await contract.functions.decimals().call()
            except Exception:
                # Default to 18 decimals if decimals() call fails
                decimals = 18
                logger.warning(f"Could not get decimals for {token_symbol_upper}, using default 18")
            
            # Convert to decimal with proper precision
            balance = Decimal(str(balance_wei)) / Decimal(str(10 ** decimals))
            
            # Update token balance cache
            self._token_balance_cache[token_symbol_upper] = (balance, time.time())
            
            logger.debug(f"Token balance for {token_symbol_upper}: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"Failed to get balance for token {token_symbol_upper}: {e}")
            # Cache zero balance to avoid repeated failed queries
            balance = Decimal("0")
            self._token_balance_cache[token_symbol_upper] = (balance, time.time())
            return balance

    async def get_balances(self, token_symbols: List[str]) -> Dict[str, Decimal]:
        """
        Returns balances for multiple tokens efficiently using batch calls where possible.
        """
        balances = {}
        
        # Separate ETH from ERC-20 tokens
        eth_requested = False
        erc20_tokens = []
        
        for symbol in token_symbols:
            symbol_upper = symbol.upper()
            if symbol_upper == 'ETH':
                eth_requested = True
            else:
                erc20_tokens.append(symbol_upper)
        
        # Get ETH balance if requested
        if eth_requested:
            await self.update_balance()
            balances['ETH'] = self.current_balance or Decimal("0")
        
        # Get ERC-20 token balances
        if erc20_tokens:
            try:
                from on1builder.integrations.abi_registry import ABIRegistry
                import asyncio
                
                abi_registry = ABIRegistry()
                
                # Get chain ID (handle both sync and async versions)
                try:
                    chain_id = await self.web3.eth.chain_id
                except TypeError:
                    # Fallback for sync chain_id property
                    chain_id = self.web3.eth.chain_id
                erc20_abi = abi_registry.get_abi("ERC20")
                
                if not erc20_abi:
                    logger.error("ERC-20 ABI not found in registry")
                    for token in erc20_tokens:
                        balances[token] = Decimal("0")
                    return balances
                
                # Create tasks for concurrent balance queries
                tasks = []
                valid_tokens = []
                
                for token_symbol in erc20_tokens:
                    token_address = abi_registry.get_token_address(token_symbol, chain_id)
                    if token_address:
                        contract = self.web3.eth.contract(
                            address=self.web3.to_checksum_address(token_address),
                            abi=erc20_abi
                        )
                        tasks.append(self._get_token_balance_data(contract, token_symbol))
                        valid_tokens.append(token_symbol)
                    else:
                        logger.warning(f"Token {token_symbol} not found in registry for chain {chain_id}")
                        balances[token_symbol] = Decimal("0")
                
                # Execute all balance queries concurrently
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for i, result in enumerate(results):
                        token_symbol = valid_tokens[i]
                        if isinstance(result, Exception):
                            logger.error(f"Failed to get balance for {token_symbol}: {result}")
                            balances[token_symbol] = Decimal("0")
                        else:
                            balances[token_symbol] = result
                            
            except Exception as e:
                logger.error(f"Failed to get ERC-20 token balances: {e}")
                for token in erc20_tokens:
                    balances[token] = Decimal("0")
        
        return balances
    
    async def _get_token_balance_data(self, contract, token_symbol: str) -> Decimal:
        """Helper method to get balance and decimals for a single token contract."""
        try:
            # Get balance and decimals concurrently
            balance_task = contract.functions.balanceOf(self.wallet_address).call()
            decimals_task = contract.functions.decimals().call()
            
            balance_wei, decimals = await asyncio.gather(balance_task, decimals_task)
            
            # Convert to decimal with proper precision
            balance = Decimal(str(balance_wei)) / Decimal(str(10 ** decimals))
            
            logger.debug(f"Token balance for {token_symbol}: {balance}")
            return balance
            
        except Exception as e:
            # Try with default decimals if decimals() call fails
            try:
                balance_wei = await contract.functions.balanceOf(self.wallet_address).call()
                balance = Decimal(str(balance_wei)) / Decimal(str(10 ** 18))  # Default 18 decimals
                logger.warning(f"Used default decimals for {token_symbol}: {balance}")
                return balance
            except Exception as e2:
                logger.error(f"Failed to get balance for {token_symbol}: {e2}")
                raise e2

    def get_total_profit(self) -> Decimal:
        """Returns the total profit earned across all strategies."""
        return self._total_profit

    def get_session_profit(self) -> Decimal:
        """Returns the profit earned in the current session."""
        return self._session_profit

    def get_profit_by_strategy(self) -> Dict[str, Decimal]:
        """Returns profit breakdown by strategy."""
        return self._profit_by_strategy.copy()

    async def record_profit(self, profit_amount: Decimal, strategy: str):
        """
        Records profit and determines reinvestment strategy.
        """
        if profit_amount <= 0:
            return
        
        # Track profit
        self._total_profit += profit_amount
        self._session_profit += profit_amount
        if strategy not in self._profit_by_strategy:
            self._profit_by_strategy[strategy] = Decimal("0")
        self._profit_by_strategy[strategy] += profit_amount
        
        reinvestment_percentage = Decimal(str(settings.profit_reinvestment_percentage)) / Decimal("100")
        
        # Adjust reinvestment based on balance tier
        tier_adjustments = {
            "emergency": Decimal("1.0"),    # Reinvest all profit
            "low": Decimal("0.9"),          # Reinvest 90%
            "medium": reinvestment_percentage,  # Use configured percentage
            "high": Decimal("0.7")          # Take more profit at high balances
        }
        
        actual_reinvestment = tier_adjustments.get(self.balance_tier, reinvestment_percentage)
        reinvest_amount = profit_amount * actual_reinvestment
        withdraw_amount = profit_amount - reinvest_amount
        
        logger.info(f"Profit recorded: {profit_amount:.6f} ETH from {strategy}. "
                   f"Reinvesting: {reinvest_amount:.6f} ETH, Withdrawing: {withdraw_amount:.6f} ETH")
        
        # Update balance to reflect new profit
        await self.update_balance(force=True)
        
        if withdraw_amount > 0 and settings.profit_receiver_address:
            # Implement automatic profit withdrawal with safety checks
            min_keep_balance = self.config.get('withdrawal_min_keep_balance', 0.1)
            withdrawal_threshold = self.config.get('withdrawal_threshold', 1.0)
            
            if profit > withdrawal_threshold and balance > min_keep_balance + profit:
                try:
                    # Create withdrawal transaction
                    tx_data = {
                        'to': self.config.get('profit_withdrawal_address'),
                        'value': self.web3.to_wei(profit, 'ether'),
                        'gas': 21000,
                        'gasPrice': self.web3.eth.gas_price
                    }
                    
                    # Sign and send withdrawal transaction
                    signed_tx = self.web3.eth.account.sign_transaction(
                        tx_data, 
                        private_key=self.config.get('private_key')
                    )
                    tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    
                    self.logger.info(f"Automated profit withdrawal: {profit} ETH, tx: {tx_hash.hex()}")
                    return True
                except Exception as e:
                    self.logger.error(f"Failed to withdraw profit: {e}")
                    return False
            logger.info(f"Profit withdrawal of {withdraw_amount:.6f} ETH scheduled to {settings.profit_receiver_address}")

    async def get_balance_summary(self) -> Dict[str, any]:
        """Returns a summary of current balance and tier information."""
        await self.update_balance()
        
        max_investment = await self.get_max_investment_amount()
        profit_threshold = await self.calculate_dynamic_profit_threshold(max_investment)
        
        return {
            "balance": float(self.current_balance),
            "balance_tier": self.balance_tier,
            "max_investment": float(max_investment),
            "profit_threshold": float(profit_threshold),
            "flashloan_recommended": await self.should_use_flashloan(max_investment),
            "emergency_mode": self.balance_tier == "emergency"
        }

    def clear_token_balance_cache(self, token_symbol: str = None):
        """
        Clears the token balance cache for a specific token or all tokens.
        
        Args:
            token_symbol: If specified, clears cache for this token only. If None, clears all.
        """
        if token_symbol:
            token_symbol_upper = token_symbol.upper()
            if token_symbol_upper in self._token_balance_cache:
                del self._token_balance_cache[token_symbol_upper]
                logger.debug(f"Cleared balance cache for {token_symbol_upper}")
        else:
            self._token_balance_cache.clear()
            logger.debug("Cleared all token balance cache")

# src/on1builder/engines/safety_guard.py
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from web3 import AsyncWeb3
from web3.types import TxParams

from on1builder.config.loaders import settings
from on1builder.utils.custom_exceptions import InsufficientFundsError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService

logger = get_logger(__name__)

class SafetyGuard:
    """
    Enhanced safety guard with sophisticated risk management, balance awareness,
    and adaptive circuit breaking.
    """
    
    def __init__(self, web3: AsyncWeb3):
        self._web3 = web3
        self._notification_service = NotificationService()
        self._settings = settings
        
        # Transaction tracking
        self._recent_tx_signatures = set()
        self._last_clear_time = time.time()
        
        # Circuit breaker state
        self._circuit_broken = False
        self._circuit_break_reason = ""
        self._circuit_break_time = 0
        self._auto_reset_delay = 1800  # 30 minutes
        
        # Risk management
        self._failed_tx_count = 0
        self._failed_tx_threshold = 5
        self._gas_spent_last_hour = 0.0
        self._hourly_gas_limit = 0.05  # 0.05 ETH per hour
        self._last_gas_reset = time.time()
        
        # Performance tracking
        self._safety_stats = {
            "total_checks": 0,
            "passed_checks": 0,
            "failed_balance_checks": 0,
            "failed_gas_checks": 0,
            "failed_duplicate_checks": 0,
            "circuit_breaks": 0
        }
        
        logger.info("Enhanced SafetyGuard initialized with advanced risk management.")

    @property
    def is_circuit_broken(self) -> bool:
        """Returns True if the circuit breaker is currently active."""
        # Auto-reset circuit breaker after delay
        if (self._circuit_broken and 
            time.time() - self._circuit_break_time > self._auto_reset_delay):
            self._auto_reset_circuit_breaker()
        
        return self._circuit_broken

    async def check_transaction(self, tx_params: TxParams) -> Tuple[bool, str]:
        """
        Enhanced comprehensive safety checks with adaptive risk management.
        """
        self._safety_stats["total_checks"] += 1
        
        if self.is_circuit_broken:
            reason = f"Circuit breaker is active: {self._circuit_break_reason}"
            logger.critical(reason)
            return False, reason

        # Reset hourly gas tracking if needed
        self._reset_hourly_gas_if_needed()

        # Run all safety checks
        checks = [
            ("balance", self._check_balance),
            ("gas_price", self._check_gas_price),
            ("gas_limit", self._check_gas_limit),
            ("duplicate", self._check_duplicate_tx),
            ("rate_limit", self._check_rate_limits),
            ("profit_viability", self._check_profit_viability),
            ("market_conditions", self._check_market_conditions)
        ]

        for check_name, check_func in checks:
            try:
                is_safe, reason = await check_func(tx_params)
                if not is_safe:
                    self._record_failed_check(check_name)
                    logger.warning(f"Safety check '{check_name}' failed: {reason}")
                    return False, reason
            except Exception as e:
                logger.error(f"Safety check '{check_name}' raised exception: {e}")
                return False, f"Safety check error: {check_name}"

        self._safety_stats["passed_checks"] += 1
        return True, "All enhanced safety checks passed."

    async def _check_balance(self, tx_params: TxParams) -> Tuple[bool, str]:
        """Enhanced balance check with tier-aware requirements."""
        try:
            tx_value = tx_params.get("value", 0)
            from_address = tx_params.get("from")
            if not from_address:
                return False, "Transaction 'from' address is missing."

            balance = await self._web3.eth.get_balance(from_address)
            balance_eth = float(self._web3.from_wei(balance, "ether"))
            
            gas_price = tx_params.get("gasPrice", await self._web3.eth.gas_price)
            gas_limit = tx_params.get("gas", self._settings.default_gas_limit)
            
            required_gas_cost = gas_price * gas_limit
            total_required = tx_value + required_gas_cost
            total_required_eth = float(self._web3.from_wei(total_required, "ether"))
            
            # Dynamic minimum balance based on current balance tier
            if balance_eth <= self._settings.emergency_balance_threshold:
                min_reserve = 0.005  # Very small reserve in emergency
            elif balance_eth <= self._settings.low_balance_threshold:
                min_reserve = 0.01   # Small reserve for low balance
            else:
                min_reserve = self._settings.min_wallet_balance
            
            if balance_eth < total_required_eth + min_reserve:
                return False, f"Insufficient balance. Required: {total_required_eth + min_reserve:.6f} ETH, Available: {balance_eth:.6f} ETH"

            # Additional check for large transactions
            if total_required_eth > balance_eth * 0.8:  # More than 80% of balance
                return False, f"Transaction too large relative to balance ({total_required_eth:.6f} ETH / {balance_eth:.6f} ETH)"

            return True, "Sufficient balance with appropriate reserves."
            
        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return False, "Error during balance check."

    async def _check_gas_price(self, tx_params: TxParams) -> Tuple[bool, str]:
        """Enhanced gas price validation with market awareness."""
        gas_price_wei = tx_params.get("gasPrice")
        if gas_price_wei is None:
            return True, "Gas price not specified, will be set by web3."

        gas_price_gwei = float(self._web3.from_wei(gas_price_wei, "gwei"))
        max_gas_price_gwei = self._settings.max_gas_price_gwei
        
        # Dynamic gas price limits based on current market
        try:
            current_market_gas = await self._web3.eth.gas_price
            current_market_gwei = float(self._web3.from_wei(current_market_gas, "gwei"))
            
            # Allow up to 3x current market price for urgent transactions
            dynamic_max = min(max_gas_price_gwei, current_market_gwei * 3)
            
            if gas_price_gwei > dynamic_max:
                return False, f"Gas price ({gas_price_gwei:.2f} Gwei) exceeds dynamic limit ({dynamic_max:.2f} Gwei)"
            
            # Warn for very high gas prices
            if gas_price_gwei > current_market_gwei * 2:
                logger.warning(f"High gas price detected: {gas_price_gwei:.2f} Gwei (market: {current_market_gwei:.2f} Gwei)")
            
            return True, "Gas price is within dynamic limits."
            
        except Exception as e:
            # Fallback to static check
            if gas_price_gwei > max_gas_price_gwei:
                return False, f"Gas price ({gas_price_gwei:.2f} Gwei) exceeds max limit ({max_gas_price_gwei} Gwei)"
            return True, "Gas price is within static limits."

    async def _check_gas_limit(self, tx_params: TxParams) -> Tuple[bool, str]:
        """Enhanced gas limit validation with transaction type awareness."""
        gas_limit = tx_params.get("gas")
        if gas_limit is None:
            return True, "Gas limit not specified, will be estimated."
        
        # Dynamic gas limit checks based on transaction type
        tx_data = tx_params.get("data", "0x")
        
        if tx_data == "0x":
            # Simple ETH transfer
            if gas_limit > 21000 * 2:  # Allow 2x buffer
                return False, f"Gas limit ({gas_limit}) too high for simple transfer"
        elif len(tx_data) > 10:
            # Contract interaction - more complex validation
            if gas_limit > 2_000_000:
                return False, f"Gas limit ({gas_limit}) is excessively high"
            elif gas_limit < 21000:
                return False, f"Gas limit ({gas_limit}) too low for contract interaction"
        
        return True, "Gas limit is reasonable for transaction type."

    async def _check_duplicate_tx(self, tx_params: TxParams) -> Tuple[bool, str]:
        """Enhanced duplicate transaction detection."""
        self._clear_stale_signatures()
        
        # More comprehensive signature including gas parameters
        tx_signature = (
            f"{tx_params.get('to')}:"
            f"{tx_params.get('value', 0)}:"
            f"{tx_params.get('data', '')}:"
            f"{tx_params.get('gasPrice', 0)}"
        )
        
        if tx_signature in self._recent_tx_signatures:
            self._safety_stats["failed_duplicate_checks"] += 1
            return False, "Potential duplicate transaction detected"
        
        self._recent_tx_signatures.add(tx_signature)
        return True, "Transaction is unique."

    async def _check_rate_limits(self, tx_params: TxParams) -> Tuple[bool, str]:
        """Check transaction rate limits and gas spending limits."""
        
        # Check hourly gas spending limit
        gas_price = tx_params.get("gasPrice", 0)
        gas_limit = tx_params.get("gas", 0)
        estimated_gas_cost_eth = float(self._web3.from_wei(gas_price * gas_limit, "ether"))
        
        if self._gas_spent_last_hour + estimated_gas_cost_eth > self._hourly_gas_limit:
            return False, f"Hourly gas limit exceeded. Spent: {self._gas_spent_last_hour:.6f} ETH, Limit: {self._hourly_gas_limit:.6f} ETH"
        
        # Check recent failure rate
        if self._failed_tx_count >= self._failed_tx_threshold:
            await self.trip_circuit_breaker(f"Too many failed transactions: {self._failed_tx_count}")
            return False, "Circuit breaker tripped due to failed transactions"
        
        return True, "Rate limits OK."

    async def _check_profit_viability(self, tx_params: TxParams) -> Tuple[bool, str]:
        """Check if transaction is likely to be profitable."""
        
        # Calculate gas cost
        gas_price = tx_params.get("gasPrice", 0)
        gas_limit = tx_params.get("gas", 0)
        gas_cost_eth = float(self._web3.from_wei(gas_price * gas_limit, "ether"))
        
        # Get expected profit from transaction metadata if available
        expected_profit = tx_params.get("expected_profit_eth", 0)
        
        if expected_profit > 0:
            # Require profit to be at least 2x gas cost
            min_required_profit = gas_cost_eth * 2
            if expected_profit < min_required_profit:
                return False, f"Expected profit ({expected_profit:.6f} ETH) too low relative to gas cost ({gas_cost_eth:.6f} ETH)"
        
        return True, "Profit viability check passed."

    async def _check_market_conditions(self, tx_params: TxParams) -> Tuple[bool, str]:
        """Check current market conditions for safe execution."""
        
        try:
            # Check current gas price volatility
            current_gas = await self._web3.eth.gas_price
            current_gas_gwei = float(self._web3.from_wei(current_gas, "gwei"))
            
            # If gas is extremely high, be more cautious
            if current_gas_gwei > 300:  # Very high gas environment
                logger.warning(f"Extreme gas environment detected: {current_gas_gwei:.2f} Gwei")
                
                # Only allow transactions with very high expected profit
                expected_profit = tx_params.get("expected_profit_eth", 0)
                if expected_profit < 0.01:  # Less than 0.01 ETH profit
                    return False, "Market conditions too volatile for low-profit transactions"
            
            return True, "Market conditions acceptable."
            
        except Exception as e:
            logger.warning(f"Market conditions check failed: {e}")
            return True, "Market conditions check skipped due to error."

    def _record_failed_check(self, check_name: str):
        """Record failed safety checks for monitoring."""
        if check_name in ["balance", "gas_price", "gas_limit", "duplicate"]:
            self._safety_stats[f"failed_{check_name}_checks"] += 1
        
        # Increment general failure counter
        self._failed_tx_count += 1

    def _reset_hourly_gas_if_needed(self):
        """Reset hourly gas tracking if an hour has passed."""
        current_time = time.time()
        if current_time - self._last_gas_reset > 3600:  # 1 hour
            self._gas_spent_last_hour = 0.0
            self._last_gas_reset = current_time

    def record_gas_spent(self, gas_cost_eth: float):
        """Record gas spent for rate limiting."""
        self._gas_spent_last_hour += gas_cost_eth

    def record_transaction_result(self, success: bool):
        """Record transaction result for failure tracking."""
        if success:
            # Reset failure counter on success
            self._failed_tx_count = max(0, self._failed_tx_count - 1)
        else:
            self._failed_tx_count += 1

    def _clear_stale_signatures(self) -> None:
        """Clear old transaction signatures."""
        if time.time() - self._last_clear_time > 60:  # Clear every 60 seconds
            self._recent_tx_signatures.clear()
            self._last_clear_time = time.time()

    async def trip_circuit_breaker(self, reason: str):
        """Enhanced circuit breaker with automatic reset scheduling."""
        if not self._circuit_broken:
            self._circuit_broken = True
            self._circuit_break_reason = reason
            self._circuit_break_time = time.time()
            self._safety_stats["circuit_breaks"] += 1
            
            logger.critical(f"CIRCUIT BREAKER TRIPPED! Reason: {reason}")
            await self._notification_service.send_alert(
                title="Circuit Breaker Tripped!",
                message=f"All trading operations halted. Auto-reset in {self._auto_reset_delay/60:.0f} minutes.",
                level="CRITICAL",
                details={
                    "reason": reason,
                    "auto_reset_minutes": self._auto_reset_delay / 60,
                    "failed_tx_count": self._failed_tx_count,
                    "gas_spent_last_hour": self._gas_spent_last_hour
                }
            )

    def _auto_reset_circuit_breaker(self):
        """Automatically reset circuit breaker after delay."""
        if self._circuit_broken:
            self._circuit_broken = False
            self._circuit_break_reason = ""
            self._failed_tx_count = 0  # Reset failure counter
            
            logger.info("Circuit breaker auto-reset. Operations can resume.")

    def reset_circuit_breaker(self):
        """Manually reset the circuit breaker."""
        if self._circuit_broken:
            self._circuit_broken = False
            self._circuit_break_reason = ""
            self._failed_tx_count = 0
            logger.info("Circuit breaker manually reset. Operations can resume.")

    def get_safety_stats(self) -> Dict[str, Any]:
        """Get comprehensive safety statistics."""
        success_rate = 0.0
        if self._safety_stats["total_checks"] > 0:
            success_rate = (self._safety_stats["passed_checks"] / 
                          self._safety_stats["total_checks"] * 100)
        
        return {
            **self._safety_stats,
            "success_rate_percentage": success_rate,
            "circuit_broken": self._circuit_broken,
            "failed_tx_count": self._failed_tx_count,
            "gas_spent_last_hour": self._gas_spent_last_hour,
            "hourly_gas_limit": self._hourly_gas_limit,
            "auto_reset_delay_minutes": self._auto_reset_delay / 60
        }
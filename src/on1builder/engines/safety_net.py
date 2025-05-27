"""
ON1Builder - Safety Net
======================

Provides safety checks and circuit-breaker functionality to prevent operational risks.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from web3 import AsyncWeb3

from on1builder.config.config import APIConfig, Configuration
from on1builder.utils.logger import setup_logging

logger = setup_logging("SafetyNet", level="DEBUG")


class SafetyNet:
    """Safety checks and circuit-breaker system for transaction execution.

    This class provides safety mechanisms such as:
    - Balance monitoring
    - Gas price safety limits
    - Transaction value limits
    - Circuit breakers for abnormal conditions
    - Duplicate transaction prevention
    """

    def __init__(
        self,
        web3: AsyncWeb3,
        config: Configuration,
        account_address: str,
        account: Optional[Any] = None,
        api_config: APIConfig = None,
    ) -> None:
        """Initialize safety net system.

        Args:
            web3: Web3 provider instance
            config: Global configuration
            account_address: Account address to monitor
            account: Account object (optional)
            api_config: API configuration object (optional)
        """
        self.web3 = web3
        self.config = config
        self.account_address = account_address
        self.account = account
        self.api_config = api_config

        # Circuit breaker state
        self.circuit_broken = False
        self.circuit_break_reason = None
        self.last_reset_time = time.time()

        # Transaction tracking
        self.recent_txs: Set[str] = set()
        self._cache_lock = asyncio.Lock()
        self._cache_expiry = time.time() + config.get("SAFETYNET_CACHE_TTL", 300)

        # History for gas price and network congestion
        self._gas_price_history: List[float] = []
        self._congestion_history: List[float] = []

        logger.info("SafetyNet initialized")

    async def initialize(self) -> None:
        """Initialize the safety net and verify connection."""
        if not self.api_config and hasattr(self, "account") and self.account:
            # Initialize api_config if not already set
            logger.info("Initializing API config for SafetyNet")
            from on1builder.config.config import APIConfig

            self.api_config = APIConfig(self.config)
            await self.api_config.initialize()

        if await self.web3.is_connected():
            logger.info("Safety net initialized with active web3 connection")
        else:
            logger.warning("Safety net initialized but web3 connection is not active")

    async def stop(self) -> None:
        """Stop the safety net system.

        Alias for close().
        """
        await self.close()

    async def get_balance(self, account) -> float:
        """Get account balance in ETH.

        Args:
            account: Account to check balance for

        Returns:
            Balance in ETH
        """
        address = account.address if hasattr(account, "address") else account
        balance_wei = await self.web3.eth.get_balance(address)
        return float(self.web3.from_wei(balance_wei, "ether"))

    async def is_safe_to_proceed(self) -> bool:
        """Check if it's safe to proceed with operations.

        Returns:
            True if safe to proceed, False otherwise
        """
        # Check circuit breaker
        if self.circuit_broken:
            logger.warning(
                f"Circuit breaker active: {
                    self.circuit_break_reason}"
            )
            return False

        # Check account balance
        balance = await self.web3.eth.get_balance(self.account_address)
        min_balance_wei = self.web3.to_wei(
            self.config.get("MIN_BALANCE", 0.001), "ether"
        )

        if balance < min_balance_wei:
            reason = f"Account balance ({
                self.web3.from_wei(
                    balance,
                    'ether'):.4f} ETH) below minimum threshold"
            await self.break_circuit(reason)
            return False

        # Check gas price
        gas_price = await self.web3.eth.gas_price
        max_gas_price = self.config.get(
            "MAX_GAS_PRICE", 500_000_000_000
        )  # Default 500 gwei

        if gas_price > max_gas_price:
            reason = f"Gas price ({
                self.web3.from_wei(
                    gas_price,
                    'gwei'):.1f} gwei) above maximum threshold"
            logger.warning(reason)
            return False

        return True

    async def break_circuit(self, reason: str) -> None:
        """Break the circuit to prevent further operations.

        Args:
            reason: Reason for breaking the circuit
        """
        self.circuit_broken = True
        self.circuit_break_reason = reason
        logger.critical(f"Circuit breaker activated: {reason}")

        # Send alert notification
        try:
            from on1builder.utils.notifications import send_alert

            details = {
                "chain_id": self.config.get("CHAIN_ID", "unknown"),
                "address": self.account_address,
                "timestamp": time.time(),
                "reason": reason,
            }
            await send_alert(
                f"Circuit breaker activated: {reason}",
                level="ERROR",
                details=details,
                config=self.config,
            )
        except ImportError:
            logger.warning(
                "Notification system not available for circuit breaker alerts"
            )

    async def reset_circuit(self) -> None:
        """Reset the circuit breaker."""
        if self.circuit_broken:
            self.circuit_broken = False
            self.circuit_break_reason = None
            self.last_reset_time = time.time()
            logger.info("Circuit breaker reset")

    async def is_transaction_duplicate(self, tx_hash: str) -> bool:
        """Check if a transaction is a potential duplicate.

        Args:
            tx_hash: Transaction hash to check

        Returns:
            True if transaction appears to be a duplicate
        """
        async with self._cache_lock:
            # Clean expired cache if needed
            current_time = time.time()
            if current_time > self._cache_expiry:
                self.recent_txs.clear()
                self._cache_expiry = current_time + self.config.get(
                    "SAFETYNET_CACHE_TTL", 300
                )

            # Check for duplicate
            if tx_hash in self.recent_txs:
                logger.warning(f"Potential duplicate transaction: {tx_hash}")
                return True

            # Store the tx hash
            self.recent_txs.add(tx_hash)
            return False

    async def validate_transaction_params(
        self, tx_params: Dict[str, Any]
    ) -> Optional[str]:
        """Validate transaction parameters for safety.

        Args:
            tx_params: Transaction parameters

        Returns:
            Error message if validation fails, None if valid
        """
        # Check gas price
        gas_price = tx_params.get("gasPrice", 0)
        max_gas_price = self.config.get("MAX_GAS_PRICE", 500_000_000_000)
        if gas_price > max_gas_price:
            return f"Gas price {self.web3.from_wei(gas_price, 'gwei'):.1f} gwei exceeds maximum allowed"

        # Check gas limit
        gas_limit = tx_params.get("gas", 0)
        max_gas_limit = self.config.get("GAS_LIMIT", 1_000_000)
        if gas_limit > max_gas_limit:
            return f"Gas limit {gas_limit} exceeds maximum allowed {max_gas_limit}"

        # Check transaction value
        value = tx_params.get("value", 0)
        balance = await self.web3.eth.get_balance(self.account_address)
        if value > balance * 0.95:  # 95% of balance
            return f"Transaction value {self.web3.from_wei(value, 'ether'):.4f} ETH too close to account balance"

        return None

    async def close(self) -> None:
        """Clean up resources."""
        logger.debug("Closing SafetyNet")
        # Nothing to clean up currently

    # Additional methods required by tests

    async def get_dynamic_gas_price(self) -> float:
        """Get dynamic gas price based on network conditions.

        Returns:
            Gas price in gwei
        """
        try:
            # Try to get gas price oracle if available
            gas_price_oracle_address = self.config.get("GAS_PRICE_ORACLE")
            if gas_price_oracle_address:
                try:
                    # Load ABI
                    from on1builder.integrations.abi_registry import ABIRegistry

                    abi_registry = ABIRegistry()
                    await abi_registry.initialize(self.config.get("BASE_PATH", "."))
                    oracle_abi = abi_registry.get_abi("gas_price_oracle")

                    if oracle_abi:
                        oracle = self.web3.eth.contract(
                            address=self.web3.to_checksum_address(
                                gas_price_oracle_address
                            ),
                            abi=oracle_abi,
                        )

                        # Call oracle method - depends on specific oracle
                        # contract
                        if hasattr(oracle.functions, "getLatestGasPrice"):
                            gas_price = (
                                await oracle.functions.getLatestGasPrice().call()
                            )
                            return float(self.web3.from_wei(gas_price, "gwei"))
                        elif hasattr(oracle.functions, "latestAnswer"):
                            gas_price = await oracle.functions.latestAnswer().call()
                            return float(self.web3.from_wei(gas_price, "gwei"))
                except Exception as e:
                    logger.error(f"Error accessing gas price oracle: {e}")

            # Get the current gas price from the network
            base_gas = await self.web3.eth.gas_price
            gas_gwei = float(self.web3.from_wei(base_gas, "gwei"))

            # Check if EIP-1559 supported (has maxPriorityFeePerGas)
            latest_block = await self.web3.eth.get_block("latest")
            eip1559_supported = "baseFeePerGas" in latest_block

            if eip1559_supported:
                # Get priority fee
                priority_fee = await self.web3.eth.max_priority_fee
                priority_gwei = float(self.web3.from_wei(priority_fee, "gwei"))

                # Get base fee
                base_fee = latest_block["baseFeePerGas"]
                base_fee_gwei = float(self.web3.from_wei(base_fee, "gwei"))

                # Calculate dynamic gas price
                # Use base fee + priority fee with adjustments based on network
                # congestion
                congestion = await self.get_network_congestion()

                # Adjust priority fee based on congestion
                adjusted_priority = priority_gwei * (1 + congestion)

                # Final gas price: base fee + adjusted priority fee
                gas_gwei = base_fee_gwei + adjusted_priority

                logger.debug(
                    f"EIP-1559 gas price: base={
                        base_fee_gwei:.2f} + priority={
                        adjusted_priority:.2f} = {
                        gas_gwei:.2f} gwei"
                )
            else:
                # For non-EIP-1559 chains, adjust based on congestion
                congestion = await self.get_network_congestion()
                gas_gwei = gas_gwei * (1 + congestion * 0.5)
                logger.debug(
                    f"Legacy gas price: {
                        gas_gwei:.2f} gwei (congestion: {
                        congestion:.2f})"
                )

            # Apply safety limits
            min_gas = self.config.get("MIN_GAS_PRICE_GWEI", 1.0)
            max_gas = self.config.get("MAX_GAS_PRICE_GWEI", 500.0)
            gas_gwei = max(min_gas, min(gas_gwei, max_gas))

            return gas_gwei
        except Exception as e:
            logger.error(f"Error calculating dynamic gas price: {e}")
            # Default to current gas price
            gas_price = await self.web3.eth.gas_price
            return float(self.web3.from_wei(gas_price, "gwei"))

    async def adjust_slippage_tolerance(self, congestion_level: float = None) -> float:
        """Adjust slippage tolerance based on network congestion.

        Args:
            congestion_level: Network congestion level (0-1), will be calculated if None

        Returns:
            Adjusted slippage tolerance as a percentage (e.g., 0.1 for 0.1%)
        """
        try:
            # Get network congestion if not provided
            if congestion_level is None:
                congestion_level = await self.get_network_congestion()

            # Get base slippage values from config
            slippage_low = self.config.get("SLIPPAGE_LOW_CONGESTION", 0.1)  # 0.1%
            slippage_medium = self.config.get("SLIPPAGE_MEDIUM_CONGESTION", 0.5)  # 0.5%
            slippage_high = self.config.get("SLIPPAGE_HIGH_CONGESTION", 1.0)  # 1.0%
            slippage_extreme = self.config.get(
                "SLIPPAGE_EXTREME_CONGESTION", 2.0
            )  # 2.0%

            # Adjust based on congestion level
            if congestion_level < 0.3:  # Low congestion
                slippage = slippage_low
            elif congestion_level < 0.6:  # Medium congestion
                slippage = slippage_medium
            elif congestion_level < 0.8:  # High congestion
                slippage = slippage_high
            else:  # Extreme congestion
                slippage = slippage_extreme

            # Further adjust based on token volatility if api_config is
            # available
            token_address = self.config.get("PRIMARY_TOKEN")
            if self.api_config and token_address:
                try:
                    # Get market volatility
                    from on1builder.monitoring.market_monitor import MarketMonitor

                    if hasattr(MarketMonitor, "check_market_conditions"):
                        # Access market monitor if available
                        market_monitor = getattr(self, "market_monitor", None)
                        if market_monitor:
                            volatility_data = (
                                await market_monitor.check_market_conditions(
                                    token_address, "volatility"
                                )
                            )
                            volatility_condition = volatility_data.get(
                                "condition", "medium"
                            )

                            # Adjust slippage based on volatility
                            if volatility_condition == "high":
                                slippage *= 1.5
                            elif volatility_condition == "low":
                                slippage *= 0.8
                except Exception as e:
                    logger.debug(f"Could not adjust slippage for token volatility: {e}")

            # Ensure slippage is within reasonable bounds
            min_slippage = self.config.get("MIN_SLIPPAGE", 0.05)  # 0.05%
            max_slippage = self.config.get("MAX_SLIPPAGE", 5.0)  # 5.0%
            slippage = max(min_slippage, min(slippage, max_slippage))

            logger.debug(
                f"Adjusted slippage tolerance: {
                    slippage:.2f}% (congestion: {
                    congestion_level:.2f})"
            )
            return slippage

        except Exception as e:
            logger.error(f"Error adjusting slippage tolerance: {e}")
            # Return default slippage
            return self.config.get("SLIPPAGE_DEFAULT", 0.5)  # 0.5%

    async def _calculate_gas_cost(self, gas_price: float, gas_used: int) -> float:
        """Calculate gas cost in ETH.

        Args:
            gas_price: Gas price in gwei
            gas_used: Gas used

        Returns:
            Gas cost in ETH
        """
        try:
            # Convert gas price from gwei to wei
            gas_price_wei = self.web3.to_wei(gas_price, "gwei")

            # Calculate cost in wei
            cost_wei = gas_price_wei * gas_used

            # Convert to ETH and return
            cost_eth = float(self.web3.from_wei(cost_wei, "ether"))

            logger.debug(
                f"Calculated gas cost: {
                    cost_eth:.6f} ETH (gas: {gas_used}, price: {
                    gas_price:.2f} gwei)"
            )
            return cost_eth
        except Exception as e:
            logger.error(f"Error calculating gas cost: {e}")
            # Fallback calculation
            return (gas_price * gas_used) / 1_000_000_000

    async def _calculate_profit(
        self, amountIn: float, amountOut: float, gas_cost: float
    ) -> float:
        """Calculate profit from a transaction.

        Args:
            amountIn: Input amount in ETH or token value
            amountOut: Output amount in ETH or token value
            gas_cost: Gas cost in ETH

        Returns:
            Profit in ETH
        """
        try:
            # Calculate raw profit
            raw_profit = amountOut - amountIn

            # Subtract gas cost
            net_profit = raw_profit - gas_cost

            # Apply safety margin
            safety_margin = self.config.get(
                "PROFIT_SAFETY_MARGIN", 0.9
            )  # 10% safety margin
            adjusted_profit = net_profit * safety_margin

            logger.debug(
                f"Calculated profit: {
                    adjusted_profit:.6f} ETH (raw: {
                    raw_profit:.6f}, gas: {
                    gas_cost:.6f})"
            )
            return adjusted_profit
        except Exception as e:
            logger.error(f"Error calculating profit: {e}")
            # Simple fallback
            return amountOut - amountIn - gas_cost

    async def get_network_congestion(self) -> float:
        """Get network congestion level.

        Returns:
            Congestion level (0-1)
        """
        try:
            # Get latest block
            latest_block = await self.web3.eth.get_block("latest")

            # Get gas used vs gas limit ratio
            gas_used = latest_block["gasUsed"]
            gas_limit = latest_block["gasLimit"]
            gas_ratio = gas_used / gas_limit

            # Get pending transaction count if possible
            pending_count = 0
            try:
                # This may not be supported by all providers
                pending_block = await self.web3.eth.get_block("pending")
                if pending_block and "transactions" in pending_block:
                    pending_count = len(pending_block["transactions"])
            except Exception:
                # If pending block not available, use a different approach
                try:
                    # Check txpool if available
                    if hasattr(self.web3, "geth") and hasattr(self.web3.geth, "txpool"):
                        txpool = await self.web3.geth.txpool.status()
                        pending_count = (
                            int(txpool.pending, 16) if hasattr(txpool, "pending") else 0
                        )
                except Exception:
                    # Unable to get pending transactions
                    pass

            # Normalize pending count (0-1)
            pending_factor = min(
                1.0, pending_count / 5000
            )  # Assume 5000+ is very congested

            # Get recent gas prices to assess trends
            gas_price_trend = 0.0
            try:
                if not hasattr(self, "_gas_price_history"):
                    self._gas_price_history = []

                current_gas = await self.web3.eth.gas_price
                self._gas_price_history.append(current_gas)

                # Keep only recent history (last 10 data points)
                if len(self._gas_price_history) > 10:
                    self._gas_price_history.pop(0)

                # Calculate trend if we have enough data points
                if len(self._gas_price_history) >= 2:
                    recent_avg = sum(self._gas_price_history[-3:]) / min(
                        3, len(self._gas_price_history)
                    )
                    older_avg = sum(self._gas_price_history[:-3]) / max(
                        1, len(self._gas_price_history) - 3
                    )

                    if older_avg > 0:
                        # Normalize trend between 0-1 (0 = decreasing, 1 =
                        # increasing sharply)
                        trend_ratio = recent_avg / older_avg
                        gas_price_trend = min(1.0, max(0.0, (trend_ratio - 0.95) / 0.5))
            except Exception as e:
                logger.debug(f"Could not calculate gas price trend: {e}")

            # Combine metrics
            congestion = (
                (gas_ratio * 0.5) + (pending_factor * 0.3) + (gas_price_trend * 0.2)
            )

            # Ensure range is 0-1
            congestion = max(0.0, min(1.0, congestion))

            # Implement proper historical tracking with exponential moving
            # average
            if not hasattr(self, "_congestion_history"):
                self._congestion_history = []

            # Store current congestion in history
            timestamp = time.time()
            self._congestion_history.append((timestamp, congestion))

            # Keep only recent history (last 1 hour of data points)
            one_hour_ago = timestamp - 3600
            self._congestion_history = [
                (t, c) for t, c in self._congestion_history if t > one_hour_ago
            ]

            # Smooth with historical values using weighted average
            if len(self._congestion_history) > 1:
                # Calculate weighted average based on recency
                total_weight = 0
                weighted_sum = 0

                for i, (t, c) in enumerate(self._congestion_history):
                    # More recent values get higher weights
                    weight = i + 1  # Linear weight increase
                    weighted_sum += c * weight
                    total_weight += weight

                # Apply smoothed value
                if total_weight > 0:
                    congestion = weighted_sum / total_weight

            # Store for simple access
            self._last_congestion = congestion

            logger.debug(
                f"Network congestion: {
                    congestion:.2f} (gas ratio: {
                    gas_ratio:.2f}, pending: {pending_count}, trend: {
                    gas_price_trend:.2f})"
            )
            return congestion

        except Exception as e:
            logger.error(f"Error calculating network congestion: {e}")
            # Return moderate congestion as fallback
            return 0.5

    async def ensure_profit(self, transaction_data: Dict[str, Any]) -> bool:
        """Ensure a transaction is profitable considering gas costs and market
        conditions.

        Args:
            transaction_data: Transaction data including token addresses and amounts

        Returns:
            True if transaction is likely profitable
        """
        try:
            # API config should already be initialized during
            # SafetyNet.initialize

            # Check if api_config initialization succeeded
            if not self.api_config:
                logger.error(
                    "API config not available for profit calculation - cannot proceed"
                )
                return False

            # Extract data from transaction
            input_token = transaction_data.get("input_token")
            output_token = transaction_data.get("output_token")
            amount_in = transaction_data.get("amountIn", 0)
            amount_out = transaction_data.get("amountOut", 0)

            # If tokens are not provided, assume ETH values
            if not input_token or not output_token:
                gas_price = transaction_data.get(
                    "gas_price", await self.get_dynamic_gas_price()
                )
                gas_used = transaction_data.get("gas_used", 21000)

                # Calculate gas cost
                gas_cost = await self._calculate_gas_cost(gas_price, gas_used)

                # Calculate raw profit
                profit = amount_out - amount_in - gas_cost

                # Check against minimum profit threshold
                min_profit = self.config.get("MIN_PROFIT", 0.001)
                is_profitable = profit >= min_profit

                logger.debug(
                    f"Profit check (ETH): {
                        profit:.6f} ETH {
                        '≥' if is_profitable else '<'} {
                        min_profit:.6f} ETH minimum"
                )
                return is_profitable

            # For token transactions, convert to common denomination (ETH)
            # Get token prices
            input_price = await self.api_config.get_real_time_price(input_token, "eth")
            output_price = await self.api_config.get_real_time_price(
                output_token, "eth"
            )

            if not input_price or not output_price:
                logger.warning(
                    f"Could not get token prices for {input_token} or {output_token}"
                )
                return False

            # Calculate values in ETH
            input_value_eth = float(amount_in) * float(input_price)
            output_value_eth = float(amount_out) * float(output_price)

            # Get gas costs
            gas_price = transaction_data.get(
                "gas_price", await self.get_dynamic_gas_price()
            )
            gas_used = transaction_data.get(
                "gas_used", 150000
            )  # Higher default for token transactions
            gas_cost = await self._calculate_gas_cost(gas_price, gas_used)

            # Calculate net profit
            profit = output_value_eth - input_value_eth - gas_cost

            # Apply safety adjustments
            # Account for slippage
            congestion = await self.get_network_congestion()
            slippage = await self.adjust_slippage_tolerance(congestion)
            slippage_factor = 1.0 - (slippage / 100)
            adjusted_profit = profit * slippage_factor

            # Check against minimum profit threshold
            min_profit = self.config.get("MIN_PROFIT", 0.001)
            is_profitable = adjusted_profit >= min_profit

            logger.debug(
                f"Profit check (tokens): {
                    adjusted_profit:.6f} ETH {
                    '≥' if is_profitable else '<'} {
                    min_profit:.6f} ETH minimum"
            )

            # Include more details in logs if profitable
            if is_profitable:
                logger.info(
                    f"Profitable transaction: {input_token}->{output_token}, in: {amount_in}, out: {amount_out}, profit: {
                        adjusted_profit:.6f} ETH"
                )

            return is_profitable

        except Exception as e:
            logger.error(f"Error ensuring profit: {e}")
            return False

    async def check_transaction_safety(
        self, tx_data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check if a transaction is safe to execute, considering multiple
        factors.

        Args:
            tx_data: Transaction data including gas price, tokens, amounts, etc.

        Returns:
            Tuple of (is_safe, details)
        """
        try:
            result = {
                "checks_passed": 0,
                "checks_total": 6,  # Update this if adding more checks
                "check_details": {},
            }

            # 1. Check gas price
            gas_price = tx_data.get("gas_price", await self.get_dynamic_gas_price())
            max_gas_price = self.config.get("MAX_GAS_PRICE_GWEI", 100)
            gas_ok = gas_price <= max_gas_price

            if gas_ok:
                result["checks_passed"] += 1

            result["check_details"]["gas_check"] = {
                "passed": gas_ok,
                "details": {"gas_price": gas_price, "max_allowed": max_gas_price},
            }

            # 2. Check network congestion
            congestion = await self.get_network_congestion()
            max_congestion = self.config.get("MAX_NETWORK_CONGESTION", 0.8)
            congestion_ok = congestion < max_congestion

            if congestion_ok:
                result["checks_passed"] += 1

            result["check_details"]["congestion_check"] = {
                "passed": congestion_ok,
                "details": {"congestion": congestion, "max_allowed": max_congestion},
            }

            # 3. Check profitability
            profit_ok = await self.ensure_profit(tx_data)

            if profit_ok:
                result["checks_passed"] += 1

            result["check_details"]["profit_check"] = {"passed": profit_ok}

            # 4. Check token allowlist if specified
            allowed_tokens = self.config.get("ALLOWED_TOKENS", [])
            token_check_required = bool(allowed_tokens)
            token_check_ok = True

            if token_check_required:
                input_token = tx_data.get("input_token")
                output_token = tx_data.get("output_token")

                if input_token and input_token not in allowed_tokens:
                    token_check_ok = False

                if output_token and output_token not in allowed_tokens:
                    token_check_ok = False

            if token_check_ok:
                result["checks_passed"] += 1

            result["check_details"]["token_check"] = {
                "passed": token_check_ok,
                "required": token_check_required,
            }

            # 5. Check balance adequacy for transaction
            balance_check_ok = True

            try:
                value = tx_data.get("value", 0)
                from_address = tx_data.get("from", self.account_address)

                # Get actual balance
                balance = await self.web3.eth.get_balance(from_address)

                # Ensure we have enough balance plus a safety margin
                required_balance = value * 1.05  # 5% margin
                balance_check_ok = balance >= required_balance

                result["check_details"]["balance_check"] = {
                    "passed": balance_check_ok,
                    "details": {
                        "balance": float(self.web3.from_wei(balance, "ether")),
                        "required": (
                            float(self.web3.from_wei(required_balance, "ether"))
                            if value
                            else "N/A"
                        ),
                    },
                }
            except Exception as e:
                logger.error(f"Error checking balance: {e}")
                result["check_details"]["balance_check"] = {
                    "passed": False,
                    "error": str(e),
                }
                balance_check_ok = False

            if balance_check_ok:
                result["checks_passed"] += 1

            # 6. Check for duplicate transaction
            tx_hash = tx_data.get("hash")
            duplicate_check_ok = True

            if tx_hash:
                duplicate_check_ok = not await self.is_transaction_duplicate(tx_hash)

                result["check_details"]["duplicate_check"] = {
                    "passed": duplicate_check_ok
                }
            else:
                result["check_details"]["duplicate_check"] = {
                    "passed": True,
                    "details": "No transaction hash provided to check",
                }

            if duplicate_check_ok:
                result["checks_passed"] += 1

            # Calculate overall safety percentage
            safety_percentage = (result["checks_passed"] / result["checks_total"]) * 100
            result["safety_percentage"] = safety_percentage

            # Determine if safe based on required percentage
            min_safety_percentage = self.config.get("MIN_SAFETY_PERCENTAGE", 85)
            is_safe = safety_percentage >= min_safety_percentage

            # Set final results
            result["is_safe"] = is_safe

            return is_safe, result

        except Exception as e:
            logger.error(f"Error checking transaction safety: {e}")
            return False, {"is_safe": False, "error": str(e)}

    async def estimate_gas(self, tx: Dict[str, Any]) -> int:
        """Estimate gas cost for a transaction.

        Args:
            tx: The transaction object to estimate gas for

        Returns:
            Estimated gas amount
        """
        try:
            # Make a copy of the transaction to avoid modifying the original
            tx_copy = tx.copy()

            # Remove keys that should not be included in estimation
            for key in [
                "nonce",
                "gasPrice",
                "gas",
                "maxFeePerGas",
                "maxPriorityFeePerGas",
            ]:
                if key in tx_copy:
                    del tx_copy[key]

            # Ensure standard transaction parameters
            if "value" not in tx_copy:
                tx_copy["value"] = 0

            gas_estimate = await self.web3.eth.estimate_gas(tx_copy)
            logger.debug(f"Gas estimate for transaction: {gas_estimate}")

            # Add a safety margin (10% by default)
            safety_margin = self.config.get("GAS_ESTIMATE_SAFETY_MARGIN", 1.1)
            adjusted_estimate = int(gas_estimate * safety_margin)

            return adjusted_estimate

        except Exception as e:
            logger.warning(f"Failed to estimate gas: {str(e)}")
            # Return a default high value as fallback
            return self.config.get("DEFAULT_GAS_LIMIT", 500000)

    async def is_healthy(self) -> bool:
        """Check if the safety net system is healthy.

        Returns:
            True if the system is in a healthy state, False otherwise
        """
        try:
            # Check web3 connection
            if not await self.web3.is_connected():
                logger.warning("Web3 connection is down")
                return False

            # Check if we can fetch account balance (basic blockchain
            # interaction)
            _ = await self.web3.eth.get_balance(self.account_address)

            # Check if circuit breaker is active
            if self.circuit_broken:
                logger.warning(
                    f"Circuit breaker is active: {self.circuit_break_reason}"
                )
                return False

            return True
        except Exception as e:
            logger.error(f"Safety net health check failed: {str(e)}")
            return False

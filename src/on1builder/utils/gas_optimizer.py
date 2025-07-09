# src/on1builder/utils/gas_optimizer.py
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import statistics

from web3 import AsyncWeb3

from on1builder.utils.logging_config import get_logger

logger = get_logger(__name__)

class GasOptimizer:
    """Advanced gas optimization manager for MEV strategies."""
    
    def __init__(self, web3: AsyncWeb3):
        self._web3 = web3
        self._gas_history: List[Tuple[datetime, int]] = []
        self._pending_tx_gas_prices: List[int] = []
        self._base_fee_history: List[Tuple[datetime, int]] = []
        self._priority_fee_history: List[Tuple[datetime, int]] = []
        self._is_eip1559_supported = None
        
    async def initialize(self):
        """Initialize gas optimizer with current network state."""
        try:
            # Check EIP-1559 support
            latest_block = await self._web3.eth.get_block('latest')
            self._is_eip1559_supported = 'baseFeePerGas' in latest_block
            
            # Initialize gas price history
            await self._update_gas_metrics()
            
            logger.info(f"GasOptimizer initialized. EIP-1559 support: {self._is_eip1559_supported}")
            
        except Exception as e:
            logger.error(f"Error initializing GasOptimizer: {e}")
            self._is_eip1559_supported = False

    async def get_optimal_gas_params(self, priority_level: str = "normal", 
                                   target_block_inclusion: int = 1) -> Dict[str, int]:
        """
        Get optimal gas parameters for transaction inclusion.
        
        Args:
            priority_level: "low", "normal", "high", "urgent"
            target_block_inclusion: Number of blocks to target for inclusion (1-5)
        """
        await self._update_gas_metrics()
        
        if self._is_eip1559_supported:
            return await self._get_eip1559_params(priority_level, target_block_inclusion)
        else:
            return await self._get_legacy_gas_params(priority_level, target_block_inclusion)

    async def _get_eip1559_params(self, priority_level: str, target_blocks: int) -> Dict[str, int]:
        """Calculate optimal EIP-1559 gas parameters."""
        try:
            latest_block = await self._web3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            # Calculate priority fee based on recent successful transactions
            priority_multipliers = {
                "low": 1.0,
                "normal": 1.2,
                "high": 1.5,
                "urgent": 2.0
            }
            
            # Base priority fee calculation
            if self._priority_fee_history:
                recent_priority_fees = [fee for _, fee in self._priority_fee_history[-20:]]
                avg_priority_fee = statistics.median(recent_priority_fees)
            else:
                avg_priority_fee = self._web3.to_wei(2, 'gwei')  # Default 2 gwei
            
            priority_fee = int(avg_priority_fee * priority_multipliers.get(priority_level, 1.2))
            
            # Calculate max fee with base fee prediction
            predicted_base_fee = self._predict_base_fee(target_blocks)
            max_fee_per_gas = predicted_base_fee + priority_fee
            
            # Add buffer for base fee fluctuations
            buffer_multiplier = 1.1 + (target_blocks - 1) * 0.05  # More buffer for later blocks
            max_fee_per_gas = int(max_fee_per_gas * buffer_multiplier)
            
            return {
                'maxFeePerGas': max_fee_per_gas,
                'maxPriorityFeePerGas': priority_fee,
                'type': 2  # EIP-1559 transaction type
            }
            
        except Exception as e:
            logger.error(f"Error calculating EIP-1559 params: {e}")
            # Fallback to legacy
            return await self._get_legacy_gas_params(priority_level, target_blocks)

    async def _get_legacy_gas_params(self, priority_level: str, target_blocks: int) -> Dict[str, int]:
        """Calculate optimal legacy gas price."""
        try:
            current_gas_price = await self._web3.eth.gas_price
            
            # Analyze recent gas prices
            if self._gas_history:
                recent_prices = [price for _, price in self._gas_history[-50:]]
                percentile_map = {
                    "low": 25,
                    "normal": 50,
                    "high": 75,
                    "urgent": 90
                }
                percentile = percentile_map.get(priority_level, 50)
                target_price = statistics.quantiles(recent_prices, n=100)[percentile-1]
            else:
                target_price = current_gas_price
            
            # Adjust for target block inclusion
            block_multiplier = 1.0 + (target_blocks - 1) * 0.1
            optimal_price = int(max(target_price, current_gas_price) * block_multiplier)
            
            return {
                'gasPrice': optimal_price,
                'type': 0  # Legacy transaction type
            }
            
        except Exception as e:
            logger.error(f"Error calculating legacy gas params: {e}")
            return {'gasPrice': await self._web3.eth.gas_price, 'type': 0}

    def _predict_base_fee(self, blocks_ahead: int) -> int:
        """Predict base fee for future blocks based on historical data."""
        if not self._base_fee_history or blocks_ahead <= 0:
            # Fallback to current base fee
            return self._base_fee_history[-1][1] if self._base_fee_history else 0
        
        # Simple linear prediction based on recent trend
        recent_fees = [fee for _, fee in self._base_fee_history[-10:]]
        if len(recent_fees) < 2:
            return recent_fees[-1] if recent_fees else 0
        
        # Calculate trend
        trend = (recent_fees[-1] - recent_fees[0]) / len(recent_fees)
        predicted_fee = recent_fees[-1] + (trend * blocks_ahead)
        
        # Apply EIP-1559 constraints (max 12.5% increase per block)
        max_increase_factor = 1.125 ** blocks_ahead
        max_predicted_fee = recent_fees[-1] * max_increase_factor
        
        return int(min(max(predicted_fee, 0), max_predicted_fee))

    async def _update_gas_metrics(self):
        """Update gas price metrics from network data."""
        try:
            now = datetime.now()
            
            # Get current gas price
            current_gas_price = await self._web3.eth.gas_price
            self._gas_history.append((now, current_gas_price))
            
            # Get current base fee if EIP-1559 is supported
            if self._is_eip1559_supported:
                latest_block = await self._web3.eth.get_block('latest')
                base_fee = latest_block.get('baseFeePerGas', 0)
                self._base_fee_history.append((now, base_fee))
                
                # Calculate priority fee by analyzing recent transactions
                try:
                    # Get recent transactions from the block
                    block_transactions = latest_block.get('transactions', [])
                    priority_fees = []
                    
                    # Sample up to 20 recent transactions for priority fee analysis
                    for tx_hash in block_transactions[-20:]:
                        try:
                            tx = await self._web3.eth.get_transaction(tx_hash)
                            if tx.get('maxPriorityFeePerGas'):
                                priority_fees.append(tx['maxPriorityFeePerGas'])
                            elif tx.get('gasPrice') and base_fee:
                                # Calculate effective priority fee for legacy transactions
                                effective_priority = max(tx['gasPrice'] - base_fee, 0)
                                priority_fees.append(effective_priority)
                        except Exception:
                            continue
                    
                    if priority_fees:
                        # Use median priority fee for more accurate estimation
                        priority_fees.sort()
                        median_priority = priority_fees[len(priority_fees) // 2]
                        estimated_priority = median_priority
                    else:
                        # Fallback calculation
                        estimated_priority = max(current_gas_price - base_fee, 0)
                        
                except Exception as e:
                    self.logger.debug(f"Failed to analyze priority fees: {e}")
                    estimated_priority = max(current_gas_price - base_fee, 0)
                
                self._priority_fee_history.append((now, estimated_priority))
            
            # Clean old data (keep last 2 hours)
            cutoff_time = now - timedelta(hours=2)
            self._gas_history = [(t, p) for t, p in self._gas_history if t > cutoff_time]
            self._base_fee_history = [(t, p) for t, p in self._base_fee_history if t > cutoff_time]
            self._priority_fee_history = [(t, p) for t, p in self._priority_fee_history if t > cutoff_time]
            
        except Exception as e:
            logger.error(f"Error updating gas metrics: {e}")

    async def estimate_transaction_cost(self, gas_limit: int, priority_level: str = "normal") -> Decimal:
        """Estimate transaction cost in ETH for given gas limit and priority."""
        gas_params = await self.get_optimal_gas_params(priority_level)
        
        if gas_params.get('type') == 2:  # EIP-1559
            # Use max fee for cost estimation (worst case)
            gas_price = gas_params['maxFeePerGas']
        else:
            gas_price = gas_params['gasPrice']
        
        cost_wei = gas_limit * gas_price
        return Decimal(cost_wei) / Decimal(10**18)

    async def should_delay_transaction(self, priority_level: str = "normal") -> Tuple[bool, Optional[int]]:
        """
        Determine if transaction should be delayed due to high gas prices.
        Returns (should_delay, estimated_wait_seconds)
        """
        try:
            if not self._gas_history or len(self._gas_history) < 10:
                return False, None
            
            current_price = self._gas_history[-1][1]
            recent_prices = [price for _, price in self._gas_history[-20:]]
            avg_recent_price = statistics.mean(recent_prices)
            
            # Calculate price premium
            price_premium = (current_price - avg_recent_price) / avg_recent_price
            
            # Delay thresholds based on priority
            delay_thresholds = {
                "low": 0.2,      # 20% above average
                "normal": 0.4,   # 40% above average  
                "high": 0.8,     # 80% above average
                "urgent": 2.0    # Never delay urgent transactions
            }
            
            threshold = delay_thresholds.get(priority_level, 0.4)
            
            if price_premium > threshold:
                # Estimate wait time based on historical gas price patterns
                try:
                    # Analyze historical base fee trends to predict normalization time
                    if len(self._base_fee_history) >= 10:
                        recent_fees = [fee for _, fee in self._base_fee_history[-10:]]
                        
                        # Calculate rate of change in base fees
                        fee_changes = []
                        for i in range(1, len(recent_fees)):
                            change_rate = (recent_fees[i] - recent_fees[i-1]) / recent_fees[i-1]
                            fee_changes.append(change_rate)
                        
                        if fee_changes:
                            avg_change_rate = sum(fee_changes) / len(fee_changes)
                            
                            # If fees are trending down, shorter wait
                            if avg_change_rate < -0.05:  # Decreasing by >5% per block
                                estimated_wait = int(300 + (price_premium * 600))  # 5-15 minutes
                            elif avg_change_rate > 0.05:  # Increasing by >5% per block
                                estimated_wait = int(600 + (price_premium * 1800))  # 10-40 minutes
                            else:  # Stable
                                estimated_wait = int(450 + (price_premium * 1200))  # 7.5-27.5 minutes
                        else:
                            estimated_wait = int(300 + (price_premium * 1200))  # Default 5-25 minutes
                    else:
                        # Not enough historical data, use conservative estimate
                        estimated_wait = int(600 + (price_premium * 900))  # 10-25 minutes
                        
                except Exception as e:
                    self.logger.debug(f"Error calculating wait time: {e}")
                    estimated_wait = int(300 + (price_premium * 1200))  # Fallback 5-25 minutes
                
                return True, estimated_wait
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error determining transaction delay: {e}")
            return False, None

    def get_gas_analytics(self) -> Dict[str, Any]:
        """
        Get comprehensive gas analytics for monitoring dashboard.
        Consolidates efficiency reporting and basic analytics.
        """
        analytics = {
            "gas_history_count": len(self._gas_history),
            "base_fee_history_count": len(self._base_fee_history),
            "priority_fee_history_count": len(self._priority_fee_history),
            "eip1559_supported": self._is_eip1559_supported,
            "last_update": self._gas_history[-1][0].isoformat() if self._gas_history else None
        }
        
        if not self._gas_history:
            analytics["error"] = "No gas history available"
            return analytics
        
        # Use recent data for analysis (last 50 data points for efficiency, last 10 for recent)
        recent_prices = [price for _, price in self._gas_history[-50:]]
        very_recent_prices = [price for _, price in self._gas_history[-10:]]
        
        if recent_prices:
            # Consolidated analytics combining both efficiency and recent data
            analytics.update({
                "current_gas_price_gwei": float(self._web3.from_wei(recent_prices[-1], 'gwei')),
                "avg_gas_price_gwei": float(self._web3.from_wei(statistics.mean(recent_prices), 'gwei')),
                "min_gas_price_gwei": float(self._web3.from_wei(min(recent_prices), 'gwei')),
                "max_gas_price_gwei": float(self._web3.from_wei(max(recent_prices), 'gwei')),
                "recent_avg_gas_gwei": float(self._web3.from_wei(statistics.mean(very_recent_prices), 'gwei')),
                "recent_min_gas_gwei": float(self._web3.from_wei(min(very_recent_prices), 'gwei')),
                "recent_max_gas_gwei": float(self._web3.from_wei(max(very_recent_prices), 'gwei')),
                "gas_price_volatility": float(statistics.stdev(recent_prices) / statistics.mean(recent_prices)) if len(recent_prices) > 1 else 0,
                "data_points": len(recent_prices)
            })
        
        # Add EIP-1559 specific data if available
        if self._is_eip1559_supported and self._base_fee_history:
            recent_base_fees = [fee for _, fee in self._base_fee_history[-20:]]
            recent_priority_fees = [fee for _, fee in self._priority_fee_history[-20:]]
            
            if recent_base_fees and recent_priority_fees:
                analytics.update({
                    "current_base_fee_gwei": float(self._web3.from_wei(recent_base_fees[-1], 'gwei')),
                    "avg_base_fee_gwei": float(self._web3.from_wei(statistics.mean(recent_base_fees), 'gwei')),
                    "avg_priority_fee_gwei": float(self._web3.from_wei(statistics.mean(recent_priority_fees), 'gwei')),
                })
        
        return analytics

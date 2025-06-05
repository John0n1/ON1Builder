#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – StrategyExecutor
========================
A lightweight reinforcement learning agent that selects and executes the best strategy
for a given transaction type, using an ε-greedy approach to explore and exploit.
License: MIT
"""

from __future__ import annotations

import json
import random
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

import numpy as np
from web3 import AsyncWeb3

from ..config.settings import GlobalSettings

# Break circular dependency
if TYPE_CHECKING:
    from ..core.transaction_manager import TransactionManager

from ..monitoring.market_data_feed import MarketDataFeed
from ..utils.logging_config import get_logger
from .safety_guard import SafetyGuard

logger = get_logger(__name__)


class StrategyPerformanceMetrics:
    """Mutable container for per-strategy stats."""

    def __init__(self) -> None:
        self.successes: int = 0
        self.failures: int = 0
        self.profit: Decimal = Decimal("0")
        self.total_executions: int = 0
        self.avg_execution_time: float = 0.0

    @property
    def success_rate(self) -> float:
        return (
            (self.successes / self.total_executions) if self.total_executions else 0.0
        )


class StrategyGlobalSettings:
    """Tunable hyper-parameters for learning."""

    def __init__(self, config: GlobalSettings):
        # Load from config or use defaults
        self.decay_factor: float = config.strategy_decay_factor
        self.base_learning_rate: float = config.strategy_learning_rate
        self.exploration_rate: float = config.strategy_exploration_rate
        self.min_weight: float = config.strategy_min_weight
        self.max_weight: float = config.strategy_max_weight
        self.market_weight: float = config.strategy_market_weight
        self.gas_weight: float = config.strategy_gas_weight


class StrategyExecutor:
    """Chooses & executes the best strategy via lightweight reinforcement learning."""

    def __init__(
        self,
        web3: AsyncWeb3,
        config: GlobalSettings,
        transaction_core: TransactionManager,
        safety_net: SafetyGuard,
        market_monitor: MarketDataFeed,
        main_orchestrator: Optional[Any] = None,  # Reference to MainOrchestrator for shared resources
    ) -> None:
        self.web3 = web3
        self.cfg = config
        self.txc = transaction_core
        self.safety_net = safety_net
        self.market_monitor = market_monitor
        self.api_manager = getattr(config, 'api', None)  # Use api attribute instead
        self.main_orchestrator = main_orchestrator  # Store reference to MainOrchestrator

        # Use path_helpers to get the correct resource path
        from ..utils.path_helpers import get_resource_path

        self._WEIGHT_FILE = get_resource_path("ml_models", "strategy_weights.json")
        self._SAVE_EVERY = config.strategy_save_interval

        # Set up access to shared components if MainCore is provided
        self.db_manager = None
        self.abi_registry = None
        if main_orchestrator and hasattr(main_orchestrator, "components"):
            self.db_manager = main_orchestrator.components.get("db_manager")
            self.abi_registry = main_orchestrator.components.get("abi_registry")
            if self.db_manager:
                logger.debug("StrategyExecutor: Using shared DB manager from MainCore")
            if self.abi_registry:
                logger.debug(
                    "StrategyExecutor: Using shared ABI registry from MainCore"
                )

        # Supported strategy types and their function lists
        self._registry: Dict[str, List[Callable[[Dict[str, Any]], Awaitable[Any]]]] = {
            "eth_transaction": [self.txc.handle_eth_transaction],
            "front_run": [self.txc.front_run],
            "back_run": [self.txc.back_run],
            "sandwich_attack": [self.txc.execute_sandwich_attack],
        }

        # Initialize metrics and weights
        self.metrics: Dict[str, StrategyPerformanceMetrics] = {
            stype: StrategyPerformanceMetrics() for stype in self._registry
        }
        self.weights: Dict[str, np.ndarray] = {
            stype: np.ones(len(funcs), dtype=float)
            for stype, funcs in self._registry.items()
        }

        self.learning_cfg = StrategyGlobalSettings(config)
        self._update_counter: int = 0
        self._last_saved_weights = ""  # Initialize to empty string

    async def initialize(self) -> None:
        """Load persisted weights from disk."""
        self._load_weights()
        logger.info("StrategyExecutor initialized – weights loaded.")

    async def stop(self) -> None:
        """Persist weights on shutdown."""
        self._save_weights()
        logger.info("StrategyExecutor state saved on shutdown.")

    def _load_weights(self) -> None:
        """Load strategy weights from JSON file."""
        if self._WEIGHT_FILE.exists():
            try:
                data = json.loads(self._WEIGHT_FILE.read_text())
                for stype, arr in data.items():
                    if stype in self.weights and len(arr) == len(self.weights[stype]):
                        self.weights[stype] = np.array(arr, dtype=float)
            except Exception as e:
                logger.warning(f"Failed to load strategy weights: {e}")

    def _save_weights(self) -> None:
        """Save strategy weights to disk if they have changed."""
        try:
            # Convert NumPy arrays to regular Python lists for JSON serialization
            serializable_weights = {}
            for stype, weights in self.weights.items():
                if hasattr(weights, "tolist"):  # Check if it's a NumPy array or similar
                    serializable_weights[stype] = weights.tolist()
                else:
                    serializable_weights[stype] = weights

            current = json.dumps(serializable_weights, sort_keys=True)
            if self._last_saved_weights != current:
                self._WEIGHT_FILE.write_text(current)
                self._last_saved_weights = current
                logger.debug(f"Saved strategy weights to {self._WEIGHT_FILE}")
        except Exception as e:
            logger.error(f"Failed to save strategy weights: {e}")

    def get_strategies(
        self, strategy_type: str
    ) -> List[Callable[[Dict[str, Any]], Awaitable[Any]]]:
        """Return the list of strategy callables for a given type."""
        return self._registry.get(strategy_type, [])

    async def execute_best_strategy(
        self, target_tx: Dict[str, Any], strategy_type: str
    ) -> bool:
        """Select and run the best strategy for the given transaction."""
        strategies = self.get_strategies(strategy_type)
        if not strategies:
            logger.debug(f"No strategies for type {strategy_type}")
            return False

        chosen = await self._select_strategy(strategies, strategy_type)
        before_profit = getattr(self.txc, "current_profit", 0.0)
        start_ts = time.perf_counter()

        success: bool = await chosen(target_tx)

        exec_time = time.perf_counter() - start_ts
        after_profit = getattr(self.txc, "current_profit", before_profit)
        profit = after_profit - before_profit

        await self._update_after_run(
            strategy_type, chosen.__name__, success, Decimal(profit), exec_time
        )
        return success

    async def _select_strategy(
        self,
        strategies: List[Callable[[Dict[str, Any]], Awaitable[Any]]],
        strategy_type: str,
    ) -> Callable[[Dict[str, Any]], Awaitable[Any]]:
        """ε-greedy selection over softmaxed weights with market condition adjustments."""
        if random.random() < self.learning_cfg.exploration_rate:
            choice = random.choice(strategies)
            logger.debug(f"Exploration chose {choice.__name__} for {strategy_type}")
            return choice

        # Get base weights
        w = self.weights[strategy_type].copy()

        # Adjust weights based on market conditions
        try:
            market_adjustment = await self._get_market_condition_adjustment(
                strategy_type
            )
            gas_adjustment = await self._get_gas_condition_adjustment(strategy_type)

            # Apply adjustments with configurable weights
            w = w * (
                1.0
                + self.learning_cfg.market_weight * market_adjustment
                + self.learning_cfg.gas_weight * gas_adjustment
            )

        except Exception as e:
            logger.debug(f"Error applying market adjustments: {e}")
            # Continue with base weights if adjustment fails

        # Softmax selection
        exp_w = np.exp(w - w.max())
        probs = exp_w / exp_w.sum()
        idx = np.random.choice(len(strategies), p=probs)
        selected = strategies[idx]
        logger.debug(
            f"Exploitation chose {selected.__name__} (weight={w[idx]:.3f}, p={probs[idx]:.3f})"
        )
        return selected

    async def _update_after_run(
        self,
        stype: str,
        sname: str,
        success: bool,
        profit: Decimal,
        exec_time: float,
    ) -> None:
        """Update metrics and adjust weights based on outcome."""
        m = self.metrics[stype]
        m.total_executions += 1
        m.avg_execution_time = (
            m.avg_execution_time * self.learning_cfg.decay_factor
            + exec_time * (1 - self.learning_cfg.decay_factor)
        )

        if success:
            m.successes += 1
            m.profit += profit
        else:
            m.failures += 1

        idx = self._strategy_index(stype, sname)
        if idx >= 0:
            reward = self._calc_reward(success, profit, exec_time)
            lr = self.learning_cfg.base_learning_rate / (1 + 0.001 * m.total_executions)
            new_weight = self.weights[stype][idx] + lr * reward
            clipped = float(
                np.clip(
                    new_weight,
                    self.learning_cfg.min_weight,
                    self.learning_cfg.max_weight,
                )
            )
            self.weights[stype][idx] = clipped
            logger.debug(
                f"Updated weight for {stype}/{sname}: {clipped:.3f} (reward={reward:.3f})"
            )

        self._update_counter += 1
        if self._update_counter % self._SAVE_EVERY == 0:
            self._save_weights()

    def _calc_reward(self, success: bool, profit: Decimal, exec_time: float) -> float:
        """Compute reward: profit-based with time and success penalties/bonuses.

        Enhanced reward function that considers:
        - Profit magnitude (primary factor)
        - Execution time penalty
        - Success/failure bonus/penalty
        - Diminishing returns for very high profits
        """
        base_reward = 0.0

        if success:
            # Profit-based reward with diminishing returns
            profit_float = float(profit)
            if profit_float > 0:
                # Use log scale for large profits to prevent extreme rewards
                base_reward = min(profit_float, 2.0 * np.log(profit_float + 1.0))
            else:
                # Small penalty for zero profit success
                base_reward = -0.01

            # Success bonus
            base_reward += 0.05
        else:
            # Failure penalty scaled by expected profit potential
            base_reward = -0.10

        # Time penalty (encourage faster execution)
        time_penalty = 0.01 * min(exec_time, 30.0)  # Cap time penalty at 30 seconds

        # Gas efficiency bonus/penalty (if available)
        gas_penalty = 0.0
        # Gas usage tracking would require additional implementation in TransactionManager

        total_reward = base_reward - time_penalty - gas_penalty
        return float(np.clip(total_reward, -1.0, 5.0))  # Reasonable reward bounds

    def _strategy_index(self, stype: str, name: str) -> int:
        """Find index of a strategy by function name."""
        for i, fn in enumerate(self.get_strategies(stype)):
            if fn.__name__ == name:
                return i
        return -1

    async def is_healthy(self) -> bool:
        """Check if StrategyExecutor is in a healthy state."""
        try:
            # Ensure core dependencies exist
            if not self.txc or not self.safety_net or not self.market_monitor:
                logger.warning("Missing core dependencies")
                return False

            # Ensure at least one strategy is available
            if not any(self._registry.values()):
                logger.warning("No strategies registered")
                return False

            return True
        except Exception as e:
            logger.error(f"StrategyExecutor health check failed: {e}")
            return False

    async def _get_market_condition_adjustment(self, strategy_type: str) -> float:
        """Calculate market condition adjustment factor for strategy weights.

        Returns adjustment factor (-1.0 to 1.0) based on current market conditions.
        Positive values favor the strategy, negative values discourage it.
        """
        try:
            # Get current market data using available methods
            if not self.market_monitor:
                logger.debug("No market monitor available, using neutral market adjustment")
                return 0.0

            # Use available market data methods for strategy optimization
            try:
                # Try to get current market conditions
                market_data = getattr(self.market_monitor, 'get_current_data', None)
                if not market_data:
                    logger.debug("Market monitor has no get_current_data method")
                    return 0.0
                
                current_data = await market_data()
                if not current_data:
                    logger.debug("No current market data available")
                    return 0.0
                
                # Extract relevant metrics for strategy adjustment
                volatility = current_data.get("volatility", 0.0)
                volume = current_data.get("volume", 0.0)
                trend = current_data.get("trend", 0.0)  # -1 to 1, bearish to bullish
                
                # Strategy-specific market condition preferences
                if strategy_type == "front_run":
                    # Front-running works better in high volatility, moderate volume
                    if volatility > 0.5 and 0.3 < volume < 0.8:
                        return min(0.3, volatility * 0.5)  # Boost up to 30%
                    return max(-0.2, -volatility * 0.3)  # Reduce in low volatility
                
                elif strategy_type == "arbitrage":
                    # Arbitrage benefits from price discrepancies and good liquidity
                    if volume > 0.6 and abs(trend) < 0.3:  # High volume, sideways market
                        return min(0.25, volume * 0.4)
                    return max(-0.15, -abs(trend) * 0.4)  # Reduce in trending markets
                
                elif strategy_type == "sandwich":
                    # Sandwich attacks work best with predictable large transactions
                    if 0.4 < volatility < 0.7 and volume > 0.5:
                        return min(0.2, (volatility + volume) * 0.15)
                    return -0.1  # Generally reduce in unfavorable conditions
                
                else:
                    # Generic strategy adjustment
                    market_score = (volatility + volume) / 2.0
                    if market_score > 0.6:
                        return min(0.2, market_score * 0.3)
                    return max(-0.1, (market_score - 0.5) * 0.2)
                    
            except Exception as e:
                logger.debug(f"Error accessing market data: {e}")
                return 0.0

        except Exception as e:
            logger.debug(f"Error calculating market adjustment: {e}")
            return 0.0

    async def _get_gas_condition_adjustment(self, strategy_type: str) -> float:
        """Calculate gas condition adjustment factor for strategy weights.

        Returns adjustment factor (-1.0 to 1.0) based on current gas conditions.
        """
        try:
            # Get current gas price from Web3
            current_gas = await self.web3.eth.gas_price
            current_gas_gwei = float(current_gas) / 1e9

            # Define gas thresholds
            low_gas_threshold = 20.0  # gwei
            high_gas_threshold = 100.0  # gwei

            # Normalize gas price to 0-1 scale
            gas_factor = min(
                1.0,
                max(
                    0.0,
                    (current_gas_gwei - low_gas_threshold)
                    / (high_gas_threshold - low_gas_threshold),
                ),
            )

            # Strategy-specific gas preferences
            if strategy_type in ["front_run", "sandwich_attack"]:
                # These strategies are sensitive to gas costs, prefer low gas
                return 1.0 - gas_factor * 1.5  # Strong penalty for high gas
            elif strategy_type == "back_run":
                # Back-running is less time-sensitive, moderate gas preference
                return 0.5 - gas_factor * 0.8
            else:
                # Default: slight preference for lower gas
                return 0.2 - gas_factor * 0.5

        except Exception as e:
            logger.debug(f"Error calculating gas adjustment: {e}")
            return 0.0

    def get_strategy_performance(self) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive performance metrics for all strategies."""
        performance = {}

        for strategy_type, metrics in self.metrics.items():
            weights = self.weights[strategy_type]
            strategies = self.get_strategies(strategy_type)

            strategy_details = []
            for i, strategy_func in enumerate(strategies):
                strategy_details.append(
                    {
                        "name": strategy_func.__name__,
                        "weight": float(weights[i]) if i < len(weights) else 1.0,
                        "selection_probability": (
                            float(
                                np.exp(weights[i] - weights.max())
                                / np.exp(weights - weights.max()).sum()
                            )
                            if len(weights) > i
                            else 0.0
                        ),
                    }
                )

            performance[strategy_type] = {
                "total_executions": metrics.total_executions,
                "successes": metrics.successes,
                "failures": metrics.failures,
                "success_rate": metrics.success_rate,
                "total_profit": float(metrics.profit),
                "avg_execution_time": metrics.avg_execution_time,
                "strategies": strategy_details,
                "exploration_rate": self.learning_cfg.exploration_rate,
            }

        return performance

    async def reset_learning_state(self) -> None:
        """Reset all learning weights and metrics (useful for testing or recalibration)."""
        logger.warning("Resetting StrategyExecutor learning state")

        # Reset weights to uniform
        for stype in self.weights:
            self.weights[stype] = np.ones(len(self.get_strategies(stype)), dtype=float)

        # Reset metrics
        for metrics in self.metrics.values():
            metrics.successes = 0
            metrics.failures = 0
            metrics.profit = Decimal("0")
            metrics.total_executions = 0
            metrics.avg_execution_time = 0.0

        self._update_counter = 0

        # Save reset state
        self._save_weights()
        logger.info("StrategyExecutor learning state reset complete")

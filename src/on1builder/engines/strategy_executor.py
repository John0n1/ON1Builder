#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from on1builder.config.loaders import settings
from on1builder.core.balance_manager import BalanceManager
from on1builder.utils.custom_exceptions import StrategyExecutionError
from on1builder.utils.logging_config import get_logger
from on1builder.utils.path_helpers import get_strategy_weights_path

logger = get_logger(__name__)


class StrategyExecutor:
    """
    ON1Builder strategy executor with dynamic ML adaptation, balance awareness,
    and sophisticated profit optimization.
    """

    def __init__(self, transaction_manager, balance_manager: BalanceManager):
        self._tx_manager = transaction_manager
        self._balance_manager = balance_manager
        self._strategy_weights_path = get_strategy_weights_path()

        # - strategy mapping with metadata
        self._strategies: dict[str, dict[str, Any]] = {
            "arbitrage": {
                "functions": [self._tx_manager.execute_arbitrage],
                "risk_level": "low",
                "min_balance_tier": "low",
                "gas_efficiency": "high",
                "profit_potential": "medium",
            },
            "front_run": {
                "functions": [self._tx_manager.execute_front_run],
                "risk_level": "medium",
                "min_balance_tier": "medium",
                "gas_efficiency": "medium",
                "profit_potential": "high",
            },
            "back_run": {
                "functions": [self._tx_manager.execute_back_run],
                "risk_level": "low",
                "min_balance_tier": "low",
                "gas_efficiency": "high",
                "profit_potential": "medium",
            },
            "sandwich": {
                "functions": [self._tx_manager.execute_sandwich],
                "risk_level": "high",
                "min_balance_tier": "medium",
                "gas_efficiency": "low",
                "profit_potential": "very_high",
            },
            "flashloan_arbitrage": {
                "functions": [self._tx_manager.execute_flashloan_arbitrage],
                "risk_level": "medium",
                "min_balance_tier": "emergency",  # Can work with very low balance
                "gas_efficiency": "medium",
                "profit_potential": "high",
            },
        }

        # ML state
        self._weights: dict[str, list[float]] = {}
        self._strategy_history: list[dict[str, Any]] = []
        self._execution_count = 0
        self._last_weight_update = 0

        # Dynamic parameters
        self._exploration_rate = settings.ml_exploration_rate
        self._learning_rate = settings.ml_learning_rate
        self._decay_rate = settings.ml_decay_rate

        # Performance tracking
        self._strategy_performance: dict[str, dict[str, float]] = {}

        self._load_weights()
        self._initialize_performance_tracking()
        logger.debug(
            "ON1Builder StrategyExecutor initialized with ML and balance awareness."
        )

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _load_weights(self):
        """weight loading with validation and migration."""
        try:
            if self._strategy_weights_path.exists():
                with open(self._strategy_weights_path) as f:
                    data = json.load(f)

                # Support both old and new format
                if "strategies" in data:
                    # New format with metadata
                    for strategy_name, strategy_data in data["strategies"].items():
                        if strategy_name in self._strategies:
                            weights = strategy_data.get("weight", [1.0])
                            if isinstance(weights, (int, float)):
                                weights = [weights]
                            self._weights[strategy_name] = [float(w) for w in weights]
                else:
                    # Old format - direct weights
                    for strategy_name, weights_list in data.items():
                        if strategy_name in self._strategies:
                            self._weights[strategy_name] = [
                                float(w) for w in weights_list
                            ]

                logger.debug("Loaded strategy weights from file.")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                f"Could not load strategy weights: {e}. Using default weights."
            )

        # Initialize missing weights
        for strategy_name, strategy_info in self._strategies.items():
            if strategy_name not in self._weights:
                num_functions = len(strategy_info["functions"])
                self._weights[strategy_name] = [1.0 for _ in range(num_functions)]

    def _is_strategy_enabled(self, strategy_name: str) -> bool:
        """Check global and per-strategy feature flags."""
        mev_disabled = not settings.mev_strategies_enabled
        if mev_disabled and strategy_name in {"front_run", "back_run", "sandwich"}:
            return False
        if strategy_name == "front_run" and not settings.front_running_enabled:
            return False
        if strategy_name == "back_run" and not settings.back_running_enabled:
            return False
        if strategy_name == "sandwich" and not settings.sandwich_attacks_enabled:
            return False
        if strategy_name == "flashloan_arbitrage" and not settings.flashloan_enabled:
            return False
        return True

    def _save_weights(self):
        """weight saving with metadata."""
        data = {
            "version": "2.0",
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "execution_count": self._execution_count,
            "strategies": {},
        }

        for strategy_name, weights in self._weights.items():
            performance = self._strategy_performance.get(strategy_name, {})
            data["strategies"][strategy_name] = {
                "weight": list(weights),
                "performance_metrics": performance,
                "risk_level": self._strategies[strategy_name]["risk_level"],
                "profit_potential": self._strategies[strategy_name]["profit_potential"],
            }

        data["global_settings"] = {
            "exploration_rate": self._exploration_rate,
            "learning_rate": self._learning_rate,
            "decay_rate": self._decay_rate,
        }

        try:
            with open(self._strategy_weights_path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to save strategy weights: {e}")

    def _initialize_performance_tracking(self):
        """Initialize performance tracking for all strategies."""
        for strategy_name in self._strategies:
            self._strategy_performance[strategy_name] = {
                "success_rate": 0.0,
                "avg_profit": 0.0,
                "total_executions": 0,
                "total_profit": 0.0,
                "avg_gas_used": 0.0,
                "last_execution": 0.0,
            }

    async def _get_eligible_strategies(self, opportunity: dict[str, Any]) -> list[str]:
        """
        Filters strategies based on balance tier, risk tolerance, and opportunity type.
        """
        balance_summary = await self._balance_manager.get_balance_summary()
        balance_tier = balance_summary["balance_tier"]

        eligible = []

        tier_rank = {
            "emergency": 0,
            "dust": 1,
            "low": 2,
            "small": 2,
            "medium": 3,
            "large": 4,
            "high": 4,
            "whale": 5,
        }
        current_rank = tier_rank.get(balance_tier, tier_rank["low"])

        for strategy_name, strategy_info in self._strategies.items():
            if not self._is_strategy_enabled(strategy_name):
                continue

            # Check balance tier requirement
            min_tier = strategy_info["min_balance_tier"]
            min_rank = tier_rank.get(min_tier, 0)

            if current_rank < min_rank:
                continue

            # Check if strategy matches opportunity type
            opportunity_type = opportunity.get("strategy_type", "")
            if (
                opportunity_type
                and strategy_name.startswith(opportunity_type)
                or not opportunity_type
            ):
                eligible.append(strategy_name)

        # Require simulation unless bypassed globally; treat missing flag as simulated for legacy callers.
        simulated_flag = opportunity.get("simulated")
        if simulated_flag is False and not settings.allow_unsimulated_trades:
            logger.debug(
                "Opportunity not simulated; restricting to strategies only if global bypass is enabled."
            )
            eligible = []

        logger.debug(
            f"Eligible strategies for balance tier '{balance_tier}': {eligible}"
        )
        return eligible

    def _calculate_strategy_score(
        self, strategy_name: str, opportunity: dict[str, Any]
    ) -> float:
        """
        Calculates a comprehensive score for strategy selection.
        """
        strategy_info = self._strategies[strategy_name]
        performance = self._strategy_performance[strategy_name]
        weights = self._weights[strategy_name]

        # Base score from ML weights
        base_score = self._mean(weights)

        # Performance adjustments
        success_rate_bonus = performance["success_rate"] * 0.3
        profit_bonus = min(performance["avg_profit"] * 100, 0.5)  # Cap profit bonus

        # Opportunity-specific adjustments
        expected_profit = opportunity.get("expected_profit_eth", 0)
        profit_fit = min(expected_profit * 10, 0.3)

        # Gas efficiency consideration
        gas_efficiency_map = {"high": 0.2, "medium": 0.1, "low": -0.1}
        gas_bonus = gas_efficiency_map.get(strategy_info["gas_efficiency"], 0)

        # Risk adjustment based on balance
        risk_penalty = 0
        if strategy_info["risk_level"] == "high":
            risk_penalty = -0.2
        elif strategy_info["risk_level"] == "medium":
            risk_penalty = -0.1

        total_score = (
            base_score
            + success_rate_bonus
            + profit_bonus
            + profit_fit
            + gas_bonus
            + risk_penalty
        )

        logger.debug(
            f"Strategy {strategy_name} score: {total_score:.3f} "
            f"(base: {base_score:.3f}, success: {success_rate_bonus:.3f}, "
            f"profit: {profit_bonus:.3f}, fit: {profit_fit:.3f})"
        )

        return total_score

    async def _select_strategy(
        self, opportunity: dict[str, Any]
    ) -> tuple[Callable | None, str]:
        """
        ON1Builder strategy selection with multi-factor optimization.
        """
        eligible_strategies = await self._get_eligible_strategies(opportunity)

        if not eligible_strategies:
            logger.warning(
                "No eligible strategies found for current balance tier and opportunity"
            )
            return None, ""

        # Exploration vs exploitation
        if random.random() < self._exploration_rate:
            chosen_strategy = random.choice(eligible_strategies)
            chosen_function = random.choice(
                self._strategies[chosen_strategy]["functions"]
            )
            logger.info(f"Exploring strategy: {chosen_strategy}")
            return chosen_function, chosen_strategy

        # Calculate scores for all eligible strategies
        strategy_scores = {}
        for strategy_name in eligible_strategies:
            strategy_scores[strategy_name] = self._calculate_strategy_score(
                strategy_name, opportunity
            )

        # Select best strategy
        best_strategy = max(strategy_scores, key=strategy_scores.get)
        best_function = self._strategies[best_strategy]["functions"][
            0
        ]  # Use first function for now

        logger.info(
            f"Selected best strategy: {best_strategy} (score: {strategy_scores[best_strategy]:.3f})"
        )
        return best_function, best_strategy

    async def simulate_opportunity(self, opportunity: dict[str, Any]) -> bool:
        """
        Attempt to simulate the opportunity before execution. For swap-based strategies,
        reuse the transaction manager's simulate-only path.
        """
        try:
            strategy_type = opportunity.get("strategy_type", "")
            if strategy_type in {"arbitrage", "front_run", "back_run", "sandwich"}:
                # For these strategies we can reuse swap simulation
                # Use the primary swap execution as simulate_only
                await self._tx_manager.execute_swap(
                    opportunity, strategy_type or "simulate", simulate_only=True
                )
                opportunity["simulated"] = True
                return True
            # If not a swap-based strategy, leave as-is
            return opportunity.get("simulated", False)
        except Exception as e:
            logger.debug(f"Simulation failed for opportunity: {e}")
            return False

    async def simulate_opportunities_batch(
        self, opportunities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Simulate a batch of opportunities with limited concurrency."""
        semaphore = asyncio.Semaphore(settings.simulation_concurrency)

        async def _simulate_one(opp: dict[str, Any]) -> dict[str, Any] | None:
            async with semaphore:
                ok = await self.simulate_opportunity(opp)
                return opp if ok else None

        tasks = [_simulate_one(opp) for opp in opportunities]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return [r for r in results if r]

    async def execute_opportunity(self, opportunity: dict[str, Any]) -> dict[str, Any]:
        """
        ON1Builder opportunity execution with comprehensive tracking and learning.
        """
        self._execution_count += 1

        # Check if we should proceed based on balance
        balance_summary = await self._balance_manager.get_balance_summary()
        if (
            balance_summary["emergency_mode"]
            and opportunity.get("expected_profit_eth", 0) < 0.001
        ):
            return {
                "success": False,
                "reason": "Emergency mode: skipping low-profit opportunities",
                "balance_tier": balance_summary["balance_tier"],
            }

        # Ensure simulation unless globally bypassed
        if (
            not opportunity.get("simulated", False)
            and not settings.allow_unsimulated_trades
        ):
            simulated = await self.simulate_opportunity(opportunity)
            if not simulated:
                return {"success": False, "reason": "Simulation failed"}

        # Enforce simulation gate consistently
        if (
            not opportunity.get("simulated", False)
            and not settings.allow_unsimulated_trades
        ):
            return {"success": False, "reason": "Opportunity not simulated"}

        strategy_func, strategy_name = await self._select_strategy(opportunity)
        if not strategy_func:
            return {
                "success": False,
                "reason": "No suitable strategy available",
                "balance_tier": balance_summary["balance_tier"],
            }

        # - opportunity with balance-aware parameters
        ON1Builder_opportunity = await self._ON1Builder_opportunity_with_balance(
            opportunity
        )

        start_time = time.monotonic()
        gas_used = 0

        try:
            result = await strategy_func(ON1Builder_opportunity)

            success = result.get("success", False)
            profit = result.get("profit_eth", 0.0)
            gas_used = result.get("gas_used", 0)

            # Record profit with balance manager
            if success and profit > 0:
                await self._balance_manager.record_profit(
                    Decimal(str(profit)), strategy_name
                )

            # Update learning
            self._update_strategy_performance(strategy_name, success, profit, gas_used)
            self._update_weights_ml(strategy_name, success, profit, opportunity)

            # Save state periodically
            if self._execution_count % settings.ml_update_frequency == 0:
                await self._update_ml_parameters()
                self._save_weights()

            return result

        except StrategyExecutionError as e:
            logger.error(f"Strategy '{strategy_name}' failed: {e}")
            self._update_strategy_performance(strategy_name, False, 0.0, gas_used)
            return {"success": False, "reason": str(e), "strategy": strategy_name}
        finally:
            execution_time = time.monotonic() - start_time
            logger.info(
                f"Strategy '{strategy_name}' execution time: {execution_time:.4f}s"
            )

    async def _ON1Builder_opportunity_with_balance(
        self, opportunity: dict[str, Any]
    ) -> dict[str, Any]:
        """
        ON1Builders opportunity parameters based on current balance situation.
        """
        ON1Builder = opportunity.copy()
        balance_summary = await self._balance_manager.get_balance_summary()

        # Adjust investment amount
        requested_amount = opportunity.get("investment_amount", 0)
        max_amount = balance_summary["max_investment"]

        if requested_amount > max_amount:
            ON1Builder["investment_amount"] = max_amount
            ON1Builder["original_amount"] = requested_amount
            ON1Builder["amount_limited"] = True

        # Set dynamic profit threshold
        ON1Builder["min_profit_threshold"] = balance_summary["profit_threshold"]
        ON1Builder["balance_tier"] = balance_summary["balance_tier"]
        ON1Builder["flashloan_recommended"] = balance_summary["flashloan_recommended"]

        # Adjust gas parameters
        expected_profit = opportunity.get("expected_profit_eth", 0)
        if expected_profit > 0:
            gas_price, should_proceed = (
                await self._balance_manager.calculate_optimal_gas_price(
                    Decimal(str(expected_profit))
                )
            )
            ON1Builder["optimal_gas_price"] = gas_price
            ON1Builder["gas_viable"] = should_proceed

        return ON1Builder

    def _update_strategy_performance(
        self, strategy_name: str, success: bool, profit: float, gas_used: int
    ):
        """Updates detailed performance metrics for a strategy."""
        perf = self._strategy_performance[strategy_name]

        total_executions = perf["total_executions"]
        new_total = total_executions + 1

        # Update success rate (exponential moving average)
        alpha = 0.1
        perf["success_rate"] = (1 - alpha) * perf["success_rate"] + alpha * (
            1.0 if success else 0.0
        )

        # Update profit metrics
        perf["total_profit"] += profit
        perf["avg_profit"] = (
            perf["avg_profit"] * total_executions + profit
        ) / new_total

        # Update gas usage
        if gas_used > 0:
            perf["avg_gas_used"] = (
                perf["avg_gas_used"] * total_executions + gas_used
            ) / new_total

        perf["total_executions"] = new_total
        perf["last_execution"] = time.time()

    def _update_weights_ml(
        self,
        strategy_name: str,
        success: bool,
        profit: float,
        opportunity: dict[str, Any],
    ):
        """ML weight update with contextual learning."""
        if strategy_name not in self._weights:
            return

        # Calculate reward based on multiple factors
        base_reward = 0.0

        if success:
            # Profit-based reward (normalized)
            profit_reward = min(profit * 50, 2.0)  # Cap at 2.0

            # Efficiency reward (profit per gas)
            gas_used = opportunity.get("gas_used", 100000)
            efficiency = profit / (gas_used / 1000000) if gas_used > 0 else 0
            efficiency_reward = min(efficiency, 1.0)

            # Speed reward (faster execution = higher reward)
            execution_time = opportunity.get("execution_time", 30)
            speed_reward = max(0, (30 - execution_time) / 30 * 0.5)

            base_reward = profit_reward + efficiency_reward + speed_reward
        else:
            # Penalty for failure
            base_reward = -1.0

        # Apply learning rate and update
        current_weights = self._weights[strategy_name]

        # Use contextual bandits approach
        context_vector = [
            opportunity.get("expected_profit_eth", 0) * 100,
            1.0 if opportunity.get("flashloan_recommended", False) else 0.0,
            {"emergency": 0, "low": 1, "medium": 2, "high": 3}.get(
                opportunity.get("balance_tier", "medium"), 2
            )
            / 3.0,
        ]

        # Simple linear update (can be ON1Builder with more sophisticated ML)
        for i in range(len(current_weights)):
            gradient = base_reward * context_vector[min(i, len(context_vector) - 1)]
            current_weights[i] += self._learning_rate * gradient

            # Ensure weights stay positive
            current_weights[i] = max(current_weights[i], 0.1)

    async def _update_ml_parameters(self):
        """Updates ML parameters based on recent performance."""
        # Decay exploration rate over time
        self._exploration_rate *= self._decay_rate
        self._exploration_rate = max(
            self._exploration_rate, 0.01
        )  # Minimum exploration

        # Adjust learning rate based on overall performance
        recent_performance = self._calculate_recent_performance()
        if recent_performance < 0.5:  # Poor performance
            self._learning_rate = min(
                self._learning_rate * 1.1, 0.1
            )  # Increase learning
        else:  # Good performance
            self._learning_rate = max(
                self._learning_rate * 0.99, 0.001
            )  # Decrease learning

        logger.info(
            f"ML parameters updated - Exploration: {self._exploration_rate:.4f}, "
            f"Learning rate: {self._learning_rate:.6f}"
        )

    def _calculate_recent_performance(self) -> float:
        """Calculates recent overall performance across all strategies."""
        total_success = 0
        total_executions = 0

        for perf in self._strategy_performance.values():
            total_success += perf["success_rate"] * perf["total_executions"]
            total_executions += perf["total_executions"]

        return total_success / total_executions if total_executions > 0 else 0.5

    async def get_strategy_report(self) -> dict[str, Any]:
        """Returns comprehensive strategy performance report."""
        return {
            "execution_count": self._execution_count,
            "ml_parameters": {
                "exploration_rate": self._exploration_rate,
                "learning_rate": self._learning_rate,
                "decay_rate": self._decay_rate,
            },
            "strategy_performance": self._strategy_performance,
            "weights": {k: list(v) for k, v in self._weights.items()},
            "recent_performance": self._calculate_recent_performance(),
            "balance_summary": await self._balance_manager.get_balance_summary(),
        }

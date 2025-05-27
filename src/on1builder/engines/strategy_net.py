# strategy_net.py
"""
ON1Builder – StrategyNet
========================
A lightweight reinforcement learning agent that selects and executes the best strategy
for a given transaction type. It uses a simple ε-greedy approach to explore and exploit.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from on1builder.config.config import APIConfig
from on1builder.core.transaction_core import TransactionCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.utils.logger import setup_logging

logger = setup_logging("Strategy_Net", level="DEBUG")


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
        if self.total_executions == 0:
            return 0.0
        return self.successes / self.total_executions


class StrategyConfiguration:
    """Tunable hyper-parameters."""

    decay_factor: float = 0.95
    base_learning_rate: float = 0.01
    exploration_rate: float = 0.10
    min_weight: float = 0.10
    max_weight: float = 10.0

    # thresholds (copied from Configuration but kept here for quick access)
    FRONT_RUN_OPPORTUNITY_SCORE_THRESHOLD: int = 75
    VOLATILITY_FRONT_RUN_SCORE_THRESHOLD: int = 75
    AGGRESSIVE_FRONT_RUN_RISK_SCORE_THRESHOLD: float = 0.7


class StrategyNet:
    """Chooses & executes the best strategy via lightweight reinforcement
    learning."""

    _WEIGHT_FILE = Path("strategy_weights.json")
    _SAVE_EVERY = 25  # save to disk every N updates to limit IO

    def __init__(
        self,
        transaction_core: TransactionCore,
        market_monitor: MarketMonitor,
        safety_net: SafetyNet,
        api_config: APIConfig,
    ) -> None:
        self.txc = transaction_core
        self.market_monitor = market_monitor
        self.safety_net = safety_net
        self.api_config = api_config

        self.strategy_types: List[str] = [
            "eth_transaction",
            "front_run",
            "back_run",
            "sandwich_attack",
        ]

        self._registry: Dict[str, List[Callable[[Dict[str, Any]], asyncio.Future]]] = {
            "eth_transaction": [self.txc.handle_eth_transaction],
            "front_run": [
                self.txc.front_run,
                self.txc.flashloan_front_run,
                self.txc.aggressive_front_run,
                self.txc.predictive_front_run,
                self.txc.volatility_front_run,
            ],
            "back_run": [
                self.txc.back_run,
                self.txc.price_dip_back_run,
                self.txc.flashloan_back_run,
                self.txc.high_volume_back_run,
            ],
            "sandwich_attack": [
                self.txc.flashloan_sandwich_attack,
                self.txc.execute_sandwich_attack,
            ],
        }

        # metrics + weights --------------------------------------------------
        self.metrics: Dict[str, StrategyPerformanceMetrics] = {
            stype: StrategyPerformanceMetrics() for stype in self.strategy_types
        }
        self.weights: Dict[str, np.ndarray] = {
            stype: np.ones(len(funcs), dtype=float)
            for stype, funcs in self._registry.items()
        }

        self.cfg = StrategyConfiguration()
        self._update_counter = 0  # for lazy disk-save throttle

        # Last saved weights JSON snapshot for persistence
        self._last_saved_weights: Optional[str] = None

    # ------------------------------------------------------------------ #
    # initialisation / shutdown                                          #
    # ------------------------------------------------------------------ #

    async def initialize(self) -> None:
        self._load_weights()
        logger.info("StrategyNet initialised – weights loaded.")

    async def stop(self) -> None:
        self._save_weights()
        logger.info("StrategyNet state saved on shutdown.")

    # ------------------------------------------------------------------ #
    # weight persistence                                                 #
    # ------------------------------------------------------------------ #

    def _load_weights(self) -> None:
        if self._WEIGHT_FILE.exists():
            try:
                data = json.loads(self._WEIGHT_FILE.read_text())
                for stype, arr in data.items():
                    if stype in self.weights and len(arr) == len(self.weights[stype]):
                        self.weights[stype] = np.array(arr, dtype=float)
            except Exception as exc:
                logger.warning("Failed to load strategy weights: %s", exc)

    def _save_weights(self) -> None:
        """Save strategy weights to disk if changed."""
        try:
            current_weights_json = json.dumps(self.weights, sort_keys=True)

            # Only save if weights have changed
            if (
                not hasattr(self, "_last_saved_weights")
                or self._last_saved_weights != current_weights_json
            ):
                with open(self._WEIGHT_FILE, "w") as f:
                    f.write(current_weights_json)
                self._last_saved_weights = current_weights_json
                logger.debug(
                    f"Saved updated strategy weights to {
                        self._WEIGHT_FILE}"
                )
        except Exception as e:
            logger.error(f"Failed to save strategy weights: {e}")

    # ------------------------------------------------------------------ #
    # public helpers                                                     #
    # ------------------------------------------------------------------ #

    def get_strategies(
        self, strategy_type: str
    ) -> List[Callable[[Dict[str, Any]], asyncio.Future]]:
        return self._registry.get(strategy_type, [])

    async def execute_best_strategy(
        self, target_tx: Dict[str, Any], strategy_type: str
    ) -> bool:
        strategies = self.get_strategies(strategy_type)
        if not strategies:
            logger.debug("No strategies registered for type %s", strategy_type)
            return False

        strategy = await self._select_strategy(strategies, strategy_type)
        before_profit = self.txc.current_profit
        start_ts = time.perf_counter()

        success: bool = await strategy(target_tx)

        exec_time = time.perf_counter() - start_ts
        profit = self.txc.current_profit - before_profit

        await self._update_after_run(
            strategy_type, strategy.__name__, success, profit, exec_time
        )
        return success

    # ------------------------------------------------------------------ #
    # strategy selection & learning                                      #
    # ------------------------------------------------------------------ #

    async def _select_strategy(
        self,
        strategies: List[Callable[[Dict[str, Any]], asyncio.Future]],
        strategy_type: str,
    ) -> Callable[[Dict[str, Any]], asyncio.Future]:
        """Ε-greedy selection over soft-maxed weights."""
        if random.random() < self.cfg.exploration_rate:
            choice = random.choice(strategies)
            logger.debug("Exploration chose %s (%s)", choice.__name__, strategy_type)
            return choice

        w = self.weights[strategy_type]
        p = np.exp(w - w.max())
        p = p / p.sum()
        idx = np.random.choice(len(strategies), p=p)
        selected = strategies[idx]
        logger.debug(
            "Exploitation chose %s (weight %.3f, p=%.3f)",
            selected.__name__,
            w[idx],
            p[idx],
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
        """Update metrics & reinforcement weight."""
        m = self.metrics[stype]
        m.total_executions += 1
        m.avg_execution_time = (
            m.avg_execution_time * self.cfg.decay_factor
            + exec_time * (1 - self.cfg.decay_factor)
        )

        if success:
            m.successes += 1
            m.profit += profit
        else:
            m.failures += 1

        idx = self._strategy_index(stype, sname)
        if idx >= 0:
            reward = self._calc_reward(success, profit, exec_time)
            lr = self.cfg.base_learning_rate / (1 + 0.001 * m.total_executions)
            new_val = self.weights[stype][idx] + lr * reward
            self.weights[stype][idx] = float(
                np.clip(new_val, self.cfg.min_weight, self.cfg.max_weight)
            )
            logger.debug(
                "Updated weight of %s/%s: %.3f (reward %.3f)",
                stype,
                sname,
                self.weights[stype][idx],
                reward,
            )

        # disk save throttle
        self._update_counter += 1
        if self._update_counter % self._SAVE_EVERY == 0:
            self._save_weights()

    # ------------------------------------------------------------------ #
    # internals                                                          #
    # ------------------------------------------------------------------ #

    def _calc_reward(self, success: bool, profit: Decimal, exec_time: float) -> float:
        """
        A simple reward:
          +profit (ETH) if success
          −0.05 if fail
          −time_penalty (0.01 * seconds) always
        """
        reward = float(profit) if success else -0.05
        reward -= 0.01 * exec_time
        return reward

    def _strategy_index(self, stype: str, name: str) -> int:
        for i, fn in enumerate(self.get_strategies(stype)):
            if fn.__name__ == name:
                return i
        return -1

    async def is_healthy(self) -> bool:
        """Check if the strategy net system is healthy.

        Returns:
            True if the system is in a healthy state, False otherwise
        """
        try:
            # Check if required dependencies are available
            if not self.txc or not self.safety_net:
                logger.warning("Required dependencies are not available")
                return False

            # Check if strategy registry is populated
            if not self._registry:
                logger.warning("No strategies are loaded")
                return False

            # Check if at least one strategy list is non-empty
            for stype, funcs in self._registry.items():
                if funcs:
                    return True

            logger.warning("No enabled strategies found")
            return False

        except Exception as e:
            logger.error(f"Strategy net health check failed: {str(e)}")
            return False

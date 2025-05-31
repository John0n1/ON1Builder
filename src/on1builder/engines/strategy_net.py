#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – StrategyNet
========================
A lightweight reinforcement learning agent that selects and executes the best strategy
for a given transaction type, using an ε-greedy approach to explore and exploit.
License: MIT
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
from web3 import AsyncWeb3

from on1builder.config.config import Configuration
from on1builder.core.transaction_core import TransactionCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.utils.logger import setup_logging

logger = setup_logging("StrategyNet", level="DEBUG")


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
        return (self.successes / self.total_executions) if self.total_executions else 0.0


class StrategyConfiguration:
    """Tunable hyper-parameters for learning."""

    decay_factor: float = 0.95
    base_learning_rate: float = 0.01
    exploration_rate: float = 0.10
    min_weight: float = 0.10
    max_weight: float = 10.0


class StrategyNet:
    """Chooses & executes the best strategy via lightweight reinforcement learning."""

    _WEIGHT_FILE = Path("strategy_weights.json")
    _SAVE_EVERY = 25  # save to disk every N updates

    def __init__(
        self,
        web3: AsyncWeb3,
        config: Configuration,
        transaction_core: TransactionCore,
        safety_net: SafetyNet,
        market_monitor: MarketMonitor,
    ) -> None:
        self.web3 = web3
        self.cfg = config
        self.txc = transaction_core
        self.safety_net = safety_net
        self.market_monitor = market_monitor
        self.api_config = config.api_config

        # Supported strategy types and their function lists
        self._registry: Dict[str, List[Callable[[Dict[str, Any]], asyncio.Future]]] = {
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

        self.learning_cfg = StrategyConfiguration()
        self._update_counter: int = 0
        self._last_saved_weights: Optional[str] = None

    async def initialize(self) -> None:
        """Load persisted weights from disk."""
        self._load_weights()
        logger.info("StrategyNet initialized – weights loaded.")

    async def stop(self) -> None:
        """Persist weights on shutdown."""
        self._save_weights()
        logger.info("StrategyNet state saved on shutdown.")

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
            current = json.dumps(self.weights, sort_keys=True)
            if self._last_saved_weights != current:
                self._WEIGHT_FILE.write_text(current)
                self._last_saved_weights = current
                logger.debug(f"Saved strategy weights to {self._WEIGHT_FILE}")
        except Exception as e:
            logger.error(f"Failed to save strategy weights: {e}")

    def get_strategies(
        self, strategy_type: str
    ) -> List[Callable[[Dict[str, Any]], asyncio.Future]]:
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
        strategies: List[Callable[[Dict[str, Any]], asyncio.Future]],
        strategy_type: str,
    ) -> Callable[[Dict[str, Any]], asyncio.Future]:
        """ε-greedy selection over softmaxed weights."""
        if random.random() < self.learning_cfg.exploration_rate:
            choice = random.choice(strategies)
            logger.debug(f"Exploration chose {choice.__name__} for {strategy_type}")
            return choice

        w = self.weights[strategy_type]
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
                np.clip(new_weight, self.learning_cfg.min_weight, self.learning_cfg.max_weight)
            )
            self.weights[stype][idx] = clipped
            logger.debug(f"Updated weight for {stype}/{sname}: {clipped:.3f} (reward={reward:.3f})")

        self._update_counter += 1
        if self._update_counter % self._SAVE_EVERY == 0:
            self._save_weights()

    def _calc_reward(self, success: bool, profit: Decimal, exec_time: float) -> float:
        """Compute reward: +profit if success, −0.05 if fail, −0.01 * time always."""
        reward = float(profit) if success else -0.05
        reward -= 0.01 * exec_time
        return reward

    def _strategy_index(self, stype: str, name: str) -> int:
        """Find index of a strategy by function name."""
        for i, fn in enumerate(self.get_strategies(stype)):
            if fn.__name__ == name:
                return i
        return -1

    async def is_healthy(self) -> bool:
        """Check if StrategyNet is in a healthy state."""
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
            logger.error(f"StrategyNet health check failed: {e}")
            return False

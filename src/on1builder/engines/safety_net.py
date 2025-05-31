#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder - Safety Net
=======================

Provides safety checks and circuit-breaker functionality to prevent operational risks.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
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
    """Safety checks and circuit-breaker system for transaction execution."""

    def __init__(
        self,
        web3: AsyncWeb3,
        config: Configuration,
        account: Any,
        api_config: Optional[APIConfig] = None,
    ) -> None:
        """Initialize SafetyNet.

        Args:
            web3: Web3 provider instance
            config: Global configuration
            account: Account object or address string
            api_config: APIConfig instance (optional)
        """
        self.web3 = web3
        self.config = config
        self.account = account
        self.account_address = (
            account.address if hasattr(account, "address") else account
        )
        # Use injected APIConfig or fallback to config.api_config
        self.api_config = api_config or config.api_config

        # Circuit breaker state
        self.circuit_broken: bool = False
        self.circuit_break_reason: Optional[str] = None
        self.last_reset_time: float = time.time()

        # Duplicate-tx tracking
        self.recent_txs: Set[str] = set()
        self._cache_lock = asyncio.Lock()
        self._cache_expiry = time.time() + config.get("SAFETYNET_CACHE_TTL", 300)

        # Historical data for smoothing
        self._gas_price_history: List[float] = []
        self._congestion_history: List[Tuple[float, float]] = []

        logger.info("SafetyNet initialized")

    async def initialize(self) -> None:
        """Initialize SafetyNet; verify web3 connection."""
        # cfg.api_config already initialized by MainCore
        self.api_config = self.api_config or self.config.api_config

        if await self.web3.is_connected():
            logger.info("SafetyNet: Web3 connection active")
        else:
            logger.warning("SafetyNet: Web3 connection not active")

    async def close(self) -> None:
        """Clean up resources (no-op)."""
        logger.debug("SafetyNet closed")

    async def stop(self) -> None:
        """Alias for close()."""
        await self.close()

    async def get_balance(self, account: Any) -> float:
        """Get account balance in ETH."""
        addr = account.address if hasattr(account, "address") else account
        bal_wei = await self.web3.eth.get_balance(addr)
        return float(self.web3.from_wei(bal_wei, "ether"))

    async def is_safe_to_proceed(self) -> bool:
        """Check circuit-breaker, balance, and gas price limits."""
        if self.circuit_broken:
            logger.warning(f"Circuit breaker active: {self.circuit_break_reason}")
            return False

        bal_wei = await self.web3.eth.get_balance(self.account_address)
        min_bal_wei = self.web3.to_wei(self.config.get("MIN_BALANCE", 0.001), "ether")
        if bal_wei < min_bal_wei:
            reason = (
                f"Balance ({self.web3.from_wei(bal_wei,'ether'):.4f} ETH) "
                "below MIN_BALANCE"
            )
            await self.break_circuit(reason)
            return False

        gas_price = await self.web3.eth.gas_price
        max_gas_price = self.config.get("MAX_GAS_PRICE", 500_000_000_000)
        if gas_price > max_gas_price:
            logger.warning(
                f"Gas price ({self.web3.from_wei(gas_price,'gwei'):.1f} gwei) "
                "above MAX_GAS_PRICE"
            )
            return False

        return True

    async def break_circuit(self, reason: str) -> None:
        """Activate circuit breaker and send alert."""
        self.circuit_broken = True
        self.circuit_break_reason = reason
        logger.critical(f"Circuit breaker activated: {reason}")

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
            logger.warning("Notification system unavailable for circuit alerts")

    async def reset_circuit(self) -> None:
        """Reset the circuit breaker."""
        if self.circuit_broken:
            self.circuit_broken = False
            self.circuit_break_reason = None
            self.last_reset_time = time.time()
            logger.info("Circuit breaker reset")

    async def is_transaction_duplicate(self, tx_hash: str) -> bool:
        """Detect duplicate transactions by hash."""
        async with self._cache_lock:
            now = time.time()
            if now > self._cache_expiry:
                self.recent_txs.clear()
                self._cache_expiry = now + self.config.get("SAFETYNET_CACHE_TTL", 300)

            if tx_hash in self.recent_txs:
                logger.warning(f"Duplicate transaction detected: {tx_hash}")
                return True

            self.recent_txs.add(tx_hash)
            return False

    async def validate_transaction_params(
        self, tx_params: Dict[str, Any]
    ) -> Optional[str]:
        """Ensure gas price, gas limit, and value are within safe bounds."""
        gp = tx_params.get("gasPrice", 0)
        max_gp = self.config.get("MAX_GAS_PRICE", 500_000_000_000)
        if gp > max_gp:
            return f"Gas price {self.web3.from_wei(gp,'gwei'):.1f} gwei exceeds MAX_GAS_PRICE"

        gl = tx_params.get("gas", 0)
        max_gl = self.config.get("GAS_LIMIT", 1_000_000)
        if gl > max_gl:
            return f"Gas limit {gl} exceeds GAS_LIMIT"

        val = tx_params.get("value", 0)
        bal_wei = await self.web3.eth.get_balance(self.account_address)
        if val > bal_wei * 0.95:
            return f"Value {self.web3.from_wei(val,'ether'):.4f} ETH too close to balance"

        return None

    async def get_dynamic_gas_price(self) -> float:
        """Compute gas price (gwei) with EIP-1559 or legacy logic + congestion."""
        try:
            # Oracle-based override
            oracle_addr = self.config.get("GAS_PRICE_ORACLE")
            if oracle_addr:
                try:
                    from on1builder.integrations.abi_registry import get_registry

                    registry = await get_registry(self.config.get("BASE_PATH", "."))
                    abi = registry.get_abi("gas_price_oracle")
                    if abi:
                        contract = self.web3.eth.contract(
                            address=self.web3.to_checksum_address(oracle_addr), abi=abi
                        )
                        if hasattr(contract.functions, "getLatestGasPrice"):
                            gp = await contract.functions.getLatestGasPrice().call()
                            return float(self.web3.from_wei(gp, "gwei"))
                        if hasattr(contract.functions, "latestAnswer"):
                            gp = await contract.functions.latestAnswer().call()
                            return float(self.web3.from_wei(gp, "gwei"))
                except Exception as e:
                    logger.error(f"Gas price oracle error: {e}")

            base_gas = await self.web3.eth.gas_price
            gas_gwei = float(self.web3.from_wei(base_gas, "gwei"))
            latest = await self.web3.eth.get_block("latest")
            if "baseFeePerGas" in latest:
                # EIP-1559
                priority = await self.web3.eth.max_priority_fee
                pri_gwei = float(self.web3.from_wei(priority, "gwei"))
                base_fee = latest["baseFeePerGas"]
                base_fee_gwei = float(self.web3.from_wei(base_fee, "gwei"))
                cong = await self.get_network_congestion()
                adj_pri = pri_gwei * (1 + cong)
                gas_gwei = base_fee_gwei + adj_pri
                logger.debug(f"EIP-1559 gas price: base={base_fee_gwei:.2f} + priority={adj_pri:.2f} = {gas_gwei:.2f} gwei")
            else:
                cong = await self.get_network_congestion()
                gas_gwei = gas_gwei * (1 + cong * 0.5)
                logger.debug(f"Legacy gas price: {gas_gwei:.2f} gwei (congestion: {cong:.2f})")

            # Enforce config limits
            min_g = self.config.get("MIN_GAS_PRICE_GWEI", 1.0)
            max_g = self.config.get("MAX_GAS_PRICE_GWEI", 500.0)
            gas_gwei = max(min_g, min(gas_gwei, max_g))
            return gas_gwei

        except Exception as e:
            logger.error(f"Error calculating dynamic gas price: {e}")
            fallback = await self.web3.eth.gas_price
            return float(self.web3.from_wei(fallback, "gwei"))

    async def adjust_slippage_tolerance(self, congestion_level: float = None) -> float:
        """Adjust slippage (%) based on network congestion & volatility."""
        try:
            cong = congestion_level if congestion_level is not None else await self.get_network_congestion()
            low = self.config.get("SLIPPAGE_LOW_CONGESTION", 0.1)
            med = self.config.get("SLIPPAGE_MEDIUM_CONGESTION", 0.5)
            high = self.config.get("SLIPPAGE_HIGH_CONGESTION", 1.0)
            extreme = self.config.get("SLIPPAGE_EXTREME_CONGESTION", 2.0)

            if cong < 0.3:
                slip = low
            elif cong < 0.6:
                slip = med
            elif cong < 0.8:
                slip = high
            else:
                slip = extreme

            # Volatility adjustment via MarketMonitor if available
            tok = self.config.get("PRIMARY_TOKEN")
            try:
                from on1builder.monitoring.market_monitor import MarketMonitor

                mm = getattr(self, "market_monitor", None)
                if mm:
                    vol_data = await mm.check_market_conditions(tok, "volatility")
                    cond = vol_data.get("condition")
                    if cond == "high":
                        slip *= 1.5
                    elif cond == "low":
                        slip *= 0.8
            except Exception:
                pass

            # Enforce slippage bounds
            min_s = self.config.get("MIN_SLIPPAGE", 0.05)
            max_s = self.config.get("MAX_SLIPPAGE", 5.0)
            slip = max(min_s, min(slip, max_s))
            logger.debug(f"Adjusted slippage: {slip:.2f}% (congestion: {cong:.2f})")
            return slip

        except Exception as e:
            logger.error(f"Error adjusting slippage: {e}")
            return self.config.get("SLIPPAGE_DEFAULT", 0.5)

    async def _calculate_gas_cost(self, gas_price: float, gas_used: int) -> float:
        """Calculate gas cost in ETH."""
        try:
            gp_wei = self.web3.to_wei(gas_price, "gwei")
            cost_wei = gp_wei * gas_used
            cost_eth = float(self.web3.from_wei(cost_wei, "ether"))
            logger.debug(f"Gas cost: {cost_eth:.6f} ETH (gas: {gas_used}, price: {gas_price:.2f} gwei)")
            return cost_eth
        except Exception as e:
            logger.error(f"Error calculating gas cost: {e}")
            return (gas_price * gas_used) / 1_000_000_000  # fallback

    async def _calculate_profit(self, amountIn: float, amountOut: float, gas_cost: float) -> float:
        """Compute profit minus gas and safety margin."""
        try:
            raw = amountOut - amountIn
            net = raw - gas_cost
            margin = self.config.get("PROFIT_SAFETY_MARGIN", 0.9)
            profit = net * margin
            logger.debug(f"Profit: {profit:.6f} ETH (raw: {raw:.6f}, gas: {gas_cost:.6f})")
            return profit
        except Exception as e:
            logger.error(f"Error calculating profit: {e}")
            return amountOut - amountIn - gas_cost

    async def get_network_congestion(self) -> float:
        """Estimate network congestion (0–1)."""
        try:
            latest = await self.web3.eth.get_block("latest")
            used = latest["gasUsed"]
            limit = latest["gasLimit"]
            ratio = used / limit
            pending = 0
            try:
                pend_block = await self.web3.eth.get_block("pending")
                pending = len(pend_block.get("transactions", []))
            except Exception:
                if hasattr(self.web3, "geth") and hasattr(self.web3.geth, "txpool"):
                    tp = await self.web3.geth.txpool.status()
                    pending = int(tp.pending, 16) if hasattr(tp, "pending") else 0

            pend_factor = min(1.0, pending / 5000)
            trend = 0.0
            gp = await self.web3.eth.gas_price
            self._gas_price_history.append(gp)
            if len(self._gas_price_history) > 10:
                self._gas_price_history.pop(0)
            if len(self._gas_price_history) >= 2:
                recent = sum(self._gas_price_history[-3:]) / min(3, len(self._gas_price_history))
                older = sum(self._gas_price_history[:-3]) / max(1, len(self._gas_price_history) - 3)
                if older > 0:
                    ratio_trend = recent / older
                    trend = min(1.0, max(0.0, (ratio_trend - 0.95) / 0.5))

            cong = 0.5 * ratio + 0.3 * pend_factor + 0.2 * trend
            cong = max(0.0, min(1.0, cong))

            now = time.time()
            self._congestion_history.append((now, cong))
            one_hr_ago = now - 3600
            self._congestion_history = [(t, c) for t, c in self._congestion_history if t > one_hr_ago]
            if len(self._congestion_history) > 1:
                total_w = 0.0
                sum_w = 0.0
                for i, (_, c) in enumerate(self._congestion_history):
                    w = i + 1
                    sum_w += c * w
                    total_w += w
                if total_w > 0:
                    cong = sum_w / total_w

            logger.debug(f"Network congestion: {cong:.2f} (gas ratio: {ratio:.2f}, pending: {pending}, trend: {trend:.2f})")
            return cong

        except Exception as e:
            logger.error(f"Error calculating congestion: {e}")
            return 0.5

    async def ensure_profit(self, tx_data: Dict[str, Any]) -> bool:
        """Ensure a transaction meets MIN_PROFIT after gas and slippage."""
        try:
            if not self.api_config:
                logger.error("APIConfig unavailable for profit check")
                return False

            in_tok = tx_data.get("input_token")
            out_tok = tx_data.get("output_token")
            amt_in = tx_data.get("amountIn", 0)
            amt_out = tx_data.get("amountOut", 0)

            if not in_tok or not out_tok:
                gp = tx_data.get("gas_price", await self.get_dynamic_gas_price())
                gu = tx_data.get("gas_used", 21000)
                gas_cost = await self._calculate_gas_cost(gp, gu)
                profit = amt_out - amt_in - gas_cost
                ok = profit >= self.config.get("MIN_PROFIT", 0.001)
                logger.debug(f"Profit check (ETH): {profit:.6f} ETH {'≥' if ok else '<'} {self.config.get('MIN_PROFIT',0.001):.6f} ETH")
                return ok

            # Token profit in ETH terms
            price_in = await self.api_config.get_real_time_price(in_tok, "eth")
            price_out = await self.api_config.get_real_time_price(out_tok, "eth")
            if not price_in or not price_out:
                logger.warning(f"Missing price for {in_tok} or {out_tok}")
                return False

            val_in = float(amt_in) * float(price_in)
            val_out = float(amt_out) * float(price_out)
            gp = tx_data.get("gas_price", await self.get_dynamic_gas_price())
            gu = tx_data.get("gas_used", tx_data.get("gas_used", 150000))
            gas_cost = await self._calculate_gas_cost(gp, gu)

            raw_profit = val_out - val_in - gas_cost
            cong = await self.get_network_congestion()
            slip = await self.adjust_slippage_tolerance(cong)
            adj_profit = raw_profit * (1 - slip / 100)

            min_p = self.config.get("MIN_PROFIT", 0.001)
            ok = adj_profit >= min_p
            logger.debug(f"Profit check (tokens): {adj_profit:.6f} ETH {'≥' if ok else '<'} {min_p:.6f} ETH")

            if ok:
                logger.info(f"Profitable tx: {in_tok}->{out_tok}, profit {adj_profit:.6f} ETH")

            return ok

        except Exception as e:
            logger.error(f"Error ensuring profit: {e}")
            return False

    async def check_transaction_safety(
        self, tx_data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Run multiple safety checks and return overall result."""
        try:
            details: Dict[str, Any] = {"check_details": {}, "checks_passed": 0}
            total_checks = 6

            # 1) Gas price check
            gp = tx_data.get("gas_price", await self.get_dynamic_gas_price())
            max_gp = self.config.get("MAX_GAS_PRICE_GWEI", 100)
            ok = gp <= max_gp
            if ok: details["checks_passed"] += 1
            details["check_details"]["gas_check"] = {"passed": ok, "value": gp, "max": max_gp}

            # 2) Network congestion check
            cong = await self.get_network_congestion()
            max_cong = self.config.get("MAX_NETWORK_CONGESTION", 0.8)
            ok = cong < max_cong
            if ok: details["checks_passed"] += 1
            details["check_details"]["congestion_check"] = {"passed": ok, "value": cong, "max": max_cong}

            # 3) Profitability check
            prof_ok = await self.ensure_profit(tx_data)
            if prof_ok: details["checks_passed"] += 1
            details["check_details"]["profit_check"] = {"passed": prof_ok}

            # 4) Token allowlist check
            allowed = self.config.get("ALLOWED_TOKENS", [])
            tok_ok = True
            if allowed:
                inp = tx_data.get("input_token")
                out = tx_data.get("output_token")
                tok_ok = (inp in allowed) and (out in allowed)
            if tok_ok: details["checks_passed"] += 1
            details["check_details"]["token_check"] = {"passed": tok_ok}

            # 5) Balance adequacy check
            try:
                val = tx_data.get("value", 0)
                bal_wei = await self.web3.eth.get_balance(self.account_address)
                required = val * 1.05 if val else 0
                bal_ok = bal_wei >= required
                if bal_ok: details["checks_passed"] += 1
                details["check_details"]["balance_check"] = {
                    "passed": bal_ok,
                    "balance": float(self.web3.from_wei(bal_wei, "ether")),
                    "required": float(self.web3.from_wei(required, "ether")) if val else 0,
                }
            except Exception as e:
                logger.error(f"Balance check error: {e}")
                details["check_details"]["balance_check"] = {"passed": False, "error": str(e)}

            # 6) Duplicate transaction check
            txh = tx_data.get("hash")
            dup_ok = True
            if txh:
                dup_ok = not await self.is_transaction_duplicate(txh)
            if dup_ok: details["checks_passed"] += 1
            details["check_details"]["duplicate_check"] = {"passed": dup_ok}

            safety_pct = (details["checks_passed"] / total_checks) * 100
            is_safe = safety_pct >= self.config.get("MIN_SAFETY_PERCENTAGE", 85)
            return is_safe, {"safety_percentage": safety_pct, **details}

        except Exception as e:
            logger.error(f"Transaction safety check error: {e}")
            return False, {"is_safe": False, "error": str(e)}

    async def estimate_gas(self, tx: Dict[str, Any]) -> int:
        """Estimate gas usage with a safety margin."""
        try:
            tx_copy = tx.copy()
            for key in ("nonce", "gasPrice", "gas", "maxFeePerGas", "maxPriorityFeePerGas"):
                tx_copy.pop(key, None)
            tx_copy.setdefault("value", 0)
            estimate = await self.web3.eth.estimate_gas(tx_copy)
            margin = self.config.get("GAS_ESTIMATE_SAFETY_MARGIN", 1.1)
            return int(estimate * margin)
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}")
            return self.config.get("DEFAULT_GAS_LIMIT", 500_000)

    async def is_healthy(self) -> bool:
        """Basic health check: web3 connectivity and circuit state."""
        try:
            if not await self.web3.is_connected():
                logger.warning("SafetyNet: Web3 connection down")
                return False
            _ = await self.web3.eth.get_balance(self.account_address)
            if self.circuit_broken:
                logger.warning(f"SafetyNet: circuit broken ({self.circuit_break_reason})")
                return False
            return True
        except Exception as e:
            logger.error(f"SafetyNet health check failed: {e}")
            return False

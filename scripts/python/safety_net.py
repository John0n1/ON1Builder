# safety_net.py
"""
ON1Builder – SafetyNet
======================
A lightweight guard-rail around transaction profitability, gas costs, and congestion.
"""

from __future__ import annotations

import asyncio
import statistics
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from cachetools import TTLCache
from eth_account import Account
from web3 import AsyncWeb3
from web3.exceptions import ContractLogicError

from api_config import APIConfig
from configuration import Configuration
from logger_on1 import setup_logging

logger = setup_logging("Safety_Net", level="DEBUG")


class SafetyNet:
    """Lightweight guard-rail around tx profitability, gas costs and congestion."""

    _BLOCK_SAMPLE = 3  # how many recent blocks to median-filter gas price

    def __init__(
        self,
        web3: AsyncWeb3,
        configuration: Configuration,
        address: Optional[str] = None,
        account: Optional[Account] = None,
        api_config: Optional[APIConfig] = None,
        market_monitor: Optional[Any] = None,
    ) -> None:
        self.web3 = web3
        self.cfg = configuration
        self.address = address
        self.account = account
        self.api_config = api_config
        self.market_monitor = market_monitor

        self._price_cache = TTLCache(maxsize=2_000, ttl=self.cfg.SAFETYNET_CACHE_TTL)
        self._gas_cache = TTLCache(maxsize=1, ttl=self.cfg.SAFETYNET_GAS_PRICE_TTL)

        self._tasks: list[asyncio.Task] = []
        self._running = False

    # ------------------------------------------------------------------ #
    # life-cycle                                                         #
    # ------------------------------------------------------------------ #

    async def initialize(self) -> None:
        if not (self.web3 and await self.web3.is_connected()):
            raise RuntimeError("SafetyNet: Web3 not connected")
        self._running = True
        logger.debug("SafetyNet initialised.")

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._price_cache.clear()
        self._gas_cache.clear()
        logger.debug("SafetyNet stopped.")

    # ------------------------------------------------------------------ #
    # price helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _dex_quote_price(self, token_addr: str, vs_symbol: str = "ETH") -> Optional[Decimal]:
        """
        Try on-chain quote via Uniswap router when off-chain APIs fail.
        Very cheap because it's pure eth_call.
        """
        try:
            if not self.market_monitor or not self.market_monitor.transaction_core.uniswap_router:
                return None
            router = self.market_monitor.transaction_core.uniswap_router
            weth = self.cfg.WETH_ADDRESS
            path = [self.web3.to_checksum_address(token_addr), self.web3.to_checksum_address(weth)]
            amounts = await router.functions.getAmountsOut(10**18, path).call()
            eth_out = Decimal(amounts[-1]) / Decimal(10**18)
            return eth_out
        except (ContractLogicError, ValueError):
            return None
        except Exception as exc:
            logger.debug("DEX quote price failed: %s", exc)
            return None

    async def get_token_price(
        self, token_or_addr: str, vs: str = "eth"
    ) -> Optional[Decimal]:
        """Resilient – tries APIConfig first, else DEX quote, else cache."""
        key = f"price:{token_or_addr.lower()}:{vs}"
        if key in self._price_cache:
            return self._price_cache[key]

        price = None
        if self.api_config:
            price = await self.api_config.get_real_time_price(token_or_addr, vs)

        if price is None:
            # Fallback to on-chain quote (vs ETH only)
            if vs.lower() == "eth" and token_or_addr.startswith("0x"):
                price = await self._dex_quote_price(token_or_addr)

        if price is None and key in self._price_cache:
            logger.debug("Returning stale cached price for %s", token_or_addr)
            return self._price_cache[key]

        if price is not None:
            self._price_cache[key] = price
        return price

    # ------------------------------------------------------------------ #
    # gas helpers                                                        #
    # ------------------------------------------------------------------ #

    async def get_dynamic_gas_price(self) -> Decimal:
        """
        Median of the last N blocks' baseFee*2 or legacy `gasPrice`.
        Cached for SAFETYNET_GAS_PRICE_TTL seconds.
        """
        if "gas_price" in self._gas_cache:
            return self._gas_cache["gas_price"]

        try:
            latest_nr = await self.web3.eth.block_number
            samples = []
            for n in range(latest_nr, latest_nr - self._BLOCK_SAMPLE, -1):
                b = await self.web3.eth.get_block(n)
                if "baseFeePerGas" in b and b["baseFeePerGas"]:
                    samples.append(b["baseFeePerGas"] * 2)  # tip heuristic
            if samples:
                wei_price = int(statistics.median(samples))
            else:
                wei_price = await self.web3.eth.gas_price
            gwei_price = Decimal(str(self.web3.from_wei(wei_price, "gwei")))
            self._gas_cache["gas_price"] = gwei_price
            return gwei_price
        except Exception as exc:
            logger.error("Gas-price oracle failed: %s", exc)
            return Decimal(self.cfg.MAX_GAS_PRICE_GWEI)

    async def get_network_congestion(self) -> float:
        try:
            blk = await self.web3.eth.get_block("latest")
            used = Decimal(blk["gasUsed"])
            limit = Decimal(blk["gasLimit"])
            return float((used / limit).quantize(Decimal("0.0001")))
        except Exception:
            return 0.50  # assume medium congestion on failure

    # ------------------------------------------------------------------ #
    # sanity validators                                                  #
    # ------------------------------------------------------------------ #

    def _validate_gas_parameters(self, gas_price_gwei: Decimal, gas_used: Decimal) -> bool:
        if gas_used <= 0:
            return False
        if gas_price_gwei > Decimal(str(self.cfg.MAX_GAS_PRICE_GWEI)):
            return False
        return True

    def _calculate_gas_cost(self, gas_price_gwei: Decimal, gas_used: Decimal) -> Decimal:
        return (
            (gas_price_gwei * gas_used * Decimal("1e-9"))
            .quantize(Decimal("0.000000001"))
        )

    async def _calculate_profit(
        self,
        tx: Dict[str, Any],
        out_price: Decimal,
        slippage: float,
        gas_cost: Decimal,
    ) -> Decimal:
        expected = out_price * Decimal(str(tx["amountOut"]))
        input_amount = Decimal(str(tx["amountIn"]))
        adjusted = expected * (Decimal("1") - Decimal(slippage))
        profit = adjusted - input_amount - gas_cost
        return profit.quantize(Decimal("0.000000001"))

    async def adjust_slippage_tolerance(self) -> float:
        congestion = await self.get_network_congestion()
        if congestion > 0.8:
            return self.cfg.SLIPPAGE_HIGH_CONGESTION
        if congestion < 0.2:
            return self.cfg.SLIPPAGE_LOW_CONGESTION
        return self.cfg.SLIPPAGE_DEFAULT

    # ------------------------------------------------------------------ #
    # external API                                                       #
    # ------------------------------------------------------------------ #

    async def ensure_profit(
        self, tx: Dict[str, Any], minimum_profit_eth: Optional[float] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Returns (is_profitable, details).  Never raises.
        """
        minimum = Decimal(str(minimum_profit_eth or self.cfg.MIN_PROFIT))

        price = await self.get_token_price(tx["output_token"])
        if price is None:
            return (
                False,
                {"reason": "price_unavailable", "details": "No API or DEX price"},
            )


        gas_price = Decimal(str(tx["gas_price"]))
        gas_used = Decimal(str(tx["gas_used"]))
        if not self._validate_gas_parameters(gas_price, gas_used):
            return (False, {"reason": "gas_invalid"})

        gas_cost = self._calculate_gas_cost(gas_price, gas_used)
        slippage = await self.adjust_slippage_tolerance()
        profit = await self._calculate_profit(tx, price, slippage, gas_cost)

        ok = profit >= minimum
        return (
            ok,
            {
                "expected_profit": profit,
                "gas_cost": gas_cost,
                "minimum_required": minimum,
                "slippage": slippage,
            },
        )
    
    async def check_transaction_safety(
        self, tx: Dict[str, Any], check_type: str = "profit"
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check transaction safety based on the type of check requested.
        """
        if check_type == "profit":
            return await self.ensure_profit(tx)
        elif check_type == "gas":
            gas_price = await self.get_dynamic_gas_price()
            return (
                self._validate_gas_parameters(gas_price, Decimal(str(tx["gas_used"]))),
                {}, 
            )
        else:
            return False, {"reason": "invalid_check_type"}

    async def validate_transaction(self, tx: Dict[str, Any]) -> bool:
        """Light json-schema-style presence + gas param check."""
        required = {"output_token", "amountOut", "amountIn", "gas_price", "gas_used"}
        if not required.issubset(tx):
            return False
        try:
            return self._validate_gas_parameters(
                Decimal(str(tx["gas_price"])), Decimal(str(tx["gas_used"]))
            )
        except Exception:
            return False

    async def estimate_gas(self, tx: Dict[str, Any]) -> int:
        try:
            return await self.web3.eth.estimate_gas(tx)
        except Exception:
            return self.cfg.BASE_GAS_LIMIT

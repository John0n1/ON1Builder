#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any

from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound
from web3.types import TxData

from on1builder.config.loaders import settings
from on1builder.engines.strategy_executor import StrategyExecutor
from on1builder.integrations.abi_registry import ABIRegistry
from on1builder.utils.constants import DEX_ROUTER_IDENTIFIERS
from on1builder.utils.logging_config import get_logger

logger = get_logger(__name__)


class TxPoolScanner:
    """transaction pool scanner with sophisticated MEV opportunity detection."""

    # MEV pattern detection
    MEV_PATTERNS = {
        "sandwich_attack": re.compile(
            r"swapExactTokensForTokens|swapTokensForExactTokens", re.IGNORECASE
        ),
        "arbitrage": re.compile(r"multicall|batchSwap", re.IGNORECASE),
        "liquidation": re.compile(r"liquidate|seize", re.IGNORECASE),
        "flash_loan": re.compile(r"flashLoan|flashSwap", re.IGNORECASE),
    }

    # Cache management constants
    MAX_TX_CACHE_SIZE = 1000
    MAX_OPPORTUNITY_CACHE_SIZE = 500
    CACHE_CLEANUP_THRESHOLD = 0.8
    MEV_LOG_EVERY = 50
    NOT_FOUND_LOG_EVERY = 50
    SUPPORTED_SWAP_DEXES = {"uniswap_v2", "uniswap_v3", "sushiswap", "pancakeswap"}

    def __init__(
        self, web3: AsyncWeb3, strategy_executor: StrategyExecutor, chain_id: int
    ):
        self._web3 = web3
        self._strategy_executor = strategy_executor
        self._chain_id = chain_id
        self._abi_registry = ABIRegistry()
        self._is_running = False
        self._scan_task: asyncio.Task | None = None

        # Build chain-specific DEX router mapping
        self._dex_routers = self._build_dex_router_mapping()
        # Initialize cached data
        self._monitored_addresses: set[str] = self._get_all_monitored_addresses()
        self._large_trader_addresses: set[str] = set()

        # Performance tracking
        self._pending_tx_count = 0
        self._processed_tx_count = 0
        self._opportunity_count = 0
        self._mev_log_counter = 0
        self._not_found_counter = 0

        # - caching with size management
        self._tx_analysis_cache: dict[str, dict] = {}
        self._opportunity_cache: dict[str, dict] = {}
        self._cache_access_times: dict[str, datetime] = {}

        logger.debug(
            "ON1Builder TxPoolScanner initialized. Monitoring %s addresses.",
            len(self._monitored_addresses),
        )

    def _build_dex_router_mapping(self) -> dict[str, str]:
        """Build chain-specific DEX router address mapping."""
        dex_routers = {}

        # Get chain-specific router addresses from settings
        for dex_name, default_address in DEX_ROUTER_IDENTIFIERS.items():
            # Try to get chain-specific address from settings
            try:
                router_addresses = getattr(settings.contracts, f"{dex_name}_router", {})
                chain_address = router_addresses.get(str(self._chain_id))

                if chain_address:
                    dex_routers[chain_address.lower()] = dex_name
                else:
                    # Fallback to default address for major chains
                    if self._chain_id in [1, 5]:  # Ethereum mainnet and Goerli
                        dex_routers[default_address.lower()] = dex_name

            except AttributeError:
                # If settings don't have this router, skip it
                logger.debug(
                    f"No configuration found for {dex_name} on chain {self._chain_id}"
                )
                continue

        logger.debug(
            "Built DEX router mapping for chain %s: %s routers",
            self._chain_id,
            len(dex_routers),
        )
        return dex_routers

    def _get_all_monitored_addresses(self) -> set[str]:
        """Gathers all unique token addresses to monitor across all configured chains."""
        addresses = set()
        for chain_id in settings.chains:
            token_map = self._abi_registry.get_monitored_tokens(chain_id)
            addresses.update(addr.lower() for addr in token_map.values())
        return addresses

    def _manage_cache_size(self) -> None:
        """Efficiently manage cache sizes to prevent memory bloat."""
        current_time = datetime.now()

        # Clean tx analysis cache
        if len(self._tx_analysis_cache) > int(
            self.MAX_TX_CACHE_SIZE * self.CACHE_CLEANUP_THRESHOLD
        ):
            # Remove oldest 20% of entries
            removal_count = len(self._tx_analysis_cache) // 5
            oldest_keys = sorted(
                self._cache_access_times.keys(),
                key=lambda k: self._cache_access_times.get(k, current_time),
            )[:removal_count]

            for key in oldest_keys:
                self._tx_analysis_cache.pop(key, None)
                self._cache_access_times.pop(key, None)

        # Clean opportunity cache
        if len(self._opportunity_cache) > int(
            self.MAX_OPPORTUNITY_CACHE_SIZE * self.CACHE_CLEANUP_THRESHOLD
        ):
            removal_count = len(self._opportunity_cache) // 5
            oldest_opportunities = list(self._opportunity_cache.keys())[:removal_count]
            for key in oldest_opportunities:
                self._opportunity_cache.pop(key, None)

    async def start(self):
        if self._is_running:
            logger.warning("TxPoolScanner is already running.")
            return

        self._is_running = True
        logger.info(
            "Scanning transaction pool for MEV opportunities on chain %s...",
            self._chain_id,
        )
        self._scan_task = asyncio.create_task(self._subscribe_to_pending_transactions())

    async def stop(self):
        if not self._is_running:
            return

        self._is_running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        logger.info("TxPoolScanner stopped.")

    async def _subscribe_to_pending_transactions(self):
        """
        Establishes a WebSocket subscription to new pending transactions and
        processes them in a continuous loop with ON1Builder analysis.
        """
        if not self._is_running:
            self._is_running = True

        chain_id = await self._web3.eth.chain_id
        ws_urls = getattr(settings, "websocket_urls", {})
        rpc_urls = getattr(settings, "rpc_urls", {})
        # settings may store URLs keyed by either int or string chain ids; try both
        ws_url = ws_urls.get(chain_id) or ws_urls.get(str(chain_id))
        rpc_url = rpc_urls.get(chain_id) or rpc_urls.get(str(chain_id))

        if not ws_url:
            logger.error(
                f"No WebSocket URL configured for chain {chain_id}. TxPoolScanner cannot run."
            )
            self._is_running = False
            return

        # Public endpoints often do not support pending tx subscriptions reliably; disable to avoid noise
        if "public" in ws_url.lower() or (rpc_url and "public" in rpc_url.lower()):
            logger.debug(
                f"[Chain {chain_id}] Public RPC/WebSocket detected ({ws_url}). "
                "Skipping txpool scanner to avoid unstable subscriptions."
            )
            self._is_running = False
            return

        backoff_delay = settings.connection_retry_delay
        while self._is_running:
            ws_provider = None
            ws_web3 = None
            subscription_id = None
            try:
                # Create a WebSocket provider for this chain (persistent connection)
                from web3 import AsyncWeb3
                from web3.providers import WebSocketProvider

                ws_provider = WebSocketProvider(ws_url)
                ws_web3 = AsyncWeb3(ws_provider)
                await ws_provider.connect()

                async def _handle_pending(context):
                    tx_hash = context.result
                    if tx_hash:
                        self._pending_tx_count += 1
                        asyncio.create_task(self._process_tx_hash(tx_hash))

                subscription_id = await ws_web3.eth.subscribe(
                    "newPendingTransactions", handler=_handle_pending
                )
                logger.info(
                    "Successfully subscribed to pending transactions (subscription: %s)",
                    subscription_id,
                )

                # Run the subscription handler loop until cancelled
                await ws_web3.subscription_manager.handle_subscriptions(
                    run_forever=True
                )
                backoff_delay = settings.connection_retry_delay
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"TxPoolScanner subscription error: {e}. Reconnecting in {backoff_delay}s.",
                    exc_info=True,
                )
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 2, 60)
            finally:
                if ws_web3 and subscription_id:
                    try:
                        await ws_web3.eth.unsubscribe(subscription_id)
                    except Exception:
                        pass
                if ws_provider:
                    try:
                        await ws_provider.disconnect()
                    except Exception:
                        pass

    async def _process_tx_hash(self, tx_hash: str):
        """transaction processing with comprehensive MEV analysis."""
        normalized_hash = self._normalize_tx_hash(tx_hash)
        try:
            # Check cache first
            if normalized_hash in self._tx_analysis_cache:
                self._cache_access_times[normalized_hash] = datetime.now()
                tx_analysis = self._tx_analysis_cache[normalized_hash]
                tx = None  # Don't need full tx data if cached
            else:
                tx = await self._web3.eth.get_transaction(normalized_hash)
                if not tx:
                    return

                # Perform analysis
                tx_analysis = self._analyze_transaction_comprehensive(tx)

                # Cache with access time tracking
                self._tx_analysis_cache[normalized_hash] = tx_analysis
                self._cache_access_times[normalized_hash] = datetime.now()

                # Manage cache size efficiently
                if len(self._tx_analysis_cache) > self.MAX_TX_CACHE_SIZE:
                    self._manage_cache_size()

            self._processed_tx_count += 1

            if self._is_relevant_for_mev(tx_analysis):
                self._mev_log_counter += 1
                if self._mev_log_counter % self.MEV_LOG_EVERY == 1:
                    logger.info(
                        "MEV-relevant transactions: %s (latest: %s)",
                        self._mev_log_counter,
                        normalized_hash,
                    )
                opportunities = await self._analyze_for_opportunities(tx_analysis)

                # Pre-execution simulation stage
                if opportunities and not settings.allow_unsimulated_trades:
                    opportunities = (
                        await self._strategy_executor.simulate_opportunities_batch(
                            opportunities
                        )
                    )

                for opportunity in opportunities:
                    self._opportunity_count += 1
                    await self._strategy_executor.execute_opportunity(opportunity)

        except TransactionNotFound:
            self._not_found_counter += 1
            if self._not_found_counter % self.NOT_FOUND_LOG_EVERY == 1:
                logger.debug(
                    "Pending transaction not found (%s). Latest: %s",
                    self._not_found_counter,
                    normalized_hash,
                )
        except Exception as e:
            logger.debug("Could not process transaction %s: %s", tx_hash, e)

    @staticmethod
    def _normalize_tx_hash(tx_hash: Any) -> str:
        """Normalize tx hashes to 0x-prefixed hex strings for cache/logging."""
        if isinstance(tx_hash, (bytes, bytearray)):
            return f"0x{tx_hash.hex()}"
        if hasattr(tx_hash, "hex") and not isinstance(tx_hash, str):
            value = tx_hash.hex()
            return value if value.startswith("0x") else f"0x{value}"
        if isinstance(tx_hash, str):
            return tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"
        return str(tx_hash)

    def _analyze_transaction_comprehensive(self, tx: TxData) -> dict[str, Any]:
        """Performs comprehensive analysis of a transaction for MEV opportunities."""
        raw_input = tx.get("input", "")
        if isinstance(raw_input, (bytes, bytearray)):
            input_hex = raw_input.hex()
        elif isinstance(raw_input, str):
            input_hex = raw_input
        else:
            input_hex = str(raw_input)
        if input_hex and not input_hex.startswith("0x"):
            input_hex = f"0x{input_hex}"

        analysis = {
            "tx_hash": tx["hash"].hex(),
            "hash": tx["hash"].hex(),
            "from": tx["from"],
            "to": tx.get("to"),
            "value_eth": float(self._web3.from_wei(tx.get("value", 0), "ether")),
            "value_wei": tx.get("value", 0),
            "gas_price": tx.get("gasPrice", 0),
            "gasPrice": tx.get("gasPrice", 0),
            "gas_limit": tx.get("gas", 0),
            "timestamp": datetime.now(),
            "input_data": input_hex,
            "mev_type": None,
            "target_dex": None,
            "estimated_profit_potential": 0.0,
            "risk_score": 0.0,
            "swap_path": None,
            "amount_in": None,
            "amount_out_min": None,
            "pool_fee": None,
            "fees": None,
        }

        # Analyze target address efficiently
        to_address = tx.get("to", "").lower() if tx.get("to") else ""
        if to_address in self._dex_routers:
            analysis["target_dex"] = self._dex_routers[to_address]

        # Detect MEV patterns in input data
        input_data = analysis["input_data"]
        for mev_type, pattern in self.MEV_PATTERNS.items():
            if pattern.search(input_data):
                analysis["mev_type"] = mev_type
                break

        # Calculate priority and profit potential
        analysis["priority_score"] = self._calculate_priority_score(analysis)
        analysis["estimated_profit_potential"] = self._estimate_profit_potential(
            analysis
        )
        analysis["risk_score"] = self._calculate_risk_score(analysis)
        swap_params = self._extract_swap_params(analysis)
        if swap_params:
            analysis.update(
                {
                    "swap_path": swap_params.get("path"),
                    "amount_in": swap_params.get("amount_in"),
                    "amount_out_min": swap_params.get("amount_out_min"),
                    "pool_fee": swap_params.get("pool_fee"),
                    "fees": swap_params.get("fees"),
                }
            )

        return analysis

    def _is_relevant_for_mev(self, analysis: dict[str, Any]) -> bool:
        """relevance check for MEV opportunities."""
        # Check if transaction targets monitored addresses
        to_address = analysis.get("to", "").lower() if analysis.get("to") else ""
        if to_address in self._monitored_addresses:
            return True

        # Check if it's a DEX transaction with significant value
        if analysis["target_dex"] and analysis["value_eth"] > 1.0:
            return True

        # Check if it matches MEV patterns
        if analysis["mev_type"]:
            return True

        # Check if it's from a known large trader
        from_address = analysis.get("from", "").lower()
        if from_address in self._large_trader_addresses:
            return True

        # Check gas price (high gas might indicate MEV competition)
        if analysis["gas_price"] > self._get_high_gas_threshold():
            return True

        return False

    def _extract_swap_params(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Extract swap parameters from common Uniswap V2-style calls."""
        input_data = analysis.get("input_data", "")
        if not input_data or len(input_data) < 10:
            return {}

        func_selector = input_data[:10]
        data_hex = input_data[10:]
        if not data_hex:
            return {}

        swap_selectors = {
            "0x38ed1739": (
                "exact_in",
                ["uint256", "uint256", "address[]", "address", "uint256"],
            ),
            "0x8803dbee": (
                "exact_out",
                ["uint256", "uint256", "address[]", "address", "uint256"],
            ),
            "0x7ff36ab5": (
                "eth_exact_in",
                ["uint256", "address[]", "address", "uint256"],
            ),
            "0x18cbafe5": (
                "exact_in",
                ["uint256", "uint256", "address[]", "address", "uint256"],
            ),
            "0x414bf389": (
                "v3_exact_input_single",
                ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
            ),
            "0xc04b8d59": (
                "v3_exact_input",
                ["(bytes,address,uint256,uint256,uint256)"],
            ),
        }

        if func_selector not in swap_selectors:
            return {}

        try:
            import eth_abi
        except Exception:
            return {}

        try:
            kind, types = swap_selectors[func_selector]
            decoded = eth_abi.decode(types, bytes.fromhex(data_hex))
            if kind == "v3_exact_input_single":
                params = decoded[0]
                token_in = params[0]
                token_out = params[1]
                fee = int(params[2])
                amount_in = int(params[5])
                amount_out_min = int(params[6])
                return {
                    "path": [token_in, token_out],
                    "amount_in": amount_in,
                    "amount_out_min": amount_out_min,
                    "pool_fee": fee,
                }
            if kind == "v3_exact_input":
                params = decoded[0]
                path_bytes = params[0]
                amount_in = int(params[3])
                amount_out_min = int(params[4])
                tokens, fees = self._decode_uniswap_v3_path(path_bytes)
                if not tokens or not fees:
                    return {}
                return {
                    "path": tokens,
                    "fees": fees,
                    "amount_in": amount_in,
                    "amount_out_min": amount_out_min,
                }
            if kind == "eth_exact_in":
                amount_out_min = int(decoded[0])
                path = list(decoded[1])
                amount_in = int(analysis.get("value_wei", 0))
            elif kind == "exact_out":
                amount_out_min = int(decoded[0])
                amount_in = int(decoded[1])
                path = list(decoded[2])
            else:
                amount_in = int(decoded[0])
                amount_out_min = int(decoded[1])
                path = list(decoded[2])
            return {
                "path": path,
                "amount_in": amount_in,
                "amount_out_min": amount_out_min,
            }
        except Exception:
            return {}

    @staticmethod
    def _decode_uniswap_v3_path(path_bytes: bytes) -> tuple[list[str], list[int]]:
        """Decode Uniswap V3 path bytes into token addresses and fee tiers."""
        if not path_bytes or len(path_bytes) < 43:
            return [], []

        tokens: list[str] = []
        fees: list[int] = []
        offset = 0
        tokens.append("0x" + path_bytes[offset : offset + 20].hex())
        offset += 20

        while offset < len(path_bytes):
            if offset + 3 > len(path_bytes):
                return [], []
            fee = int.from_bytes(path_bytes[offset : offset + 3], "big")
            fees.append(fee)
            offset += 3
            if offset + 20 > len(path_bytes):
                return [], []
            tokens.append("0x" + path_bytes[offset : offset + 20].hex())
            offset += 20

        return tokens, fees

    async def _analyze_for_opportunities(
        self, analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Analyzes transaction for specific MEV opportunities."""
        opportunities = []
        target_dex = analysis.get("target_dex")
        v3_fee_ok = analysis.get("pool_fee") is not None or analysis.get("fees")
        swap_supported = (
            target_dex in self.SUPPORTED_SWAP_DEXES
            and analysis.get("swap_path")
            and analysis.get("amount_in")
            and (target_dex != "uniswap_v3" or v3_fee_ok)
        )

        try:
            # Front-running opportunities
            if swap_supported and (
                analysis["mev_type"] == "sandwich_attack" or analysis["value_eth"] > 5.0
            ):
                front_run_opp = await self._analyze_front_running(analysis)
                if front_run_opp:
                    opportunities.append(front_run_opp)

            # Back-running opportunities
            if swap_supported:
                back_run_opp = await self._analyze_back_running(analysis)
                if back_run_opp:
                    opportunities.append(back_run_opp)

            # Arbitrage opportunities
            if swap_supported:
                arb_opp = await self._analyze_arbitrage_opportunity(analysis)
                if arb_opp:
                    opportunities.append(arb_opp)

            # Liquidation opportunities
            if analysis["mev_type"] == "liquidation":
                liq_opp = await self._analyze_liquidation_opportunity(analysis)
                if liq_opp:
                    opportunities.append(liq_opp)

            # Tag opportunities as unsimulated; downstream must simulate or bypass
            for opp in opportunities:
                opp.setdefault("simulated", False)
                opp.setdefault("chain_id", self._chain_id)
                if swap_supported:
                    opp.setdefault("dex", analysis.get("target_dex"))
                    opp.setdefault("path", analysis.get("swap_path"))
                    opp.setdefault("amount_in", analysis.get("amount_in"))
                    if analysis.get("pool_fee") is not None:
                        opp.setdefault("fee", analysis.get("pool_fee"))
                    if analysis.get("fees"):
                        opp.setdefault("fees", analysis.get("fees"))
                    if analysis.get("amount_out_min"):
                        opp.setdefault(
                            "expected_amount_out", analysis.get("amount_out_min")
                        )
                if opp.get("estimated_profit_eth") is not None:
                    opp.setdefault(
                        "expected_profit_eth", opp.get("estimated_profit_eth")
                    )

            # Rate-limit dispatch: keep top 3 by estimated_profit_eth
            opportunities = sorted(
                opportunities,
                key=lambda o: o.get("estimated_profit_eth", 0),
                reverse=True,
            )[:3]

        except Exception as e:
            logger.error(
                f"Error analyzing opportunities for {analysis['tx_hash']}: {e}"
            )

        return opportunities

    async def _analyze_front_running(
        self, analysis: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Analyzes potential front-running opportunities."""
        if analysis["value_eth"] < 2.0:  # Not worth front-running small trades
            return None

        # Estimate potential profit from front-running
        estimated_slippage = min(
            analysis["value_eth"] * 0.01, 0.05
        )  # 1% per $1, max 5%
        potential_profit = (
            analysis["value_eth"] * estimated_slippage * 0.5
        )  # Conservative estimate

        if potential_profit < 0.01:  # Minimum profit threshold
            return None

        return {
            "strategy_type": "front_run",
            "target_tx": analysis,
            "estimated_profit_eth": potential_profit,
            "expected_profit_eth": potential_profit,
            "profit_potential": potential_profit,
            "confidence": min(analysis["priority_score"], 1.0),
            "gas_price_multiplier": 1.2,  # 20% higher gas for priority
            "execution_deadline": datetime.now() + timedelta(seconds=30),
        }

    async def _analyze_back_running(
        self, analysis: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Analyzes potential back-running opportunities."""
        if not analysis["target_dex"]:
            return None

        # Look for potential arbitrage after the target transaction
        potential_arbitrage = (
            analysis["value_eth"] * 0.005
        )  # Conservative 0.5% arbitrage

        if potential_arbitrage < 0.005:
            return None

        return {
            "strategy_type": "back_run",
            "target_tx": analysis,
            "estimated_profit_eth": potential_arbitrage,
            "expected_profit_eth": potential_arbitrage,
            "profit_potential": potential_arbitrage,
            "confidence": 0.6,
            "wait_for_confirmation": True,
            "execution_deadline": datetime.now() + timedelta(minutes=2),
        }

    async def _analyze_arbitrage_opportunity(
        self, analysis: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Analyzes arbitrage opportunities created by the transaction."""
        if not analysis["target_dex"] or analysis["value_eth"] < 1.0:
            return None

        # Advanced arbitrage detection by decoding swap parameters
        try:
            # Decode transaction input data to get swap parameters
            tx_input = analysis.get("input_data", "0x")
            if len(tx_input) < 10:  # Must have function selector + data
                return None

            # Common DEX function selectors
            swap_selectors = {
                "0x38ed1739": "swapExactTokensForTokens",  # Uniswap V2
                "0x8803dbee": "swapTokensForExactTokens",  # Uniswap V2
                "0x7ff36ab5": "swapExactETHForTokens",  # Uniswap V2
                "0x18cbafe5": "swapExactTokensForETH",  # Uniswap V2
                "0x414bf389": "exactInputSingle",  # Uniswap V3
                "0xc04b8d59": "exactInput",  # Uniswap V3
            }

            func_selector = tx_input[:10]
            if func_selector not in swap_selectors:
                estimated_price_impact = (
                    analysis["value_eth"] * 0.002
                )  # Fallback estimate
            else:
                # Parse swap parameters for better analysis
                try:
                    import eth_abi

                    # Decode based on function type
                    if func_selector == "0x38ed1739":  # swapExactTokensForTokens
                        # (uint amountIn, uint amountOutMin, address[] path, address to, uint deadline)
                        decoded = eth_abi.decode(
                            ["uint256", "uint256", "address[]", "address", "uint256"],
                            bytes.fromhex(tx_input[10:]),
                        )
                        amount_in = decoded[0]
                        _ = decoded[1], decoded[2]

                        # Calculate price impact based on amounts
                        if amount_in > 0:
                            # Estimate price impact using liquidity-based model
                            impact_factor = min(
                                amount_in / 10**18 / 100, 0.05
                            )  # Max 5% impact
                            estimated_price_impact = impact_factor
                        else:
                            estimated_price_impact = 0.001
                    else:
                        # For other functions, use heuristic
                        estimated_price_impact = analysis["value_eth"] * 0.001

                except Exception as decode_error:
                    logger.debug(f"Failed to decode swap parameters: {decode_error}")
                    estimated_price_impact = analysis["value_eth"] * 0.002

        except Exception as e:
            logger.warning(f"Error in arbitrage detection: {e}")
            estimated_price_impact = analysis["value_eth"] * 0.002  # Fallback estimate

        if estimated_price_impact < 0.01:
            return None

        return {
            "strategy_type": "arbitrage",
            "dex": analysis["target_dex"],
            "estimated_profit_eth": estimated_price_impact * 0.8,
            "expected_profit_eth": estimated_price_impact * 0.8,
            "profit_potential": estimated_price_impact * 0.8,
            "confidence": 0.7,
            "requires_flash_loan": analysis["value_eth"] > 10.0,
        }

    async def _analyze_liquidation_opportunity(
        self, analysis: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Analyzes liquidation opportunities."""
        if analysis["mev_type"] != "liquidation":
            return None

        # Liquidation opportunities typically have good profit margins
        estimated_profit = analysis["value_eth"] * 0.05  # 5% liquidation bonus estimate

        return {
            "strategy_type": "liquidation",
            "target_tx": analysis,
            "estimated_profit_eth": estimated_profit,
            "confidence": 0.8,
            "high_priority": True,
        }

    def _calculate_priority_score(self, analysis: dict[str, Any]) -> float:
        """Calculates priority score for the transaction."""
        score = 0.0

        # Value contribution
        score += min(analysis["value_eth"] / 10, 0.3)  # Max 0.3 for value

        # Gas price contribution (higher gas = higher priority)
        if analysis["gas_price"] > 0:
            gas_score = min(analysis["gas_price"] / self._get_high_gas_threshold(), 0.2)
            score += gas_score

        # MEV type contribution
        mev_scores = {
            "sandwich_attack": 0.3,
            "arbitrage": 0.25,
            "liquidation": 0.35,
            "flash_loan": 0.2,
        }
        if analysis["mev_type"] in mev_scores:
            score += mev_scores[analysis["mev_type"]]

        # DEX interaction bonus
        if analysis["target_dex"]:
            score += 0.15

        return min(score, 1.0)

    def _estimate_profit_potential(self, analysis: dict[str, Any]) -> float:
        """Estimates profit potential for the transaction."""
        base_profit = analysis["value_eth"] * 0.01  # 1% base estimate

        # Adjust based on MEV type
        multipliers = {
            "sandwich_attack": 1.5,
            "arbitrage": 1.2,
            "liquidation": 2.0,
            "flash_loan": 1.8,
        }

        if analysis["mev_type"] in multipliers:
            base_profit *= multipliers[analysis["mev_type"]]

        return base_profit

    def _calculate_risk_score(self, analysis: dict[str, Any]) -> float:
        """Calculates risk score for the opportunity."""
        risk = 0.5  # Base risk

        # Higher value = higher risk
        if analysis["value_eth"] > 10:
            risk += 0.2

        # Unknown MEV type = higher risk
        if not analysis["mev_type"]:
            risk += 0.2

        # Very high gas = competition risk
        if analysis["gas_price"] > self._get_high_gas_threshold() * 2:
            risk += 0.1

        return min(risk, 1.0)

    def _get_high_gas_threshold(self) -> int:
        """Gets the threshold for considering gas price as high."""
        # This would ideally be dynamic based on network conditions
        return 50 * 10**9  # 50 gwei

    def get_pending_tx_count(self) -> int:
        """Returns the count of processed pending transactions."""
        return self._pending_tx_count

    def get_cache_stats(self) -> dict[str, int]:
        """Returns cache statistics for monitoring."""
        return {
            "tx_analysis_cache_size": len(self._tx_analysis_cache),
            "opportunity_cache_size": len(self._opportunity_cache),
            "monitored_addresses": len(self._monitored_addresses),
            "dex_addresses": len(self._dex_routers),
            "processed_transactions": self._processed_tx_count,
            "detected_opportunities": self._opportunity_count,
            "cache_access_entries": len(self._cache_access_times),
        }

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics."""
        total_pending = max(self._pending_tx_count, 1)

        return {
            "pending_transactions": self._pending_tx_count,
            "processed_transactions": self._processed_tx_count,
            "detected_opportunities": self._opportunity_count,
            "processing_rate": self._processed_tx_count / total_pending,
            "opportunity_detection_rate": self._opportunity_count / total_pending,
            "cache_hit_efficiency": len(self._cache_access_times)
            / max(len(self._tx_analysis_cache), 1),
            "memory_usage": {
                "tx_cache_size": len(self._tx_analysis_cache),
                "opportunity_cache_size": len(self._opportunity_cache),
                "monitored_addresses": len(self._monitored_addresses),
            },
        }

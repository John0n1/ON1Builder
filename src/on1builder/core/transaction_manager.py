#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from eth_account import Account
from eth_account.datastructures import SignedTransaction
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3
from web3.types import TxParams, Wei
from web3.exceptions import TransactionNotFound
import aiohttp

from on1builder.config.loaders import settings
from on1builder.core.balance_manager import BalanceManager
from on1builder.core.nonce_manager import NonceManager
from on1builder.engines.safety_guard import SafetyGuard
from on1builder.integrations.abi_registry import ABIRegistry
from on1builder.integrations.external_apis import ExternalAPIManager
from on1builder.persistence.db_interface import DatabaseInterface
from on1builder.utils.custom_exceptions import (
    ConnectionError,
    InitializationError,
    InsufficientFundsError,
    StrategyExecutionError,
    TransactionError,
)
from on1builder.utils.error_recovery import get_error_recovery_manager
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService
from on1builder.utils.gas_optimizer import GasOptimizer
from on1builder.utils.profit_calculator import ProfitCalculator

logger = get_logger(__name__)


class TransactionManager:
    """
    ON1Builder transaction manager with balance awareness, flashloan support,
    and comprehensive profit tracking.
    """

    def __init__(
        self,
        web3: AsyncWeb3,
        account: LocalAccount,
        chain_id: int,
        balance_manager: BalanceManager,
    ):
        self._web3 = web3
        self._account = account
        self._address = account.address
        self._chain_id = chain_id
        self._balance_manager = balance_manager

        self._abi_registry = ABIRegistry()
        self._nonce_manager = NonceManager(web3, self._address)
        self._safety_guard = SafetyGuard(
            web3, balance_manager=balance_manager, chain_id=chain_id
        )
        self._db_interface = DatabaseInterface()
        self._api_manager = ExternalAPIManager()
        self._notification_service = NotificationService()
        self._gas_optimizer = GasOptimizer(web3)
        self._profit_calculator = ProfitCalculator(web3)
        self._private_rpc_url = getattr(settings, "private_rpc_url", None)
        self._tenderly_account = getattr(settings, "tenderly_account_slug", None)
        self._tenderly_project = getattr(settings, "tenderly_project_slug", None)
        self._tenderly_token = getattr(settings, "tenderly_access_token", None)
        self._tenderly_base_url = getattr(
            settings, "tenderly_base_url", "https://api.tenderly.co/api/v1"
        )
        self._bundle_relay_url = getattr(settings, "bundle_relay_url", None)
        self._bundle_relay_auth = getattr(settings, "bundle_relay_auth_token", None)
        self._bundle_target_block_offset = getattr(
            settings, "bundle_target_block_offset", 1
        )
        self._bundle_timeout_seconds = getattr(settings, "bundle_timeout_seconds", 30)
        self._bundle_signer_key = getattr(settings, "bundle_signer_key", None)
        self._bundle_signer_key_path = getattr(settings, "bundle_signer_key_path", None)
        self._bundle_signer_account: Optional[LocalAccount] = None

        # Performance tracking
        self._execution_stats = {
            "total_transactions": 0,
            "successful_transactions": 0,
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0,
        }
        self._last_bundle_hash: Optional[str] = None

        logger.debug(
            "ON1Builder TransactionManager initialized for chain ID %s.", chain_id
        )

    async def initialize(self):
        """Initialize the transaction manager and its components."""
        try:
            # Validate provider chain alignment
            provider_chain_id = await self._web3.eth.chain_id
            if int(provider_chain_id) != int(self._chain_id):
                raise InitializationError(
                    f"Web3 provider chain_id {provider_chain_id} does not match configured chain_id {self._chain_id}"
                )

            await self._gas_optimizer.initialize()
            logger.debug(
                "TransactionManager initialization complete for chain %s",
                self._chain_id,
            )
        except Exception as e:
            logger.error(f"Error initializing TransactionManager: {e}")
            raise

    async def _build_transaction(
        self,
        to: str,
        value: Wei = Wei(0),
        data: str = "0x",
        gas_limit: Optional[int] = None,
        gas_price: Optional[Wei] = None,
        nonce: Optional[int] = None,
    ) -> TxParams:
        """transaction building with dynamic gas optimization."""

        nonce = (
            nonce if nonce is not None else await self._nonce_manager.get_next_nonce()
        )

        tx_params: TxParams = {
            "from": self._address,
            "to": self._web3.to_checksum_address(to),
            "value": value,
            "data": data,
            "nonce": nonce,
            "chainId": self._chain_id,
        }

        # Dynamic gas pricing
        if gas_price:
            tx_params["gasPrice"] = gas_price
        elif settings.dynamic_gas_pricing:
            # Use balance manager for optimal gas price
            expected_profit = value / 10**18 * 0.01  # Rough estimate
            optimal_gas_gwei, should_proceed = (
                await self._balance_manager.calculate_optimal_gas_price(
                    Decimal(str(expected_profit))
                )
            )
            if should_proceed:
                tx_params["gasPrice"] = self._web3.to_wei(optimal_gas_gwei, "gwei")
            else:
                if getattr(settings, "allow_insufficient_funds_tests", False):
                    tx_params["gasPrice"] = await self._web3.eth.gas_price
                else:
                    raise InsufficientFundsError(
                        "Gas price too high relative to expected profit"
                    )
        else:
            tx_params["gasPrice"] = await self._web3.eth.gas_price

        # Enforce max gas price ceiling to avoid runaway costs
        max_allowed = self._web3.to_wei(settings.max_gas_price_gwei, "gwei")
        if tx_params["gasPrice"] > max_allowed:
            raise TransactionError(
                f"Gas price {tx_params['gasPrice']} exceeds max_gas_price_gwei "
                f"({settings.max_gas_price_gwei} gwei)"
            )

        # Gas limit estimation with fallback
        if gas_limit:
            tx_params["gas"] = gas_limit
        else:
            try:
                estimated_gas = await self._web3.eth.estimate_gas(tx_params)
                # Add 20% buffer for safety
                tx_params["gas"] = min(int(estimated_gas * 1.2), 30_000_000)
            except Exception as e:
                logger.warning(f"Gas estimation failed: {e}. Using default limit.")
                tx_params["gas"] = settings.default_gas_limit

        return tx_params

    async def _sign_and_send(self, tx_params: TxParams) -> str:
        """transaction signing with comprehensive safety checks."""

        # Safety check with balance awareness
        is_safe, reason = await self._safety_guard.check_transaction(tx_params)
        if not is_safe:
            raise StrategyExecutionError(f"Safety check failed: {reason}")

        # Additional balance check
        if not getattr(settings, "allow_insufficient_funds_tests", False):
            max_cost = tx_params.get("value", 0) + (
                tx_params.get("gas", 0) * tx_params.get("gasPrice", 0)
            )
            current_balance = await self._balance_manager.update_balance()
            balance_wei = self._web3.to_wei(current_balance, "ether")

            if max_cost > balance_wei:
                raise InsufficientFundsError(
                    f"Insufficient balance for transaction. Required: {max_cost}, Available: {balance_wei}"
                )

        logger.debug(f"Signing transaction for nonce {tx_params['nonce']}.")
        signed_tx: SignedTransaction = self._account.sign_transaction(tx_params)
        raw_tx = self._get_raw_transaction_bytes(signed_tx)

        for attempt in range(settings.transaction_retry_count):
            try:
                if settings.submission_mode == "public":
                    tx_hash = await self._web3.eth.send_raw_transaction(raw_tx)
                    logger.info(f"Transaction sent: {tx_hash.hex()}")
                    return tx_hash.hex()
                elif settings.submission_mode == "private":
                    if not self._private_rpc_url:
                        raise StrategyExecutionError(
                            "submission_mode is private but no private_rpc_url configured"
                        )
                    tx_hash_hex = await self._send_private_transaction(raw_tx)
                    logger.info(f"Private transaction sent: {tx_hash_hex}")
                    return tx_hash_hex
                elif settings.submission_mode == "bundle":
                    if not self._bundle_relay_url:
                        raise StrategyExecutionError(
                            "submission_mode is bundle but no bundle_relay_url configured"
                        )
                    tx_hash_hex = signed_tx.hash.hex()
                    bundle_hash = await self._send_bundle([raw_tx])
                    self._last_bundle_hash = bundle_hash
                    logger.info(
                        "Bundle submitted: %s (tx: %s)", bundle_hash, tx_hash_hex
                    )
                    return tx_hash_hex
                else:
                    raise StrategyExecutionError(
                        f"Submission mode '{settings.submission_mode}' not implemented; use public or private."
                    )
            except Exception as e:
                error_text = str(e).lower()
                logger.warning(f"Transaction send attempt {attempt + 1} failed: {e}")

                # Nonce too low: resync and retry with new nonce
                if "nonce too low" in error_text:
                    await self._nonce_manager.resync_nonce()
                    tx_params["nonce"] = await self._nonce_manager.get_next_nonce()
                    signed_tx = self._account.sign_transaction(tx_params)
                    logger.info("Nonce resynced. Retrying with new nonce.")

                # Replacement underpriced: bump gas and retry
                elif (
                    "replacement transaction underpriced" in error_text
                    or "underpriced" in error_text
                ):
                    bump_factor = Decimal("1.1")
                    current_gas_price = (
                        tx_params.get("gasPrice") or await self._web3.eth.gas_price
                    )
                    bumped = int(Decimal(current_gas_price) * bump_factor)
                    max_allowed = self._web3.to_wei(settings.max_gas_price_gwei, "gwei")
                    if bumped > max_allowed:
                        raise TransactionError(
                            f"Cannot bump gas price beyond max_gas_price_gwei ({settings.max_gas_price_gwei} gwei)"
                        )
                    tx_params["gasPrice"] = bumped
                    signed_tx = self._account.sign_transaction(tx_params)
                    raw_tx = self._get_raw_transaction_bytes(signed_tx)
                    logger.info(
                        f"Gas price bumped to {bumped} wei due to underpriced replacement."
                    )

                await asyncio.sleep(settings.transaction_retry_delay)

        raise TransactionError("Failed to send transaction after multiple retries.")

    async def wait_for_receipt(
        self, tx_hash: str, timeout: int = 120
    ) -> Dict[str, Any]:
        """Wait for transaction receipt with timeout and dropped-tx detection."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                receipt = await self._web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return receipt
            except TransactionNotFound:
                # Keep polling; tx may still be pending or replaced
                pass
            await asyncio.sleep(2)

        # Timeout: check if tx still exists in mempool; if not, treat as dropped
        try:
            pending_tx = await self._web3.eth.get_transaction(tx_hash)
        except TransactionNotFound:
            pending_tx = None

        if pending_tx is None:
            await self._nonce_manager.resync_nonce()
            raise TransactionError(
                f"Transaction {tx_hash} appears dropped or replaced after {timeout}s; nonce resynced."
            )

        raise TransactionError(
            f"Transaction {tx_hash} not confirmed within {timeout}s."
        )

    async def _send_private_transaction(self, raw_tx: bytes) -> str:
        """
        Send a private transaction via a configured private RPC (e.g., Flashbots Protect).
        Tries eth_sendPrivateTransaction first, then falls back to eth_sendRawTransaction.
        """
        if not self._private_rpc_url:
            raise StrategyExecutionError("Private RPC URL not configured.")

        async def _post(method: str) -> Optional[str]:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": [self._format_raw_tx(raw_tx)],
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._private_rpc_url, json=payload, timeout=15
                ) as resp:
                    data = await resp.json()
                    if "error" in data:
                        raise StrategyExecutionError(
                            f"Private submission ({method}) failed: {data['error'].get('message', data['error'])}"
                        )
                    return data.get("result")

        # Try eth_sendPrivateTransaction if relay supports it
        try:
            result = await _post("eth_sendPrivateTransaction")
            if result:
                return result
        except Exception as e:
            logger.debug(f"eth_sendPrivateTransaction failed, falling back: {e}")

        result = await _post("eth_sendRawTransaction")
        if not result:
            raise StrategyExecutionError("Private submission returned no result")
        return result

    async def _send_bundle(self, raw_txs: List[bytes]) -> str:
        """
        Send a bundle to a MEV-Boost/Flashbots relay via eth_sendBundle.
        """
        if not self._bundle_relay_url:
            raise StrategyExecutionError("Bundle relay URL not configured.")

        # Target a future block
        target_block = (
            await self._web3.eth.block_number
        ) + self._bundle_target_block_offset
        import time as _time

        now = int(_time.time())

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_sendBundle",
            "params": [
                {
                    "txs": [self._format_raw_tx(tx) for tx in raw_txs],
                    "blockNumber": hex(target_block),
                    "minTimestamp": now,
                    "maxTimestamp": now + self._bundle_timeout_seconds,
                }
            ],
        }

        headers = {"Content-Type": "application/json"}
        if self._bundle_relay_auth:
            headers["Authorization"] = f"Bearer {self._bundle_relay_auth}"
        try:
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            signer = self._get_bundle_signer_account()
            signature = signer.sign_message(encode_defunct(text=body)).signature.hex()
            headers["X-Flashbots-Signature"] = f"{signer.address}:{signature}"
        except Exception as e:
            raise StrategyExecutionError(f"Failed to sign bundle payload: {e}") from e

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._bundle_relay_url, data=body, headers=headers, timeout=15
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise StrategyExecutionError(
                        f"Bundle submission failed: {data['error'].get('message', data['error'])}"
                    )
                result = data.get("result")
                if isinstance(result, dict):
                    bundle_hash = result.get("bundleHash") or result.get("hash")
                    if bundle_hash:
                        return bundle_hash
                if isinstance(result, str) and result:
                    return result
                raise StrategyExecutionError("Bundle submission returned no result")

    def _get_bundle_signer_account(self) -> LocalAccount:
        if self._bundle_signer_account:
            return self._bundle_signer_account

        key = self._bundle_signer_key
        key_path = self._bundle_signer_key_path
        if not key and key_path:
            try:
                path = Path(key_path).expanduser()
                if path.exists():
                    key = path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.warning(f"Failed to read bundle signer key: {e}")

        if not key:
            account = Account.create()
            key = account.key.hex()
            if not key.startswith("0x"):
                key = f"0x{key}"

            if key_path:
                path = Path(key_path).expanduser()
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not path.exists():
                        path.write_text(f"{key}\n", encoding="utf-8")
                        try:
                            os.chmod(path, 0o600)
                        except Exception:
                            # Best effort only; Windows may not support chmod.
                            pass
                        logger.info("Generated bundle signer key at %s", path)
                except Exception as e:
                    logger.warning(f"Failed to persist bundle signer key: {e}")

        if not key:
            raise StrategyExecutionError("Bundle signer key is missing.")

        try:
            if not key.startswith("0x"):
                key = f"0x{key}"
            self._bundle_signer_account = Account.from_key(key)
        except Exception as e:
            raise StrategyExecutionError(f"Invalid bundle signer key: {e}") from e

        self._bundle_signer_key = key
        return self._bundle_signer_account

    @staticmethod
    def _format_raw_tx(raw_tx: bytes) -> str:
        """Ensure raw transaction hex is 0x-prefixed for JSON-RPC payloads."""
        hex_str = raw_tx.hex()
        return hex_str if hex_str.startswith("0x") else f"0x{hex_str}"

    @staticmethod
    def _get_raw_transaction_bytes(signed_tx: SignedTransaction) -> bytes:
        raw_tx = getattr(signed_tx, "rawTransaction", None)
        if raw_tx is None:
            raw_tx = getattr(signed_tx, "raw_transaction", None)
        if raw_tx is None:
            raise StrategyExecutionError(
                "Signed transaction missing raw transaction bytes."
            )
        return raw_tx

    async def execute_and_confirm(
        self,
        tx_params: TxParams,
        strategy_name: str,
        expected_profit: Optional[Decimal] = None,
        allow_recovery_retry: bool = True,
    ) -> Dict[str, Any]:
        """execution with profit tracking and comprehensive logging."""

        start_time = time.monotonic()
        tx_hash = ""

        try:
            # Pre-execution balance
            pre_balance = await self._balance_manager.update_balance()

            if expected_profit is not None:
                tx_params = dict(tx_params)
                tx_params["expected_profit_eth"] = float(expected_profit)

            tx_hash = await self._sign_and_send(tx_params)
            receipt = await self.wait_for_receipt(tx_hash)

            execution_time = time.monotonic() - start_time

            # Calculate actual costs and profit
            gas_used = receipt.get("gasUsed", 0)
            effective_gas_price = receipt.get(
                "effectiveGasPrice", tx_params.get("gasPrice", 0)
            )
            gas_cost_wei = gas_used * effective_gas_price
            gas_cost_eth = float(self._web3.from_wei(gas_cost_wei, "ether"))

            status = receipt.get("status") == 1

            # Post-execution balance and profit calculation.
            post_balance = await self._balance_manager.update_balance(force=True)
            balance_delta = Decimal(post_balance) - Decimal(pre_balance)
            actual_profit_eth = float(balance_delta - Decimal(str(gas_cost_eth)))

            # Update stats
            self._execution_stats["total_transactions"] += 1
            if status:
                self._execution_stats["successful_transactions"] += 1
                self._execution_stats["total_profit_eth"] += actual_profit_eth
            self._execution_stats["total_gas_spent_eth"] += gas_cost_eth

            # Save transaction to database
            await self._db_interface.save_transaction(
                {
                    "tx_hash": tx_hash,
                    "chain_id": self._chain_id,
                    "block_number": receipt.get("blockNumber"),
                    "from_address": self._address,
                    "to_address": tx_params.get("to"),
                    "value": tx_params.get("value", 0),
                    "gas_used": gas_used,
                    "gas_price": effective_gas_price,
                    "status": status,
                    "strategy": strategy_name,
                }
            )

            # Save profit record if profitable
            if status and actual_profit_eth > 0:
                await self._db_interface.save_profit_record(
                    {
                        "tx_hash": tx_hash,
                        "chain_id": self._chain_id,
                        "profit_amount_eth": actual_profit_eth,
                        "strategy": strategy_name,
                        "gas_cost_eth": gas_cost_eth,
                        "execution_time_s": execution_time,
                    }
                )

                # Record profit with balance manager
                await self._balance_manager.record_profit(
                    Decimal(str(actual_profit_eth)), strategy_name
                )

            profit_analysis = None
            if getattr(settings, "profit_analysis_enabled", False):
                try:
                    profit_calculator = getattr(self, "_profit_calculator", None)
                    if profit_calculator is None:
                        profit_calculator = ProfitCalculator(self._web3)
                        self._profit_calculator = profit_calculator
                    profit_analysis = (
                        await profit_calculator.calculate_transaction_profit(
                            tx_hash, strategy_name
                        )
                    )
                except Exception as exc:
                    logger.debug("Profit analysis failed: %s", exc)

            result = {
                "success": status,
                "tx_hash": tx_hash,
                "receipt": receipt,
                "gas_cost_eth": gas_cost_eth,
                "gas_used": gas_used,
                "profit_eth": actual_profit_eth,
                "execution_time_s": execution_time,
                "pre_balance": float(pre_balance),
                "post_balance": float(post_balance),
                "strategy": strategy_name,
                "profit_analysis": profit_analysis,
            }

            # Send notification for significant profits or failures
            if status and actual_profit_eth > 0.01:
                await self._notification_service.send_alert(
                    title=f"Profitable Trade: {strategy_name}",
                    message=f"Profit: {actual_profit_eth:.6f} ETH",
                    level="INFO",
                    details=result,
                )
            elif not status:
                await self._notification_service.send_alert(
                    title=f"Transaction Failed: {strategy_name}",
                    message=f"Transaction {tx_hash} failed",
                    level="WARNING",
                    details=result,
                )

            return result

        except (
            StrategyExecutionError,
            TransactionError,
            InsufficientFundsError,
            ConnectionError,
        ) as e:
            try:
                recovery_manager = get_error_recovery_manager()
                recovery_context = {
                    "chain_id": self._chain_id,
                    "strategy": strategy_name,
                    "tx_params": tx_params,
                    "retry_tx_params": dict(tx_params),
                    "transaction_manager": self,
                }
                await recovery_manager.handle_error(
                    e,
                    recovery_context,
                    "TransactionManager",
                )
                if allow_recovery_retry and recovery_context.get("retry"):
                    retry_params = recovery_context.get("retry_tx_params")
                    if retry_params:
                        return await self.execute_and_confirm(
                            retry_params,
                            strategy_name,
                            expected_profit,
                            allow_recovery_retry=False,
                        )
            except Exception as recovery_exc:
                logger.debug(
                    "Error recovery handling failed: %s",
                    recovery_exc,
                    exc_info=True,
                )
            logger.error(f"Execution failed for strategy '{strategy_name}': {e}")
            await self._notification_service.send_alert(
                title=f"Strategy '{strategy_name}' Failed",
                message=str(e),
                level="ERROR",
                details={"tx_hash": tx_hash, "strategy": strategy_name},
            )
            return {
                "success": False,
                "reason": str(e),
                "tx_hash": tx_hash,
                "strategy": strategy_name,
            }

    async def _get_dex_contract(self, dex_name: str):
        """Get DEX contract with ON1Builder error handling."""
        abi_name = f"{dex_name.lower()}_abi"
        abi = self._abi_registry.get_abi(abi_name)
        if not abi:
            raise StrategyExecutionError(
                f"{dex_name} ABI not found. Available ABIs: {list(self._abi_registry._abis.keys())}"
            )

        # Try different address mapping formats
        address_maps = [
            getattr(settings.contracts, f"{dex_name.lower()}_router", {}),
            getattr(settings.contracts, f"{dex_name.lower()}_addresses", {}),
            getattr(settings.contracts, dex_name.lower(), {}),
        ]

        address = None
        for address_map in address_maps:
            if isinstance(address_map, dict):
                address = address_map.get(str(self._chain_id))
                if address:
                    break

        if not address:
            raise StrategyExecutionError(
                f"{dex_name} router address not configured for chain {self._chain_id}."
            )

        return self._web3.eth.contract(address=address, abi=abi)

    def _get_wrapped_native_address(self) -> str:
        """
        Resolve the chain-specific wrapped native token address (e.g., WETH/WBNB).
        Falls back to mainnet WETH if not configured, but logs so callers know.
        """
        address = self._abi_registry.get_token_address("WETH", self._chain_id)
        if not address:
            logger.warning(
                f"No wrapped native token configured for chain {self._chain_id}; "
                "falling back to mainnet WETH address."
            )
            address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
        return address.lower()

    async def _simulate_transaction(self, tx_params: TxParams) -> None:
        """
        Lightweight preflight simulation using the configured backend.
        For now, only eth_call is supported; other backends are placeholders.
        """
        backend = settings.simulation_backend
        if backend == "eth_call":
            tx_for_call = dict(tx_params)
            tx_for_call.pop("nonce", None)
            try:
                await self._web3.eth.call(tx_for_call)
            except Exception as e:
                raise StrategyExecutionError(f"Simulation failed: {e}")
        elif backend == "anvil":
            # Use a local anvil fork RPC if provided
            fork_rpc = self._private_rpc_url or getattr(
                settings, "private_rpc_url", None
            )
            if not fork_rpc:
                raise StrategyExecutionError(
                    "Simulation backend 'anvil' requires private_rpc_url pointing to a forked node."
                )
            tx_for_call = dict(tx_params)
            tx_for_call.pop("nonce", None)
            async with aiohttp.ClientSession() as session:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [tx_for_call, "latest"],
                }
                async with session.post(fork_rpc, json=payload, timeout=15) as resp:
                    data = await resp.json()
                    if "error" in data:
                        raise StrategyExecutionError(
                            f"Anvil simulation failed: {data['error'].get('message', data['error'])}"
                        )
        elif backend == "tenderly":
            await self._simulate_with_tenderly(tx_params)
        else:
            raise StrategyExecutionError(
                f"Simulation backend '{backend}' not implemented; switch to eth_call or disable allow_unsimulated_trades"
            )

    async def _simulate_with_tenderly(self, tx_params: TxParams) -> None:
        """Simulate a transaction using Tenderly API."""
        if not (
            self._tenderly_account and self._tenderly_project and self._tenderly_token
        ):
            raise StrategyExecutionError("Tenderly credentials not configured.")

        url = (
            f"{self._tenderly_base_url}/account/"
            f"{self._tenderly_account}/project/{self._tenderly_project}/simulate"
        )

        payload = {
            "network_id": str(self._chain_id),
            "from": tx_params.get("from"),
            "to": tx_params.get("to"),
            "input": tx_params.get("data", "0x"),
            "gas": tx_params.get("gas", settings.default_gas_limit),
            "gas_price": tx_params.get("gasPrice") or await self._web3.eth.gas_price,
            "value": tx_params.get("value", 0),
            "save": False,
            "save_if_fails": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._tenderly_token}",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=15
            ) as resp:
                data = await resp.json()
                if resp.status >= 400 or "error" in data:
                    message = (
                        data.get("error", {}).get("message")
                        if isinstance(data.get("error"), dict)
                        else data.get("error")
                    )
                    raise StrategyExecutionError(
                        f"Tenderly simulation failed: {message or data}"
                    )
                # success: no return value needed

    async def _get_token_allowance(self, token_address: str, spender: str) -> int:
        """Check ERC20 allowance for the spender."""
        erc20_abi = self._abi_registry.get_abi("erc20_abi")
        token_contract = self._web3.eth.contract(address=token_address, abi=erc20_abi)
        return await token_contract.functions.allowance(self._address, spender).call()

    async def _get_swap_path(self, opportunity: Dict[str, Any]) -> List[str]:
        """path resolution with validation."""
        path = opportunity.get("path")
        if not path or len(path) < 2:
            raise StrategyExecutionError("Invalid or missing swap path in opportunity.")

        resolved_path = []
        for symbol in path:
            if symbol.startswith("0x"):
                # Already an address
                resolved_path.append(self._web3.to_checksum_address(symbol))
            else:
                # Resolve symbol to address
                address = self._abi_registry.get_token_address(symbol, self._chain_id)
                if not address:
                    raise StrategyExecutionError(
                        f"Token address not found for symbol: {symbol}"
                    )
                resolved_path.append(address)

        return resolved_path

    @staticmethod
    def _encode_uniswap_v3_path(tokens: List[str], fees: List[int]) -> bytes:
        """Encode Uniswap V3 path bytes from token addresses and fee tiers."""
        if len(tokens) != len(fees) + 1:
            raise StrategyExecutionError(
                "Uniswap V3 path requires fees for each hop (len(tokens) = len(fees) + 1)."
            )

        encoded = b""
        for idx, fee in enumerate(fees):
            if fee < 0 or fee >= 2**24:
                raise StrategyExecutionError(
                    f"Invalid Uniswap V3 fee tier: {fee}. Must fit uint24."
                )
            token = tokens[idx]
            encoded += bytes.fromhex(token[2:])
            encoded += int(fee).to_bytes(3, "big")
        encoded += bytes.fromhex(tokens[-1][2:])
        return encoded

    async def _calculate_amounts_with_slippage(
        self, opportunity: Dict[str, Any], expected_amount_out: Optional[int] = None
    ) -> Tuple[int, int]:
        """Calculate swap amounts with slippage protection."""
        amount_in = opportunity.get("amount_in", 0)
        expected_out = (
            expected_amount_out
            if expected_amount_out is not None
            else opportunity.get("expected_amount_out", 0)
        )

        # Convert to Wei if necessary
        if isinstance(amount_in, float):
            amount_in = int(amount_in * 10**18)
        if isinstance(expected_out, float):
            expected_out = int(expected_out * 10**18)

        if expected_out <= 0:
            raise StrategyExecutionError(
                "Missing expected_amount_out; cannot protect slippage."
            )

        # Apply slippage tolerance
        slippage_multiplier = 1 - (settings.slippage_tolerance / 100)
        amount_out_min = int(expected_out * slippage_multiplier)

        return amount_in, amount_out_min

    async def _quote_expected_output(
        self, dex_contract, amount_in: int, path: List[str]
    ) -> int:
        """Quote expected output using getAmountsOut on the DEX contract."""
        try:
            amounts = await dex_contract.functions.getAmountsOut(amount_in, path).call()
            if not amounts or len(amounts) < 2:
                raise StrategyExecutionError("DEX quote returned no amounts.")
            return int(amounts[-1])
        except Exception as e:
            raise StrategyExecutionError(f"Failed to quote expected output: {e}")

    async def execute_swap(
        self,
        opportunity: Dict[str, Any],
        strategy_name: str,
        simulate_only: bool = False,
    ) -> Dict[str, Any]:
        """swap execution with comprehensive validation."""

        if (
            not opportunity.get("simulated", False)
            and not settings.allow_unsimulated_trades
            and not simulate_only
        ):
            reason = "Opportunity not simulated and allow_unsimulated_trades is False"
            logger.warning(reason)
            return {"success": False, "reason": reason}

        # Validate opportunity has required fields
        required_fields = ["dex", "path", "amount_in"]
        for field in required_fields:
            if field not in opportunity:
                raise StrategyExecutionError(
                    f"Missing required field in opportunity: {field}"
                )

        dex_name = opportunity.get("dex", "uniswap")
        if dex_name in {"uniswap_v3", "uniswapv3", "v3"}:
            return await self._execute_swap_v3(
                opportunity, strategy_name, simulate_only
            )
        dex_contract = await self._get_dex_contract(dex_name)

        # Normalize path to checksum addresses for web3 compatibility
        raw_path = await self._get_swap_path(opportunity)
        path = [self._web3.to_checksum_address(addr) for addr in raw_path]

        # Determine expected output; if not provided, quote via DEX
        expected_out = opportunity.get("expected_amount_out", 0)
        if not expected_out or expected_out <= 0:
            expected_out = await self._quote_expected_output(
                dex_contract, amount_in=opportunity.get("amount_in", 0), path=path
            )
            opportunity["expected_amount_out"] = expected_out

        amount_in, amount_out_min = await self._calculate_amounts_with_slippage(
            opportunity, expected_amount_out=expected_out
        )

        deadline = int(time.time()) + 300  # 5 minute deadline

        # Check if we have enough balance for this swap
        wrapped_native = self._get_wrapped_native_address()
        first_hop = path[0].lower()
        if first_hop != wrapped_native:  # Token in
            token_contract = self._web3.eth.contract(
                address=path[0], abi=self._abi_registry.get_abi("erc20_abi")
            )
            balance = await token_contract.functions.balanceOf(self._address).call()
            if balance < amount_in:
                raise InsufficientFundsError(
                    f"Insufficient token balance. Required: {amount_in}, Available: {balance}"
                )
            # Ensure allowance is non-zero by default to avoid on-chain failures.
            allowance = await self._get_token_allowance(path[0], dex_contract.address)
            if allowance < amount_in:
                raise StrategyExecutionError(
                    f"Token allowance too low for spender {dex_contract.address}: {allowance} < {amount_in}"
                )

        # Build transaction based on swap type
        if path[0].lower() == wrapped_native:  # ETH to token
            function_call = dex_contract.functions.swapExactETHForTokens(
                amount_out_min, path, self._address, deadline
            )
            value = Wei(amount_in)
        elif path[-1].lower() == wrapped_native:  # Token to ETH
            function_call = dex_contract.functions.swapExactTokensForETH(
                amount_in, amount_out_min, path, self._address, deadline
            )
            value = Wei(0)
        else:  # Token to token
            function_call = dex_contract.functions.swapExactTokensForTokens(
                amount_in, amount_out_min, path, self._address, deadline
            )
            value = Wei(0)

        # Build and send transaction
        tx_data = function_call.build_transaction(
            {
                "from": self._address,
                "value": value,
                "gas": settings.default_gas_limit,
            }
        )["data"]

        tx_params = await self._build_transaction(
            to=dex_contract.address, data=tx_data, value=value
        )

        # Preflight simulate unless caller already simulated/bypassed
        if not opportunity.get("simulated", False):
            await self._simulate_transaction(tx_params)
            opportunity["simulated"] = True

        if simulate_only:
            return {"success": True, "simulated": True}

        # Override gas price if specified
        if opportunity.get("gas_price_wei"):
            tx_params["gasPrice"] = Wei(opportunity["gas_price_wei"])
        elif opportunity.get("optimal_gas_price"):
            tx_params["gasPrice"] = self._web3.to_wei(
                opportunity["optimal_gas_price"], "gwei"
            )

        expected_profit = opportunity.get("expected_profit_eth", 0)
        return await self.execute_and_confirm(
            tx_params,
            strategy_name,
            Decimal(str(expected_profit)) if expected_profit else None,
        )

    async def _execute_swap_v3(
        self, opportunity: Dict[str, Any], strategy_name: str, simulate_only: bool
    ) -> Dict[str, Any]:
        """Execute Uniswap V3 swap using exactInput or exactInputSingle."""
        dex_contract = await self._get_dex_contract("uniswap_v3")

        raw_path = await self._get_swap_path(opportunity)
        path = [self._web3.to_checksum_address(addr) for addr in raw_path]

        expected_out = opportunity.get("expected_amount_out") or opportunity.get(
            "amount_out_min"
        )
        if not expected_out or expected_out <= 0:
            raise StrategyExecutionError(
                "Uniswap V3 requires expected_amount_out/amount_out_min for slippage protection."
            )

        amount_in, amount_out_min = await self._calculate_amounts_with_slippage(
            opportunity, expected_amount_out=expected_out
        )

        deadline = int(time.time()) + 300
        sqrt_price_limit = int(opportunity.get("sqrt_price_limit_x96", 0))

        wrapped_native = self._get_wrapped_native_address()
        token_in = path[0].lower()
        value = Wei(amount_in) if token_in == wrapped_native else Wei(0)

        if token_in != wrapped_native:
            allowance = await self._get_token_allowance(path[0], dex_contract.address)
            if allowance < amount_in:
                raise StrategyExecutionError(
                    f"Token allowance too low for spender {dex_contract.address}: {allowance} < {amount_in}"
                )

        if len(path) == 2:
            fee = opportunity.get("fee") or opportunity.get("pool_fee")
            if fee is None:
                raise StrategyExecutionError(
                    "Uniswap V3 single-hop swaps require fee or pool_fee."
                )
            params = (
                path[0],
                path[1],
                int(fee),
                self._address,
                deadline,
                amount_in,
                amount_out_min,
                sqrt_price_limit,
            )
            function_call = dex_contract.functions.exactInputSingle(params)
        else:
            fees = opportunity.get("fees")
            if not fees:
                raise StrategyExecutionError(
                    "Uniswap V3 multi-hop swaps require fees list."
                )
            path_bytes = self._encode_uniswap_v3_path(path, [int(f) for f in fees])
            params = (
                path_bytes,
                self._address,
                deadline,
                amount_in,
                amount_out_min,
            )
            function_call = dex_contract.functions.exactInput(params)

        tx_data = function_call.build_transaction(
            {
                "from": self._address,
                "value": value,
                "gas": settings.default_gas_limit,
            }
        )["data"]

        tx_params = await self._build_transaction(
            to=dex_contract.address, data=tx_data, value=value
        )

        if not opportunity.get("simulated", False):
            await self._simulate_transaction(tx_params)
            opportunity["simulated"] = True

        if simulate_only:
            return {"success": True, "simulated": True}

        if opportunity.get("gas_price_wei"):
            tx_params["gasPrice"] = Wei(opportunity["gas_price_wei"])
        elif opportunity.get("optimal_gas_price"):
            tx_params["gasPrice"] = self._web3.to_wei(
                opportunity["optimal_gas_price"], "gwei"
            )

        expected_profit = opportunity.get("expected_profit_eth", 0)
        return await self.execute_and_confirm(
            tx_params,
            strategy_name,
            Decimal(str(expected_profit)) if expected_profit else None,
        )

    async def execute_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute arbitrage opportunity with ON1Builder validation."""
        logger.info(f"Executing arbitrage opportunity: {opportunity}")

        # Validate arbitrage opportunity
        if not opportunity.get("profit_potential", 0) > 0:
            return {
                "success": False,
                "reason": "No profit potential in arbitrage opportunity",
            }

        # Check if we should use flashloan
        required_amount = Decimal(str(opportunity.get("amount_in", 0)))
        if await self._balance_manager.should_use_flashloan(required_amount):
            return await self.execute_flashloan_arbitrage(opportunity)

        return await self.execute_swap(opportunity, "arbitrage")

    async def execute_front_run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute front-running strategy with gas optimization."""
        logger.info(f"Executing front-run opportunity: {opportunity}")

        target_tx = opportunity.get("target_tx", {})
        if not target_tx:
            return {
                "success": False,
                "reason": "No target transaction for front-running",
            }

        target_gas_price = target_tx.get("gasPrice", 0)

        # Calculate competitive gas price
        gas_premium = self._web3.to_wei(2, "gwei")  # 2 gwei premium
        opportunity["gas_price_wei"] = target_gas_price + gas_premium

        # Ensure we can afford the higher gas price
        expected_profit = opportunity.get("expected_profit_eth", 0)
        gas_cost_estimate = (
            opportunity.get("gas_limit", 150000) * (target_gas_price + gas_premium)
        ) / 10**18

        if gas_cost_estimate >= expected_profit * 0.8:  # Gas cost > 80% of profit
            return {
                "success": False,
                "reason": "Gas cost too high relative to expected profit",
            }

        return await self.execute_swap(opportunity, "front_run")

    async def execute_back_run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute back-running strategy with timing optimization."""
        logger.info(f"Executing back-run opportunity: {opportunity}")

        target_tx = opportunity.get("target_tx", {})
        if not target_tx:
            return {
                "success": False,
                "reason": "No target transaction for back-running",
            }

        # Wait for target transaction to be mined
        target_hash = target_tx.get("hash")
        if target_hash:
            try:
                await self.wait_for_receipt(target_hash, timeout=60)
                logger.info("Target transaction confirmed, executing back-run")
            except TransactionError:
                return {
                    "success": False,
                    "reason": "Target transaction not confirmed in time",
                }

        # Use slightly lower gas price for back-running
        target_gas_price = target_tx.get("gasPrice", 0)
        opportunity["gas_price_wei"] = max(
            target_gas_price - self._web3.to_wei(1, "gwei"),
            await self._web3.eth.gas_price,
        )

        return await self.execute_swap(opportunity, "back_run")

    async def execute_sandwich(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute sandwich attack with comprehensive coordination."""
        logger.info("Executing sandwich attack strategy")

        target_tx = opportunity.get("target_tx", {})
        if not target_tx:
            return {
                "success": False,
                "reason": "No target transaction for sandwich attack",
            }

        # Prepare front-run and back-run opportunities
        front_run_opp = opportunity.copy()
        back_run_opp = opportunity.copy()

        target_gas_price = target_tx.get("gasPrice", 0)

        # Front-run with higher gas price
        front_run_opp["gas_price_wei"] = target_gas_price + self._web3.to_wei(2, "gwei")

        # Execute front-run
        logger.info("Executing sandwich front-run")
        front_run_result = await self.execute_swap(front_run_opp, "sandwich_front_run")

        if not front_run_result.get("success"):
            return {
                "success": False,
                "reason": "Sandwich front-run failed",
                "front_run_result": front_run_result,
            }

        logger.info("Front-run successful, waiting for target transaction")

        # Wait for target transaction
        try:
            target_hash = target_tx.get("hash")
            if target_hash:
                await self.wait_for_receipt(target_hash, timeout=120)
            else:
                # Wait a bit for target to be mined
                await asyncio.sleep(15)
        except TransactionError as e:
            logger.warning(f"Target transaction monitoring failed: {e}")
            # Continue with back-run anyway

        logger.info("Executing sandwich back-run")

        # Prepare back-run (reverse the path)
        back_run_opp["path"] = list(reversed(opportunity["path"]))
        back_run_opp["gas_price_wei"] = target_gas_price

        # Use proceeds from front-run for back-run
        front_run_receipt = front_run_result.get("receipt", {})
        if front_run_receipt:
            # Calculate amount received from front-run by parsing logs
            try:
                receipt_obj = await self._web3.eth.get_transaction_receipt(
                    front_run_receipt.get("transactionHash")
                )
                amount_received = Decimal("0")

                # Parse Transfer events to get actual output amount
                for log in receipt_obj.logs:
                    try:
                        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
                        if log.topics and log.topics[0].hex() == transfer_topic:
                            # Check if transfer is to our address
                            to_address = "0x" + log.topics[2].hex()[-40:]
                            if to_address.lower() == self._account.address.lower():
                                amount_hex = log.data[0:64] if log.data else "0x0"
                                amount = int(amount_hex, 16)
                                amount_received = max(
                                    amount_received,
                                    self._web3.from_wei(amount, "ether"),
                                )
                    except (IndexError, ValueError, AttributeError):
                        continue

                back_run_opp["amount_in"] = (
                    float(amount_received)
                    if amount_received > 0
                    else opportunity.get("amount_in", 0)
                )
            except Exception as e:
                logger.warning(f"Failed to parse front-run proceeds: {e}")
                back_run_opp["amount_in"] = opportunity.get("amount_in", 0)

        back_run_result = await self.execute_swap(back_run_opp, "sandwich_back_run")

        # Calculate total profit/loss
        front_run_cost = front_run_result.get("gas_cost_eth", 0)
        back_run_cost = back_run_result.get("gas_cost_eth", 0)
        back_run_profit = back_run_result.get("profit_eth", 0)

        total_profit = back_run_profit - front_run_cost - back_run_cost

        return {
            "success": back_run_result.get("success", False),
            "profit_eth": total_profit,
            "front_run_tx": front_run_result.get("tx_hash"),
            "back_run_tx": back_run_result.get("tx_hash"),
            "front_run_result": front_run_result,
            "back_run_result": back_run_result,
            "total_gas_cost_eth": front_run_cost + back_run_cost,
        }

    async def execute_flashloan_arbitrage(
        self, opportunity: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute flashloan-based arbitrage with ON1Builder safety."""
        logger.info("Executing flashloan arbitrage strategy")

        if not settings.flashloan_enabled:
            return {"success": False, "reason": "Flashloan functionality is disabled"}

        # Validate flashloan opportunity
        required_amount = opportunity.get(
            "flashloan_amount", opportunity.get("amount_in", 0)
        )
        max_flashloan = settings.flashloan_max_amount_eth

        if required_amount > max_flashloan:
            return {
                "success": False,
                "reason": f"Flashloan amount {required_amount} exceeds maximum {max_flashloan}",
            }

        expected_profit = opportunity.get("expected_profit_eth", 0)
        min_profit_required = (
            required_amount * settings.flashloan_min_profit_multiplier / 100
        )

        if expected_profit < min_profit_required:
            return {
                "success": False,
                "reason": f"Expected profit {expected_profit} below minimum required {min_profit_required}",
            }

        # Prepare flashloan parameters
        assets = [
            opportunity.get(
                "flashloan_asset", "0xA0b86a33E6441E6b99aba6c00bbe0c47D6D2EC30"
            )
        ]  # WETH default
        amounts = [int(required_amount * 10**18)]  # Convert to Wei

        # Encode arbitrage data for flashloan callback
        arbitrage_data = {
            "dex_buy": opportunity.get("dex_buy", "uniswap"),
            "dex_sell": opportunity.get("dex_sell", "sushiswap"),
            "path_buy": opportunity.get("path_buy", opportunity.get("path", [])),
            "path_sell": opportunity.get("path_sell", opportunity.get("path", [])),
            "min_profit_wei": int(min_profit_required * 10**18),
        }

        # Properly encode arbitrage data for flashloan contract callback
        import json

        try:
            # Create structured data for the flashloan callback
            callback_data = {
                "type": "arbitrage",
                "exchanges": [
                    arbitrage_data.get("exchange_a", ""),
                    arbitrage_data.get("exchange_b", ""),
                ],
                "token_path": arbitrage_data.get("token_path", []),
                "amounts": [
                    str(arbitrage_data.get("amount_in", 0)),
                    str(arbitrage_data.get("expected_out", 0)),
                ],
                "min_profit": str(arbitrage_data.get("min_profit", 0)),
                "deadline": int(time.time()) + 300,  # 5 minute deadline
            }
            user_data = json.dumps(callback_data).encode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to encode callback data: {e}")
            user_data = str(arbitrage_data).encode("utf-8")

        flashloan_opportunity = {
            "assets": assets,
            "amounts": amounts,
            "user_data": user_data,
            "strategy_type": "flashloan_arbitrage",
            "expected_profit_eth": expected_profit,
        }

        return await self.execute_flashloan(flashloan_opportunity)

    async def execute_flashloan(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """flashloan execution with comprehensive validation."""
        strategy_name = "flashloan"
        logger.info(f"Executing flashloan strategy with opportunity: {opportunity}")

        # Validate flashloan parameters
        assets: List[str] = opportunity.get("assets", [])
        amounts: List[int] = opportunity.get("amounts", [])
        user_data: bytes = opportunity.get("user_data", b"")

        if not all([assets, amounts]):
            raise StrategyExecutionError(
                "Flashloan opportunity missing 'assets' or 'amounts'."
            )

        if len(assets) != len(amounts):
            raise StrategyExecutionError(
                "Assets and amounts arrays must have same length."
            )

        # Get flashloan contract
        flashloan_contract_addresses = settings.contracts.simple_flashloan_contract
        flashloan_contract_address = flashloan_contract_addresses.get(
            str(self._chain_id)
        )

        if not flashloan_contract_address:
            raise StrategyExecutionError(
                f"Flashloan contract not configured for chain {self._chain_id}."
            )

        flashloan_abi = self._abi_registry.get_abi("aave_flashloan_abi")
        if not flashloan_abi:
            raise StrategyExecutionError("Flashloan ABI not found.")

        contract = self._web3.eth.contract(
            address=flashloan_contract_address, abi=flashloan_abi
        )

        # Check if we have enough ETH for flashloan fees
        balance_summary = await self._balance_manager.get_balance_summary()
        if balance_summary["balance"] < 0.01:  # Need some ETH for fees
            raise InsufficientFundsError(
                "Insufficient ETH balance to pay flashloan fees"
            )

        # Build flashloan transaction
        try:
            encoded_function = contract.functions.requestFlashLoan(
                assets, amounts, user_data
            ).build_transaction(
                {
                    "chainId": self._chain_id,
                    "from": self._address,
                    "value": 0,
                }
            )

            tx_params = await self._build_transaction(
                to=flashloan_contract_address, data=encoded_function["data"]
            )

            # Add buffer for flashloan gas requirements
            tx_params["gas"] = int(tx_params["gas"] * 1.5)

            expected_profit = opportunity.get("expected_profit_eth", 0)
            result = await self.execute_and_confirm(
                tx_params,
                strategy_name,
                Decimal(str(expected_profit)) if expected_profit else None,
            )

            if result["success"]:
                # Calculate actual flashloan profit from logs
                receipt = result.get("receipt", {})
                actual_profit = await self._calculate_flashloan_profit(receipt)
                result["profit_eth"] = actual_profit
                result["flashloan_amounts"] = amounts
                result["flashloan_assets"] = assets

                logger.info(
                    f"Flashloan executed successfully. Profit: {actual_profit:.6f} ETH"
                )

            return result

        except Exception as e:
            logger.error(f"Flashloan execution failed: {e}")
            return {
                "success": False,
                "reason": f"Flashloan execution error: {str(e)}",
                "strategy": strategy_name,
            }

    async def _calculate_flashloan_profit(self, receipt: Dict[str, Any]) -> float:
        """Calculate actual profit from flashloan transaction receipt."""
        try:
            # Parse transaction logs to get exact profit by analyzing Transfer events
            logs = receipt.get("logs", [])
            profit = Decimal("0")
            our_address = self._account.address.lower()

            # Track all token transfers to/from our address
            transfers_in = Decimal("0")
            transfers_out = Decimal("0")

            for log in logs:
                try:
                    # Check for Transfer events (ERC20)
                    transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
                    if log.get("topics") and len(log["topics"]) >= 3:
                        if log["topics"][0].hex() == transfer_topic:
                            from_addr = "0x" + log["topics"][1].hex()[-40:]
                            to_addr = "0x" + log["topics"][2].hex()[-40:]

                            # Parse amount from data field
                            data = log.get("data", "0x")
                            if len(data) >= 66:  # 0x + 64 hex chars
                                amount_hex = data[2:66]
                                amount = int(amount_hex, 16)
                                amount_ether = self._web3.from_wei(amount, "ether")

                                # Track transfers to/from our address
                                if to_addr.lower() == our_address:
                                    transfers_in += amount_ether
                                elif from_addr.lower() == our_address:
                                    transfers_out += amount_ether
                except (IndexError, ValueError, AttributeError) as e:
                    continue

            # Calculate net profit (transfers in minus transfers out)
            net_profit = transfers_in - transfers_out

            # Account for gas costs
            gas_used = receipt.get("gasUsed", 0)
            gas_price = receipt.get("effectiveGasPrice", 0)
            gas_cost = self._web3.from_wei(gas_used * gas_price, "ether")

            final_profit = net_profit - gas_cost

            return float(final_profit)

        except Exception as e:
            logger.error(f"Failed to calculate flashloan profit: {e}")
            return 0.0

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Return comprehensive performance statistics."""
        success_rate = 0.0
        if self._execution_stats["total_transactions"] > 0:
            success_rate = (
                self._execution_stats["successful_transactions"]
                / self._execution_stats["total_transactions"]
                * 100
            )

        net_profit = (
            self._execution_stats["total_profit_eth"]
            - self._execution_stats["total_gas_spent_eth"]
        )

        return {
            **self._execution_stats,
            "success_rate_percentage": success_rate,
            "net_profit_eth": net_profit,
            "average_profit_per_transaction": (
                self._execution_stats["total_profit_eth"]
                / max(1, self._execution_stats["successful_transactions"])
            ),
            "average_gas_cost_per_transaction": (
                self._execution_stats["total_gas_spent_eth"]
                / max(1, self._execution_stats["total_transactions"])
            ),
        }

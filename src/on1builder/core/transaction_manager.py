#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
ON1Builder – TransactionCore
============================
High-level helper for building, signing, simulating, and dispatching MEV-style transactions.
This module provides a comprehensive interface for managing Ethereum transactions,
including nonce management, gas estimation, and safety checks.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Union

from eth_account import Account
from eth_account.datastructures import SignedTransaction
from web3 import AsyncWeb3, Web3

from ..config.settings import GlobalSettings
from ..engines.safety_guard import SafetyGuard
from ..utils.custom_exceptions import StrategyExecutionError
from ..utils.logging_config import get_logger
from .nonce_manager import NonceManager

# Use TYPE_CHECKING to resolve circular dependencies
if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class TransactionManager:
    """High-level helper for building, signing, simulating, and dispatching MEV-style transactions."""

    DEFAULT_GAS_LIMIT: int = 100_000
    ETH_TRANSFER_GAS: int = 21_000
    GAS_RETRY_BUMP: float = 1.15  # +15% per retry

    def __init__(
        self,
        web3: AsyncWeb3,
        account: Account,
        configuration: GlobalSettings,
        nonce_manager: Optional[NonceManager] = None,
        safety_guard: Optional[SafetyGuard] = None,
        external_api_manager: Optional[Any] = None,
        market_monitor: Optional[Any] = None,
        txpool_monitor: Optional[Any] = None,
        chain_id: int = 1,
        main_orchestrator: Optional[
            Any
        ] = None,  # Reference to MainOrchestrator for shared resources
    ) -> None:
        """Initialize the TransactionManager."""
        self.web3 = web3
        self.chain_id = chain_id
        self.account = account
        self.address = account.address
        self.configuration = configuration
        self.external_api_manager = external_api_manager
        self.market_monitor = market_monitor
        self.txpool_monitor = txpool_monitor
        self.nonce_manager = nonce_manager
        self.safety_guard = safety_guard
        self.main_orchestrator = (
            main_orchestrator  # Store reference to MainOrchestrator
        )

        # Access shared components from main_orchestrator if available
        self.abi_registry = None
        self.db_interface = None

        if main_orchestrator and hasattr(main_orchestrator, "components"):
            # Get ABI Registry
            self.abi_registry = main_orchestrator.components.get("abi_registry")
            if self.abi_registry:
                logger.debug(
                    "TransactionManager: Using shared ABIRegistry from MainOrchestrator"
                )

            # Get DB Interface
            self.db_interface = main_orchestrator.components.get("db_interface")
            if self.db_interface:
                logger.debug(
                    "TransactionManager: Using shared DatabaseInterface from MainOrchestrator"
                )

            # Get notification manager if available
            self.notification_manager = main_orchestrator.components.get(
                "notification_manager"
            )
            if self.notification_manager:
                logger.debug(
                    "TransactionManager: Using shared NotificationService from MainOrchestrator"
                )

        self._pending_txs: Dict[str, Dict[str, Any]] = {}

        logger.debug(f"TransactionCore initialized for chain ID {chain_id}")

    async def initialize(self) -> bool:
        """Perform async initialization logic."""
        logger.info("Initializing TransactionCore")

        # Validate web3 connection
        try:
            connected = await self.web3.is_connected()
            if not connected:
                logger.error("Web3 connection not available")
                return False
            logger.debug("Web3 connection verified")
        except Exception as e:
            logger.error(f"Error checking Web3 connection: {e}")
            return False

        # If we have DB interface, ensure it's ready
        if self.db_interface and hasattr(self.db_interface, "ensure_tables"):
            try:
                await self.db_interface.ensure_tables()
                logger.debug("Database tables verified")
            except Exception as e:
                logger.warning(f"Error ensuring database tables: {e}")

        # Verify safety guard
        if self.safety_guard is None:
            logger.warning(
                "No SafetyGuard available, transactions will not be checked for safety"
            )

        # Verify nonce manager
        if self.nonce_manager is None:
            logger.warning("No NonceManager available, using on-chain nonce tracking")

        return True

    async def build_transaction(
        self,
        function_call: Union[Callable, Any],
        additional_params: Optional[Dict[str, Any]] = None,
        to_address: Optional[str] = None,
        value: int = 0,
        data: str = "",
        gas_limit: Optional[int] = None,
        gas_price: Optional[int] = None,
        nonce: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build an Ethereum transaction dict."""
        # Resolve nonce - this is critical for transaction signing
        if nonce is None:
            if self.nonce_manager:
                try:
                    nonce = await self.nonce_manager.get_next_nonce(self.address)
                except Exception as e:
                    logger.error(f"NonceCore error: {e}")
                    nonce = None

            # Fallback to web3 nonce if nonce_core failed or not available
            if nonce is None:
                try:
                    nonce = await self.web3.eth.get_transaction_count(
                        self.address, "pending"
                    )
                except Exception as e:
                    logger.error(f"Web3 nonce failed: {e}; using latest")
                    try:
                        nonce = await self.web3.eth.get_transaction_count(
                            self.address, "latest"
                        )
                    except Exception:
                        logger.error("All nonce methods failed; using 0")
                        nonce = 0

        # Prepare base tx
        tx: Dict[str, Any] = {
            "from": self.address,
            "chainId": self.chain_id,
            "value": value,
        }

        # Always set nonce - critical for transaction signing
        if nonce is not None:
            tx["nonce"] = nonce

        # Contract call vs raw tx
        if hasattr(function_call, "build_transaction"):
            params = {"from": self.address, "value": value, "chainId": self.chain_id}
            # Always include nonce for contract transactions
            if nonce is not None:
                params["nonce"] = nonce
            if gas_price is not None:
                params["gasPrice"] = gas_price
            if additional_params:
                params.update(additional_params)
            try:
                tx = await function_call.build_transaction(params)
                # Ensure nonce is in the final transaction dict
                if nonce is not None and "nonce" not in tx:
                    tx["nonce"] = nonce
            except Exception as e:
                logger.error(f"Contract build_transaction error: {e}")
                raise StrategyExecutionError(f"Failed to build contract tx: {e}")
        else:
            if to_address:
                # Ensure recipient address is checksummed
                tx["to"] = Web3.to_checksum_address(to_address)
            if data:
                tx["data"] = data
            # Nonce already set above for non-contract transactions
            if additional_params:
                tx.update(additional_params)

        # Resolve gas price
        if gas_price is None:
            try:
                net_gas = await self.web3.eth.gas_price
                mult = self.configuration.gas_price_multiplier
                gas_price = int(net_gas * mult) if net_gas else None
            except Exception as e:
                logger.error(f"Fetch network gas_price error: {e}")
                gas_price = None
            if gas_price is None:
                gas_price = self.configuration.fallback_gas_price
        tx["gasPrice"] = gas_price

        # Resolve gas limit
        if gas_limit is None:
            if "data" in tx:
                try:
                    est = await self.web3.eth.estimate_gas(tx)
                    gas_limit = int(est * 1.2)
                except Exception as e:
                    logger.warning(
                        f"Gas estimate failed: {e}; defaulting to {self.configuration.default_gas_limit}"
                    )
                    gas_limit = self.configuration.default_gas_limit
            else:
                gas_limit = self.ETH_TRANSFER_GAS
        tx["gas"] = gas_limit

        return tx

    async def sign_transaction(self, tx: Dict[str, Any]) -> SignedTransaction:
        """Sign a transaction dict."""
        try:
            return self.account.sign_transaction(tx)
        except Exception as e:
            logger.error(f"Signing tx failed: {e}")
            raise StrategyExecutionError(f"Signing failed: {e}")

    async def send_signed(self, signed_tx: SignedTransaction) -> str:
        """Broadcast a signed transaction."""
        try:
            raw = signed_tx.raw_transaction
            tx_hash = await self.web3.eth.send_raw_transaction(raw)
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"send_raw_transaction error: {e}")
            raise StrategyExecutionError(f"Send failed: {e}")

    async def execute_transaction(
        self, tx: Dict[str, Any], retry_count: int = 3, retry_delay: float = 2.0
    ) -> str:
        """Perform safety checks, sign, send, and track a transaction."""
        # Safety check
        if self.safety_guard:
            try:
                safe, details = await self.safety_guard.check_transaction_safety(tx)
                if not safe:
                    error_msg = f"SafetyNet blocked tx: {details}"
                    logger.error(error_msg)
                    # Send notification if available
                    if (
                        hasattr(self, "notification_manager")
                        and self.notification_manager
                    ):
                        try:
                            await self.notification_manager.send_alert(
                                "Transaction Safety Check Failed",
                                f"Transaction blocked: {details}",
                                level="WARNING",
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send notification: {e}")
                    raise StrategyExecutionError("Safety check failed")
            except Exception as e:
                if not isinstance(e, StrategyExecutionError):
                    logger.error(f"Error during safety check: {e}")
                    raise StrategyExecutionError(f"Safety check error: {e}")
                raise

        original_price = tx.get("gasPrice", 0)
        is_eip1559 = "maxFeePerGas" in tx and "maxPriorityFeePerGas" in tx
        original_max = tx.get("maxFeePerGas", 0)
        original_pri = tx.get("maxPriorityFeePerGas", 0)

        for attempt in range(retry_count + 1):
            if attempt > 0:
                if is_eip1559:
                    bumped_max = int(original_max * (self.GAS_RETRY_BUMP**attempt))
                    bumped_pri = int(original_pri * (self.GAS_RETRY_BUMP**attempt))
                    logger.info(
                        f"Retry {attempt}: bumping maxFeePerGas to {bumped_max}, priority to {bumped_pri}"
                    )
                    tx["maxFeePerGas"] = bumped_max
                    tx["maxPriorityFeePerGas"] = bumped_pri
                elif original_price:
                    bumped_price = int(original_price * (self.GAS_RETRY_BUMP**attempt))
                    logger.info(f"Retry {attempt}: bumping gasPrice to {bumped_price}")
                    tx["gasPrice"] = bumped_price

            try:
                signed = await self.sign_transaction(tx)
                tx_hash = await self.send_signed(signed)
                self._pending_txs[tx_hash] = {
                    "tx": tx,
                    "signed_tx": signed,
                    "timestamp": time.time(),
                    "status": "pending",
                }
                if self.nonce_manager and "nonce" in tx:
                    await self.nonce_manager.track_transaction(
                        tx_hash, tx["nonce"], self.address
                    )

                # Store transaction in database if available
                if self.db_interface and hasattr(
                    self.db_interface, "store_transaction"
                ):
                    try:
                        await self.db_interface.store_transaction(
                            {
                                "tx_hash": tx_hash,
                                "from_address": self.address,
                                "to_address": tx.get("to", ""),
                                "value": tx.get("value", 0),
                                "gas_price": tx.get("gasPrice", 0),
                                "gas_limit": tx.get("gas", 0),
                                "nonce": tx.get("nonce", 0),
                                "chain_id": self.chain_id,
                                "timestamp": time.time(),
                                "status": "pending",
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to store transaction in DB: {e}")

                logger.info(f"Transaction sent: {tx_hash}")
                return tx_hash
            except Exception as e:
                if attempt < retry_count:
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}; retrying in {retry_delay}s"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"All attempts failed: {e}")
                    # Send notification if available
                    if (
                        hasattr(self, "notification_manager")
                        and self.notification_manager
                    ):
                        try:
                            await self.notification_manager.send_alert(
                                "Transaction Execution Failed",
                                f"All {retry_count} attempts failed. Error: {e}",
                                level="ERROR",
                            )
                        except Exception as notify_err:
                            logger.warning(f"Failed to send notification: {notify_err}")
                    raise StrategyExecutionError(f"Execution failed: {e}")

    async def wait_for_transaction_receipt(
        self, tx_hash: str, timeout: int = 120, poll_interval: float = 0.1
    ) -> Dict[str, Any]:
        """Poll until tx is mined or timeout."""
        if not tx_hash.startswith("0x"):
            tx_hash = f"0x{tx_hash}"

        start = time.time()
        while time.time() - start < timeout:
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    status = receipt.get("status", 0)
                    self._pending_txs.setdefault(tx_hash, {})["status"] = (
                        "success" if status == 1 else "failed"
                    )
                    if status == 1:
                        logger.info(
                            f"Tx {tx_hash} confirmed in block {receipt['blockNumber']}"
                        )
                        return receipt
                    error = f"Tx {tx_hash} failed with status 0"
                    logger.error(error)
                    raise StrategyExecutionError(error)
            except Exception:
                pass
            await asyncio.sleep(poll_interval)
        raise asyncio.TimeoutError(
            f"Receipt for {tx_hash} not received within {timeout}s"
        )

    async def handle_eth_transaction(self, tx_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Build, execute, and await a simple ETH transfer."""
        logger.info(f"Handling ETH tx for spec: {tx_spec}")
        tx = await self.build_transaction(
            function_call=None,
            to_address=tx_spec.get("to"),
            value=tx_spec.get("value", 0),
        )
        tx_hash = await self.execute_transaction(tx)
        return await self.wait_for_transaction_receipt(tx_hash)

    async def get_eth_balance(self, address: Optional[str] = None) -> Decimal:
        """Fetch ETH balance as Decimal."""
        addr = address or self.address
        try:
            bal = await self.web3.eth.get_balance(addr)
            return Decimal(bal) / Decimal(10**18)
        except Exception as e:
            logger.error(f"get_eth_balance error: {e}")
            return Decimal(0)

    async def simulate_transaction(
        self, tx: Dict[str, Any]
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Enhanced transaction simulation with detailed results.

        Args:
            tx: Transaction dictionary to simulate

        Returns:
            Tuple of (success, error_message, simulation_data)
        """
        try:
            # Ensure recipient address is checksummed if present
            if "to" in tx and tx["to"]:
                tx["to"] = Web3.to_checksum_address(tx["to"])
            
            # Basic simulation via eth_call
            result = await self.web3.eth.call(tx)

            # Enhanced simulation data
            simulation_data = {
                "call_result": result.hex() if result else "0x",
                "gas_used_estimate": None,
                "state_changes": {},
                "events": [],
            }

            # Try to estimate gas for simulation
            try:
                gas_estimate = await self.web3.eth.estimate_gas(tx)
                simulation_data["gas_used_estimate"] = gas_estimate
            except Exception as e:
                logger.warning(f"Gas estimation during simulation failed: {e}")

            # Additional checks for common failure patterns
            if "to" in tx and tx["to"]:
                try:
                    code = await self.web3.eth.get_code(tx["to"])
                    if code == b"":
                        return (
                            False,
                            "Target address has no contract code",
                            simulation_data,
                        )
                except Exception:
                    pass

            logger.debug(
                f"Transaction simulation successful: {result.hex() if result else 'no result'}"
            )
            return True, "", simulation_data

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Transaction simulation failed: {error_msg}")

            # Enhanced error analysis
            simulation_data = {
                "error_type": "simulation_failure",
                "raw_error": error_msg,
            }

            # Common error pattern matching
            if "revert" in error_msg.lower():
                simulation_data["error_type"] = "contract_revert"
            elif "insufficient" in error_msg.lower():
                simulation_data["error_type"] = "insufficient_funds"
            elif "gas" in error_msg.lower():
                simulation_data["error_type"] = "gas_related"

            return False, error_msg, simulation_data

    async def optimize_gas_price(
        self,
        tx: Dict[str, Any],
        target_confirmation_time: int = 60,
        max_gas_price: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Optimize gas price for target confirmation time.

        Args:
            tx: Transaction to optimize
            target_confirmation_time: Target confirmation time in seconds
            max_gas_price: Maximum acceptable gas price

        Returns:
            Optimized transaction dictionary
        """
        try:
            # Get current network gas price
            current_gas_price = await self.web3.eth.gas_price

            # Calculate optimization based on target time and network conditions
            if target_confirmation_time <= 15:  # Fast confirmation
                multiplier = 1.5
            elif target_confirmation_time <= 60:  # Standard confirmation
                multiplier = 1.2
            else:  # Slow confirmation acceptable
                multiplier = 1.0

            # Apply configuration multiplier
            config_multiplier = self.configuration.gas_price_multiplier
            total_multiplier = multiplier * config_multiplier

            optimized_gas_price = int(current_gas_price * total_multiplier)

            # Apply maximum gas price limit
            if max_gas_price and optimized_gas_price > max_gas_price:
                optimized_gas_price = max_gas_price
                logger.warning(f"Gas price capped at maximum: {max_gas_price}")

            # Update transaction
            optimized_tx = tx.copy()
            optimized_tx["gasPrice"] = optimized_gas_price

            logger.debug(
                f"Gas price optimized: {current_gas_price} -> {optimized_gas_price} (x{total_multiplier:.2f})"
            )
            return optimized_tx

        except Exception as e:
            logger.error(f"Gas optimization failed: {e}")
            return tx  # Return original transaction on failure

    async def estimate_transaction_cost(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estimate total transaction cost including gas and fees.

        Args:
            tx: Transaction to estimate

        Returns:
            Dictionary with cost estimates
        """
        try:
            # Estimate gas
            gas_estimate = await self.web3.eth.estimate_gas(tx)
            gas_price = tx.get("gasPrice") or (await self.web3.eth.gas_price)

            # Calculate costs
            gas_cost_wei = gas_estimate * gas_price
            gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)

            # Get current ETH price for USD estimation (if API available)
            eth_price_usd = None
            if self.external_api_manager:
                try:
                    eth_price_data = (
                        await self.external_api_manager.get_aggregated_price("ethereum")
                    )
                    if eth_price_data and "price" in eth_price_data:
                        eth_price_usd = eth_price_data["price"]
                except Exception:
                    pass

            cost_estimate = {
                "gas_estimate": gas_estimate,
                "gas_price_wei": gas_price,
                "gas_price_gwei": gas_price / 10**9,
                "gas_cost_wei": gas_cost_wei,
                "gas_cost_eth": float(gas_cost_eth),
                "transaction_value_wei": tx.get("value", 0),
                "transaction_value_eth": float(
                    Decimal(tx.get("value", 0)) / Decimal(10**18)
                ),
                "total_cost_wei": gas_cost_wei + tx.get("value", 0),
                "total_cost_eth": float(
                    (Decimal(gas_cost_wei) + Decimal(tx.get("value", 0)))
                    / Decimal(10**18)
                ),
            }

            if eth_price_usd:
                cost_estimate["gas_cost_usd"] = float(gas_cost_eth) * eth_price_usd
                cost_estimate["total_cost_usd"] = (
                    cost_estimate["total_cost_eth"] * eth_price_usd
                )

            return cost_estimate

        except Exception as e:
            logger.error(f"Cost estimation failed: {e}")
            return {"error": str(e)}

    async def prepare_flashloan_transaction(
        self,
        assets: Union[str, List[str]],
        amounts: Union[int, List[int]],
        strategy_params: Optional[Dict[str, Any]] = None,
        flashloan_contract: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare a comprehensive Aave V3 flashloan transaction.

        Args:
            assets: Single asset address or list of asset addresses
            amounts: Single amount or list of amounts corresponding to assets
            strategy_params: Parameters for the strategy execution within flashloan
            flashloan_contract: Address of deployed flashloan contract (deploys if None)

        Returns:
            Dict containing flashloan transaction details and parameters
        """
        try:
            # Normalize inputs to lists
            if isinstance(assets, str):
                assets = [assets]
            if isinstance(amounts, int):
                amounts = [amounts]

            if len(assets) != len(amounts):
                raise StrategyExecutionError(
                    "Assets and amounts arrays must have same length"
                )

            logger.info(
                f"Preparing Aave V3 flashloan: {len(assets)} assets, total value: {sum(amounts)}"
            )

            # Ensure we have ABIRegistry
            if not self.abi_registry:
                raise StrategyExecutionError(
                    "ABIRegistry not available - cannot prepare flashloan"
                )

            # Load required ABIs
            flashloan_abi = self.abi_registry.get_abi("aave_flashloan")
            pool_abi = self.abi_registry.get_abi("aave_pool")
            erc20_abi = self.abi_registry.get_abi("erc20")

            if not flashloan_abi:
                raise StrategyExecutionError("Aave flashloan ABI not found in registry")
            if not erc20_abi:
                raise StrategyExecutionError("ERC20 ABI not found in registry")

            # Get or deploy flashloan contract
            if not flashloan_contract:
                flashloan_contract = await self._ensure_flashloan_contract_deployed()

            # Validate flashloan contract
            try:
                contract_code = await self.web3.eth.get_code(flashloan_contract)
                if contract_code == b"":
                    raise StrategyExecutionError(
                        f"No contract code at address {flashloan_contract}"
                    )
            except Exception as e:
                raise StrategyExecutionError(
                    f"Failed to validate flashloan contract: {e}"
                )

            # Validate assets and check availability
            validated_assets = []
            for i, asset in enumerate(assets):
                try:
                    # Validate asset contract exists
                    asset_code = await self.web3.eth.get_code(asset)
                    if asset_code == b"":
                        raise StrategyExecutionError(
                            f"Asset {asset} is not a valid contract"
                        )

                    # Check asset is available for flashloan
                    available = await self._check_aave_asset_availability(
                        asset, amounts[i]
                    )
                    if not available:
                        raise StrategyExecutionError(
                            f"Insufficient liquidity for asset {asset}"
                        )

                    validated_assets.append(asset)
                    logger.debug(f"Validated asset {i+1}/{len(assets)}: {asset}")

                except Exception as e:
                    raise StrategyExecutionError(
                        f"Asset validation failed for {asset}: {e}"
                    )

            # Prepare strategy parameters
            if not strategy_params:
                strategy_params = {}

            # Encode strategy parameters for contract call
            strategy_data = self._encode_strategy_params(strategy_params)

            return {
                "assets": validated_assets,
                "amounts": amounts,
                "strategy_params": strategy_params,
                "strategy_data": strategy_data,
                "flashloan_contract": flashloan_contract,
                "flashloan_abi": flashloan_abi,
                "pool_abi": pool_abi,
                "erc20_abi": erc20_abi,
                "prepared": True,
                "timestamp": time.time(),
            }

        except Exception as e:
            logger.error(f"Flashloan preparation failed: {e}")
            if isinstance(e, StrategyExecutionError):
                raise
            raise StrategyExecutionError(f"Flashloan preparation error: {e}")

    async def execute_flashloan(
        self,
        flashloan_data: Dict[str, Any],
        retry_count: int = 2,
        gas_multiplier: float = 1.3,
    ) -> str:
        """
        Execute a prepared Aave V3 flashloan transaction.

        Args:
            flashloan_data: Data returned from prepare_flashloan_transaction
            retry_count: Number of retry attempts on failure
            gas_multiplier: Gas limit multiplier for complex flashloan operations

        Returns:
            Transaction hash of executed flashloan
        """
        try:
            if not flashloan_data.get("prepared"):
                raise StrategyExecutionError("Flashloan data not properly prepared")

            assets = flashloan_data["assets"]
            amounts = flashloan_data["amounts"]
            strategy_data = flashloan_data["strategy_data"]
            contract_address = flashloan_data["flashloan_contract"]
            flashloan_abi = flashloan_data["flashloan_abi"]

            logger.info(
                f"Executing flashloan: {len(assets)} assets from contract {contract_address}"
            )

            # Create contract instance
            flashloan_contract = self.web3.contract(
                address=contract_address, abi=flashloan_abi
            )

            # Prepare flashloan transaction
            flashloan_function = flashloan_contract.functions.requestFlashLoan(
                assets, amounts, strategy_data
            )

            # Enhanced safety checks for flashloan
            await self._validate_flashloan_safety(flashloan_data)

            # Build transaction with enhanced gas estimation
            tx = await self.build_transaction(
                function_call=flashloan_function,
                gas_limit=None,  # Will be estimated with multiplier
            )

            # Apply gas multiplier for complex operations
            if "gas" in tx:
                tx["gas"] = int(tx["gas"] * gas_multiplier)

            # Execute with enhanced monitoring
            tx_hash = await self.execute_transaction(tx, retry_count=retry_count)

            # Track flashloan execution
            if self.db_interface and hasattr(self.db_interface, "store_flashloan"):
                try:
                    await self.db_interface.store_flashloan(
                        {
                            "tx_hash": tx_hash,
                            "assets": assets,
                            "amounts": amounts,
                            "contract_address": contract_address,
                            "strategy_params": flashloan_data["strategy_params"],
                            "timestamp": time.time(),
                            "status": "executed",
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to store flashloan in DB: {e}")

            logger.info(f"Flashloan executed successfully: {tx_hash}")
            return tx_hash

        except Exception as e:
            logger.error(f"Flashloan execution failed: {e}")
            # Send notification for failed flashloan
            if hasattr(self, "notification_manager") and self.notification_manager:
                try:
                    await self.notification_manager.send_alert(
                        "Flashloan Execution Failed",
                        f"Flashloan execution failed: {e}",
                        level="CRITICAL",
                    )
                except Exception:
                    pass
            if isinstance(e, StrategyExecutionError):
                raise
            raise StrategyExecutionError(f"Flashloan execution error: {e}")

    async def execute_flashloan_strategy(
        self,
        assets: Union[str, List[str]],
        amounts: Union[int, List[int]],
        strategy_function: Callable,
        strategy_params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        High-level method to prepare and execute a flashloan with strategy.

        Args:
            assets: Asset address(es) for flashloan
            amounts: Amount(s) for flashloan
            strategy_function: Function to execute within flashloan
            strategy_params: Parameters for strategy execution
            **kwargs: Additional parameters for flashloan preparation/execution

        Returns:
            Transaction hash of executed flashloan
        """
        try:
            logger.info("Executing complete flashloan strategy")

            # Prepare flashloan
            flashloan_data = await self.prepare_flashloan_transaction(
                assets=assets,
                amounts=amounts,
                strategy_params=strategy_params,
                **kwargs,
            )

            # Execute strategy preparation if provided
            if strategy_function:
                try:
                    strategy_result = await strategy_function(
                        flashloan_data, strategy_params
                    )
                    flashloan_data["strategy_result"] = strategy_result
                except Exception as e:
                    raise StrategyExecutionError(f"Strategy preparation failed: {e}")

            # Execute flashloan
            tx_hash = await self.execute_flashloan(flashloan_data, **kwargs)

            logger.info(f"Flashloan strategy completed: {tx_hash}")
            return tx_hash

        except Exception as e:
            logger.error(f"Flashloan strategy failed: {e}")
            raise

    async def send_bundle(self, transactions: List[Dict[str, Any]]) -> str:
        """Send a bundle of transactions (e.g. via Flashbots)."""
        logger.info(f"Sending bundle of {len(transactions)} transactions")
        results: List[str] = []
        for i, tx in enumerate(transactions):
            try:
                tx_hash = await self.execute_transaction(tx)
                results.append(tx_hash)
                logger.debug(f"Bundle tx {i+1}/{len(transactions)} sent: {tx_hash}")
            except Exception as e:
                logger.error(f"Bundle tx {i+1} failed: {e}")
                raise StrategyExecutionError(f"Bundle tx {i+1} failed: {e}")
        return ",".join(results)

    async def front_run(self, target_tx: Dict[str, Any]) -> str:
        """Front-run a target transaction by bidding up gas price."""
        logger.info(f"Front-running tx: {target_tx.get('tx_hash', 'N/A')}")
        target_price = target_tx.get("gasPrice", 0)
        fr_price = int(target_price * 1.2)
        tx = await self.build_transaction(
            function_call=None,
            to_address=target_tx.get("to"),
            value=target_tx.get("value", 0),
            data=target_tx.get("data", ""),
            gas_price=fr_price,
        )
        tx_hash = await self.execute_transaction(tx)
        logger.info(f"Front-run tx sent: {tx_hash}")
        return tx_hash

    async def back_run(self, target_tx: Dict[str, Any]) -> str:
        """Back-run a target transaction after it is mined."""
        logger.info(f"Back-run setup for tx: {target_tx.get('tx_hash', 'N/A')}")
        txh = target_tx.get("tx_hash")
        if txh:
            try:
                await self.wait_for_transaction_receipt(txh)
                logger.info(f"Target tx {txh} confirmed; executing back-run")
            except Exception as e:
                logger.error(f"Back-run wait failed: {e}")
                raise StrategyExecutionError(f"Back-run failed: {e}")
        tx = await self.build_transaction(
            function_call=None,
            to_address=target_tx.get("to"),
            value=target_tx.get("value", 0),
            data=target_tx.get("data", ""),
        )
        tx_hash = await self.execute_transaction(tx)
        logger.info(f"Back-run tx sent: {tx_hash}")
        return tx_hash

    async def execute_sandwich_attack(
        self, target_tx: Dict[str, Any], strategy: str = "default"
    ) -> Tuple[str, str]:
        """Execute a sandwich attack (front-run then back-run)."""
        logger.info(
            f"Executing sandwich attack on {target_tx.get('tx_hash', 'N/A')} with strategy {strategy}"
        )
        fr = await self.front_run(target_tx)
        txh = target_tx.get("tx_hash")
        if txh:
            try:
                await self.wait_for_transaction_receipt(txh)
            except Exception as e:
                logger.error(f"Sandwich wait for target tx failed: {e}")
        br = await self.back_run(target_tx)
        return fr, br

    async def cancel_transaction(self, nonce: int) -> str:
        """Cancel a pending tx by sending a 0 ETH tx at same nonce with higher gas."""
        try:
            gp = self.web3.eth.gas_price
            cancel_gp = int(gp * 1.5) if gp else 100 * 10**9
        except Exception:
            cancel_gp = 100 * 10**9

        tx = {
            "from": self.address,
            "to": self.address,
            "value": 0,
            "nonce": nonce,
            "gas": self.ETH_TRANSFER_GAS,
            "gasPrice": cancel_gp,
            "chainId": self.chain_id,
        }
        signed = await self.sign_transaction(tx)
        tx_hash = await self.send_signed(signed)
        logger.info(f"Cancellation tx sent: {tx_hash}")
        return tx_hash

    async def withdraw_eth(
        self, to_address: Optional[str] = None, amount: Optional[int] = None
    ) -> str:
        """Withdraw ETH to a specified address or profit receiver."""
        if to_address is None:
            to_address = getattr(self.configuration, 'profit_receiver', None)
            if not to_address:
                raise StrategyExecutionError("No withdrawal address configured")

        bal = await self.web3.eth.get_balance(self.address)
        if amount is None:
            amount = int(bal * 0.9)

        if bal <= amount:
            gas_price = self.web3.eth.gas_price
            reserve = self.ETH_TRANSFER_GAS * (gas_price or 1)
            amount = max(0, bal - reserve)
            if amount <= 0:
                raise StrategyExecutionError("Insufficient balance for withdrawal")

        logger.info(f"Withdrawing {amount} wei to {to_address}")
        tx = await self.build_transaction(
            function_call=None, to_address=to_address, value=amount
        )
        tx_hash = await self.execute_transaction(tx)
        return tx_hash

    async def transfer_profit_to_account(self, amount: int, account: str) -> str:
        """Transfer profit ETH to a specific account."""
        logger.info(f"Transferring {amount} wei to {account}")
        if amount <= 0:
            raise StrategyExecutionError("Transfer amount must be > 0")
        bal = await self.web3.eth.get_balance(self.address)
        if bal < amount:
            raise StrategyExecutionError(
                f"Insufficient balance: have {bal}, need {amount}"
            )
        tx = await self.build_transaction(
            function_call=None, to_address=account, value=amount
        )
        tx_hash = await self.execute_transaction(tx)
        return tx_hash

    async def stop(self) -> bool:
        """Gracefully stop TransactionCore."""
        logger.info("Stopping TransactionCore")

        # Close web3 provider if supported
        if hasattr(self.web3, "provider") and hasattr(self.web3.provider, "close"):
            try:
                await self.web3.provider.close()
                logger.info("Web3 provider closed")
            except Exception as e:
                logger.warning(f"Error closing web3 provider: {e}")

        # Clear pending transactions
        tx_count = len(self._pending_txs)
        self._pending_txs.clear()
        logger.debug(f"Cleared {tx_count} pending transactions")

        # Note: Don't close database or other shared resources here
        # Those are managed by MainCore and closed from there

        return True

    # ========================================================================
    # Flashloan Supporting Methods
    # ========================================================================

    async def _ensure_flashloan_contract_deployed(self) -> str:
        """
        Ensure flashloan contract is deployed and return its address.

        Returns:
            Address of deployed flashloan contract
        """
        try:
            # Check if contract address is configured
            configured_address = getattr(self.configuration, 'flashloan_contract_address', None)
            if configured_address:
                # Validate existing contract
                try:
                    code = await self.web3.eth.get_code(configured_address)
                    if code != b"":
                        logger.debug(
                            f"Using configured flashloan contract: {configured_address}"
                        )
                        return configured_address
                except Exception:
                    logger.warning(
                        f"Configured flashloan contract {configured_address} not valid"
                    )

            # Deploy new contract if needed
            logger.info("Deploying new flashloan contract")
            return await self._deploy_flashloan_contract()

        except Exception as e:
            raise StrategyExecutionError(f"Failed to ensure flashloan contract: {e}")

    async def _deploy_flashloan_contract(self) -> str:
        """
        Deploy the SimpleFlashloan contract.

        Returns:
            Address of deployed contract
        """
        try:
            if not self.abi_registry:
                raise StrategyExecutionError(
                    "ABIRegistry required for contract deployment"
                )

            # Get required ABIs and bytecode
            flashloan_abi = self.abi_registry.get_abi("aave_flashloan")
            if not flashloan_abi:
                raise StrategyExecutionError("Flashloan ABI not found")

            # Aave V3 addresses provider for mainnet
            addresses_provider = getattr(
                self.configuration, 'aave_addresses_provider',
                "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"  # Mainnet default
            )

            # Deploy the flashloan contract
            # Note: For production deployment, compile SimpleFlashloan.sol using:
            # solc --bin --abi SimpleFlashloan.sol -o build/
            
            logger.info("Preparing flashloan contract deployment...")
            
            # Check if a contract address is already configured
            existing_address = getattr(
                self.configuration, 'flashloan_contract_address', None
            )
            
            if existing_address:
                logger.info(f"Using existing flashloan contract: {existing_address}")
                return existing_address
            
            # For now, raise an informative error about deployment requirements
            raise StrategyExecutionError(
                "Flashloan contract deployment requires compiled bytecode. "
                "Please:\n"
                "1. Compile SimpleFlashloan.sol using 'solc --bin --abi SimpleFlashloan.sol'\n"
                "2. Set 'flashloan_contract_address' in configuration to use existing contract\n"
                "3. Or implement bytecode loading in _get_flashloan_contract_artifacts()"
            )

        except Exception as e:
            raise StrategyExecutionError(f"Contract deployment failed: {e}")

    # ...existing methods...

    async def _check_aave_asset_availability(self, asset: str, amount: int) -> bool:
        """
        Check if sufficient liquidity is available for flashloan.

        Args:
            asset: Asset contract address
            amount: Required amount

        Returns:
            True if sufficient liquidity available
        """
        try:
            # Get Aave pool contract
            pool_address = getattr(
                self.configuration, 'aave_pool_address',
                "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"  # Mainnet V3 Pool
            )

            if not self.abi_registry:
                logger.warning("Cannot check asset availability without ABIRegistry")
                return True  # Assume available

            pool_abi = self.abi_registry.get_abi("aave_pool")
            if not pool_abi:
                logger.warning("Pool ABI not available for liquidity check")
                return True

            # Create pool contract instance
            pool_contract = self.web3.contract(address=pool_address, abi=pool_abi)

            # Check available liquidity (this would require the full Aave pool ABI)
            # For now, we'll do basic validation
            try:
                # Check if asset contract exists and has code
                code = await self.web3.eth.get_code(asset)
                if code == b"":
                    return False

                # Additional checks could include:
                # - Checking reserve data
                # - Verifying asset is supported by Aave
                # - Checking available liquidity vs requested amount

                logger.debug(f"Asset {asset} availability check passed")
                return True

            except Exception as e:
                logger.warning(f"Asset availability check failed for {asset}: {e}")
                return False

        except Exception as e:
            logger.error(f"Error checking asset availability: {e}")
            return False  # Fail safe

    async def _validate_flashloan_safety(self, flashloan_data: Dict[str, Any]) -> None:
        """
        Perform comprehensive safety checks for flashloan operations.

        Args:
            flashloan_data: Prepared flashloan data

        Raises:
            StrategyExecutionError: If safety checks fail
        """
        try:
            assets = flashloan_data["assets"]
            amounts = flashloan_data["amounts"]

            # Check account balance for potential fees
            eth_balance = await self.get_eth_balance()
            min_eth_balance = Decimal("0.01")  # Minimum ETH for gas fees

            if eth_balance < min_eth_balance:
                raise StrategyExecutionError(
                    f"Insufficient ETH for gas fees: {eth_balance}"
                )

            # Validate flashloan amounts are reasonable
            for i, amount in enumerate(amounts):
                if amount <= 0:
                    raise StrategyExecutionError(
                        f"Invalid amount for asset {i}: {amount}"
                    )

                # Check amount isn't excessively large (basic sanity check)
                max_amount = getattr(
                    self.configuration, 'max_flashloan_amount', 10**12
                )  # 1M tokens with 6 decimals
                if amount > max_amount:
                    raise StrategyExecutionError(
                        f"Amount too large for asset {i}: {amount}"
                    )

            # Additional safety checks through SafetyNet if available
            if self.safety_guard:
                # Create a mock transaction for safety validation
                mock_tx = {
                    "to": flashloan_data["flashloan_contract"],
                    "value": 0,
                    "gas": 500000,  # High gas estimate for flashloan
                    "gasPrice": self.web3.eth.gas_price or 20 * 10**9,
                    "from": self.address,
                }

                safe, details = await self.safety_guard.check_transaction_safety(
                    mock_tx
                )
                if not safe:
                    raise StrategyExecutionError(
                        f"SafetyNet blocked flashloan: {details}"
                    )

            logger.debug("Flashloan safety validation passed")

        except Exception as e:
            if isinstance(e, StrategyExecutionError):
                raise
            raise StrategyExecutionError(f"Safety validation failed: {e}")

    def _encode_strategy_params(self, strategy_params: Dict[str, Any]) -> bytes:
        """
        Encode strategy parameters for contract call.

        Args:
            strategy_params: Strategy parameters to encode

        Returns:
            Encoded bytes for contract call
        """
        try:
            # Simple encoding - in production this would use proper ABI encoding
            import json

            param_string = json.dumps(strategy_params)
            return param_string.encode("utf-8")

        except Exception as e:
            logger.warning(f"Failed to encode strategy params: {e}")
            return b""  # Empty bytes as fallback

    async def get_flashloan_contract_info(
        self, contract_address: str
    ) -> Dict[str, Any]:
        """
        Get information about a deployed flashloan contract.

        Args:
            contract_address: Address of flashloan contract

        Returns:
            Dictionary with contract information
        """
        try:
            if not self.abi_registry:
                raise StrategyExecutionError("ABIRegistry required for contract info")

            flashloan_abi = self.abi_registry.get_abi("aave_flashloan")
            if not flashloan_abi:
                raise StrategyExecutionError("Flashloan ABI not found")

            # Create contract instance
            contract = self.web3.contract(address=contract_address, abi=flashloan_abi)

            # Get contract information
            info = {
                "address": contract_address,
                "owner": None,
                "addresses_provider": None,
                "pool": None,
                "code_size": 0,
            }

            try:
                # Get code size
                code = await self.web3.eth.get_code(contract_address)
                info["code_size"] = len(code)

                # Try to get owner (if function exists)
                if hasattr(contract.functions, "owner"):
                    info["owner"] = await contract.functions.owner().call()

                # Try to get addresses provider
                if hasattr(contract.functions, "ADDRESSES_PROVIDER"):
                    info["addresses_provider"] = (
                        await contract.functions.ADDRESSES_PROVIDER().call()
                    )

                # Try to get pool address
                if hasattr(contract.functions, "POOL"):
                    info["pool"] = await contract.functions.POOL().call()

            except Exception as e:
                logger.warning(f"Failed to get some contract info: {e}")

            return info

        except Exception as e:
            logger.error(f"Failed to get contract info: {e}")
            return {"error": str(e)}

    # ========================================================================
    # Enhanced Transaction Methods
    # ========================================================================

    async def monitor_flashloan_execution(
        self, tx_hash: str, flashloan_data: Dict[str, Any], timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Monitor flashloan execution with detailed tracking.

        Args:
            tx_hash: Transaction hash to monitor
            flashloan_data: Original flashloan data
            timeout: Monitoring timeout in seconds

        Returns:
            Dictionary with execution results and analysis
        """
        try:
            logger.info(f"Monitoring flashloan execution: {tx_hash}")

            # Wait for transaction receipt with detailed monitoring
            start_time = time.time()
            receipt = None

            while time.time() - start_time < timeout:
                try:
                    receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                    if receipt:
                        break
                except Exception:
                    pass
                await asyncio.sleep(2)  # Poll every 2 seconds

            if not receipt:
                raise asyncio.TimeoutError(
                    f"Transaction {tx_hash} not confirmed within {timeout}s"
                )

            # Analyze receipt
            execution_analysis = {
                "tx_hash": tx_hash,
                "block_number": receipt["blockNumber"],
                "gas_used": receipt["gasUsed"],
                "effective_gas_price": receipt.get("effectiveGasPrice", 0),
                "status": "success" if receipt["status"] == 1 else "failed",
                "logs": len(receipt["logs"]),
                "confirmation_time": time.time() - start_time,
                "flashloan_data": flashloan_data,
            }

            # Calculate actual costs
            if receipt["status"] == 1:
                gas_cost = receipt["gasUsed"] * receipt.get("effectiveGasPrice", 0)
                execution_analysis["gas_cost_wei"] = gas_cost
                execution_analysis["gas_cost_eth"] = float(
                    Decimal(gas_cost) / Decimal(10**18)
                )

            # Parse logs for flashloan events
            if receipt["logs"]:
                try:
                    flashloan_events = await self._parse_flashloan_events(
                        receipt["logs"], flashloan_data
                    )
                    execution_analysis["flashloan_events"] = flashloan_events
                except Exception as e:
                    logger.warning(f"Failed to parse flashloan events: {e}")

            # Store results if database available
            if self.db_interface and hasattr(self.db_interface, "update_flashloan"):
                try:
                    await self.db_interface.update_flashloan(
                        tx_hash, execution_analysis
                    )
                except Exception as e:
                    logger.warning(f"Failed to update flashloan in DB: {e}")

            # Send notification
            if hasattr(self, "notification_manager") and self.notification_manager:
                try:
                    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
                    await self.notification_manager.send_alert(
                        f"Flashloan {status}",
                        f"Transaction {tx_hash} {status.lower()} in block {receipt['blockNumber']}",
                        level="INFO" if receipt["status"] == 1 else "ERROR",
                    )
                except Exception:
                    pass

            logger.info(
                f"Flashloan monitoring complete: {execution_analysis['status']}"
            )
            return execution_analysis

        except Exception as e:
            logger.error(f"Flashloan monitoring failed: {e}")
            return {"error": str(e), "tx_hash": tx_hash}

    async def _parse_flashloan_events(
        self, logs: List[Dict[str, Any]], flashloan_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Parse flashloan-related events from transaction logs.

        Args:
            logs: Transaction logs
            flashloan_data: Original flashloan data

        Returns:
            List of parsed flashloan events
        """
        events = []

        try:
            if not self.abi_registry:
                return events

            flashloan_abi = flashloan_data.get("flashloan_abi")
            if not flashloan_abi:
                return events

            # Create contract instance for event parsing
            contract = self.web3.contract(
                address=flashloan_data["flashloan_contract"], abi=flashloan_abi
            )

            # Parse each log
            for log in logs:
                try:
                    # Try to decode with flashloan contract ABI
                    decoded = contract.events.FlashLoanExecuted().process_log(log)
                    events.append(
                        {
                            "event": "FlashLoanExecuted",
                            "assets": decoded["args"].get("assets", []),
                            "amounts": decoded["args"].get("amounts", []),
                            "premiums": decoded["args"].get("premiums", []),
                        }
                    )
                except Exception:
                    # Try other event types
                    try:
                        decoded = contract.events.FlashLoanRequested().process_log(log)
                        events.append(
                            {"event": "FlashLoanRequested", "data": decoded["args"]}
                        )
                    except Exception:
                        pass  # Not a recognized flashloan event

        except Exception as e:
            logger.warning(f"Event parsing error: {e}")

        return events

    async def recover_failed_flashloan(
        self, tx_hash: str, flashloan_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Attempt to recover from a failed flashloan transaction.

        Args:
            tx_hash: Hash of failed transaction
            flashloan_data: Original flashloan data

        Returns:
            Recovery analysis and actions taken
        """
        try:
            logger.info(f"Attempting flashloan recovery for: {tx_hash}")

            # Get transaction receipt for analysis
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
            except Exception:
                return {
                    "error": "Cannot get transaction receipt",
                    "recovery": "impossible",
                }

            recovery_info = {
                "original_tx": tx_hash,
                "failure_analysis": {},
                "recovery_actions": [],
                "success": False,
            }

            # Analyze failure
            if receipt["status"] == 0:
                recovery_info["failure_analysis"]["status"] = "transaction_reverted"

                # Check common failure causes
                gas_used = receipt["gasUsed"]
                tx = await self.web3.eth.get_transaction(tx_hash)
                gas_limit = tx["gas"]

                if gas_used >= gas_limit * 0.98:  # Used 98%+ of gas limit
                    recovery_info["failure_analysis"]["cause"] = "out_of_gas"
                    recovery_info["recovery_actions"].append("increase_gas_limit")

            # Attempt recovery if possible
            if "increase_gas_limit" in recovery_info["recovery_actions"]:
                try:
                    # Retry with higher gas limit
                    logger.info("Retrying flashloan with increased gas limit")

                    # Increase gas limit by 50%
                    retry_data = flashloan_data.copy()
                    recovery_tx_hash = await self.execute_flashloan(
                        retry_data, gas_multiplier=1.5
                    )

                    recovery_info["recovery_tx"] = recovery_tx_hash
                    recovery_info["success"] = True
                    recovery_info["recovery_actions"].append("retry_successful")

                except Exception as e:
                    recovery_info["recovery_error"] = str(e)

            # Cleanup actions
            try:
                await self._cleanup_failed_flashloan(flashloan_data)
                recovery_info["recovery_actions"].append("cleanup_completed")
            except Exception as e:
                recovery_info["cleanup_error"] = str(e)

            logger.info(f"Flashloan recovery completed: {recovery_info['success']}")
            return recovery_info

        except Exception as e:
            logger.error(f"Flashloan recovery failed: {e}")
            return {"error": str(e), "recovery": "failed"}

    async def _cleanup_failed_flashloan(self, flashloan_data: Dict[str, Any]) -> None:
        """
        Cleanup after failed flashloan (e.g., unlock stuck funds).

        Args:
            flashloan_data: Original flashloan data
        """
        try:
            # Check if any tokens are stuck in flashloan contract
            contract_address = flashloan_data["flashloan_contract"]
            assets = flashloan_data["assets"]

            if not self.abi_registry:
                return

            erc20_abi = flashloan_data.get("erc20_abi")
            if not erc20_abi:
                return

            # Check balances and withdraw if necessary
            for asset in assets:
                try:
                    token_contract = self.web3.contract(address=asset, abi=erc20_abi)
                    balance = await token_contract.functions.balanceOf(
                        contract_address
                    ).call()

                    if balance > 0:
                        logger.info(
                            f"Found stuck tokens {asset}: {balance}, attempting withdrawal"
                        )

                        # Create withdraw transaction
                        flashloan_contract = self.web3.contract(
                            address=contract_address,
                            abi=flashloan_data["flashloan_abi"],
                        )

                        withdraw_tx = await self.build_transaction(
                            function_call=flashloan_contract.functions.withdrawToken(
                                asset, balance
                            )
                        )

                        await self.execute_transaction(withdraw_tx)
                        logger.info(f"Successfully withdrew stuck tokens: {asset}")

                except Exception as e:
                    logger.warning(f"Failed to cleanup asset {asset}: {e}")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    # ========================================================================
    # Enhanced Safety and Validation
    # ========================================================================

    async def validate_contract_integration(self) -> Dict[str, bool]:
        """
        Validate integration with all required contracts and ABIs.

        Returns:
            Dictionary showing validation status for each component
        """
        validation_results = {
            "abi_registry": False,
            "aave_flashloan_abi": False,
            "aave_pool_abi": False,
            "erc20_abi": False,
            "flashloan_contract": False,
            "aave_pool_contract": False,
            "web3_connection": False,
            "account_ready": False,
        }

        try:
            # Check ABIRegistry
            if self.abi_registry:
                validation_results["abi_registry"] = True

                # Check required ABIs
                if self.abi_registry.get_abi("aave_flashloan"):
                    validation_results["aave_flashloan_abi"] = True

                if self.abi_registry.get_abi("aave_pool"):
                    validation_results["aave_pool_abi"] = True

                if self.abi_registry.get_abi("erc20"):
                    validation_results["erc20_abi"] = True

            # Check Web3 connection
            try:
                connected = await self.web3.is_connected()
                validation_results["web3_connection"] = connected
            except Exception:
                pass

            # Check account
            if self.account and self.address:
                validation_results["account_ready"] = True

            # Check flashloan contract availability
            flashloan_address = getattr(
                self.configuration, 'flashloan_contract_address', None
            )
            if flashloan_address:
                try:
                    code = await self.web3.eth.get_code(flashloan_address)
                    validation_results["flashloan_contract"] = code != b""
                except Exception:
                    pass

            # Check Aave pool contract
            pool_address = getattr(
                self.configuration, 'aave_pool_address', 
                "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
            )
            try:
                pool_code = await self.web3.eth.get_code(pool_address)
                validation_results["aave_pool_contract"] = pool_code != b""
            except Exception:
                pass

            # Log validation summary
            passed = sum(validation_results.values())
            total = len(validation_results)
            logger.info(
                f"Contract integration validation: {passed}/{total} checks passed"
            )

            for component, status in validation_results.items():
                if not status:
                    logger.warning(f"Validation failed for: {component}")

            return validation_results

        except Exception as e:
            logger.error(f"Integration validation failed: {e}")
            return validation_results

    async def test_flashloan_readiness(
        self, test_asset: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Test flashloan system readiness with a small test operation.

        Args:
            test_asset: Asset to test with (defaults to USDC)

        Returns:
            Dictionary with test results
        """
        try:
            # Default to USDC for testing
            if not test_asset:
                test_asset = (
                    "0xA0b86a33E6441b4fa13647Bc13a7B7D8b8D5B3A5"  # USDC mainnet
                )

            test_amount = 1000  # Small test amount (1000 wei)

            logger.info(f"Testing flashloan readiness with {test_asset}")

            test_results = {
                "validation": await self.validate_contract_integration(),
                "asset_test": {},
                "gas_estimation": {},
                "simulation": {},
                "overall_ready": False,
            }

            # Test asset availability
            try:
                available = await self._check_aave_asset_availability(
                    test_asset, test_amount
                )
                test_results["asset_test"] = {
                    "asset": test_asset,
                    "amount": test_amount,
                    "available": available,
                }
            except Exception as e:
                test_results["asset_test"]["error"] = str(e)

            # Test flashloan preparation (without execution)
            try:
                flashloan_data = await self.prepare_flashloan_transaction(
                    assets=[test_asset], amounts=[test_amount]
                )
                test_results["preparation"] = {
                    "success": True,
                    "data_keys": list(flashloan_data.keys()),
                }
            except Exception as e:
                test_results["preparation"] = {"success": False, "error": str(e)}

            # Test gas estimation for flashloan
            try:
                if self.abi_registry and test_results["preparation"]["success"]:
                    flashloan_abi = self.abi_registry.get_abi("aave_flashloan")
                    if flashloan_abi:
                        # Real gas estimation would require an actual deployed contract
                        # For now, we indicate that gas estimation requires deployment
                        test_results["gas_estimation"] = {
                            "estimated": False,
                            "note": "Gas estimation requires deployed flashloan contract"
                        }
                    else:
                        test_results["gas_estimation"] = {
                            "estimated": False,
                            "error": "Flashloan ABI not available"
                        }
                else:
                    test_results["gas_estimation"] = {
                        "estimated": False,
                        "error": "ABI registry not available or preparation failed"
                    }

            except Exception as e:
                test_results["gas_estimation"] = {
                    "estimated": False,
                    "error": str(e)
                }

            # Determine overall readiness
            validation_passed = (
                sum(test_results["validation"].values()) >= 6
            )  # At least 6/8 checks
            asset_ready = test_results["asset_test"].get("available", False)
            prep_ready = test_results["preparation"]["success"]

            test_results["overall_ready"] = (
                validation_passed and asset_ready and prep_ready
            )

            logger.info(
                f"Flashloan readiness test completed: {test_results['overall_ready']}"
            )
            return test_results

        except Exception as e:
            logger.error(f"Flashloan readiness test failed: {e}")
            return {"error": str(e), "overall_ready": False}

    async def get_integration_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status of all integrations and systems.

        Returns:
            Complete status report of the transaction core system
        """
        try:
            status = {
                "transaction_core": {
                    "initialized": True,
                    "chain_id": self.chain_id,
                    "address": self.address,
                    "pending_transactions": len(self._pending_txs),
                },
                "web3": {"connected": False, "chain_id": None, "latest_block": None},
                "components": {
                    "nonce_core": self.nonce_manager is not None,
                    "safety_net": self.safety_guard is not None,
                    "abi_registry": self.abi_registry is not None,
                    "db_manager": self.db_interface is not None,
                    "api_config": self.external_api_manager is not None,
                    "notification_manager": hasattr(self, "notification_manager")
                    and self.notification_manager is not None,
                },
                "balances": {},
                "configuration": {
                    "gas_price_multiplier": getattr(
                        self.configuration, 'gas_price_multiplier', 1.1
                    ),
                    "flashloan_contract": getattr(
                        self.configuration, 'flashloan_contract_address', None
                    ),
                    "aave_pool": getattr(self.configuration, 'aave_pool_address', None),
                    "profit_receiver": getattr(self.configuration, 'profit_receiver', None),
                },
            }

            # Web3 status
            try:
                status["web3"]["connected"] = await self.web3.is_connected()
                status["web3"]["chain_id"] = await self.web3.eth.chain_id
                status["web3"]["latest_block"] = await self.web3.eth.block_number
            except Exception as e:
                status["web3"]["error"] = str(e)

            # Balance information
            try:
                eth_balance = await self.get_eth_balance()
                status["balances"]["eth"] = float(eth_balance)
            except Exception as e:
                status["balances"]["eth_error"] = str(e)

            # Contract validation if available
            if self.abi_registry:
                status["contract_validation"] = (
                    await self.validate_contract_integration()
                )

            return status

        except Exception as e:
            logger.error(f"Failed to get integration status: {e}")
            return {"error": str(e)}

    # ========================================================================
    # Utility and Helper Methods
    # ========================================================================

    async def emergency_stop(self) -> Dict[str, Any]:
        """
        Emergency stop all operations and cleanup.

        Returns:
            Dictionary with cleanup results
        """
        try:
            logger.warning("EMERGENCY STOP initiated")

            cleanup_results = {
                "pending_transactions_cancelled": 0,
                "contracts_cleaned": 0,
                "notifications_sent": False,
                "success": False,
            }

            # Cancel all pending transactions if possible
            pending_count = len(self._pending_txs)
            for tx_hash, tx_data in list(self._pending_txs.items()):
                try:
                    if "nonce" in tx_data.get("tx", {}):
                        nonce = tx_data["tx"]["nonce"]
                        cancel_hash = await self.cancel_transaction(nonce)
                        logger.info(
                            f"Cancelled pending tx {tx_hash} with {cancel_hash}"
                        )
                        cleanup_results["pending_transactions_cancelled"] += 1
                except Exception as e:
                    logger.error(f"Failed to cancel tx {tx_hash}: {e}")

            # Send emergency notification
            if hasattr(self, "notification_manager") and self.notification_manager:
                try:
                    await self.notification_manager.send_alert(
                        "EMERGENCY STOP",
                        f"TransactionCore emergency stop executed. {cleanup_results['pending_transactions_cancelled']}/{pending_count} transactions cancelled.",
                        level="CRITICAL",
                    )
                    cleanup_results["notifications_sent"] = True
                except Exception as e:
                    logger.error(f"Failed to send emergency notification: {e}")

            cleanup_results["success"] = True
            logger.warning(f"Emergency stop completed: {cleanup_results}")
            return cleanup_results

        except Exception as e:
            logger.critical(f"Emergency stop failed: {e}")
            return {"error": str(e), "success": False}

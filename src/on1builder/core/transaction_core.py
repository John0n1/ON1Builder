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
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from eth_account import Account
from eth_account.datastructures import SignedTransaction
from web3 import AsyncWeb3

from on1builder.config.config import Configuration, APIConfig
from on1builder.core.nonce_core import NonceCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.utils.logger import setup_logging
from on1builder.utils.strategyexecutionerror import StrategyExecutionError

logger = setup_logging("TransactionCore", level="DEBUG")


class TransactionCore:
    """High-level helper for building, signing, simulating, and dispatching MEV-style transactions."""

    DEFAULT_GAS_LIMIT: int = 100_000
    ETH_TRANSFER_GAS: int = 21_000
    GAS_RETRY_BUMP: float = 1.15  # +15% per retry

    def __init__(
        self,
        web3: AsyncWeb3,
        account: Account,
        configuration: Configuration,
        api_config: Optional[APIConfig] = None,
        market_monitor: Optional[Any] = None,
        txpool_monitor: Optional[Any] = None,
        nonce_core: Optional[NonceCore] = None,
        safety_net: Optional[SafetyNet] = None,
        chain_id: int = 1,
    ) -> None:
        """Initialize the TransactionCore."""
        self.web3 = web3
        self.chain_id = chain_id
        self.account = account
        self.address = account.address
        self.configuration = configuration
        self.api_config = api_config or configuration.api_config
        self.market_monitor = market_monitor
        self.txpool_monitor = txpool_monitor
        self.nonce_core = nonce_core
        self.safety_net = safety_net

        self._pending_txs: Dict[str, Dict[str, Any]] = {}

        logger.debug(f"TransactionCore initialized for chain ID {chain_id}")

    async def initialize(self) -> bool:
        """Perform any async initialization logic."""
        logger.info("Initializing TransactionCore")
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
        # Resolve nonce
        if nonce is None and self.nonce_core:
            try:
                nonce = await self.nonce_core.get_next_nonce(self.address)
            except Exception as e:
                logger.error(f"NonceCore error: {e}")
                try:
                    nonce = await self.web3.eth.get_transaction_count(self.address)
                except Exception:
                    logger.error("Fallback to web3 nonce failed; using 0")
                    nonce = 0

        # Prepare base tx
        tx: Dict[str, Any] = {"from": self.address, "chainId": self.chain_id, "value": value}

        # Contract call vs raw tx
        if hasattr(function_call, "build_transaction"):
            params = {"from": self.address, "value": value, "chainId": self.chain_id}
            if nonce is not None:
                params["nonce"] = nonce
            if gas_price is not None:
                params["gasPrice"] = gas_price
            if additional_params:
                params.update(additional_params)
            try:
                tx = await function_call.build_transaction(params)
            except Exception as e:
                logger.error(f"Contract build_transaction error: {e}")
                raise StrategyExecutionError(f"Failed to build contract tx: {e}")
        else:
            if to_address:
                tx["to"] = to_address
            if data:
                tx["data"] = data
            if nonce is not None:
                tx["nonce"] = nonce
            if additional_params:
                tx.update(additional_params)

        # Resolve gas price
        if gas_price is None:
            try:
                net_gas = await self.web3.eth.gas_price
                mult = self.configuration.get("GAS_PRICE_MULTIPLIER", 1.1)
                gas_price = int(net_gas * mult) if net_gas else None
            except Exception as e:
                logger.error(f"Fetch network gas_price error: {e}")
            if gas_price is None:
                gas_price = self.configuration.get("FALLBACK_GAS_PRICE", 50 * 10**9)
        tx["gasPrice"] = gas_price

        # Resolve gas limit
        if gas_limit is None:
            if "data" in tx:
                try:
                    est = await self.web3.eth.estimate_gas(tx)
                    gas_limit = int(est * 1.2)
                except Exception as e:
                    logger.warning(f"Gas estimate failed: {e}; defaulting to {self.DEFAULT_GAS_LIMIT}")
                    gas_limit = self.configuration.get("DEFAULT_GAS_LIMIT", self.DEFAULT_GAS_LIMIT)
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
            raw = signed_tx.rawTransaction
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
        if self.safety_net:
            safe, details = await self.safety_net.check_transaction_safety(tx)
            if not safe:
                logger.error(f"SafetyNet blocked tx: {details}")
                raise StrategyExecutionError("Safety check failed")

        original_price = tx.get("gasPrice", 0)
        is_eip1559 = "maxFeePerGas" in tx and "maxPriorityFeePerGas" in tx
        original_max = tx.get("maxFeePerGas", 0)
        original_pri = tx.get("maxPriorityFeePerGas", 0)

        for attempt in range(retry_count + 1):
            if attempt > 0:
                if is_eip1559:
                    bumped_max = int(original_max * (self.GAS_RETRY_BUMP**attempt))
                    bumped_pri = int(original_pri * (self.GAS_RETRY_BUMP**attempt))
                    logger.info(f"Retry {attempt}: bumping maxFeePerGas to {bumped_max}, priority to {bumped_pri}")
                    tx["maxFeePerGas"] = bumped_max
                    tx["maxPriorityFeePerGas"] = bumped_pri
                elif original_price:
                    bumped_price = int(original_price * (self.GAS_RETRY_BUMP**attempt))
                    logger.info(f"Retry {attempt}: bumping gasPrice to {bumped_price}")
                    tx["gasPrice"] = bumped_price

            try:
                signed = await self.sign_transaction(tx)
                tx_hash = await self.send_signed(signed)
                self._pending_txs[tx_hash] = {"tx": tx, "signed_tx": signed, "timestamp": time.time(), "status": "pending"}
                if self.nonce_core and "nonce" in tx:
                    await self.nonce_core.track_transaction(tx_hash, tx["nonce"], self.address)
                logger.info(f"Transaction sent: {tx_hash}")
                return tx_hash
            except Exception as e:
                if attempt < retry_count:
                    logger.warning(f"Attempt {attempt + 1} failed: {e}; retrying in {retry_delay}s")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"All attempts failed: {e}")
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
                    self._pending_txs.setdefault(tx_hash, {})["status"] = "success" if status == 1 else "failed"
                    if status == 1:
                        logger.info(f"Tx {tx_hash} confirmed in block {receipt['blockNumber']}")
                        return receipt
                    error = f"Tx {tx_hash} failed with status 0"
                    logger.error(error)
                    raise StrategyExecutionError(error)
            except Exception:
                pass
            await asyncio.sleep(poll_interval)
        raise asyncio.TimeoutError(f"Receipt for {tx_hash} not received within {timeout}s")

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

    async def simulate_transaction(self, tx: Dict[str, Any]) -> Tuple[bool, str]:
        """Simulate a transaction via eth_call."""
        try:
            await self.web3.eth.call(tx)
            return True, ""
        except Exception as e:
            err = str(e)
            logger.warning(f"Simulation failed: {err}")
            return False, err

    async def prepare_flashloan_transaction(
        self, flashloan_asset: str, flashloan_amount: int
    ) -> Dict[str, Any]:
        """Prepare a flashloan transaction (placeholder)."""
        logger.info(f"Preparing flashloan: asset={flashloan_asset}, amount={flashloan_amount}")
        return {"flashloan_asset": flashloan_asset, "flashloan_amount": flashloan_amount, "prepared": True}

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
        logger.info(f"Executing sandwich attack on {target_tx.get('tx_hash', 'N/A')} with strategy {strategy}")
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
            gp = await self.web3.eth.gas_price
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
            to_address = self.configuration.get("PROFIT_RECEIVER")
            if not to_address:
                raise StrategyExecutionError("No withdrawal address configured")

        bal = await self.web3.eth.get_balance(self.address)
        if amount is None:
            amount = int(bal * 0.9)

        if bal <= amount:
            gas_price = await self.web3.eth.gas_price
            reserve = self.ETH_TRANSFER_GAS * (gas_price or 1)
            amount = max(0, bal - reserve)
            if amount <= 0:
                raise StrategyExecutionError("Insufficient balance for withdrawal")

        logger.info(f"Withdrawing {amount} wei to {to_address}")
        tx = await self.build_transaction(function_call=None, to_address=to_address, value=amount)
        tx_hash = await self.execute_transaction(tx)
        return tx_hash

    async def transfer_profit_to_account(self, amount: int, account: str) -> str:
        """Transfer profit ETH to a specific account."""
        logger.info(f"Transferring {amount} wei to {account}")
        if amount <= 0:
            raise StrategyExecutionError("Transfer amount must be > 0")
        bal = await self.web3.eth.get_balance(self.address)
        if bal < amount:
            raise StrategyExecutionError(f"Insufficient balance: have {bal}, need {amount}")
        tx = await self.build_transaction(function_call=None, to_address=account, value=amount)
        tx_hash = await self.execute_transaction(tx)
        return tx_hash

    async def stop(self) -> bool:
        """Gracefully stop TransactionCore."""
        logger.info("Stopping TransactionCore")
        if hasattr(self.web3, "provider") and hasattr(self.web3.provider, "close"):
            try:
                await self.web3.provider.close()
                logger.info("Web3 provider closed")
            except Exception as e:
                logger.warning(f"Error closing provider: {e}")
        self._pending_txs.clear()
        return True

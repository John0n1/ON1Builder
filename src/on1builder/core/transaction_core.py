# transaction_core.py
"""
ON1Builder – TransactionCore
============================
A high-level helper for building, signing, simulating and dispatching MEV-style transactions.
This module provides a set of functions to interact with Ethereum smart contracts, manage
transactions, and execute various strategies such as front-running, back-running, and sandwich attacks.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import time

from web3 import AsyncWeb3
from web3.exceptions import ContractLogicError, TransactionNotFound
from eth_account import Account

from on1builder.integrations.abi_registry import ABIRegistry
from on1builder.config.config import APIConfig, Configuration
from on1builder.core.nonce_core import NonceCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.utils.logger import setup_logging

# Use TYPE_CHECKING to prevent circular imports at runtime
if TYPE_CHECKING:
    from on1builder.monitoring.market_monitor import MarketMonitor
    from on1builder.monitoring.txpool_monitor import TxpoolMonitor

logger = setup_logging("TransactionCore", level="DEBUG")


class TransactionCore:
    """High-level helper for building, signing, simulating and dispatching MEV-style
    transactions."""

    DEFAULT_GAS_LIMIT: int = 100_000
    ETH_TRANSFER_GAS: int = 21_000
    GAS_RETRY_BUMP: float = 1.15        # +15 % per retry

    # --------------------------------------------------------------------- #
    # life-cycle                                                            #
    # --------------------------------------------------------------------- #

    def __init__(
        self,
        web3: AsyncWeb3,
        account: Account,
        configuration: Configuration,
        api_config: Optional[APIConfig] = None,
        market_monitor: Optional['MarketMonitor'] = None,
        txpool_monitor: Optional['TxpoolMonitor'] = None,
        nonce_core: Optional[NonceCore] = None,
        safety_net: Optional[SafetyNet] = None,
        gas_price_multiplier: float = 1.10,
    ) -> None:
        """Initialize transaction core."""
        self.web3 = web3
        self.account = account
        self.config = configuration
        self.api_config = api_config
        self.market_monitor = market_monitor
        self.txpool_monitor = txpool_monitor
        self.nonce_core = nonce_core
        self._safety_net = safety_net
        self.gas_price_multiplier = gas_price_multiplier
        
        # Contracts
        self.weth_contract = None
        self.usdc_contract = None
        self.usdt_contract = None
        self.uniswap_contract = None
        self.sushiswap_contract = None
        self.aave_pool_contract = None
        self.aave_flashloan_contract = None
        self.gas_price_oracle_contract = None
        self.abi_registry = ABIRegistry()

        # runtime state -----------------------------------------------------
        self.erc20_abi: List[Dict[str, Any]] = []
        self.flashloan_abi: List[Dict[str, Any]] = []

        # NEW: global running profit counter read by StrategyNet
        self.current_profit: Decimal = Decimal("0")

    # --------------------------------------------------------------------- #
    # init helpers                                                          #
    # --------------------------------------------------------------------- #

    async def initialize(self) -> None:
        await self._load_abis()
        await self._initialize_contracts()
        logger.info("TransactionCore initialised.")

    async def _load_abis(self) -> None:
        await self.abi_registry.initialize(self.config.BASE_PATH)
        self.erc20_abi = self.abi_registry.get_abi("erc20") or []
        self.flashloan_abi = self.abi_registry.get_abi("aave_flashloan") or []
        self.aave_pool_abi = self.abi_registry.get_abi("aave") or []
        self.uniswap_abi = self.abi_registry.get_abi("uniswap") or []
        self.sushiswap_abi = self.abi_registry.get_abi("sushiswap") or []

    async def _initialize_contracts(self) -> None:
        self.aave_flashloan = self.web3.eth.contract(
            address=self.web3.to_checksum_address(self.config.AAVE_FLASHLOAN_ADDRESS),
            abi=self.flashloan_abi,
        )
        self.aave_pool = self.web3.eth.contract(
            address=self.web3.to_checksum_address(self.config.AAVE_POOL_ADDRESS),
            abi=self.aave_pool_abi,
        )

        # validate
        for c in (self.aave_flashloan, self.aave_pool):
            await self._validate_contract(c)

        if self.uniswap_abi and self.config.UNISWAP_ADDRESS:
            self.uniswap_router = self.web3.eth.contract(
                address=self.web3.to_checksum_address(self.config.UNISWAP_ADDRESS),
                abi=self.uniswap_abi,
            )
            await self._validate_contract(self.uniswap_router)

        if self.sushiswap_abi and self.config.SUSHISWAP_ADDRESS:
            self.sushiswap_router = self.web3.eth.contract(
                address=self.web3.to_checksum_address(self.config.SUSHISWAP_ADDRESS),
                abi=self.sushiswap_abi,
            )
            await self._validate_contract(self.sushiswap_router)

    async def _validate_contract(self, contract: Any) -> None:
        code = await self.web3.eth.get_code(contract.address)
        if not code or code == b"":
            raise ValueError(f"No contract code at {contract.address}")

    # --------------------------------------------------------------------- #
    # tx building helpers                                                   #
    # --------------------------------------------------------------------- #

    async def build_transaction(
        self,
        function_call: Any,
        additional_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Builds a tx, picking correct gas-model and nonce."""
        additional_params = additional_params or {}
        chain_id = await self.web3.eth.chain_id
        latest = await self.web3.eth.get_block("latest")
        supports_1559 = "baseFeePerGas" in latest

        nonce = await self.nonce_core.get_nonce()

        params: Dict[str, Any] = {
            "chainId": chain_id,
            "nonce": nonce,
            "from": self.account.address,
            "gas": self.DEFAULT_GAS_LIMIT,
        }

        if supports_1559:
            base = latest["baseFeePerGas"]
            priority = await self.web3.eth.max_priority_fee
            params.update(
                {
                    "maxFeePerGas": int(base * 2),
                    "maxPriorityFeePerGas": int(priority),
                }
            )
        else:
            dyn_gas_gwei = await self._safety_net.get_dynamic_gas_price()
            params["gasPrice"] = int(
                self.web3.to_wei(dyn_gas_gwei * self.gas_price_multiplier, "gwei")
            )

        tx = function_call.build_transaction(params)
        tx.update(additional_params)

        estimated = await self.estimate_gas(tx)
        tx["gas"] = max(int(estimated * 1.1), self.DEFAULT_GAS_LIMIT)

        # ensure mutually-exclusive gas fields
        is_1559 = "maxFeePerGas" in tx
        tx = {k: v for k, v in tx.items() if k not in {"gasPrice", "maxFeePerGas", "maxPriorityFeePerGas"}}
        if is_1559:
            tx["maxFeePerGas"] = params["maxFeePerGas"]
            tx["maxPriorityFeePerGas"] = params["maxPriorityFeePerGas"]
        else:
            tx["gasPrice"] = params["gasPrice"]

        return tx

    async def estimate_gas(self, tx: Dict[str, Any]) -> int:
        try:
            return await self.web3.eth.estimate_gas(tx)
        except (ContractLogicError, TransactionNotFound):
            return self.DEFAULT_GAS_LIMIT
        except Exception as exc:
            logger.debug("estimate_gas failed (%s) – using fallback", exc)
            return self.DEFAULT_GAS_LIMIT

    # --------------------------------------------------------------------- #
    # sign / send helpers                                                   #
    # --------------------------------------------------------------------- #

    async def sign_transaction(self, tx: Dict[str, Any]) -> bytes:
        clean = self._clean_tx(tx)
        if "chainId" not in clean:
            clean["chainId"] = await self.web3.eth.chain_id
        signed = self.web3.eth.account.sign_transaction(clean, private_key=self.account.key)
        return signed.rawTransaction

    async def send_signed(self, raw: bytes, nonce_used: Optional[int] = None) -> str:
        tx_hash = await self.web3.eth.send_raw_transaction(raw)
        # update nonce-cache immediately; keep tracker alive in the background
        asyncio.create_task(
            self.nonce_core.track_transaction(tx_hash.hex(), nonce_used or await self.nonce_core.get_nonce())
        )
        return tx_hash.hex()

    # retain only valid keys
    @staticmethod
    def _clean_tx(tx: Dict[str, Any]) -> Dict[str, Any]:
        valid = {
            "nonce",
            "gas",
            "gasPrice",
            "maxFeePerGas",
            "maxPriorityFeePerGas",
            "to",
            "value",
            "data",
            "chainId",
            "from",
            "type",
        }
        return {k: v for k, v in tx.items() if k in valid}

    # --------------------------------------------------------------------- #
    # high-level send with retries                                          #
    # --------------------------------------------------------------------- #

    async def execute_transaction(self, tx: Dict[str, Any]) -> Optional[str]:
        """Signs and broadcasts a tx, retrying with gas bump on failure."""
        # Ensure nonce is set before simulation
        if "nonce" not in tx and self.nonce_core:
            tx["nonce"] = await self.nonce_core.get_nonce()
            
        # Apply gas price adjustments if gas_multiplier is present
        if "gas_multiplier" in tx:
            self._bump_gas(tx)
            
        # Perform simulation with the correct nonce and gas prices
        simulation_success = await self.simulate_transaction(tx)
        if not simulation_success:
            logger.error("Transaction simulation failed, aborting execution")
            return None
            
        max_retries = self.config.MEMPOOL_MAX_RETRIES
        delay_s = float(self.config.MEMPOOL_RETRY_DELAY)

        # use our account (where we know private key) if not specified
        if "from" not in tx:
            tx["from"] = self.account.address

        # retry loop up to `max_retries` times
        for attempt in range(max_retries):
            try:
                # sign tx via our account object
                raw = await self.sign_transaction(tx)

                # send tx to node
                tx_hash = await self.send_signed(raw, tx.get("nonce"))
                logger.info(f"Transaction sent: {tx_hash}")

                # return resulting transaction hash
                return tx_hash

            except Exception as e:
                if attempt >= max_retries - 1:
                    logger.exception(f"Final attempt ({attempt+1}/{max_retries}) failed: {e}")
                    return None

                logger.warning(f"Attempt {attempt+1}/{max_retries} failed: {e}")
                self._bump_gas(tx)

                if tx.get("gasPrice") and int(tx["gasPrice"]) > self.web3.to_wei(
                    self.config.MAX_GAS_PRICE_GWEI, "gwei"
                ):
                    logger.warning("Gas price cap reached – aborting retries.")
                    return None

                # sleep and retry
                await asyncio.sleep(delay_s)

        return None

    def _bump_gas(self, tx: Dict[str, Any]) -> None:
        """Apply exponential bump to whichever gas field is present."""
        # Get multiplier from tx if present, otherwise use default
        multiplier = tx.pop("gas_multiplier", self.GAS_RETRY_BUMP)
        
        if "gasPrice" in tx:
            tx["gasPrice"] = int(tx["gasPrice"] * multiplier)
        else:
            tx["maxFeePerGas"] = int(tx["maxFeePerGas"] * multiplier)
            tx["maxPriorityFeePerGas"] = int(tx["maxPriorityFeePerGas"] * multiplier)

    # --------------------------------------------------------------------- #
    # user-facing helpers (withdraw, transfers, strategies etc.)            #
    # --------------------------------------------------------------------- #

    async def withdraw_eth(self) -> bool:
        fn = self.aave_flashloan.functions.withdrawETH()
        tx = await self.build_transaction(fn)
        sent = await self.execute_transaction(tx)
        return bool(sent)

    async def transfer_profit_to_account(
        self, token_address: str, amount: Decimal, target: str
    ) -> bool:
        """Transfer profit to a specified account and update profit tracking with on-chain receipt.
    
        Args:
            token_address: The address of the token to transfer
            amount: The amount to transfer
            target: The target address to receive the tokens
            
        Returns:
            bool: True if transfer successful
        """
        token = self.web3.eth.contract(
            address=self.web3.to_checksum_address(token_address), abi=self.erc20_abi
        )
        decimals = await token.functions.decimals().call()
        amt_raw = int(amount * Decimal(10) ** decimals)

        fn = token.functions.transfer(self.web3.to_checksum_address(target), amt_raw)
        tx = await self.build_transaction(fn)
        tx_hash = await self.execute_transaction(tx)
        
        if tx_hash:
            try:
                # Get receipt to confirm transaction success
                receipt = await self.web3.eth.wait_for_transaction_receipt(tx_hash)
                
                # Only update profit if transaction was successful
                if receipt and receipt.status == 1:
                    # Look for Transfer event to confirm actual amount transferred
                    transfer_events = token.events.Transfer().process_receipt(receipt)
                    
                    # Update profit with actual transferred amount from blockchain if event exists
                    if transfer_events:
                        event = transfer_events[0]
                        actual_amount = Decimal(event.args.value) / Decimal(10) ** decimals
                        self.current_profit += actual_amount
                        logger.info(f"Profit updated: +{actual_amount} tokens (tx: {tx_hash})")
                    else:
                        # Fall back to expected amount if event parsing fails
                        self.current_profit += amount
                        logger.info(f"Profit updated (estimate): +{amount} tokens (tx: {tx_hash})")
                        
                    return True
                else:
                    logger.warning(f"Transfer failed: {tx_hash}")
                    return False
                    
            except Exception as exc:
                logger.error(f"Error confirming profit transfer: {exc}")
                # Use naive profit count as fallback
                self.current_profit += amount
                return True
        
        return False

    # --------------------------------------------------------------------- #
    # simple ETH forwarding variant                                         #
    # --------------------------------------------------------------------- #

    async def handle_eth_transaction(self, target_tx: Dict[str, Any]) -> bool:
        value = int(target_tx.get("value", 0))
        if value <= 0:
            return False

        nonce = await self.nonce_core.get_nonce()
        chain_id = await self.web3.eth.chain_id

        tx = {
            "to": target_tx.get("to", ""),
            "value": value,
            "nonce": nonce,
            "chainId": chain_id,
            "from": self.account.address,
            "gas": self.ETH_TRANSFER_GAS,
            "gas_multiplier": self.GAS_RETRY_BUMP  # Set desired gas aggressiveness factor
        }

        sent = await self.execute_transaction(tx)
        return bool(sent)

    # --------------------------------------------------------------------- #
    # strategy wrappers – unchanged except they now rely on updated helpers #
    # --------------------------------------------------------------------- #

    async def front_run(self, target_tx: Dict[str, Any]) -> bool:
        return bool(await self.execute_transaction(target_tx))

    async def back_run(self, target_tx: Dict[str, Any]) -> bool:
        return bool(await self.execute_transaction(target_tx))

    async def execute_sandwich_attack(self, target_tx: Dict[str, Any], strategy: str = "default") -> bool:
        """Execute a sandwich attack on a target transaction with optional strategy parameter.
        
        Args:
            target_tx: The target transaction to sandwich
            strategy: Strategy to use ("default", "aggressive", "safe")
            
        Returns:
            bool: True if both transactions were sent successfully
        """
        front_tx = target_tx.copy()
        back_tx = target_tx.copy()

        # Set gas multipliers based on strategy instead of modifying gasPrice directly
        if strategy == "aggressive":
            front_tx["gas_multiplier"] = 1.25
            back_tx["gas_multiplier"] = 0.95
        elif strategy == "safe":
            front_tx["gas_multiplier"] = 1.10
            back_tx["gas_multiplier"] = 0.85
        else:  # default strategy
            front_tx["gas_multiplier"] = 1.15
            back_tx["gas_multiplier"] = 0.90
            
        res_front = await self.execute_transaction(front_tx)
        await asyncio.sleep(1)
        res_back = await self.execute_transaction(back_tx)
        return bool(res_front and res_back)

    async def prepare_flashloan_transaction(self, token_address: str, amount: int) -> Dict[str, Any]:
        """Prepare a flashloan transaction for the specified token and amount.
        
        Args:
            token_address: The address of the token to borrow
            amount: The amount to borrow (in raw units)
            
        Returns:
            Dict[str, Any]: The prepared transaction
        """
        if not self.aave_flashloan:
            await self._initialize_contracts()
        
        # Convert address to checksum format
        token_address = self.web3.to_checksum_address(token_address)
        
        # Prepare flashloan parameters
        # params: assets, amounts, modes, onBehalfOf, params
        assets = [token_address]
        amounts = [amount]
        modes = [0]  # 0 = no debt (flash loan)
        on_behalf_of = self.account.address
        params = b""  # Optional params (byte encoded)
        
        # Build flashloan function call
        flashloan_call = self.aave_flashloan.functions.flashLoan(
            assets, amounts, modes, on_behalf_of, params
        )
        
        # Build transaction
        tx = await self.build_transaction(flashloan_call)
        
        # Simulate the transaction to check if it will succeed
        simulation_success = await self.simulate_transaction(tx)
        if not simulation_success:
            logger.warning("Flashloan transaction simulation failed")
        
        return tx

    async def send_bundle(self, transactions: List[Dict[str, Any]]) -> List[str]:
        """Send a bundle of transactions using bundle_transactions and return hashes.
        An alias for execute_bundle with additional pre-processing.
        
        Args:
            transactions: List of transaction dictionaries to bundle
            
        Returns:
            List[str]: List of transaction hashes
        """
        # Preprocess transactions - ensure they have proper nonces
        for i, tx in enumerate(transactions):
            if "nonce" not in tx and self.nonce_core:
                # Each tx needs an incrementing nonce
                tx["nonce"] = await self.nonce_core.get_nonce() + i
        
        # Use execute_bundle to send transactions
        return await self.execute_bundle(transactions)

    async def cancel_transaction(self, nonce: int) -> Optional[str]:
        """Cancel a pending transaction with the specified nonce.
        
        Args:
            nonce: The nonce of the transaction to cancel
            
        Returns:
            Optional[str]: The hash of the cancellation transaction, or None if failed
        """
        # Build a transaction to ourselves with 0 value but higher gas price
        chain_id = await self.web3.eth.chain_id
        latest = await self.web3.eth.get_block("latest")
        supports_1559 = "baseFeePerGas" in latest
        
        cancel_tx = {
            "to": self.account.address,  # Send to ourselves
            "value": 0,  # Zero value
            "nonce": nonce,  # The nonce to override
            "chainId": chain_id,
            "from": self.account.address,
            "gas": self.ETH_TRANSFER_GAS,  # Minimal gas for transfer
        }
        
        # Set gas price significantly higher to encourage miners to include it
        multiplier = 1.5  # 50% higher than current
        
        if supports_1559:
            base = latest["baseFeePerGas"]
            priority = await self.web3.eth.max_priority_fee
            cancel_tx["maxFeePerGas"] = int(base * 2 * multiplier)
            cancel_tx["maxPriorityFeePerGas"] = int(priority * multiplier)
        else:
            dyn_gas_gwei = await self._safety_net.get_dynamic_gas_price()
            cancel_tx["gasPrice"] = int(
                self.web3.to_wei(dyn_gas_gwei * self.gas_price_multiplier * multiplier, "gwei")
            )
        
        # Execute the cancel transaction
        return await self.execute_transaction(cancel_tx)

    # aggressive / predictive / volatility helpers unchanged --------------

    async def aggressive_front_run(self, target_tx: Dict[str, Any]) -> bool:
        # Use gas_multiplier instead of direct gasPrice manipulation
        target_tx["gas_multiplier"] = 1.30
        return bool(await self.execute_transaction(target_tx))

    async def predictive_front_run(self, target_tx: Dict[str, Any]) -> bool:
        if await self.simulate_transaction(target_tx):
            return await self.front_run(target_tx)
        return False

    async def volatility_front_run(self, target_tx: Dict[str, Any]) -> bool:
        # Use gas_multiplier instead of direct gasPrice manipulation
        target_tx["gas_multiplier"] = 1.50
        return bool(await self.execute_transaction(target_tx))

    # back-run helpers ------------------------------------------------------

    async def price_dip_back_run(self, target_tx: Dict[str, Any]) -> bool:
        # Instead of directly manipulating gasPrice, set gas_multiplier to let _bump_gas handle it
        target_tx["gas_multiplier"] = 0.80
        return bool(await self.execute_transaction(target_tx))

    async def flashloan_back_run(self, target_tx: Dict[str, Any]) -> bool:
        if await self.withdraw_eth():
            return await self.back_run(target_tx)
        return False

    async def high_volume_back_run(self, target_tx: Dict[str, Any]) -> bool:
        # Instead of directly manipulating gasPrice, set gas_multiplier to let _bump_gas handle it
        target_tx["gas_multiplier"] = 0.85
        return bool(await self.execute_transaction(target_tx))

    # flash-loan + combo wrappers ------------------------------------------

    async def flashloan_front_run(self, target_tx: Dict[str, Any]) -> bool:
        if await self.withdraw_eth():
            return await self.front_run(target_tx)
        return False

    async def flashloan_sandwich_attack(self, target_tx: Dict[str, Any]) -> bool:
        if await self.withdraw_eth():
            return await self.execute_sandwich_attack(target_tx)
        return False

    # --------------------------------------------------------------------- #
    # bundles                                                               #
    # --------------------------------------------------------------------- #

    async def bundle_transactions(self, transactions: List[Dict[str, Any]]) -> List[str]:
        """
        Sign & send a list of tx-dicts sequentially.
        Each dict **must already** contain correct nonce / gas.
        Returns list of tx-hashes (hex).  No fancy flashbots; just serial send.
        """
        tx_hashes: List[str] = []
        for tx in transactions:
            raw = await self.sign_transaction(tx)
            tx_hash = await self.send_signed(raw, nonce_used=tx["nonce"])
            tx_hashes.append(tx_hash)
        return tx_hashes

    async def execute_bundle(self, transactions: List[Dict[str, Any]]) -> List[str]:
        hashes = await self.bundle_transactions(transactions)
        for h in hashes:
            try:
                receipt = await self.web3.eth.wait_for_transaction_receipt(h)
                if receipt.status == 1:
                    logger.info("Bundle tx %s mined OK", h)
                else:
                    logger.error("Bundle tx %s reverted", h)
            except Exception as exc:
                logger.error("Waiting for bundle tx %s failed: %s", h, exc)
        return hashes

    # --------------------------------------------------------------------- #
    # misc utilities                                                        #
    # --------------------------------------------------------------------- #

    async def simulate_transaction(self, tx: Dict[str, Any]) -> bool:
        try:
            await self.web3.eth.call(tx, block_identifier="pending")
            return True
        except ContractLogicError:
            return False

    async def stop(self) -> None:
        # future-proof placeholder
        await asyncio.sleep(0)

    async def get_cached_token_price(self, token_address: str, vs: str = "eth") -> Optional[Decimal]:
        """Get token price using the APIConfig's caching mechanism.
        
        Note: This method is kept for backwards compatibility but now delegates directly
        to the APIConfig's get_real_time_price method which has its own caching.
        """
        if self.api_config:
            return await self.api_config.get_real_time_price(token_address, vs)
        return None

    async def is_healthy(self) -> bool:
        """Check if the transaction core is in a healthy state.
        
        Returns:
            bool: True if healthy
        """
        # Check web3 connection
        try:
            await self.web3.eth.get_block_number()
            
            # Check contract access
            if self.aave_flashloan:
                code = await self.web3.eth.get_code(self.aave_flashloan.address)
                if not code or code == b"":
                    logger.warning("Aave flashloan contract not found")
                    return False
                    
            return True
        except Exception as exc:
            logger.error(f"TransactionCore health check failed: {exc}")
            return False

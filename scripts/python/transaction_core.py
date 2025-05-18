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
from typing import Any, Dict, List, Optional
import time

from web3 import AsyncWeb3
from web3.exceptions import ContractLogicError, TransactionNotFound
from eth_account import Account

from abi_registry import ABIRegistry
from api_config import APIConfig
from configuration import Configuration
from market_monitor import MarketMonitor
from txpool_monitor import TxpoolMonitor
from nonce_core import NonceCore
from safety_net import SafetyNet
from logger_on1 import setup_logging

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
        market_monitor: Optional[MarketMonitor] = None,
        txpool_monitor: Optional[TxpoolMonitor] = None,
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
        
        # Price caching
        self._price_cache = {}
        self._price_cache_expiry = {}
        self._cache_lock = asyncio.Lock()
        self._price_cache_ttl = 60  # seconds
        
        # Contracts
        self.weth_contract = None
        self.usdc_contract = None
        self.usdt_contract = None
        self.uniswap_contract = None
        self.sushiswap_contract = None
        self.aave_pool_contract = None
        self.aave_flashloan_contract = None
        self.gas_price_oracle_contract = None
        self.abi_registry = None

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
        # Perform simulation first
        simulation_success = await self.simulate_transaction(tx)
        if not simulation_success:
            logger.error("Transaction simulation failed, aborting execution")
            return None
            
        max_retries = self.config.MEMPOOL_MAX_RETRIES
        delay_s = float(self.config.MEMPOOL_RETRY_DELAY)

        # ensure nonce
        if "nonce" not in tx and self.nonce_core:
            tx["nonce"] = await self.nonce_core.get_nonce()

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
        if "gasPrice" in tx:
            tx["gasPrice"] = int(tx["gasPrice"] * self.GAS_RETRY_BUMP)
        else:
            tx["maxFeePerGas"] = int(tx["maxFeePerGas"] * self.GAS_RETRY_BUMP)
            tx["maxPriorityFeePerGas"] = int(tx["maxPriorityFeePerGas"] * self.GAS_RETRY_BUMP)

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
        token = self.web3.eth.contract(
            address=self.web3.to_checksum_address(token_address), abi=self.erc20_abi
        )
        decimals = await token.functions.decimals().call()
        amt_raw = int(amount * Decimal(10) ** decimals)

        fn = token.functions.transfer(self.web3.to_checksum_address(target), amt_raw)
        tx = await self.build_transaction(fn)
        sent = await self.execute_transaction(tx)
        if sent:
            # naive profit-count; refine with actual on-chain receipt if desired
            self.current_profit += amount
        return bool(sent)

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
        }

        gas_price_field = (
            "gasPrice"
            if "gasPrice" in target_tx or "maxFeePerGas" not in target_tx
            else "maxFeePerGas"
        )

        if gas_price_field == "gasPrice":
            price = target_tx.get("gasPrice") or self.web3.to_wei(
                (await self._safety_net.get_dynamic_gas_price()) * self.gas_price_multiplier,
                "gwei",
            )
            tx["gasPrice"] = int(price * self.GAS_RETRY_BUMP)
        else:
            price = target_tx.get("maxFeePerGas") or self.web3.to_wei(
                (await self._safety_net.get_dynamic_gas_price()) * self.gas_price_multiplier,
                "gwei",
            )
            tx["maxFeePerGas"] = int(price * self.GAS_RETRY_BUMP)
            tx["maxPriorityFeePerGas"] = int(price * 0.1)

        sent = await self.execute_transaction(tx)
        return bool(sent)

    # --------------------------------------------------------------------- #
    # strategy wrappers – unchanged except they now rely on updated helpers #
    # --------------------------------------------------------------------- #

    async def front_run(self, target_tx: Dict[str, Any]) -> bool:
        return bool(await self.execute_transaction(target_tx))

    async def back_run(self, target_tx: Dict[str, Any]) -> bool:
        return bool(await self.execute_transaction(target_tx))

    async def execute_sandwich_attack(self, target_tx: Dict[str, Any]) -> bool:
        front_tx = target_tx.copy()
        back_tx = target_tx.copy()

        # adjust gas
        front_tx["gasPrice"] = int(
            (front_tx.get("gasPrice") or front_tx.get("maxFeePerGas", 0)) * 1.15
        )
        back_tx["gasPrice"] = int(
            (back_tx.get("gasPrice") or back_tx.get("maxFeePerGas", 0)) * 0.90
        )

        res_front = await self.execute_transaction(front_tx)
        await asyncio.sleep(1)
        res_back = await self.execute_transaction(back_tx)
        return bool(res_front and res_back)

    # aggressive / predictive / volatility helpers unchanged --------------

    async def aggressive_front_run(self, target_tx: Dict[str, Any]) -> bool:
        if "gasPrice" in target_tx:
            target_tx["gasPrice"] = int(target_tx["gasPrice"] * 1.30)
        else:
            dyn = await self._safety_net.get_dynamic_gas_price()
            target_tx["gasPrice"] = int(
                self.web3.to_wei(dyn * self.gas_price_multiplier * 1.30, "gwei")
            )
        return bool(await self.execute_transaction(target_tx))

    async def predictive_front_run(self, target_tx: Dict[str, Any]) -> bool:
        if await self.simulate_transaction(target_tx):
            return await self.front_run(target_tx)
        return False

    async def volatility_front_run(self, target_tx: Dict[str, Any]) -> bool:
        mult = 1.50
        if "gasPrice" in target_tx:
            target_tx["gasPrice"] = int(target_tx["gasPrice"] * mult)
        else:
            dyn = await self._safety_net.get_dynamic_gas_price()
            target_tx["gasPrice"] = int(
                self.web3.to_wei(dyn * self.gas_price_multiplier * mult, "gwei")
            )
        return bool(await self.execute_transaction(target_tx))

    # back-run helpers ------------------------------------------------------

    async def price_dip_back_run(self, target_tx: Dict[str, Any]) -> bool:
        if "gasPrice" in target_tx:
            target_tx["gasPrice"] = int(target_tx["gasPrice"] * 0.80)
        else:
            dyn = await self._safety_net.get_dynamic_gas_price()
            target_tx["gasPrice"] = int(
                self.web3.to_wei(dyn * self.gas_price_multiplier * 0.80, "gwei")
            )
        return bool(await self.execute_transaction(target_tx))

    async def flashloan_back_run(self, target_tx: Dict[str, Any]) -> bool:
        if await self.withdraw_eth():
            return await self.back_run(target_tx)
        return False

    async def high_volume_back_run(self, target_tx: Dict[str, Any]) -> bool:
        if "gasPrice" in target_tx:
            target_tx["gasPrice"] = int(target_tx["gasPrice"] * 0.85)
        else:
            dyn = await self._safety_net.get_dynamic_gas_price()
            target_tx["gasPrice"] = int(
                self.web3.to_wei(dyn * self.gas_price_multiplier * 0.85, "gwei")
            )
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
        """Get token price with caching for efficiency."""
        cache_key = f"{token_address}:{vs}"
        current_time = time.time()
        
        async with self._cache_lock:
            if (cache_key in self._price_cache and 
                cache_key in self._price_cache_expiry and 
                current_time < self._price_cache_expiry[cache_key]):
                return self._price_cache[cache_key]
        
        # Cache miss or expired, fetch new price
        if self._safety_net:
            price = await self._safety_net.get_token_price(token_address, vs)
            
            if price is not None:
                async with self._cache_lock:
                    self._price_cache[cache_key] = price
                    self._price_cache_expiry[cache_key] = current_time + self._price_cache_ttl
                    
            return price
        return None

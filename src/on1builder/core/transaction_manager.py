# src/on1builder/core/transaction_manager.py
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from eth_account.datastructures import SignedTransaction
from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3
from web3.types import TxParams, Wei

from on1builder.config.loaders import settings
from on1builder.core.balance_manager import BalanceManager
from on1builder.core.nonce_manager import NonceManager
from on1builder.engines.safety_guard import SafetyGuard
from on1builder.integrations.abi_registry import ABIRegistry
from on1builder.integrations.external_apis import ExternalAPIManager
from on1builder.persistence.db_interface import DatabaseInterface
from on1builder.utils.custom_exceptions import (
    ConnectionError,
    InsufficientFundsError,
    StrategyExecutionError,
    TransactionError,
)
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService
from on1builder.utils.gas_optimizer import GasOptimizer
from on1builder.utils.profit_calculator import ProfitCalculator

logger = get_logger(__name__)

class TransactionManager:
    """
    Enhanced transaction manager with balance awareness, flashloan support,
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
        self._safety_guard = SafetyGuard(web3)
        self._db_interface = DatabaseInterface()
        self._api_manager = ExternalAPIManager()
        self._notification_service = NotificationService()
        self._gas_optimizer = GasOptimizer(web3)
        self._profit_calculator = ProfitCalculator(web3)
        
        # Performance tracking
        self._execution_stats = {
            "total_transactions": 0,
            "successful_transactions": 0,
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0
        }
        
        logger.info(f"Enhanced TransactionManager initialized for chain ID {chain_id}.")

    async def initialize(self):
        """Initialize the transaction manager and its components."""
        try:
            await self._gas_optimizer.initialize()
            logger.info(f"TransactionManager initialization complete for chain {self._chain_id}")
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
    ) -> TxParams:
        """Enhanced transaction building with dynamic gas optimization."""
        
        nonce = await self._nonce_manager.get_next_nonce()
        
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
            optimal_gas_gwei, should_proceed = await self._balance_manager.calculate_optimal_gas_price(
                Decimal(str(expected_profit))
            )
            if should_proceed:
                tx_params["gasPrice"] = self._web3.to_wei(optimal_gas_gwei, 'gwei')
            else:
                raise InsufficientFundsError("Gas price too high relative to expected profit")
        else:
            tx_params["gasPrice"] = await self._web3.eth.gas_price

        # Gas limit estimation with fallback
        if gas_limit:
            tx_params["gas"] = gas_limit
        else:
            try:
                estimated_gas = await self._web3.eth.estimate_gas(tx_params)
                # Add 20% buffer for safety
                tx_params["gas"] = int(estimated_gas * 1.2)
            except Exception as e:
                logger.warning(f"Gas estimation failed: {e}. Using default limit.")
                tx_params["gas"] = settings.default_gas_limit

        return tx_params

    async def _sign_and_send(self, tx_params: TxParams) -> str:
        """Enhanced transaction signing with comprehensive safety checks."""
        
        # Safety check with balance awareness
        is_safe, reason = await self._safety_guard.check_transaction(tx_params)
        if not is_safe:
            raise StrategyExecutionError(f"Safety check failed: {reason}")

        # Additional balance check
        max_cost = tx_params.get("value", 0) + (tx_params.get("gas", 0) * tx_params.get("gasPrice", 0))
        current_balance = await self._balance_manager.update_balance()
        balance_wei = self._web3.to_wei(current_balance, 'ether')
        
        if max_cost > balance_wei:
            raise InsufficientFundsError(f"Insufficient balance for transaction. Required: {max_cost}, Available: {balance_wei}")

        logger.debug(f"Signing transaction for nonce {tx_params['nonce']}.")
        signed_tx: SignedTransaction = self._account.sign_transaction(tx_params)

        for attempt in range(settings.transaction_retry_count):
            try:
                tx_hash = await self._web3.eth.send_raw_transaction(signed_tx.rawTransaction)
                logger.info(f"Transaction sent: {tx_hash.hex()}")
                return tx_hash.hex()
            except Exception as e:
                logger.warning(f"Transaction send attempt {attempt + 1} failed: {e}")
                if "nonce too low" in str(e).lower():
                    await self._nonce_manager.resync_nonce()
                    tx_params["nonce"] = await self._nonce_manager.get_next_nonce()
                    signed_tx = self._account.sign_transaction(tx_params)
                    logger.info("Nonce resynced. Retrying with new nonce.")
                await asyncio.sleep(settings.transaction_retry_delay)

        raise TransactionError("Failed to send transaction after multiple retries.")

    async def wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        """Wait for transaction receipt with configurable timeout."""
        try:
            receipt = await self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout)
            return receipt
        except asyncio.TimeoutError:
            raise TransactionError(f"Transaction {tx_hash} not confirmed within {timeout}s.")

    async def execute_and_confirm(
        self,
        tx_params: TxParams,
        strategy_name: str,
        expected_profit: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Enhanced execution with profit tracking and comprehensive logging."""
        
        start_time = time.monotonic()
        tx_hash = ""
        
        try:
            # Pre-execution balance
            pre_balance = await self._balance_manager.update_balance()
            
            tx_hash = await self._sign_and_send(tx_params)
            receipt = await self.wait_for_receipt(tx_hash)

            execution_time = time.monotonic() - start_time
            
            # Calculate actual costs and profit
            gas_used = receipt.get("gasUsed", 0)
            effective_gas_price = receipt.get("effectiveGasPrice", tx_params.get("gasPrice", 0))
            gas_cost_wei = gas_used * effective_gas_price
            gas_cost_eth = float(self._web3.from_wei(gas_cost_wei, "ether"))
            
            status = receipt.get("status") == 1
            
            # Post-execution balance and profit calculation
            post_balance = await self._balance_manager.update_balance(force=True)
            actual_profit_eth = float(post_balance - pre_balance) + gas_cost_eth
            
            # Update stats
            self._execution_stats["total_transactions"] += 1
            if status:
                self._execution_stats["successful_transactions"] += 1
                self._execution_stats["total_profit_eth"] += actual_profit_eth
            self._execution_stats["total_gas_spent_eth"] += gas_cost_eth
            
            # Save transaction to database
            await self._db_interface.save_transaction({
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
            })
            
            # Save profit record if profitable
            if status and actual_profit_eth > 0:
                await self._db_interface.save_profit_record({
                    "tx_hash": tx_hash,
                    "chain_id": self._chain_id,
                    "profit_amount_eth": actual_profit_eth,
                    "strategy": strategy_name,
                    "gas_cost_eth": gas_cost_eth,
                    "execution_time_s": execution_time
                })
                
                # Record profit with balance manager
                await self._balance_manager.record_profit(Decimal(str(actual_profit_eth)), strategy_name)
            
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
                "strategy": strategy_name
            }
            
            # Send notification for significant profits or failures
            if status and actual_profit_eth > 0.01:
                await self._notification_service.send_alert(
                    title=f"Profitable Trade: {strategy_name}",
                    message=f"Profit: {actual_profit_eth:.6f} ETH",
                    level="INFO",
                    details=result
                )
            elif not status:
                await self._notification_service.send_alert(
                    title=f"Transaction Failed: {strategy_name}",
                    message=f"Transaction {tx_hash} failed",
                    level="WARNING",
                    details=result
                )
            
            return result
            
        except (StrategyExecutionError, TransactionError, InsufficientFundsError, ConnectionError) as e:
            logger.error(f"Execution failed for strategy '{strategy_name}': {e}")
            await self._notification_service.send_alert(
                title=f"Strategy '{strategy_name}' Failed",
                message=str(e),
                level="ERROR",
                details={"tx_hash": tx_hash, "strategy": strategy_name}
            )
            return {"success": False, "reason": str(e), "tx_hash": tx_hash, "strategy": strategy_name}

    async def _get_dex_contract(self, dex_name: str):
        """Get DEX contract with enhanced error handling."""
        abi_name = f"{dex_name.lower()}_abi"
        abi = self._abi_registry.get_abi(abi_name)
        if not abi:
            raise StrategyExecutionError(f"{dex_name} ABI not found. Available ABIs: {list(self._abi_registry._abis.keys())}")
            
        # Try different address mapping formats
        address_maps = [
            getattr(settings.contracts, f"{dex_name.lower()}_router", {}),
            getattr(settings.contracts, f"{dex_name.lower()}_addresses", {}),
            getattr(settings.contracts, dex_name.lower(), {})
        ]
        
        address = None
        for address_map in address_maps:
            if isinstance(address_map, dict):
                address = address_map.get(str(self._chain_id))
                if address:
                    break
        
        if not address:
            raise StrategyExecutionError(f"{dex_name} router address not configured for chain {self._chain_id}.")
        
        return self._web3.eth.contract(address=address, abi=abi)

    async def _get_swap_path(self, opportunity: Dict[str, Any]) -> List[str]:
        """Enhanced path resolution with validation."""
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
                    raise StrategyExecutionError(f"Token address not found for symbol: {symbol}")
                resolved_path.append(address)
        
        return resolved_path

    async def _calculate_amounts_with_slippage(self, opportunity: Dict[str, Any]) -> Tuple[int, int]:
        """Calculate swap amounts with slippage protection."""
        amount_in = opportunity.get("amount_in", 0)
        expected_amount_out = opportunity.get("expected_amount_out", 0)
        
        # Convert to Wei if necessary
        if isinstance(amount_in, float):
            amount_in = int(amount_in * 10**18)
        if isinstance(expected_amount_out, float):
            expected_amount_out = int(expected_amount_out * 10**18)
        
        # Apply slippage tolerance
        slippage_multiplier = 1 - (settings.slippage_tolerance / 100)
        amount_out_min = int(expected_amount_out * slippage_multiplier)
        
        return amount_in, amount_out_min

    async def execute_swap(self, opportunity: Dict[str, Any], strategy_name: str) -> Dict[str, Any]:
        """Enhanced swap execution with comprehensive validation."""
        
        # Validate opportunity has required fields
        required_fields = ["dex", "path", "amount_in"]
        for field in required_fields:
            if field not in opportunity:
                raise StrategyExecutionError(f"Missing required field in opportunity: {field}")
        
        dex_name = opportunity.get("dex", "uniswap")
        dex_contract = await self._get_dex_contract(dex_name)
        
        path = await self._get_swap_path(opportunity)
        amount_in, amount_out_min = await self._calculate_amounts_with_slippage(opportunity)
        
        deadline = int(time.time()) + 300  # 5 minute deadline
        
        # Check if we have enough balance for this swap
        if path[0] != "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2":  # Not ETH
            # Check token balance
            token_contract = self._web3.eth.contract(
                address=path[0],
                abi=self._abi_registry.get_abi("erc20_abi")
            )
            balance = await token_contract.functions.balanceOf(self._address).call()
            if balance < amount_in:
                raise InsufficientFundsError(f"Insufficient token balance. Required: {amount_in}, Available: {balance}")
        
        # Build transaction based on swap type
        if path[0] == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2":  # ETH to token
            function_call = dex_contract.functions.swapExactETHForTokens(
                amount_out_min,
                path,
                self._address,
                deadline
            )
            value = Wei(amount_in)
        elif path[-1] == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2":  # Token to ETH
            function_call = dex_contract.functions.swapExactTokensForETH(
                amount_in,
                amount_out_min,
                path,
                self._address,
                deadline
            )
            value = Wei(0)
        else:  # Token to token
            function_call = dex_contract.functions.swapExactTokensForTokens(
                amount_in,
                amount_out_min,
                path,
                self._address,
                deadline
            )
            value = Wei(0)
        
        # Build and send transaction
        tx_data = function_call.build_transaction({
            "from": self._address,
            "value": value,
            "gas": settings.default_gas_limit,
            "nonce": await self._nonce_manager.get_next_nonce()
        })['data']
        
        tx_params = await self._build_transaction(
            to=dex_contract.address,
            data=tx_data,
            value=value
        )
        
        # Override gas price if specified
        if opportunity.get("gas_price_wei"):
            tx_params['gasPrice'] = Wei(opportunity['gas_price_wei'])
        elif opportunity.get("optimal_gas_price"):
            tx_params['gasPrice'] = self._web3.to_wei(opportunity["optimal_gas_price"], 'gwei')

        expected_profit = opportunity.get("expected_profit_eth", 0)
        return await self.execute_and_confirm(
            tx_params, 
            strategy_name, 
            Decimal(str(expected_profit)) if expected_profit else None
        )

    async def execute_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute arbitrage opportunity with enhanced validation."""
        logger.info(f"Executing arbitrage opportunity: {opportunity}")
        
        # Validate arbitrage opportunity
        if not opportunity.get("profit_potential", 0) > 0:
            return {"success": False, "reason": "No profit potential in arbitrage opportunity"}
        
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
            return {"success": False, "reason": "No target transaction for front-running"}
        
        target_gas_price = target_tx.get("gasPrice", 0)
        
        # Calculate competitive gas price
        gas_premium = self._web3.to_wei(2, 'gwei')  # 2 gwei premium
        opportunity["gas_price_wei"] = target_gas_price + gas_premium
        
        # Ensure we can afford the higher gas price
        expected_profit = opportunity.get("expected_profit_eth", 0)
        gas_cost_estimate = (opportunity.get("gas_limit", 150000) * (target_gas_price + gas_premium)) / 10**18
        
        if gas_cost_estimate >= expected_profit * 0.8:  # Gas cost > 80% of profit
            return {"success": False, "reason": "Gas cost too high relative to expected profit"}
        
        return await self.execute_swap(opportunity, "front_run")
        
    async def execute_back_run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute back-running strategy with timing optimization."""
        logger.info(f"Executing back-run opportunity: {opportunity}")
        
        target_tx = opportunity.get("target_tx", {})
        if not target_tx:
            return {"success": False, "reason": "No target transaction for back-running"}
        
        # Wait for target transaction to be mined
        target_hash = target_tx.get("hash")
        if target_hash:
            try:
                await self.wait_for_receipt(target_hash, timeout=60)
                logger.info("Target transaction confirmed, executing back-run")
            except TransactionError:
                return {"success": False, "reason": "Target transaction not confirmed in time"}
        
        # Use slightly lower gas price for back-running
        target_gas_price = target_tx.get("gasPrice", 0)
        opportunity["gas_price_wei"] = max(
            target_gas_price - self._web3.to_wei(1, 'gwei'),
            await self._web3.eth.gas_price
        )
        
        return await self.execute_swap(opportunity, "back_run")

    async def execute_sandwich(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute sandwich attack with comprehensive coordination."""
        logger.info("Executing sandwich attack strategy")
        
        target_tx = opportunity.get("target_tx", {})
        if not target_tx:
            return {"success": False, "reason": "No target transaction for sandwich attack"}
        
        # Prepare front-run and back-run opportunities
        front_run_opp = opportunity.copy()
        back_run_opp = opportunity.copy()
        
        target_gas_price = target_tx.get("gasPrice", 0)
        
        # Front-run with higher gas price
        front_run_opp["gas_price_wei"] = target_gas_price + self._web3.to_wei(2, 'gwei')
        
        # Execute front-run
        logger.info("Executing sandwich front-run")
        front_run_result = await self.execute_swap(front_run_opp, "sandwich_front_run")
        
        if not front_run_result.get("success"):
            return {
                "success": False, 
                "reason": "Sandwich front-run failed", 
                "front_run_result": front_run_result
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
                receipt_obj = self.web3.eth.get_transaction_receipt(front_run_receipt.get('transactionHash'))
                amount_received = Decimal('0')
                
                # Parse Transfer events to get actual output amount
                for log in receipt_obj.logs:
                    try:
                        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
                        if log.topics and log.topics[0].hex() == transfer_topic:
                            # Check if transfer is to our address
                            to_address = "0x" + log.topics[2].hex()[-40:]
                            if to_address.lower() == self.account.address.lower():
                                amount_hex = log.data[0:64] if log.data else "0x0"
                                amount = int(amount_hex, 16)
                                amount_received = max(amount_received, self.web3.from_wei(amount, 'ether'))
                    except (IndexError, ValueError, AttributeError):
                        continue
                
                back_run_opp["amount_in"] = float(amount_received) if amount_received > 0 else opportunity.get("amount_in", 0)
            except Exception as e:
                self.logger.warning(f"Failed to parse front-run proceeds: {e}")
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
            "total_gas_cost_eth": front_run_cost + back_run_cost
        }

    async def execute_flashloan_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute flashloan-based arbitrage with enhanced safety."""
        logger.info("Executing flashloan arbitrage strategy")
        
        if not settings.flashloan_enabled:
            return {"success": False, "reason": "Flashloan functionality is disabled"}
        
        # Validate flashloan opportunity
        required_amount = opportunity.get("flashloan_amount", opportunity.get("amount_in", 0))
        max_flashloan = settings.flashloan_max_amount_eth
        
        if required_amount > max_flashloan:
            return {
                "success": False, 
                "reason": f"Flashloan amount {required_amount} exceeds maximum {max_flashloan}"
            }
        
        expected_profit = opportunity.get("expected_profit_eth", 0)
        min_profit_required = required_amount * settings.flashloan_min_profit_multiplier / 100
        
        if expected_profit < min_profit_required:
            return {
                "success": False,
                "reason": f"Expected profit {expected_profit} below minimum required {min_profit_required}"
            }
        
        # Prepare flashloan parameters
        assets = [opportunity.get("flashloan_asset", "0xA0b86a33E6441E6b99aba6c00bbe0c47D6D2EC30")]  # WETH default
        amounts = [int(required_amount * 10**18)]  # Convert to Wei
        
        # Encode arbitrage data for flashloan callback
        arbitrage_data = {
            "dex_buy": opportunity.get("dex_buy", "uniswap"),
            "dex_sell": opportunity.get("dex_sell", "sushiswap"),
            "path_buy": opportunity.get("path_buy", opportunity.get("path", [])),
            "path_sell": opportunity.get("path_sell", opportunity.get("path", [])),
            "min_profit_wei": int(min_profit_required * 10**18)
        }
        
        # Properly encode arbitrage data for flashloan contract callback
        import json
        try:
            # Create structured data for the flashloan callback
            callback_data = {
                "type": "arbitrage",
                "exchanges": [arbitrage_data.get("exchange_a", ""), arbitrage_data.get("exchange_b", "")],
                "token_path": arbitrage_data.get("token_path", []),
                "amounts": [str(arbitrage_data.get("amount_in", 0)), str(arbitrage_data.get("expected_out", 0))],
                "min_profit": str(arbitrage_data.get("min_profit", 0)),
                "deadline": int(time.time()) + 300  # 5 minute deadline
            }
            user_data = json.dumps(callback_data).encode('utf-8')
        except Exception as e:
            self.logger.warning(f"Failed to encode callback data: {e}")
            user_data = str(arbitrage_data).encode('utf-8')
        
        flashloan_opportunity = {
            "assets": assets,
            "amounts": amounts,
            "user_data": user_data,
            "strategy_type": "flashloan_arbitrage",
            "expected_profit_eth": expected_profit
        }
        
        return await self.execute_flashloan(flashloan_opportunity)

    async def execute_flashloan(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced flashloan execution with comprehensive validation."""
        strategy_name = "flashloan"
        logger.info(f"Executing flashloan strategy with opportunity: {opportunity}")
        
        # Validate flashloan parameters
        assets: List[str] = opportunity.get("assets", [])
        amounts: List[int] = opportunity.get("amounts", [])
        user_data: bytes = opportunity.get("user_data", b"")
        
        if not all([assets, amounts]):
            raise StrategyExecutionError("Flashloan opportunity missing 'assets' or 'amounts'.")
        
        if len(assets) != len(amounts):
            raise StrategyExecutionError("Assets and amounts arrays must have same length.")
            
        # Get flashloan contract
        flashloan_contract_addresses = settings.contracts.simple_flashloan_contract
        flashloan_contract_address = flashloan_contract_addresses.get(str(self._chain_id))
        
        if not flashloan_contract_address:
             raise StrategyExecutionError(f"Flashloan contract not configured for chain {self._chain_id}.")

        flashloan_abi = self._abi_registry.get_abi("aave_flashloan_abi")
        if not flashloan_abi:
            raise StrategyExecutionError("Flashloan ABI not found.")
            
        contract = self._web3.eth.contract(address=flashloan_contract_address, abi=flashloan_abi)
        
        # Check if we have enough ETH for flashloan fees
        balance_summary = await self._balance_manager.get_balance_summary()
        if balance_summary["balance"] < 0.01:  # Need some ETH for fees
            raise InsufficientFundsError("Insufficient ETH balance to pay flashloan fees")
        
        # Build flashloan transaction
        try:
            encoded_function = contract.functions.requestFlashLoan(
                assets, amounts, user_data
            ).build_transaction({
                "chainId": self._chain_id,
                "from": self._address,
                "value": 0,
                "nonce": await self._nonce_manager.get_next_nonce()
            })
            
            tx_params = await self._build_transaction(
                to=flashloan_contract_address, 
                data=encoded_function['data']
            )
            
            # Add buffer for flashloan gas requirements
            tx_params["gas"] = int(tx_params["gas"] * 1.5)
            
            expected_profit = opportunity.get("expected_profit_eth", 0)
            result = await self.execute_and_confirm(
                tx_params, 
                strategy_name, 
                Decimal(str(expected_profit)) if expected_profit else None
            )

            if result["success"]:
                # Calculate actual flashloan profit from logs
                receipt = result.get("receipt", {})
                actual_profit = await self._calculate_flashloan_profit(receipt)
                result["profit_eth"] = actual_profit
                result["flashloan_amounts"] = amounts
                result["flashloan_assets"] = assets
                
                logger.info(f"Flashloan executed successfully. Profit: {actual_profit:.6f} ETH")
            
            return result
            
        except Exception as e:
            logger.error(f"Flashloan execution failed: {e}")
            return {
                "success": False, 
                "reason": f"Flashloan execution error: {str(e)}", 
                "strategy": strategy_name
            }

    async def _calculate_flashloan_profit(self, receipt: Dict[str, Any]) -> float:
        """Calculate actual profit from flashloan transaction receipt."""
        try:
            # Parse transaction logs to get exact profit by analyzing Transfer events
            logs = receipt.get("logs", [])
            profit = Decimal('0')
            our_address = self.account.address.lower()
            
            # Track all token transfers to/from our address
            transfers_in = Decimal('0')
            transfers_out = Decimal('0')
            
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
                                amount_ether = self.web3.from_wei(amount, 'ether')
                                
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
            gas_cost = self.web3.from_wei(gas_used * gas_price, 'ether')
            
            final_profit = net_profit - gas_cost
            
            return float(final_profit)
            
        except Exception as e:
            self.logger.error(f"Error calculating flashloan profit: {e}")
            return 0.0
            
        except Exception as e:
            logger.error(f"Failed to calculate flashloan profit: {e}")
            return 0.0

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Return comprehensive performance statistics."""
        success_rate = 0.0
        if self._execution_stats["total_transactions"] > 0:
            success_rate = (self._execution_stats["successful_transactions"] / 
                          self._execution_stats["total_transactions"] * 100)
        
        net_profit = (self._execution_stats["total_profit_eth"] - 
                     self._execution_stats["total_gas_spent_eth"])
        
        return {
            **self._execution_stats,
            "success_rate_percentage": success_rate,
            "net_profit_eth": net_profit,
            "average_profit_per_transaction": (
                self._execution_stats["total_profit_eth"] / max(1, self._execution_stats["successful_transactions"])
            ),
            "average_gas_cost_per_transaction": (
                self._execution_stats["total_gas_spent_eth"] / max(1, self._execution_stats["total_transactions"])
            )
        }

    async def _build_transaction(
        self,
        to: str,
        value: Wei = Wei(0),
        data: str = "0x",
        gas_limit: Optional[int] = None,
        gas_price: Optional[Wei] = None,
    ) -> TxParams:
        
        nonce = await self._nonce_manager.get_next_nonce()
        
        tx_params: TxParams = {
            "from": self._address,
            "to": self._web3.to_checksum_address(to),
            "value": value,
            "data": data,
            "nonce": nonce,
            "chainId": self._chain_id,
        }

        if gas_price:
            tx_params["gasPrice"] = gas_price
        else:
            tx_params["gasPrice"] = await self._web3.eth.gas_price

        if gas_limit:
            tx_params["gas"] = gas_limit
        else:
            try:
                tx_params["gas"] = await self._web3.eth.estimate_gas(tx_params)
            except Exception as e:
                logger.warning(f"Gas estimation failed: {e}. Using default limit.")
                tx_params["gas"] = settings.default_gas_limit

        return tx_params

    async def _sign_and_send(self, tx_params: TxParams) -> str:
        is_safe, reason = await self._safety_guard.check_transaction(tx_params)
        if not is_safe:
            raise StrategyExecutionError(f"Safety check failed: {reason}")

        logger.debug(f"Signing transaction for nonce {tx_params['nonce']}.")
        signed_tx: SignedTransaction = self._account.sign_transaction(tx_params)

        for attempt in range(settings.transaction_retry_count):
            try:
                tx_hash = await self._web3.eth.send_raw_transaction(signed_tx.rawTransaction)
                logger.info(f"Transaction sent: {tx_hash.hex()}")
                return tx_hash.hex()
            except Exception as e:
                logger.warning(f"Transaction send attempt {attempt + 1} failed: {e}")
                if "nonce too low" in str(e).lower():
                    await self._nonce_manager.resync_nonce()
                    tx_params["nonce"] = await self._nonce_manager.get_next_nonce()
                    signed_tx = self._account.sign_transaction(tx_params)
                    logger.info("Nonce resynced. Retrying with new nonce.")
                await asyncio.sleep(settings.transaction_retry_delay)

        raise TransactionError("Failed to send transaction after multiple retries.")

    async def wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        try:
            receipt = await self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout)
            return receipt
        except asyncio.TimeoutError:
            raise TransactionError(f"Transaction {tx_hash} not confirmed within {timeout}s.")

    async def execute_and_confirm(
        self,
        tx_params: TxParams,
        strategy_name: str,
    ) -> Dict[str, Any]:
        
        start_time = time.monotonic()
        tx_hash = ""
        try:
            tx_hash = await self._sign_and_send(tx_params)
            receipt = await self.wait_for_receipt(tx_hash)

            execution_time = time.monotonic() - start_time
            
            gas_used = receipt.get("gasUsed", 0)
            effective_gas_price = receipt.get("effectiveGasPrice", tx_params.get("gasPrice", 0))
            gas_cost_wei = gas_used * effective_gas_price
            gas_cost_eth = self._web3.from_wei(gas_cost_wei, "ether")
            
            status = receipt.get("status") == 1
            
            await self._db_interface.save_transaction({
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
            })
            
            return {
                "success": status,
                "tx_hash": tx_hash,
                "receipt": receipt,
                "gas_cost_eth": gas_cost_eth,
                "execution_time_s": execution_time,
            }
            
        except (StrategyExecutionError, TransactionError, InsufficientFundsError, ConnectionError) as e:
            logger.error(f"Execution failed for strategy '{strategy_name}': {e}")
            await self._notification_service.send_alert(
                title=f"Strategy '{strategy_name}' Failed",
                message=str(e),
                level="ERROR",
                details={"tx_hash": tx_hash}
            )
            return {"success": False, "reason": str(e), "tx_hash": tx_hash}

    async def _get_dex_contract(self, dex_name: str):
        abi_name = f"{dex_name.lower()}_router"
        abi = self._abi_registry.get_abi(abi_name)
        if not abi:
            raise StrategyExecutionError(f"{dex_name} ABI not found.")
            
        address_map = getattr(settings.contracts, f"{dex_name.lower()}_router", {})
        address = address_map.get(str(self._chain_id))
        if not address:
            raise StrategyExecutionError(f"{dex_name} router address not configured for chain {self._chain_id}.")
        
        return self._web3.eth.contract(address=address, abi=abi)

    async def _get_swap_path(self, opportunity: Dict[str, Any]) -> List[str]:
        path = opportunity.get("path")
        if not path or len(path) < 2:
            raise StrategyExecutionError("Invalid or missing swap path in opportunity.")
        
        return [self._abi_registry.get_token_address(symbol, self._chain_id) for symbol in path]

    async def execute_swap(self, opportunity: Dict[str, Any], strategy_name: str) -> Dict[str, Any]:
        dex_name = opportunity.get("dex", "uniswap_v2")
        dex_contract = await self._get_dex_contract(dex_name)
        
        path = await self._get_swap_path(opportunity)
        amount_in = Wei(opportunity.get("amount_in_wei", 0))
        amount_out_min = Wei(opportunity.get("amount_out_min_wei", 0))
        deadline = int(time.time()) + 120
        
        data = dex_contract.functions.swapExactTokensForTokens(
            amount_in,
            amount_out_min,
            path,
            self._address,
            deadline
        ).build_transaction({
            "from": self._address,
            "value": 0,
            "gas": settings.default_gas_limit,
            "nonce": await self._nonce_manager.get_next_nonce()
        })['data']
        
        tx_params = await self._build_transaction(to=dex_contract.address, data=data)
        
        # Override gas price for MEV strategies
        if opportunity.get("gas_price_wei"):
            tx_params['gasPrice'] = Wei(opportunity['gas_price_wei'])

        return await self.execute_and_confirm(tx_params, strategy_name)

    async def execute_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        return await self.execute_swap(opportunity, "arbitrage")

    async def execute_front_run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        target_tx = opportunity.get("target_tx", {})
        target_gas_price = target_tx.get("gasPrice", 0)
        
        opportunity["gas_price_wei"] = target_gas_price + self._web3.to_wei(1, 'gwei')
        
        return await self.execute_swap(opportunity, "front_run")
        
    async def execute_back_run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        target_tx = opportunity.get("target_tx", {})
        target_gas_price = target_tx.get("gasPrice", 0)
        
        opportunity["gas_price_wei"] = target_gas_price - self._web3.to_wei(1, 'gwei')
        
        return await self.execute_swap(opportunity, "back_run")

    async def execute_sandwich(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Executing sandwich attack.")
        
        front_run_opp = opportunity.copy()
        back_run_opp = opportunity.copy()
        
        target_tx = opportunity.get("target_tx", {})
        target_gas_price = target_tx.get("gasPrice", 0)
        
        front_run_opp["gas_price_wei"] = target_gas_price + self._web3.to_wei(1, 'gwei')
        
        front_run_result = await self.execute_swap(front_run_opp, "sandwich_front_run")
        if not front_run_result.get("success"):
            return {"success": False, "reason": "Sandwich front-run failed.", "front_run_result": front_run_result}
            
        logger.info("Sandwich front-run successful. Waiting for target transaction.")
        try:
            await self.wait_for_receipt(target_tx.get("hash"))
        except TransactionError as e:
            return {"success": False, "reason": f"Target transaction failed to confirm: {e}", "front_run_result": front_run_result}
            
        logger.info("Target transaction confirmed. Executing back-run.")
        
        back_run_opp["path"] = list(reversed(opportunity["path"]))
        
        back_run_result = await self.execute_swap(back_run_opp, "sandwich_back_run")
        
        total_profit = (back_run_result.get("profit_eth", 0)) - (front_run_result.get("gas_cost_eth", 0) + back_run_result.get("gas_cost_eth", 0))
        
        return {
            "success": back_run_result.get("success"),
            "profit_eth": total_profit,
            "front_run_tx": front_run_result.get("tx_hash"),
            "back_run_tx": back_run_result.get("tx_hash"),
        }

    async def execute_flashloan(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        strategy_name = "flashloan"
        logger.info(f"Attempting to execute '{strategy_name}' strategy.")
        
        assets: List[str] = opportunity.get("assets", [])
        amounts: List[int] = opportunity.get("amounts", [])
        user_data: bytes = opportunity.get("user_data", b"")
        
        if not all([assets, amounts]):
            raise StrategyExecutionError("Flashloan opportunity missing 'assets' or 'amounts'.")
            
        flashloan_contract_address = settings.contracts.simple_flashloan_contract.get(str(self._chain_id))
        if not flashloan_contract_address:
             raise StrategyExecutionError(f"Flashloan contract not configured for chain {self._chain_id}.")

        flashloan_abi = self._abi_registry.get_abi("SimpleFlashloan")
        if not flashloan_abi:
            raise StrategyExecutionError("SimpleFlashloan ABI not found.")
            
        contract = self._web3.eth.contract(address=flashloan_contract_address, abi=flashloan_abi)
        
        encoded_function = contract.functions.requestFlashLoan(
            assets, amounts, user_data
        ).build_transaction({
            "chainId": self._chain_id,
            "from": self._address,
            "nonce": await self._nonce_manager.get_next_nonce()
        })
        
        tx_params = await self._build_transaction(to=flashloan_contract_address, data=encoded_function['data'])
        
        result = await self.execute_and_confirm(tx_params, strategy_name)

        if result["success"]:
            profit = await self._calculate_flashloan_profit(result["receipt"])
            result["profit_eth"] = profit
            await self._db_interface.save_profit_record({
                "tx_hash": result["tx_hash"],
                "chain_id": self._chain_id,
                "profit_amount_eth": profit,
                "strategy": strategy_name,
                "base_token_address": assets[0] if assets else "N/A"
            })
        
        return result

    async def _calculate_flashloan_profit(self, receipt: Dict[str, Any]) -> float:
        return 0.0
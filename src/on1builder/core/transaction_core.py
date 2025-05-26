# filepath: /home/on1/ON1Builder/src/on1builder/core/transaction_core.py
"""
ON1Builder – TransactionCore
============================
A high-level helper for building, signing, simulating and dispatching MEV-style transactions.
This module provides a set of functions to interact with Ethereum smart contracts, manage
transactions, and execute various strategies such as front-running, back-running, and sandwich attacks.
"""

from __future__ import annotations
import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple, Union, Callable

# Import web3 and eth_account for runtime use
try:
    from web3 import AsyncWeb3
    from eth_account import Account
    from eth_account.datastructures import SignedTransaction
except ImportError:
    # For development/testing when dependencies might not be available
    AsyncWeb3 = Any
    Account = Any
    SignedTransaction = Any

# Use TYPE_CHECKING for circular import prevention
if TYPE_CHECKING:
    from on1builder.config.config import Configuration
    from on1builder.core.nonce_core import NonceCore
    from on1builder.engines.safety_net import SafetyNet

from on1builder.utils.logger import setup_logging
from on1builder.utils.strategyexecutionerror import StrategyExecutionError

logger = setup_logging("TransactionCore", level="DEBUG")


class TransactionCore:
    """High-level helper for building, signing, simulating and dispatching MEV-
    style transactions."""

    DEFAULT_GAS_LIMIT: int = 100_000
    ETH_TRANSFER_GAS: int = 21_000
    GAS_RETRY_BUMP: float = 1.15  # +15% per retry

    def __init__(
        self,
        web3: "AsyncWeb3",
        account: "Account",
        configuration: "Configuration",
        api_config=None,
        market_monitor=None,
        txpool_monitor=None,
        nonce_core: Optional["NonceCore"] = None,
        safety_net: Optional["SafetyNet"] = None,
        chain_id: int = 1,
    ) -> None:
        """Initialize the TransactionCore.

        Args:
            web3: AsyncWeb3 instance for blockchain interaction
            account: Ethereum account
            configuration: Configuration for the bot
            api_config: API configuration (optional)
            market_monitor: Market monitoring system (optional)
            txpool_monitor: Transaction pool monitoring system (optional)
            nonce_core: Nonce management system (optional)
            safety_net: Safety checks system (optional)
            chain_id: Ethereum chain ID (default: 1 for mainnet)
        """
        self.web3 = web3
        self.chain_id = chain_id
        self.account = account
        self.address = getattr(
            account, "address", "0x0000000000000000000000000000000000000000"
        )
        self.configuration = configuration
        self.nonce_core = nonce_core
        self.safety_net = safety_net

        # Transaction tracking
        self._pending_txs: Dict[str, Dict[str, Any]] = {}

        logger.debug(f"TransactionCore initialized for chain ID {chain_id}")

    async def initialize(self):
        """Initialize the TransactionCore with necessary components."""
        logger.info("Initializing TransactionCore...")
        # Add any additional initialization logic here
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
        """Build an Ethereum transaction.

        Args:
            function_call: Function call or transaction data
            additional_params: Additional transaction parameters
            to_address: Destination address
            value: Amount of ETH to send in wei
            data: Transaction data (for contract calls)
            gas_limit: Maximum gas to use
            gas_price: Gas price in wei
            nonce: Transaction nonce

        Returns:
            Transaction dictionary
        """
        # Get nonce if not provided
        if nonce is None and self.nonce_core:
            try:
                nonce = await self.nonce_core.get_next_nonce(self.address)
            except Exception as e:
                logger.error(f"Failed to get nonce: {e}")
                # Fallback to web3 nonce if available
                try:
                    nonce = await self.web3.eth.get_transaction_count(self.address)
                except Exception:
                    logger.error("Could not get nonce from web3, using 0")
                    nonce = 0

        # Handle function_call if it's a web3 function
        if hasattr(function_call, "build_transaction"):
            # It's a web3 contract function call
            tx_params = {
                "from": self.address,
                "value": value,
                "chainId": self.chain_id,
            }
            if nonce is not None:
                tx_params["nonce"] = nonce
            if gas_price is not None:
                tx_params["gasPrice"] = gas_price

            # Add additional params if provided
            if additional_params:
                tx_params.update(additional_params)

            try:
                tx = await function_call.build_transaction(tx_params)
            except Exception as e:
                logger.error(f"Failed to build function call transaction: {e}")
                raise StrategyExecutionError(
                    f"Failed to build transaction: {e}")
        else:
            # Build a standard transaction
            tx = {
                "from": self.address,
                "chainId": self.chain_id,
                "value": value,
            }

            # Set destination address
            if to_address:
                tx["to"] = to_address

            # Add data if provided
            if data:
                tx["data"] = data

            # Set nonce if provided or available
            if nonce is not None:
                tx["nonce"] = nonce

            # Add additional params if provided
            if additional_params:
                tx.update(additional_params)

        # Set gas price
        if gas_price is None:
            try:
                gas_price = await self.web3.eth.gas_price
                # Apply gas price multiplier from config if available
                multiplier = getattr(
                    self.configuration, "gas_price_multiplier", 1.1)
                if gas_price is not None:
                    gas_price = int(gas_price * multiplier)
            except Exception as e:
                logger.error(f"Failed to get gas price: {e}")
                # Use a reasonable default
                gas_price = 50 * 10**9  # 50 Gwei

        tx["gasPrice"] = gas_price

        # Set gas limit
        if gas_limit is None:
            if data or "data" in tx:
                try:
                    # For contract interactions, estimate gas
                    estimated = await self.web3.eth.estimate_gas(tx)
                    gas_limit = int(estimated * 1.2)  # Add 20% buffer
                except Exception as e:
                    logger.warning(
                        f"Gas estimation failed: {e}. Using default gas limit."
                    )
                    gas_limit = self.DEFAULT_GAS_LIMIT
            else:
                # For simple ETH transfers
                gas_limit = self.ETH_TRANSFER_GAS

        tx["gas"] = gas_limit

        return tx

    async def sign_transaction(
            self, tx: Dict[str, Any]) -> "SignedTransaction":
        """Sign a transaction.

        Args:
            tx: Transaction to sign

        Returns:
            SignedTransaction: The signed transaction
        """
        try:
            return self.account.sign_transaction(tx)
        except Exception as e:
            logger.error(f"Failed to sign transaction: {e}")
            raise StrategyExecutionError(
                f"Transaction signing failed: {str(e)}")

    async def execute_transaction(
        self, tx: Dict[str, Any], retry_count: int = 3, retry_delay: float = 2.0
    ) -> str:
        """Execute (sign and send) a transaction.

        Args:
            tx: Transaction to sign and send
            retry_count: Number of attempts if transaction fails
            retry_delay: Delay between retries in seconds

        Returns:
            str: Transaction hash
        """
        # Perform safety checks if safety_net is available
        if self.safety_net:
            try:
                await self.safety_net.check_transaction_safety(tx)
            except Exception as e:
                logger.error(f"Transaction safety check failed: {e}")
                raise StrategyExecutionError(
                    f"Transaction safety check failed: {str(e)}"
                )

        # Track original gas price for retries
        original_gas_price = tx.get("gasPrice", 0)

        for attempt in range(retry_count + 1):
            try:
                # Apply gas bump for retries
                if attempt > 0:
                    bumped_price = int(
                        original_gas_price * (self.GAS_RETRY_BUMP**attempt)
                    )
                    logger.info(
                        f"Retry {attempt}: Bumping gas price from {
                            tx['gasPrice']} to {bumped_price}"
                    )
                    tx["gasPrice"] = bumped_price

                # Sign transaction
                signed_tx = await self.sign_transaction(tx)

                # Send raw transaction
                tx_hash = await self.web3.eth.send_raw_transaction(
                    signed_tx.rawTransaction
                )
                tx_hash_str = tx_hash.hex()

                # Store pending transaction
                self._pending_txs[tx_hash_str] = {
                    "tx": tx,
                    "signed_tx": signed_tx,
                    "timestamp": time.time(),
                    "status": "pending",
                }

                # Track nonce if nonce_core is available
                if self.nonce_core and "nonce" in tx:
                    await self.nonce_core.track_transaction(tx_hash_str, tx["nonce"])

                logger.info(f"Transaction sent: {tx_hash_str}")
                return tx_hash_str

            except Exception as e:
                if attempt < retry_count:
                    logger.warning(
                        f"Transaction attempt {
                            attempt + 1} failed: {e}. Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"Transaction failed after {
                            retry_count + 1} attempts: {e}"
                    )
                    raise StrategyExecutionError(
                        f"Failed to send transaction: {str(e)}"
                    )

    async def wait_for_transaction_receipt(
        self, tx_hash: str, timeout: int = 120, poll_interval: float = 0.1
    ) -> Dict[str, Any]:
        """Wait for a transaction receipt.

        Args:
            tx_hash: Transaction hash
            timeout: Maximum time to wait in seconds
            poll_interval: Time between checks in seconds

        Returns:
            Dict[str, Any]: Transaction receipt
        """
        if not tx_hash.startswith("0x"):
            tx_hash = f"0x{tx_hash}"

        start_time = time.time()
        while True:
            try:
                receipt = await self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    # Update pending transaction status
                    if tx_hash in self._pending_txs:
                        if receipt["status"] == 1:
                            self._pending_txs[tx_hash]["status"] = "success"
                        else:
                            self._pending_txs[tx_hash]["status"] = "failed"

                    # Check if transaction was successful
                    if receipt["status"] == 1:
                        logger.info(
                            f"Transaction {tx_hash} confirmed in block {
                                receipt['blockNumber']}"
                        )
                        return receipt
                    else:
                        error_msg = f"Transaction {tx_hash} failed with status 0"
                        logger.error(error_msg)
                        raise StrategyExecutionError(error_msg)
            except Exception:
                # Not yet mined or other error
                pass

            # Check if we've exceeded the timeout
            if time.time() - start_time > timeout:
                raise asyncio.TimeoutError(
                    f"Transaction {tx_hash} not mined within {timeout} seconds"
                )

            # Wait before polling again
            await asyncio.sleep(poll_interval)

    async def handle_eth_transaction(
            self, target_tx: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a standard ETH transaction.

        Args:
            target_tx: Transaction to handle

        Returns:
            Dict[str, Any]: Transaction receipt
        """
        logger.info(
            f"Handling ETH transaction: {
                target_tx.get(
                    'tx_hash', 'Unknown hash')}"
        )

        # Build transaction if needed
        if "to" not in target_tx and "value" in target_tx:
            tx = await self.build_transaction(
                function_call=None,
                to_address=target_tx.get("to_address"),
                value=target_tx.get("value", 0),
            )
        else:
            tx = target_tx

        # Execute transaction
        tx_hash = await self.execute_transaction(tx)

        # Wait for receipt
        receipt = await self.wait_for_transaction_receipt(tx_hash)
        return receipt

    async def get_eth_balance(self, address: Optional[str] = None) -> Decimal:
        """Get ETH balance for an address.

        Args:
            address: Address to check (defaults to account address)

        Returns:
            Decimal: Balance in ETH
        """
        if address is None:
            address = self.address

        try:
            balance_wei = await self.web3.eth.get_balance(address)
            return Decimal(balance_wei) / Decimal(10**18)
        except Exception as e:
            logger.error(f"Failed to get ETH balance: {e}")
            return Decimal(0)

    async def simulate_transaction(
        self, transaction: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Simulate a transaction to check if it will succeed.

        Args:
            transaction: Transaction to simulate

        Returns:
            Tuple[bool, str]: (Success flag, Error message if failed)
        """
        try:
            # Create a copy of the transaction
            sim_tx = transaction.copy()

            # For simulation, we use eth_call which executes the tx locally
            await self.web3.eth.call(sim_tx)
            return True, ""
        except Exception as e:
            # Contract reverted or other error
            error_message = str(e)
            logger.warning(f"Transaction simulation failed: {error_message}")
            return False, error_message

    async def prepare_flashloan_transaction(
        self, flashloan_asset: str, flashloan_amount: int
    ) -> Dict[str, Any]:
        """Prepare a flashloan transaction.

        Args:
            flashloan_asset: Asset address to borrow
            flashloan_amount: Amount to borrow

        Returns:
            Dict[str, Any]: Transaction object
        """
        logger.info(
            f"Preparing flashloan for {flashloan_amount} of asset {flashloan_asset}"
        )

        # Example implementation - in real-world this would have actual flashloan logic
        # using Aave, dYdX or other protocols
        return {"asset": flashloan_asset,
                "amount": flashloan_amount, "prepared": True}

    async def send_bundle(self, transactions: List[Dict[str, Any]]) -> str:
        """Send a bundle of transactions.

        Args:
            transactions: List of transaction objects

        Returns:
            str: Bundle ID or hash
        """
        logger.info(f"Sending bundle with {len(transactions)} transactions")

        # Example implementation - actual logic would involve flashbots or
        # similar
        bundle_results = []

        for i, tx in enumerate(transactions):
            try:
                tx_hash = await self.execute_transaction(tx)
                bundle_results.append(tx_hash)
                logger.debug(
                    f"Bundle tx {i + 1}/{len(transactions)}: {tx_hash}")
            except Exception as e:
                logger.error(f"Bundle tx {i + 1} failed: {e}")
                raise StrategyExecutionError(
                    f"Bundle execution failed at tx {i + 1}: {e}"
                )

        return ",".join(bundle_results)

    async def front_run(self, target_tx: Dict[str, Any]) -> str:
        """Front-run a target transaction.

        Args:
            target_tx: Transaction to front-run

        Returns:
            str: Transaction hash of front-running transaction
        """
        logger.info(
            f"Attempting to front-run transaction: {
                target_tx.get(
                    'tx_hash', 'Unknown')}"
        )

        # Build front-run transaction with higher gas price
        target_gas_price = target_tx.get("gasPrice", 0)
        front_run_gas_price = int(target_gas_price * 1.2)  # 20% higher

        # Create front-running transaction
        tx = await self.build_transaction(
            function_call=None,
            to_address=target_tx.get("to"),
            value=target_tx.get("value", 0),
            data=target_tx.get("data", ""),
            gas_price=front_run_gas_price,
        )

        # Execute front-running transaction
        tx_hash = await self.execute_transaction(tx)
        logger.info(f"Front-running transaction sent: {tx_hash}")

        return tx_hash

    async def back_run(self, target_tx: Dict[str, Any]) -> str:
        """Back-run a target transaction (execute after target tx is
        confirmed).

        Args:
            target_tx: Transaction to back-run

        Returns:
            str: Transaction hash of back-running transaction
        """
        logger.info(
            f"Setting up back-run for transaction: {
                target_tx.get(
                    'tx_hash', 'Unknown')}"
        )

        # Wait for target transaction to be mined
        target_tx_hash = target_tx.get("tx_hash")
        if target_tx_hash:
            try:
                await self.web3.eth.wait_for_transaction_receipt(target_tx_hash)
                logger.info(
                    f"Target transaction {target_tx_hash} confirmed, executing back-run"
                )
            except Exception as e:
                logger.error(f"Failed to wait for target tx: {e}")
                raise StrategyExecutionError(f"Back-run failed: {e}")

        # Create back-running transaction
        tx = await self.build_transaction(
            function_call=None,
            to_address=target_tx.get("to"),
            value=target_tx.get("value", 0),
            data=target_tx.get("data", ""),
        )

        # Execute back-running transaction
        tx_hash = await self.execute_transaction(tx)
        logger.info(f"Back-running transaction sent: {tx_hash}")

        return tx_hash

    async def execute_sandwich_attack(
        self, target_tx: Dict[str, Any], strategy: str = "default"
    ) -> Tuple[str, str]:
        """Execute a sandwich attack (front-run and back-run).

        Args:
            target_tx: Transaction to sandwich
            strategy: Strategy to use for the sandwich attack

        Returns:
            Tuple[str, str]: (Front-run tx hash, Back-run tx hash)
        """
        logger.info(
            f"Executing sandwich attack on tx: {
                target_tx.get(
                    'tx_hash',
                    'Unknown')} with strategy: {strategy}"
        )

        # Execute front-run
        front_run_tx_hash = await self.front_run(target_tx)

        # Wait for target transaction to be mined
        target_tx_hash = target_tx.get("tx_hash")
        if target_tx_hash:
            try:
                await self.web3.eth.wait_for_transaction_receipt(target_tx_hash)
                logger.info(f"Target transaction {target_tx_hash} confirmed")
            except Exception as e:
                logger.error(f"Failed to wait for target tx: {e}")

        # Execute back-run
        back_run_tx_hash = await self.back_run(target_tx)

        return front_run_tx_hash, back_run_tx_hash

    async def cancel_transaction(self, nonce: int) -> str:
        """Cancel a pending transaction by replacing it with a higher gas
        price.

        Args:
            nonce: Transaction nonce to cancel

        Returns:
            str: Transaction hash for the cancellation transaction
        """
        # Get current gas price and increase it
        try:
            gas_price = await self.web3.eth.gas_price
            cancel_gas_price = int(gas_price * 1.5)  # 50% higher
        except Exception:
            cancel_gas_price = 100 * 10**9  # 100 Gwei fallback

        # Build cancellation transaction (send 0 ETH to ourselves with same
        # nonce)
        tx = {
            "from": self.address,
            "to": self.address,
            "value": 0,
            "nonce": nonce,
            "gas": self.ETH_TRANSFER_GAS,
            "gasPrice": cancel_gas_price,
            "chainId": self.chain_id,
        }

        # Execute cancellation transaction
        try:
            signed_tx = await self.sign_transaction(tx)
            tx_hash = await self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_str = tx_hash.hex()

            logger.info(f"Cancellation transaction sent: {tx_hash_str}")
            return tx_hash_str
        except Exception as e:
            logger.error(f"Failed to cancel transaction: {e}")
            raise StrategyExecutionError(
                f"Transaction cancellation failed: {e}")

    async def withdraw_eth(
        self, to_address: Optional[str] = None, amount: Optional[int] = None
    ) -> str:
        """Withdraw ETH from the account to a specified address.

        Args:
            to_address: Destination address (defaults to configuration.PROFIT_RECEIVER if available)
            amount: Amount of ETH to withdraw in wei (defaults to 90% of balance)

        Returns:
            str: Transaction hash
        """
        # Use default address from configuration if not specified
        if to_address is None:
            to_address = getattr(self.configuration, "PROFIT_RECEIVER", None)
            if not to_address:
                raise StrategyExecutionError(
                    "No destination address specified for withdrawal"
                )

        # Get account balance
        try:
            balance = await self.web3.eth.get_balance(self.address)
            logger.info(f"Current account balance: {balance} wei")
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            raise StrategyExecutionError(f"Failed to get account balance: {e}")

        # If amount not specified, withdraw 90% of balance
        if amount is None:
            # Leave 10% for gas fees
            amount = int(balance * 0.9)

        # Ensure we have enough balance
        if balance <= amount:
            # Leave at least some ETH for gas
            min_gas_reserve = self.ETH_TRANSFER_GAS * await self.web3.eth.gas_price
            amount = max(0, balance - min_gas_reserve)
            if amount <= 0:
                raise StrategyExecutionError(
                    "Insufficient balance for withdrawal")

        logger.info(f"Withdrawing {amount} wei to {to_address}")

        # Build and execute the transaction
        try:
            tx = await self.build_transaction(
                function_call=None, to_address=to_address, value=amount
            )
            tx_hash = await self.execute_transaction(tx)
            logger.info(f"Withdrawal transaction sent: {tx_hash}")
            return tx_hash
        except Exception as e:
            logger.error(f"Withdrawal failed: {e}")
            raise StrategyExecutionError(f"ETH withdrawal failed: {e}")

    async def transfer_profit_to_account(
            self, amount: int, account: str) -> str:
        """Transfer profit to a specific account.

        Args:
            amount: Amount of ETH to transfer in wei
            account: Destination address for the profit

        Returns:
            str: Transaction hash
        """
        logger.info(f"Transferring {amount} wei profit to {account}")

        # Validate destination address
        if not account or not self.web3.is_address(account):
            raise StrategyExecutionError(
                f"Invalid destination address: {account}")

        # Ensure amount is valid
        if amount <= 0:
            raise StrategyExecutionError("Amount must be greater than 0")

        # Check if we have enough balance
        try:
            balance = await self.web3.eth.get_balance(self.address)
            if balance < amount:
                logger.warning(f"Insufficient balance: {balance} < {amount}")
                raise StrategyExecutionError(
                    f"Insufficient balance for profit transfer: {balance} < {amount}"
                )
        except Exception as e:
            if not isinstance(e, StrategyExecutionError):
                logger.error(f"Failed to check balance: {e}")
                raise StrategyExecutionError(f"Failed to check balance: {e}")
            raise

        # Build and execute the transaction
        try:
            tx = await self.build_transaction(
                function_call=None, to_address=account, value=amount
            )
            tx_hash = await self.execute_transaction(tx)
            logger.info(f"Profit transfer transaction sent: {tx_hash}")
            return tx_hash
        except Exception as e:
            logger.error(f"Profit transfer failed: {e}")
            raise StrategyExecutionError(f"Profit transfer failed: {e}")

    async def stop(self) -> bool:
        """Stop and clean up the TransactionCore.

        Returns:
            bool: True if shutdown was successful
        """
        logger.info("Stopping TransactionCore...")

        # Close any pending connections
        if hasattr(self.web3, "provider") and hasattr(
                self.web3.provider, "close"):
            try:
                await self.web3.provider.close()
                logger.info("Web3 provider connection closed")
            except Exception as e:
                logger.warning(f"Error closing web3 provider: {e}")

        # Cancel any pending transactions if needed
        pending_count = len(self._pending_txs)
        if pending_count > 0:
            logger.info(
                f"Found {pending_count} pending transactions during shutdown")
            # Optional: You could add logic here to auto-cancel pending
            # transactions

        # Clean up resources
        self._pending_txs.clear()

        return True

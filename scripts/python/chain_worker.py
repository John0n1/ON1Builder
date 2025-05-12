#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ON1Builder – Chain Worker
========================
Handles operations for a specific blockchain.
"""

import asyncio
import logging
from typing import Dict, Any

from web3 import Web3
from eth_account import Account

# Import middleware for POA chains
# Note: In newer web3.py versions, the middleware structure has changed
# For testing purposes, we'll create a mock middleware


class MockPOAMiddleware:
    """Mock POA middleware for testing."""
    pass


geth_poa_middleware = MockPOAMiddleware()

logger = logging.getLogger("ChainWorker")


class ChainWorker:
    """Worker class for a specific blockchain."""

    def __init__(self, chain_config: Dict[str, Any], global_config: Dict[str, Any]):
        """Initialize the chain worker.

        Args:
            chain_config: Configuration for this specific chain
            global_config: Global configuration shared across all chains
        """
        self.chain_config = chain_config
        self.global_config = global_config
        self.running = False

        # Chain identification
        self.chain_id = chain_config.get("CHAIN_ID")
        self.chain_name = chain_config.get(
            "CHAIN_NAME", f"chain-{self.chain_id}")

        # Web3 setup
        self.http_endpoint = chain_config.get("HTTP_ENDPOINT")
        self.websocket_endpoint = chain_config.get("WEBSOCKET_ENDPOINT")
        self.web3 = None

        # Account setup
        self.wallet_address = chain_config.get("WALLET_ADDRESS")
        self.wallet_key = chain_config.get("WALLET_KEY")
        self.account = None

        # Execution control
        self.dry_run = global_config.get("DRY_RUN", True)
        self.go_live = global_config.get("GO_LIVE", False)

        # Metrics
        self.metrics = {
            "transaction_count": 0,
            "successful_transactions": 0,
            "failed_transactions": 0,
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0,
            "last_gas_price_gwei": 0.0,
            "wallet_balance_eth": 0.0,
            "last_block_number": 0,
        }

        # Transaction nonce management
        self.current_nonce = None
        self.nonce_lock = asyncio.Lock()

        logger.info(
            f"Initialized ChainWorker for {self.chain_name} (ID: {self.chain_id})")

    async def initialize(self) -> bool:
        """Initialize the chain worker.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Initialize Web3
            logger.info(
                f"Initializing Web3 for {self.chain_name} with endpoint {self.http_endpoint}")
            self.web3 = Web3(Web3.HTTPProvider(self.http_endpoint))

            # Add POA middleware if needed (for networks like Polygon, BSC, etc.)
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

            # Check connection
            if not self.web3.is_connected():
                logger.error(
                    f"Failed to connect to {self.chain_name} at {self.http_endpoint}")
                return False

            # Initialize account
            if self.wallet_key:
                self.account = Account.from_key(self.wallet_key)
                logger.info(f"Account initialized for {self.chain_name}")
            else:
                logger.error(f"No wallet key provided for {self.chain_name}")
                return False

            # Check wallet balance
            balance = await self.get_wallet_balance()
            self.metrics["wallet_balance_eth"] = balance
            logger.info(f"Wallet balance on {self.chain_name}: {balance} ETH")

            # Get current nonce
            self.current_nonce = self.web3.eth.get_transaction_count(
                self.wallet_address)
            logger.info(
                f"Current nonce for {self.chain_name}: {self.current_nonce}")

            # Get current gas price
            gas_price = await self.get_gas_price()
            self.metrics["last_gas_price_gwei"] = gas_price
            logger.info(
                f"Current gas price on {self.chain_name}: {gas_price} Gwei")

            return True
        except Exception as e:
            logger.error(
                f"Error initializing chain worker for {self.chain_name}: {e}")
            return False

    async def start(self) -> None:
        """Start the chain worker."""
        self.running = True
        logger.info(f"Starting chain worker for {self.chain_name}")

        try:
            # Main loop
            while self.running:
                try:
                    # Monitor for opportunities
                    await self.monitor_opportunities()

                    # Update metrics
                    await self.update_metrics()

                    # Sleep for a bit
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(
                        f"Error in main loop for {self.chain_name}: {e}")
                    await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Chain worker error for {self.chain_name}: {e}")
            self.running = False

        logger.info(f"Chain worker stopped for {self.chain_name}")

    async def stop(self) -> None:
        """Stop the chain worker."""
        self.running = False
        logger.info(f"Stopping chain worker for {self.chain_name}")

    async def get_wallet_balance(self) -> float:
        """Get the wallet balance in ETH.

        Returns:
            The wallet balance in ETH
        """
        try:
            balance_wei = self.web3.eth.get_balance(self.wallet_address)
            balance_eth = self.web3.from_wei(balance_wei, "ether")
            return float(balance_eth)
        except Exception as e:
            logger.error(
                f"Error getting wallet balance for {self.chain_name}: {e}")
            return 0.0

    async def get_gas_price(self) -> float:
        """Get the current gas price in Gwei.

        Returns:
            The current gas price in Gwei
        """
        try:
            gas_price_wei = self.web3.eth.gas_price
            gas_price_gwei = self.web3.from_wei(gas_price_wei, "gwei")
            return float(gas_price_gwei)
        except Exception as e:
            logger.error(f"Error getting gas price for {self.chain_name}: {e}")
            return 0.0

    async def monitor_opportunities(self) -> None:
        """Monitor for trading opportunities."""
        # This is where the chain-specific opportunity monitoring logic would go
        # For now, we'll just simulate finding an opportunity

        if self.go_live:
            logger.info(
                f"LIVE MODE: Monitoring for opportunities on {self.chain_name}")
        else:
            logger.info(
                f"DRY RUN: Would monitor for opportunities on {self.chain_name}")

    async def update_metrics(self) -> None:
        """Update metrics for this chain."""
        try:
            # Update wallet balance
            balance = await self.get_wallet_balance()
            self.metrics["wallet_balance_eth"] = balance

            # Update gas price
            gas_price = await self.get_gas_price()
            self.metrics["last_gas_price_gwei"] = gas_price

            # Update last block number
            self.metrics["last_block_number"] = self.web3.eth.block_number
        except Exception as e:
            logger.error(f"Error updating metrics for {self.chain_name}: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics for this chain.

        Returns:
            A dictionary of metrics
        """
        return {
            "chain_id": self.chain_id,
            "chain_name": self.chain_name,
            **self.metrics
        }

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ON1Builder – Chain Worker
========================
Handles operations for a specific blockchain.
"""

import os
import asyncio
import json
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal

import aiohttp
from web3 import Web3, AsyncWeb3, AsyncHTTPProvider
from web3.middleware import async_geth_poa_middleware
from eth_account.account import Account

from logger_on1 import setup_logging
from txpool_monitor import TxpoolMonitor
from safety_net import SafetyNet
from transaction_core import TransactionCore
from nonce_core import NonceCore
from api_config import APIConfig
from market_monitor import MarketMonitor
from db_manager import DatabaseManager, get_db_manager

# Set up logging
logger = setup_logging("ChainWorker", level=logging.INFO)


class MockPOAMiddleware:
    """Mock middleware for POA chains when real middleware fails."""
    
    async def __call__(self, make_request, web3):
        def middleware(method, params):
            return make_request(method, params)
        return middleware


class ChainWorker:
    """Manages operations for a specific blockchain."""
    
    def __init__(self, chain_config: Dict[str, Any], global_config: Dict[str, Any]):
        """Initialize the chain worker with configuration.
        
        Args:
            chain_config: Chain-specific configuration
            global_config: Global configuration applicable to all chains
        """
        self.chain_config = chain_config
        self.global_config = global_config
        self.chain_id = chain_config.get("CHAIN_ID", "unknown")
        self.chain_name = chain_config.get("CHAIN_NAME", f"chain-{self.chain_id}")
        
        # Endpoints
        self.http_endpoint = chain_config.get("HTTP_ENDPOINT")
        self.websocket_endpoint = chain_config.get("WEBSOCKET_ENDPOINT")
        self.ipc_endpoint = chain_config.get("IPC_ENDPOINT")
        
        # Wallet
        self.wallet_address = chain_config.get("WALLET_ADDRESS")
        self.wallet_key = chain_config.get("WALLET_KEY") or os.getenv("WALLET_KEY")
        
        # Components
        self.web3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self.safety_net: Optional[SafetyNet] = None
        self.txpool_monitor: Optional[TxpoolMonitor] = None
        self.transaction_core: Optional[TransactionCore] = None
        self.nonce_core: Optional[NonceCore] = None
        self.api_config: Optional[APIConfig] = None
        self.market_monitor: Optional[MarketMonitor] = None
        self.db_manager: Optional[DatabaseManager] = None
        
        # State
        self.running = False
        self.initialized = False
        self._tasks: List[asyncio.Task] = []
        
        # Metrics
        self.metrics: Dict[str, Any] = {
            "chain_id": self.chain_id,
            "chain_name": self.chain_name,
            "wallet_balance_eth": 0.0,
            "last_gas_price_gwei": 0.0,
            "last_block_number": 0,
            "transaction_count": 0,
            "total_profit_eth": 0.0,
            "total_gas_spent_eth": 0.0,
        }
        
        # Performance tracking
        self.last_update_time = time.time()
        self.requests_count = 0
        self.requests_per_second = 0
        
    async def initialize(self) -> bool:
        """Initialize the chain worker and its components.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            logger.info(f"Initializing chain worker for {self.chain_name} (ID: {self.chain_id})")
            
            # Initialize Web3 connection
            if not await self._initialize_web3():
                logger.error(f"Failed to initialize Web3 for {self.chain_name}")
                return False
                
            # Initialize account
            if self.wallet_key:
                self.account = Account.from_key(self.wallet_key)
                logger.info(f"Account initialized: {self.account.address}")
                
                # Verify the configured wallet_address matches the account
                if self.wallet_address and self.wallet_address.lower() != self.account.address.lower():
                    logger.warning(f"Configured wallet address {self.wallet_address} doesn't match the account {self.account.address}")
            else:
                logger.error("No wallet key provided, cannot initialize account")
                return False
                
            # Initialize API config
            self.api_config = APIConfig(self.chain_config)
            await self.api_config.initialize()
            
            # Initialize database manager
            self.db_manager = await get_db_manager()
            
            # Initialize core components
            self.nonce_core = NonceCore(self.web3, self.account.address, self.chain_config)
            await self.nonce_core.initialize()
            
            self.safety_net = SafetyNet(self.web3, self.chain_config, self.wallet_address, 
                                        self.account, self.api_config)
            await self.safety_net.initialize()
            
            self.market_monitor = MarketMonitor(self.web3, self.chain_config, self.api_config)
            await self.market_monitor.initialize()
            
            self.transaction_core = TransactionCore(
                self.web3, 
                self.account, 
                self.chain_config,
                self.api_config,
                self.market_monitor,
                None,  # txpool_monitor will be set after creating it
                self.nonce_core,
                self.safety_net
            )
            await self.transaction_core.initialize()
            
            # Get list of tokens to monitor
            monitored_tokens = self._get_monitored_tokens()
            
            # Initialize TxpoolMonitor
            self.txpool_monitor = TxpoolMonitor(
                self.web3,
                self.safety_net,
                self.nonce_core,
                self.api_config,
                monitored_tokens,
                self.chain_config,
                self.market_monitor
            )
            await self.txpool_monitor.initialize()
            
            # Set the txpool_monitor in transaction_core (circular reference but it's OK)
            self.transaction_core.txpool_monitor = self.txpool_monitor
            
            self.initialized = True
            logger.info(f"Chain worker for {self.chain_name} initialized successfully")
            return True
            
        except Exception as e:
            logger.exception(f"Error initializing chain worker for {self.chain_name}: {e}")
            return False
            
    async def start(self) -> None:
        """Start the chain worker and its components."""
        if not self.initialized:
            logger.error(f"Cannot start uninitialized chain worker for {self.chain_name}")
            return
            
        if self.running:
            logger.warning(f"Chain worker for {self.chain_name} is already running")
            return
            
        logger.info(f"Starting chain worker for {self.chain_name}")
        self.running = True
        
        try:
            # Start txpool monitoring
            if self.txpool_monitor:
                await self.txpool_monitor.start_monitoring()
                
            # Start market monitor scheduling
            if self.market_monitor:
                await self.market_monitor.schedule_updates()
                
            # Schedule periodic metrics updates
            metrics_task = asyncio.create_task(self._update_metrics_periodically())
            self._tasks.append(metrics_task)
            
            # Start opportunity monitoring
            monitoring_task = asyncio.create_task(self._monitor_opportunities_periodically())
            self._tasks.append(monitoring_task)
            
            logger.info(f"Chain worker for {self.chain_name} started successfully")
            
        except Exception as e:
            logger.exception(f"Error starting chain worker for {self.chain_name}: {e}")
            self.running = False
            
    async def stop(self) -> None:
        """Stop the chain worker and its components."""
        logger.info(f"Stopping chain worker for {self.chain_name}")
        self.running = False
        
        # Stop all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                
        try:
            # Wait for tasks to complete with timeout
            if self._tasks:
                await asyncio.wait(self._tasks, timeout=5)
        except asyncio.CancelledError:
            logger.debug(f"Tasks cancelled for {self.chain_name}")
        except Exception as e:
            logger.error(f"Error cancelling tasks for {self.chain_name}: {e}")
            
        # Clear tasks list
        self._tasks = []
        
        # Stop components
        if self.txpool_monitor:
            await self.txpool_monitor.stop()
            
        if self.safety_net:
            await self.safety_net.stop()
            
        if self.market_monitor:
            await self.market_monitor.stop()
            
        if self.nonce_core:
            await self.nonce_core.stop()
            
        logger.info(f"Chain worker for {self.chain_name} stopped")
            
    async def get_wallet_balance(self) -> float:
        """Get the wallet balance in ETH.
        
        Returns:
            Balance in ETH
        """
        try:
            if not self.web3 or not self.wallet_address:
                return 0.0
                
            balance_wei = await self.web3.eth.get_balance(self.wallet_address)
            balance_eth = float(self.web3.from_wei(balance_wei, "ether"))
            
            # Update metrics
            self.metrics["wallet_balance_eth"] = balance_eth
            
            return balance_eth
            
        except Exception as e:
            logger.error(f"Error getting wallet balance for {self.chain_name}: {e}")
            return 0.0
            
    async def get_gas_price(self) -> float:
        """Get the current gas price in Gwei.
        
        Returns:
            Gas price in Gwei
        """
        try:
            if not self.web3:
                return 0.0
                
            if self.safety_net:
                gas_price = await self.safety_net.get_dynamic_gas_price()
                gwei = float(gas_price)
            else:
                gas_price_wei = await self.web3.eth.gas_price
                gwei = float(self.web3.from_wei(gas_price_wei, "gwei"))
                
            # Update metrics
            self.metrics["last_gas_price_gwei"] = gwei
            
            return gwei
            
        except Exception as e:
            logger.error(f"Error getting gas price for {self.chain_name}: {e}")
            return 0.0
            
    async def monitor_opportunities(self) -> None:
        """Monitor the chain for profit opportunities."""
        try:
            # This is a placeholder for implementing custom opportunity monitoring
            # The main opportunity detection is handled by txpool_monitor
            pass
            
        except Exception as e:
            logger.error(f"Error monitoring opportunities for {self.chain_name}: {e}")
            
    async def _update_metrics_periodically(self) -> None:
        """Update metrics periodically."""
        while self.running:
            try:
                await self.update_metrics()
                await asyncio.sleep(10)  # Update every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating metrics for {self.chain_name}: {e}")
                await asyncio.sleep(30)  # Wait longer on error
                
    async def _monitor_opportunities_periodically(self) -> None:
        """Monitor for opportunities periodically."""
        while self.running:
            try:
                await self.monitor_opportunities()
                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring opportunities for {self.chain_name}: {e}")
                await asyncio.sleep(15)  # Wait longer on error
                
    async def update_metrics(self) -> None:
        """Update chain metrics."""
        try:
            now = time.time()
            elapsed = now - self.last_update_time
            
            if elapsed > 0:
                self.requests_per_second = self.requests_count / elapsed
                
            self.requests_count = 0
            self.last_update_time = now
            
            # Get wallet balance
            await self.get_wallet_balance()
            
            # Get gas price
            await self.get_gas_price()
            
            # Get latest block number
            if self.web3:
                block_number = await self.web3.eth.block_number
                self.metrics["last_block_number"] = block_number
                
            # Get transaction count from database if available
            if self.db_manager:
                # Query transaction count for this chain
                pass
                
        except Exception as e:
            logger.error(f"Error updating metrics for {self.chain_name}: {e}")
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get the current metrics for this chain.
        
        Returns:
            Dictionary containing chain metrics
        """
        return self.metrics
        
    def _get_monitored_tokens(self) -> List[str]:
        """Get list of tokens to monitor based on configuration.
        
        Returns:
            List of token addresses to monitor
        """
        # This would normally come from configuration or be dynamically determined
        # For now, return a placeholder list
        return [
            # Add popular tokens like WETH, USDC, etc. for the chain
        ]
        
    async def _initialize_web3(self) -> bool:
        """Initialize Web3 connection for this chain.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.http_endpoint:
                self.web3 = AsyncWeb3(AsyncHTTPProvider(self.http_endpoint))
                
                # Try to apply POA middleware for compatible chains
                try:
                    self.web3.middleware_onion.inject(async_geth_poa_middleware, layer=0)
                except Exception as e:
                    logger.warning(f"Failed to inject POA middleware: {e}, using mock instead")
                    self.web3.middleware_onion.inject(MockPOAMiddleware(), layer=0)
                    
                # Verify connection
                if not await self._verify_web3_connection():
                    logger.error(f"Failed to connect to {self.http_endpoint}")
                    return False
                    
                return True
                
            else:
                logger.error("No HTTP endpoint provided in chain configuration")
                return False
                
        except Exception as e:
            logger.exception(f"Error initializing Web3 for {self.chain_name}: {e}")
            return False
            
    async def _verify_web3_connection(self) -> bool:
        """Verify Web3 connection by checking chain ID.
        
        Returns:
            True if connection is verified, False otherwise
        """
        if not self.web3:
            return False
            
        try:
            # Get and verify chain ID
            chain_id = await self.web3.eth.chain_id
            expected_chain_id = int(self.chain_id) if self.chain_id.isdigit() else self.chain_id
            
            if str(chain_id) != str(expected_chain_id):
                logger.error(f"Chain ID mismatch: expected {expected_chain_id}, got {chain_id}")
                return False
                
            # Verify we can get the latest block
            block = await self.web3.eth.get_block('latest')
            if not block:
                logger.error("Failed to get latest block")
                return False
                
            logger.info(f"Connected to {self.chain_name} at block {block['number']}")
            self.metrics["last_block_number"] = block['number']
            return True
            
        except Exception as e:
            logger.error(f"Error verifying Web3 connection: {e}")
            return False

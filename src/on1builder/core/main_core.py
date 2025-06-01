#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – MainCore
=====================
Boot-straps every long-lived component, owns the single AsyncIO event-loop,
and exposes `.run()`, `.stop()`, and `.connect()` for callers (CLI, Flask UI, tests).
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
import tracemalloc
from typing import Any, Dict, List, Optional
from pathlib import Path

from eth_account import Account
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import AsyncHTTPProvider, IPCProvider, WebSocketProvider

from on1builder.config.config import APIConfig, Configuration
from on1builder.core.nonce_core import NonceCore
from on1builder.core.transaction_core import TransactionCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.engines.strategy_net import StrategyNet
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.monitoring.txpool_monitor import TxpoolMonitor
from on1builder.utils.logger import setup_logging
from on1builder.utils.strategyexecutionerror import StrategyExecutionError


logger = setup_logging(__name__, level="DEBUG", log_dir="none")

_POA_CHAINS: set[int] = {99, 100, 77, 7766, 56, 11155111}


class MainCore:
    logger = logger

    def __init__(self, configuration: Configuration) -> None:
        self.cfg = configuration
        self.web3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self._bg: List[asyncio.Task[Any]] = []
        self._running_evt = asyncio.Event()
        self._stop_evt = asyncio.Event()
        self.components: Dict[str, Any] = {}
        self.component_health: Dict[str, bool] = {}

        if not tracemalloc.is_tracing():
            tracemalloc.start()
        self._mem_snapshot = tracemalloc.take_snapshot()

    async def connect(self) -> bool:
        conn = self._connect_web3()
        web3 = await conn if inspect.isawaitable(conn) else conn

        try:
            connected = await web3.is_connected()
        except TypeError:
            connected = web3.is_connected()

        if connected:
            self.web3 = web3
            return True
        return False

    async def connect_websocket(self) -> bool:
        if not self.web3:
            logger.error("Web3.py is not installed")
            return False

        if not getattr(self.cfg, "WEBSOCKET_ENDPOINT", None):
            logger.warning("No WebSocket endpoint configured")
            return False

        retry_count = getattr(self.cfg, "CONNECTION_RETRY_COUNT", 3)
        retry_delay = getattr(self.cfg, "CONNECTION_RETRY_DELAY", 1.0)

        for attempt in range(retry_count + 1):
            try:
                provider = WebSocketProvider(self.cfg.WEBSOCKET_ENDPOINT)
                web3 = AsyncWeb3(provider)

                if hasattr(web3.eth, "chain_id"):
                    try:
                        chain_id = await web3.eth.chain_id
                    except TypeError:
                        chain_id = 1
                else:
                    chain_id = 1

                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")

                if hasattr(web3.is_connected, "__await__"):
                    connected = await web3.is_connected()
                else:
                    connected = web3.is_connected()

                if connected:
                    self.web3 = web3
                    logger.info(f"Connected to WebSocket endpoint: {self.cfg.WEBSOCKET_ENDPOINT}")
                    return True

            except Exception as e:
                if attempt < retry_count:
                    logger.warning(f"WebSocket connection attempt {attempt + 1}/{retry_count + 1} failed: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"All WebSocket connection attempts failed: {e}")
                    return False

        return False

    async def run(self) -> None:
        await self._bootstrap()
        self._running_evt.set()
        self._bg = []

        if "txpool_monitor" in self.components:
            self._bg.append(asyncio.create_task(self.components["txpool_monitor"].start_monitoring(), name="MM_run"))

        self._bg.append(asyncio.create_task(self._tx_processor(), name="TX_proc"))
        self._bg.append(asyncio.create_task(self._heartbeat(), name="Heartbeat"))

        try:
            await asyncio.shield(self._stop_evt.wait())
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.stop()
            logger.info("MainCore run() finished")

    async def stop(self) -> None:
        if self._stop_evt.is_set():
            return
        self._stop_evt.set()
        logger.info("MainCore stopping...")

        for task in self._bg:
            if not task.done():
                task.cancel()

        if self._bg:
            try:
                await asyncio.gather(*self._bg, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error during task shutdown: {e}")

        if getattr(self.web3, "provider", None) and hasattr(self.web3.provider, "disconnect"):
            try:
                await self.web3.provider.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting web3 provider: {e}")

        # First close components that have stop method
        for name, component in self.components.items():
            if hasattr(component, "stop") and callable(component.stop):
                try:
                    await component.stop()
                    logger.debug(f"Component {name} stopped")
                except Exception as e:
                    logger.error(f"Error stopping component {name}: {e}")
        
        # Special handling for APIConfig which needs close() to be called to clean up sessions
        if "api_config" in self.components:
            try:
                api_config = self.components["api_config"]
                if hasattr(api_config, "close") and callable(api_config.close):
                    await api_config.close()
                    logger.debug("API Config closed and cleaned up")
            except Exception as e:
                logger.error(f"Error closing API Config: {e}")

        self._bg = []
        logger.info("MainCore stopped")

    async def _bootstrap(self) -> None:
        logger.info("Bootstrapping components...")
        await self.cfg.load()

        self.web3 = await self._connect_web3()
        if not self.web3:
            raise StrategyExecutionError("Failed to create Web3 connection")

        self.account = await self._create_account()
        if not self.account:
            raise StrategyExecutionError("Failed to create account")

        # Initialize core data services first
        self.components["api_config"] = await self._mk_api_config()
        self.components["abi_registry"] = await self._mk_abi_registry()
        
        # Initialize notification system
        try:
            self.components["notification_manager"] = await self._mk_notification_manager()
        except Exception as e:
            logger.warning(f"Notification manager initialization error: {e}")
            logger.warning("Continuing without notification support")
        
        # Initialize persistence layer (optional, will auto-initialize if needed)
        try:
            self.components["db_manager"] = await self._mk_db_manager()
        except Exception as e:
            logger.warning(f"Database manager initialization error: {e}")
            logger.warning("Continuing without database persistence")
        
        # Initialize core components
        self.components["nonce_core"] = await self._mk_nonce_core()
        self.components["safety_net"] = await self._mk_safety_net()
        self.components["transaction_core"] = await self._mk_txcore()
        self.components["market_monitor"] = await self._mk_market_monitor()
        self.components["txpool_monitor"] = await self._mk_txpool_monitor()
        self.components["strategy_net"] = await self._mk_strategy_net()

        logger.info("All components initialized")

    async def _connect_web3(self) -> Optional[AsyncWeb3]:
        return await self._create_web3_connection()

    async def _mk_api_config(self) -> APIConfig:
        api = APIConfig(self.cfg)
        await api.initialize()
        return api

    async def _mk_nonce_core(self) -> NonceCore:
        return await self._create_nonce_core()

    async def _mk_safety_net(self) -> SafetyNet:
        return await self._create_safety_net()

    async def _mk_txcore(self) -> TransactionCore:
        return await self._create_transaction_core()

    async def _mk_market_monitor(self) -> MarketMonitor:
        return await self._create_market_monitor()

    async def _mk_txpool_monitor(self) -> TxpoolMonitor:
        return await self._create_txpool_monitor()

    async def _mk_strategy_net(self) -> StrategyNet:
        return await self._create_strategy_net()

    async def _mk_abi_registry(self) -> Any:
        """Initialize and return the ABI Registry.
        
        The ABI Registry loads and manages smart contract ABIs for all components.
        """
        from on1builder.integrations.abi_registry import get_registry
        
        try:
            # Use the specific resources/abi path for ABIs
            base_path = Path(self.cfg.get("BASE_PATH", "."))
            abi_path = base_path / "resources" / "abi"
            
            if not abi_path.exists():
                logger.warning(f"ABI path not found: {abi_path}")
                abi_path = base_path  # Fallback to base path
            
            # Handle non-ABI JSON files that might cause issues
            strategy_weights_path = Path("strategy_weights.json")
            if strategy_weights_path.exists():
                # Temporarily rename the file to prevent loading it as an ABI
                temp_path = Path("strategy_weights.json.bak")
                strategy_weights_path.rename(temp_path)
                
                # Initialize with specific ABI path
                registry = await get_registry(str(abi_path))
                
                # Restore the file
                temp_path.rename(strategy_weights_path)
            else:
                # Standard initialization
                registry = await get_registry(str(abi_path))
            
            logger.info(f"ABI Registry initialized with {len(registry.abis)} contract definitions")
            return registry
        except Exception as e:
            logger.warning(f"ABI Registry initialization error: {e}")
            logger.warning("Continuing with empty ABI registry")
            
            # Create an empty registry as fallback
            from on1builder.integrations.abi_registry import ABIRegistry
            return ABIRegistry()

    async def _mk_db_manager(self) -> Any:
        """Initialize and return the Database Manager.
        
        The Database Manager handles persistent storage of transaction history and profits.
        """
        from on1builder.persistence.db_manager import get_db_manager
        # Initialize with configuration
        db_url = self.cfg.get("DATABASE_URL", "sqlite+aiosqlite:///on1builder.db")
        # Retrieve singleton DatabaseManager
        db_manager = get_db_manager(self.cfg, db_url)
        # Ensure tables are created
        try:
            await db_manager.initialize()
        except Exception as e:
            logger.warning(f"DatabaseManager initialization error: {e}")
        logger.info("Database Manager initialized")
        return db_manager

    async def _mk_notification_manager(self) -> Any:
        """Initialize and return the Notification Manager.
        
        This manages sending alerts and notifications through configured channels (Slack, Email, etc.)
        """
        from on1builder.utils.notifications import get_notification_manager
        
        # Initialize notification manager with our configuration
        notification_manager = get_notification_manager(self.cfg)
        logger.info("Notification Manager initialized")
        return notification_manager

    async def _create_web3_connection(self) -> Optional[AsyncWeb3]:
        try:
            if self.cfg.HTTP_ENDPOINT:
                provider = AsyncHTTPProvider(self.cfg.HTTP_ENDPOINT)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                logger.info(f"Connected to HTTP endpoint: {self.cfg.HTTP_ENDPOINT}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to HTTP endpoint: {e}")

        try:
            if self.cfg.WEBSOCKET_ENDPOINT:
                provider = WebSocketProvider(self.cfg.WEBSOCKET_ENDPOINT)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                logger.info(f"Connected to WebSocket endpoint: {self.cfg.WEBSOCKET_ENDPOINT}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to WebSocket endpoint: {e}")

        try:
            if self.cfg.IPC_ENDPOINT:
                provider = IPCProvider(self.cfg.IPC_ENDPOINT)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                logger.info(f"Connected to IPC endpoint: {self.cfg.IPC_ENDPOINT}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to IPC endpoint: {e}")

        logger.error("Failed to connect to any Web3 endpoint")
        return None

    async def _create_account(self) -> Optional[Account]:
        if hasattr(self.cfg, "WALLET_KEY") and self.cfg.WALLET_KEY:
            return Account.from_key(self.cfg.WALLET_KEY)
        logger.error("No WALLET_KEY provided in configuration")
        return None

    async def _create_nonce_core(self) -> NonceCore:
        nonce_core = NonceCore(
            web3=self.web3, 
            configuration=self.cfg,
            main_core=self  # Pass reference to MainCore for shared resources
        )
        await nonce_core.initialize()
        return nonce_core

    async def _create_safety_net(self) -> SafetyNet:
        # Pass reference to self (MainCore) to allow SafetyNet to access shared resources
        safety_net = SafetyNet(
            web3=self.web3, 
            config=self.cfg, 
            account=self.account,
            api_config=self.components.get("api_config"),
            main_core=self
        )
        await safety_net.initialize()
        return safety_net

    async def _create_transaction_core(self) -> TransactionCore:
        chain_id = await self.web3.eth.chain_id if self.web3 else 1
        tx_core = TransactionCore(
            web3=self.web3,
            account=self.account,
            configuration=self.cfg,
            nonce_core=self.components.get("nonce_core"),
            safety_net=self.components.get("safety_net"),
            api_config=self.components.get("api_config"),
            market_monitor=self.components.get("market_monitor"),
            txpool_monitor=self.components.get("txpool_monitor"),
            chain_id=chain_id,
            main_core=self  # Pass reference to MainCore for shared components
        )
        await tx_core.initialize()
        return tx_core

    async def _create_market_monitor(self) -> MarketMonitor:
        market_monitor = MarketMonitor(self.web3, self.cfg, self.components["api_config"])
        await market_monitor.initialize()
        return market_monitor

    async def _create_txpool_monitor(self) -> TxpoolMonitor:
        # Get the list of monitored tokens from config
        monitored_tokens_config = self.cfg.get("MONITORED_TOKENS", [])
        monitored_tokens = []
        
        # Check if the value is a string (likely a file path)
        if isinstance(monitored_tokens_config, str):
            # If it's a file path, try to load it
            if os.path.exists(monitored_tokens_config):
                try:
                    # Try to load tokens from file
                    with open(monitored_tokens_config, 'r') as f:
                        token_data = json.load(f)
                    
                    # If it's the address2symbol.json format, get the top tokens 
                    # by taking a slice of the keys (addresses) and values (symbols)
                    if isinstance(token_data, dict):
                        # Take top tokens (limit to avoid excessive monitoring)
                        top_tokens = list(token_data.values())[:50]
                        monitored_tokens.extend(top_tokens)
                        logger.info(f"Loaded {len(monitored_tokens)} tokens from {monitored_tokens_config}")
                except Exception as e:
                    logger.error(f"Failed to load monitored tokens from {monitored_tokens_config}: {e}")
        elif isinstance(monitored_tokens_config, list):
            # If it's already a list, use it directly
            monitored_tokens = monitored_tokens_config
            
        # If no valid tokens found, use defaults
        if not monitored_tokens:
            logger.warning("No monitored tokens defined or loaded, using default token list")
            # Use some default tokens like ETH, WETH, etc.
            monitored_tokens = ["ETH", "WETH", "USDC", "USDT", "DAI"]
        
        logger.info(f"Monitoring {len(monitored_tokens)} tokens: {', '.join(monitored_tokens[:10])}...")
        
        txpool_monitor = TxpoolMonitor(
            web3=self.web3,
            safety_net=self.components["safety_net"],
            nonce_core=self.components["nonce_core"],
            api_config=self.components["api_config"],
            monitored_tokens=monitored_tokens,
            configuration=self.cfg,
            market_monitor=self.components["market_monitor"]
        )
        await txpool_monitor.initialize()
        return txpool_monitor

    async def _create_strategy_net(self) -> StrategyNet:
        strategy_net = StrategyNet(
            web3=self.web3,
            config=self.cfg,
            transaction_core=self.components["transaction_core"],
            safety_net=self.components["safety_net"],
            market_monitor=self.components["market_monitor"],
            main_core=self  # Pass reference to MainCore for shared resources
        )
        await strategy_net.initialize()
        return strategy_net

    async def _heartbeat(self) -> None:
        interval = getattr(self.cfg, "HEARTBEAT_INTERVAL", 60)
        memory_report_interval = getattr(self.cfg, "MEMORY_REPORT_INTERVAL", 300)
        health_check_interval = getattr(self.cfg, "HEALTH_CHECK_INTERVAL", 10)

        last_memory_report = 0
        last_health_check = 0

        while not self._stop_evt.is_set():
            try:
                current_time = time.time()
                if current_time - last_health_check >= health_check_interval:
                    await self._check_component_health()
                    last_health_check = current_time

                if current_time - last_memory_report >= memory_report_interval:
                    await self._report_memory_usage()
                    last_memory_report = current_time

                logger.debug("MainCore heartbeat - System operational")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Heartbeat task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
                await asyncio.sleep(5)

    async def _tx_processor(self) -> None:
        interval = getattr(self.cfg, "TX_PROCESSOR_INTERVAL", 5)
        while not self._stop_evt.is_set():
            try:
                logger.debug("Transaction processor checking for new transactions")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Transaction processor task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in transaction processor: {e}")
                await asyncio.sleep(5)

    async def _check_component_health(self) -> None:
        for name, component in self.components.items():
            try:
                if hasattr(component, "check_health") and callable(component.check_health):
                    health_status = await component.check_health()
                    self.component_health[name] = health_status
                    if not health_status:
                        logger.warning(f"Component {name} reports unhealthy state")
                else:
                    self.component_health[name] = True
            except Exception as e:
                logger.error(f"Error checking health of {name}: {e}")
                self.component_health[name] = False

    async def _report_memory_usage(self) -> None:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            return
        try:
            current_snapshot = tracemalloc.take_snapshot()
            top_stats = current_snapshot.compare_to(self._mem_snapshot, "lineno")
            logger.info("Top 10 memory usage differences:")
            for stat in top_stats[:10]:
                logger.info(str(stat))
        except Exception as e:
            logger.error(f"Error generating memory report: {e}")

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
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from eth_account import Account
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import AsyncHTTPProvider, WebSocketProvider

from ..config.loaders import get_config_loader
from ..config.settings import GlobalSettings, MultiChainSettings
from ..engines.safety_guard import SafetyGuard
from ..engines.strategy_executor import StrategyExecutor
from ..integrations.external_apis import ExternalAPIManager
from ..monitoring.market_data_feed import MarketDataFeed
from ..monitoring.txpool_scanner import TxPoolScanner
from ..utils.custom_exceptions import StrategyExecutionError
from ..utils.logging_config import get_logger
from .nonce_manager import NonceManager
from .transaction_manager import TransactionManager

logger = get_logger(__name__)

_POA_CHAINS: set[int] = {99, 100, 77, 7766, 56, 11155111}


class MainOrchestrator:
    logger = logger

    def __init__(
        self, config: Optional[Union[str, GlobalSettings, Dict[str, Any]]] = None
    ) -> None:
        """Initialize orchestrator with MultiChainSettings or GlobalSettings."""
        # Load configuration
        if isinstance(config, GlobalSettings):
            self.cfg = config
        elif isinstance(config, str):
            # assume multi-chain config file
            self.cfg = get_config_loader().load_multi_chain_config(config)
        elif isinstance(config, dict):
            # raw dict -> GlobalSettings
            self.cfg = GlobalSettings(**config)
        else:
            # default to multi-chain
            self.cfg = get_config_loader().load_multi_chain_config()

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
        web3 = await self._connect_web3()
        if not web3:
            return False

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

        # Get websocket endpoint from chain configuration
        websocket_endpoint = None
        if isinstance(self.cfg, MultiChainSettings) and self.cfg.active_chains:
            chain_name = self.cfg.active_chains[0]
            chain_config = self.cfg.get_chain_config(chain_name)
            websocket_endpoint = (
                chain_config.websocket_endpoint if chain_config else None
            )
        elif self.cfg.chains:
            chain_name = next(iter(self.cfg.chains.keys()))
            chain_config = self.cfg.chains[chain_name]
            websocket_endpoint = chain_config.websocket_endpoint

        if not websocket_endpoint:
            logger.warning("No WebSocket endpoint configured")
            return False

        retry_count = self.cfg.connection_retry_count
        retry_delay = self.cfg.connection_retry_delay

        for attempt in range(retry_count + 1):
            try:
                provider = WebSocketProvider(websocket_endpoint)
                web3 = AsyncWeb3(provider)

                if hasattr(web3.eth, "chain_id"):
                    try:
                        chain_id = await web3.eth.chain_id
                    except TypeError:
                        chain_id = 1
                else:
                    chain_id = 1

                if chain_id in self.cfg.poa_chains:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")

                # Always use async version for consistency
                try:
                    if hasattr(web3.is_connected, "__await__"):
                        connected = await web3.is_connected()
                    else:
                        # Wrap sync call in async context
                        connected = web3.is_connected()
                except Exception as e:
                    logger.warning(f"Failed to check Web3 connection: {e}")
                    connected = False

                if connected:
                    self.web3 = web3
                    logger.info(
                        f"Connected to WebSocket endpoint: {websocket_endpoint}"
                    )
                    return True

            except Exception as e:
                if attempt < retry_count:
                    logger.warning(
                        f"WebSocket connection attempt {attempt + 1}/{retry_count + 1} failed: {e}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"All WebSocket connection attempts failed: {e}")
                    return False

        return False

    async def run(self) -> None:
        await self._bootstrap()
        self._running_evt.set()
        self._bg = []

        logger.info("🚀 ON1Builder MainCore is now RUNNING!")
        logger.info("📊 Starting background monitoring tasks...")

        if "txpool_monitor" in self.components:
            self._bg.append(
                asyncio.create_task(
                    self.components["txpool_monitor"].start_monitoring(), name="MM_run"
                )
            )
            logger.info("✅ TxpoolMonitor task started")

        self._bg.append(asyncio.create_task(self._tx_processor(), name="TX_proc"))
        logger.info("✅ Transaction processor task started")

        self._bg.append(asyncio.create_task(self._heartbeat(), name="Heartbeat"))
        logger.info("✅ Heartbeat task started")

        logger.info(
            "🔄 All background tasks running - ON1Builder is actively monitoring..."
        )
        logger.info("⏹️  Press Ctrl+C to stop the application")

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

        if (
            self.web3
            and getattr(self.web3, "provider", None)
            and hasattr(self.web3.provider, "disconnect")
        ):
            try:
                disconnect_call = self.web3.provider.disconnect()
                if inspect.iscoroutine(disconnect_call):
                    await disconnect_call
            except Exception as e:
                logger.warning(f"Error disconnecting web3 provider: {e}")

        # First close components that have stop method
        for name, component in self.components.items():
            if hasattr(component, "stop") and callable(component.stop):
                try:
                    stop_call = component.stop()
                    if inspect.iscoroutine(stop_call):
                        await stop_call
                    logger.debug(f"Component {name} stopped")
                except Exception as e:
                    logger.error(f"Error stopping component {name}: {e}")

        # Special handling for APIConfig which needs close() to be called to clean up sessions
        if "api_config" in self.components:
            try:
                api_config = self.components["api_config"]
                if hasattr(api_config, "close") and callable(api_config.close):
                    close_call = api_config.close()
                    if inspect.iscoroutine(close_call):
                        await close_call
                    logger.debug("API Config closed and cleaned up")
            except Exception as e:
                logger.error(f"Error closing API Config: {e}")

        self._bg = []
        logger.info("MainCore stopped")

    async def _bootstrap(self) -> None:
        logger.info("Bootstrapping components...")
        # Configuration already loaded in __init__, no need to reload here

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
            self.components["notification_manager"] = (
                await self._mk_notification_manager()
            )
        except Exception as e:
            logger.warning(f"Notification manager initialization error: {e}")
            logger.warning("Continuing without notification support")

        # Initialize persistence layer (optional, will auto-initialize if needed)
        try:
            self.components["db_manager"] = await self._mk_db_manager()
        except Exception as e:
            logger.warning(f"Database manager initialization error: {e}")
            logger.warning("Continuing without database persistence")

        # Initialize core components (these require web3 and account to be set)
        self.components["nonce_core"] = await self._mk_nonce_core()
        self.components["safety_net"] = await self._mk_safety_net()
        self.components["transaction_core"] = await self._mk_txcore()
        self.components["market_monitor"] = await self._mk_market_monitor()
        self.components["txpool_monitor"] = await self._mk_txpool_monitor()
        self.components["strategy_net"] = await self._mk_strategy_net()

        logger.info("All components initialized")

    async def _connect_web3(self) -> Optional[AsyncWeb3]:
        return await self._create_web3_connection()

    async def _mk_api_config(self) -> ExternalAPIManager:
        # Initialize external API manager with APISettings
        api = ExternalAPIManager(self.cfg.api)
        await api.initialize()
        return api

    async def _mk_nonce_core(self) -> NonceManager:
        return await self._create_nonce_core()

    async def _mk_safety_net(self) -> SafetyGuard:
        return await self._create_safety_net()

    async def _mk_txcore(self) -> TransactionManager:
        return await self._create_transaction_core()

    async def _mk_market_monitor(self) -> MarketDataFeed:
        return await self._create_market_monitor()

    async def _mk_txpool_monitor(self) -> TxPoolScanner:
        return await self._create_txpool_monitor()

    async def _mk_strategy_net(self) -> StrategyExecutor:
        return await self._create_strategy_net()

    async def _mk_abi_registry(self) -> Any:
        """Initialize and return the ABI Registry.

        The ABI Registry loads and manages smart contract ABIs for all components.
        """
        from on1builder.integrations.abi_registry import get_registry

        try:
            # Use the specific resources/abi path for ABIs
            base_path = self.cfg.base_path
            abi_path = base_path / "resources" / "abi"

            if not abi_path.exists():
                logger.warning(f"ABI path not found: {abi_path}")
                abi_path = base_path  # Fallback to base path

            # Handle non-ABI JSON files that might cause issues
            strategy_weights_path = Path("resources/ml_data/strategy_weights.json")
            if strategy_weights_path.exists():
                # Temporarily rename the file to prevent loading it as an ABI
                temp_path = Path("resources/ml_data/strategy_weights.json.bak")
                strategy_weights_path.rename(temp_path)

                # Initialize with specific ABI path
                registry = await get_registry(str(abi_path))

                # Restore the file
                temp_path.rename(strategy_weights_path)
            else:
                # Standard initialization
                registry = await get_registry(str(abi_path))

            logger.info(
                f"ABI Registry initialized with {len(registry.abis)} contract definitions"
            )
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
        from on1builder.persistence.db_interface import get_db_manager

        # Initialize with configuration
        db_url = self.cfg.database_url
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
        from on1builder.utils.notification_service import get_notification_manager

        # Initialize notification manager with our configuration
        notification_manager = get_notification_manager(self.cfg)
        logger.info("Notification Manager initialized")
        return notification_manager

    async def _create_web3_connection(self) -> Optional[AsyncWeb3]:
        """Create Web3 connection using chain configuration."""
        # For multi-chain, connect to the first active chain or first available chain
        chain_config = None

        if isinstance(self.cfg, MultiChainSettings) and self.cfg.active_chains:
            # Use first active chain
            chain_name = self.cfg.active_chains[0]
            chain_config = self.cfg.get_chain_config(chain_name)
        elif self.cfg.chains:
            # Use first available chain
            chain_name = next(iter(self.cfg.chains.keys()))
            chain_config = self.cfg.chains[chain_name]

        if not chain_config:
            logger.error("No chain configuration available")
            return None

        # Try HTTP endpoint first
        if chain_config.http_endpoint:
            try:
                provider = AsyncHTTPProvider(chain_config.http_endpoint)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id

                # Apply PoA middleware if needed
                if chain_id in self.cfg.poa_chains or chain_config.is_poa:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")

                logger.info(
                    f"Connected to HTTP endpoint: {chain_config.http_endpoint} (chain: {chain_config.name})"
                )
                return web3
            except Exception as e:
                logger.warning(f"Failed to connect to HTTP endpoint: {e}")

        # Try WebSocket endpoint
        if chain_config.websocket_endpoint:
            try:
                provider = WebSocketProvider(chain_config.websocket_endpoint)
                web3 = AsyncWeb3(provider)
                chain_id = await web3.eth.chain_id

                if chain_id in self.cfg.poa_chains or chain_config.is_poa:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")

                logger.info(
                    f"Connected to WebSocket endpoint: {chain_config.websocket_endpoint} (chain: {chain_config.name})"
                )
                return web3
            except Exception as e:
                logger.warning(f"Failed to connect to WebSocket endpoint: {e}")

        # Try IPC endpoint (Note: IPC is not supported with AsyncWeb3)
        if chain_config.ipc_endpoint:
            logger.warning(
                f"IPC endpoint configured but not supported with AsyncWeb3: {chain_config.ipc_endpoint}"
            )

        logger.error(f"Failed to connect to any endpoint for chain {chain_config.name}")
        return None

    async def _create_account(self) -> Optional[Account]:
        if hasattr(self.cfg, "wallet_key") and self.cfg.wallet_key:
            return Account.from_key(self.cfg.wallet_key)
        logger.error("No wallet_key provided in configuration")
        return None

    async def _create_nonce_core(self) -> NonceManager:
        assert self.web3 is not None, "Web3 connection must be established"
        nonce_core = NonceManager(web3=self.web3, configuration=self.cfg)
        await nonce_core.initialize()
        return nonce_core

    async def _create_safety_net(self) -> SafetyGuard:
        assert self.web3 is not None, "Web3 connection must be established"
        assert self.account is not None, "Account must be established"

        # Pass reference to self (MainCore) to allow SafetyNet to access shared resources
        safety_guard = SafetyGuard(
            web3=self.web3,
            config=self.cfg,
            account=self.account,
            external_api_manager=self.components.get("api_config"),
            main_orchestrator=self,
        )
        await safety_guard.initialize()
        return safety_guard

    async def _create_transaction_core(self) -> TransactionManager:
        assert self.web3 is not None, "Web3 connection must be established"
        assert self.account is not None, "Account must be established"

        chain_id = await self.web3.eth.chain_id if self.web3 else 1
        tx_core = TransactionManager(
            web3=self.web3,
            account=self.account,
            configuration=self.cfg,
            nonce_manager=self.components.get("nonce_core"),
            safety_guard=self.components.get("safety_net"),
            external_api_manager=self.components.get("api_config"),
            market_monitor=self.components.get("market_monitor"),
            txpool_monitor=self.components.get("txpool_monitor"),
            chain_id=chain_id,
            main_orchestrator=self,  # Pass reference for shared components
        )
        await tx_core.initialize()
        return tx_core

    async def _create_market_monitor(self) -> MarketDataFeed:
        assert self.web3 is not None, "Web3 connection must be established"

        # Get the APISettings from the ExternalAPIManager
        api_manager = self.components.get("api_config")
        api_settings = api_manager.api_settings if api_manager else self.cfg.api

        market_monitor = MarketDataFeed(self.web3, self.cfg, api_settings)
        await market_monitor.initialize()
        return market_monitor

    async def _create_txpool_monitor(self) -> TxPoolScanner:
        assert self.web3 is not None, "Web3 connection must be established"

        # Get the list of monitored tokens from config
        monitored_tokens_config = self.cfg.monitored_tokens
        monitored_tokens = []

        # Check if the value is a string (likely a file path)
        if isinstance(monitored_tokens_config, str):
            # If it's a file path, try to load it
            if os.path.exists(monitored_tokens_config):
                try:
                    # Try to load tokens from file
                    with open(monitored_tokens_config, "r") as f:
                        token_data = json.load(f)

                    # If it's the address2symbol.json format, get the top tokens
                    # by taking a slice of the keys (addresses) and values (symbols)
                    if isinstance(token_data, dict):
                        # Take top tokens (limit to avoid excessive monitoring)
                        top_tokens = list(token_data.values())[:50]
                        monitored_tokens.extend(top_tokens)
                        logger.info(
                            f"Loaded {len(monitored_tokens)} tokens from {monitored_tokens_config}"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to load monitored tokens from {monitored_tokens_config}: {e}"
                    )
        elif isinstance(monitored_tokens_config, list):
            # If it's already a list, use it directly
            monitored_tokens = monitored_tokens_config

        # If no valid tokens found, use defaults
        if not monitored_tokens:
            logger.warning(
                "No monitored tokens defined or loaded, using default token list"
            )
            # Use some default tokens like ETH, WETH, etc.
            monitored_tokens = ["ETH", "WETH", "USDC", "USDT", "DAI"]

        logger.info(
            f"Monitoring {len(monitored_tokens)} tokens: {', '.join(monitored_tokens[:10])}..."
        )

        txpool_monitor = TxPoolScanner(
            web3=self.web3,
            safety_net=self.components["safety_net"],
            nonce_core=self.components["nonce_core"],
            api_config=self.components["api_config"],
            monitored_tokens=monitored_tokens,
            configuration=self.cfg,
            market_monitor=self.components["market_monitor"],
        )
        await txpool_monitor.initialize()
        return txpool_monitor

    async def _create_strategy_net(self) -> StrategyExecutor:
        assert self.web3 is not None, "Web3 connection must be established"

        strategy_net = StrategyExecutor(
            web3=self.web3,
            config=self.cfg,
            transaction_core=self.components["transaction_core"],
            safety_net=self.components["safety_net"],
            market_monitor=self.components["market_monitor"],
            main_orchestrator=self,  # Pass reference to MainOrchestrator for shared resources
        )
        await strategy_net.initialize()
        return strategy_net

    async def _heartbeat(self) -> None:
        interval = 30  # Default heartbeat interval
        memory_report_interval = self.cfg.memory_check_interval
        health_check_interval = 10  # Default health check interval

        last_memory_report = 0
        last_health_check = 0

        logger.info(
            f"Heartbeat started - interval: {interval}s, health checks: {health_check_interval}s"
        )

        while not self._stop_evt.is_set():
            try:
                current_time = time.time()
                if current_time - last_health_check >= health_check_interval:
                    await self._check_component_health()
                    last_health_check = current_time

                if current_time - last_memory_report >= memory_report_interval:
                    await self._report_memory_usage()
                    last_memory_report = current_time

                logger.info(
                    "💓 MainCore heartbeat - System operational and monitoring..."
                )
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Heartbeat task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
                await asyncio.sleep(5)

    async def _tx_processor(self) -> None:
        interval = 5  # Default transaction processor interval
        logger.info(f"Transaction processor started with {interval}s interval")

        while not self._stop_evt.is_set():
            try:
                # Check if we have the required components
                txpool_monitor = self.components.get("txpool_monitor")
                strategy_net = self.components.get("strategy_net")

                if not txpool_monitor or not strategy_net:
                    logger.warning(
                        "Missing required components for transaction processing"
                    )
                    await asyncio.sleep(interval)
                    continue

                # Process any profitable transactions found by TxpoolMonitor
                processed_count = 0
                try:
                    # Check for profitable transactions (non-blocking)
                    while not txpool_monitor.profitable_transactions.empty():
                        try:
                            profitable_tx = await asyncio.wait_for(
                                txpool_monitor.profitable_transactions.get(),
                                timeout=0.1,
                            )

                            if profitable_tx:
                                logger.info(
                                    f"💰 Found profitable transaction: {profitable_tx['tx_hash'][:10]}..."
                                )
                                logger.info(
                                    f"📊 Strategy type: {profitable_tx.get('strategy_type', 'unknown')}"
                                )

                                # Execute the strategy
                                success = await strategy_net.execute_best_strategy(
                                    profitable_tx["tx"],
                                    profitable_tx.get("strategy_type", "front_run"),
                                )

                                if success:
                                    logger.info(
                                        f"✅ Successfully executed strategy for {profitable_tx['tx_hash'][:10]}..."
                                    )
                                    processed_count += 1
                                else:
                                    logger.warning(
                                        f"❌ Failed to execute strategy for {profitable_tx['tx_hash'][:10]}..."
                                    )

                                # Mark as done
                                txpool_monitor.profitable_transactions.task_done()

                        except asyncio.TimeoutError:
                            # No more transactions available
                            break
                        except Exception as e:
                            logger.error(
                                f"Error processing profitable transaction: {e}"
                            )

                except Exception as e:
                    logger.debug(f"No profitable transactions in queue: {e}")

                if processed_count > 0:
                    logger.info(
                        f"📈 Processed {processed_count} profitable transactions this cycle"
                    )
                else:
                    logger.debug(
                        "Transaction processor checking for new transactions... (no profitable txs found)"
                    )

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
                if hasattr(component, "check_health") and callable(
                    component.check_health
                ):
                    # Handle both sync and async health check methods
                    health_check = component.check_health()
                    if inspect.iscoroutine(health_check):
                        health_status = await health_check
                    else:
                        health_status = health_check

                    # Ensure boolean type
                    self.component_health[name] = bool(health_status)
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

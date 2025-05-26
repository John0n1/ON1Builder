# src/on1builder/core/main_core.py

"""
ON1Builder – MainCore
=====================
Boot-straps every long-lived component, owns the single AsyncIO event-loop,
and exposes `.run()`, `.stop()`, and `.connect()` for callers (CLI, Flask UI, tests).
"""

from __future__ import annotations

import asyncio
import os
import random
import tracemalloc
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

# Import these only if available
try:
    import async_timeout
    from eth_account import Account
    from web3 import AsyncWeb3
    from web3.eth import AsyncEth
    from web3.middleware import ExtraDataToPOAMiddleware
    from web3.providers import AsyncHTTPProvider, WebSocketProvider, IPCProvider
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    class Account:
        pass
    class AsyncWeb3:
        pass
    class AsyncHTTPProvider:
        pass
    class WebSocketProvider:
        pass
    class IPCProvider:
        pass
    class ExtraDataToPOAMiddleware:
        pass

from on1builder.config.config import Configuration
from on1builder.config.config import APIConfig
from on1builder.utils.logger import setup_logging
from on1builder.core.nonce_core import NonceCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.engines.strategy_net import StrategyNet
from on1builder.core.transaction_core import TransactionCore
from on1builder.utils.strategyexecutionerror import StrategyExecutionError

# Conditional imports for monitors
if TYPE_CHECKING:
    from on1builder.monitoring.market_monitor import MarketMonitor
    from on1builder.monitoring.txpool_monitor import TxpoolMonitor
else:
    try:
        from on1builder.monitoring.market_monitor import MarketMonitor
        from on1builder.monitoring.txpool_monitor import TxpoolMonitor
    except ImportError:
        class MarketMonitor:
            pass
        class TxpoolMonitor:
            pass

logger = setup_logging("MainCore", level="DEBUG")

# Chains that need the geth/erigon "extraData" PoA middleware
_POA_CHAINS: set[int] = {99, 100, 77, 7766, 56, 11155111}


class MainCore:
    """High-level conductor that owns all sub-components and the main loop."""
    logger = logger

    def __init__(self, configuration: Configuration) -> None:
        """Initialize MainCore with configuration."""
        self.cfg = configuration

        self.web3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None

        self._bg: List[asyncio.Task[Any]] = []
        self._running_evt = asyncio.Event()          # signaled by run()
        self._stop_evt = asyncio.Event()             # set by stop()

        # component registry
        self.components: Dict[str, Any] = {}
        self.component_health: Dict[str, bool] = {}

        # memory diff baseline
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        self._mem_snapshot = tracemalloc.take_snapshot()

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    async def connect(self) -> bool:
        """
        Establish a Web3 connection. Returns True if connected, False otherwise.
        """
        web3 = await self._connect_web3()
        if not web3:
            return False

        # Some mocks use async is_connected, others sync
        try:
            connected = await web3.is_connected()
        except TypeError:
            connected = web3.is_connected()

        if connected:
            self.web3 = web3
            return True
        return False

    # -------------------------------------------------------------------
    # run / stop
    # -------------------------------------------------------------------

    async def run(self) -> None:
        """
        Construct components and start high-level tasks – blocks until stop().
        """
        await self._bootstrap()
        self._running_evt.set()

        self._bg = []

        # txpool_monitor task
        if "txpool_monitor" in self.components:
            self._bg.append(asyncio.create_task(
                self.components["txpool_monitor"].start_monitoring(),
                name="MM_run"
            ))

        # transaction processor
        self._bg.append(asyncio.create_task(
            self._tx_processor(),
            name="TX_proc"
        ))

        # heartbeat
        self._bg.append(asyncio.create_task(
            self._heartbeat(),
            name="Heartbeat"
        ))

        try:
            await asyncio.shield(self._stop_evt.wait())
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.stop()
            logger.info("MainCore run() finished")

    async def stop(self) -> None:
        """
        Graceful tear-down; idempotent.
        """
        if self._stop_evt.is_set():
            return
        self._stop_evt.set()

        logger.info("MainCore stopping...")

        # Cancel background tasks
        for task in self._bg:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        if self._bg:
            try:
                await asyncio.gather(*self._bg, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error during task shutdown: {e}")

        # Disconnect web3 provider if available
        if self.web3 and hasattr(self.web3, "provider") and hasattr(self.web3.provider, "disconnect"):
            try:
                await self.web3.provider.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting web3 provider: {e}")

        # Stop all components
        for name, component in self.components.items():
            if hasattr(component, 'stop') and callable(component.stop):
                try:
                    await component.stop()
                    logger.debug(f"Component {name} stopped")
                except Exception as e:
                    logger.error(f"Error stopping component {name}: {e}")

        # Clear background task list
        self._bg = []

        logger.info("MainCore stopped")

    # -------------------------------------------------------------------
    # Bootstrap & wiring (uses alias methods for test patching)
    # -------------------------------------------------------------------

    async def _bootstrap(self) -> None:
        """Initialize all components in the right order."""
        logger.info("Bootstrapping components...")

        # Allow config.load() to be tested
        await self.cfg.load()

        # Web3 connection
        self.web3 = await self._connect_web3()
        if not self.web3:
            raise StrategyExecutionError("Failed to create Web3 connection")

        # Account creation
        self.account = await self._create_account()
        if not self.account:
            raise StrategyExecutionError("Failed to create account")

        # APIConfig
        self.components["api_config"] = await self._mk_api_config()

        # Core/safety components
        self.components["nonce_core"] = await self._mk_nonce_core()
        self.components["safety_net"] = await self._mk_safety_net()
        self.components["transaction_core"] = await self._mk_txcore()

        # Monitoring components
        self.components["market_monitor"] = await self._mk_market_monitor()
        self.components["txpool_monitor"] = await self._mk_txpool_monitor()

        # Strategy components
        self.components["strategy_net"] = await self._mk_strategy_net()

        logger.info("All components initialized")

    # -------------------------------------------------------------------
    # Alias helpers for testing
    # -------------------------------------------------------------------

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

    # -------------------------------------------------------------------
    # Detailed component creation
    # -------------------------------------------------------------------

    async def _create_web3_connection(self) -> Optional[AsyncWeb3]:
        """Create Web3 connection using available endpoints."""
        if not HAS_WEB3:
            logger.error("Web3.py is not installed")
            return None

        # Try HTTP endpoint first
        try:
            if hasattr(self.cfg, 'HTTP_ENDPOINT') and self.cfg.HTTP_ENDPOINT:
                provider = AsyncHTTPProvider(self.cfg.HTTP_ENDPOINT)
                web3 = AsyncWeb3(provider)
                await web3.eth.chain_id
                logger.info(f"Connected to HTTP endpoint: {self.cfg.HTTP_ENDPOINT}")

                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to HTTP endpoint: {e}")

        # Try WebSocket endpoint
        try:
            if hasattr(self.cfg, 'WEBSOCKET_ENDPOINT') and self.cfg.WEBSOCKET_ENDPOINT:
                provider = WebSocketProvider(self.cfg.WEBSOCKET_ENDPOINT)
                web3 = AsyncWeb3(provider)
                await web3.eth.chain_id
                logger.info(f"Connected to WebSocket endpoint: {self.cfg.WEBSOCKET_ENDPOINT}")

                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to WebSocket endpoint: {e}")

        # Try IPC endpoint
        try:
            if hasattr(self.cfg, 'IPC_ENDPOINT') and self.cfg.IPC_ENDPOINT:
                provider = IPCProvider(self.cfg.IPC_ENDPOINT)
                web3 = AsyncWeb3(provider)
                await web3.eth.chain_id
                logger.info(f"Connected to IPC endpoint: {self.cfg.IPC_ENDPOINT}")

                chain_id = await web3.eth.chain_id
                if chain_id in _POA_CHAINS:
                    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    logger.info(f"Applied PoA middleware for chain ID {chain_id}")
                return web3
        except Exception as e:
            logger.warning(f"Failed to connect to IPC endpoint: {e}")

        logger.error("Failed to connect to any Web3 endpoint")
        return None

    async def _create_account(self) -> Optional[Account]:
        """Create account from private key or mnemonic."""
        if not HAS_WEB3:
            logger.error("Web3.py is not installed")
            return None

        try:
            if hasattr(self.cfg, 'WALLET_KEY') and self.cfg.WALLET_KEY:
                return Account.from_key(self.cfg.WALLET_KEY)
            elif hasattr(self.cfg, 'MNEMONIC') and self.cfg.MNEMONIC:
                logger.error("Mnemonic support not implemented")
                return None
            else:
                logger.error("No WALLET_KEY or MNEMONIC provided in configuration")
                return None
        except Exception as e:
            logger.error(f"Failed to create account: {e}")
            return None

    async def _create_nonce_core(self) -> NonceCore:
        """Create and initialize NonceCore."""
        nonce_core = NonceCore(self.web3, self.account)
        await nonce_core.initialize()
        return nonce_core

    async def _create_safety_net(self) -> SafetyNet:
        """Create and initialize SafetyNet."""
        safety_net = SafetyNet(self.web3, self.cfg)
        await safety_net.initialize()
        return safety_net

    async def _create_transaction_core(self) -> TransactionCore:
        """Create and initialize TransactionCore."""
        chain_id = await self.web3.eth.chain_id if HAS_WEB3 and self.web3 else 1
        tx_core = TransactionCore(
            self.web3,
            self.account,
            self.cfg,
            self.components["nonce_core"],
            self.components["safety_net"],
            chain_id=chain_id
        )
        await tx_core.initialize()
        return tx_core

    async def _create_market_monitor(self) -> MarketMonitor:
        """Create and initialize MarketMonitor."""
        market_monitor = MarketMonitor(self.web3, self.cfg)
        await market_monitor.initialize()
        return market_monitor

    async def _create_txpool_monitor(self) -> TxpoolMonitor:
        """Create and initialize TxpoolMonitor."""
        txpool_monitor = TxpoolMonitor(
            self.web3,
            self.cfg,
            self.components["market_monitor"]
        )
        await txpool_monitor.initialize()
        return txpool_monitor

    async def _create_strategy_net(self) -> StrategyNet:
        """Create and initialize StrategyNet."""
        strategy_net = StrategyNet(
            self.web3,
            self.cfg,
            self.components["transaction_core"],
            self.components["safety_net"],
            self.components["market_monitor"]
        )
        await strategy_net.initialize()
        return strategy_net

    # -------------------------------------------------------------------
    # Background tasks: heartbeat, tx-processor, health checks, memory
    # -------------------------------------------------------------------

    async def _heartbeat(self) -> None:
        """Periodic health check and memory usage reporting."""
        interval = getattr(self.cfg, 'HEARTBEAT_INTERVAL', 60)
        memory_report_interval = getattr(self.cfg, 'MEMORY_REPORT_INTERVAL', 300)
        health_check_interval = getattr(self.cfg, 'HEALTH_CHECK_INTERVAL', 10)

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
        """Process pending transactions (placeholder workload)."""
        interval = getattr(self.cfg, 'TX_PROCESSOR_INTERVAL', 5)
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
        """Check health of all components."""
        for name, component in self.components.items():
            try:
                if hasattr(component, 'check_health') and callable(component.check_health):
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
        """Report memory usage differences since startup."""
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            return

        try:
            current_snapshot = tracemalloc.take_snapshot()
            top_stats = current_snapshot.compare_to(self._mem_snapshot, 'lineno')
            logger.info("Top 10 memory usage differences:")
            for stat in top_stats[:10]:
                logger.info(str(stat))
        except Exception as e:
            logger.error(f"Error generating memory report: {e}")

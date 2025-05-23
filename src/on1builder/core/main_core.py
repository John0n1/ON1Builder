# src/on1builder/core/main_core.py

"""
ON1Builder – MainCo# Chains that need the geth/erigon "extraData" PoA middleware
_POA_CHAINS: set[int] = {99, 100, 77, 7766, 56, 11155111}
import random Use POA_CHAINS from Configuration=====================
Boot-straps every long-lived component, owns the single AsyncIO event-loop,
and exposes `.run()` / `.stop()` for callers (CLI, Flask UI, tests).

All heavy lifting lives in the leaf components; MainCore only wires them and
keeps a minimal heartbeat to verify health.
"""

from __future__ import annotations

import asyncio
import os
import random
import tracemalloc
from typing import Any, Dict, List, Optional, Tuple

import async_timeout
from eth_account import Account
from web3 import AsyncWeb3
from web3.eth import AsyncEth
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import AsyncHTTPProvider, WebSocketProvider, IPCProvider

from on1builder.config.config import APIConfig, Configuration
from on1builder.utils.logger import setup_logging
from on1builder.utils import logger
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.monitoring.txpool_monitor import TxpoolMonitor
from on1builder.core.nonce_core import NonceCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.engines.strategy_net import StrategyNet
from on1builder.core.transaction_core import TransactionCore

logger = setup_logging("MainCore", level="DEBUG")


# --------------------------------------------------------------------------- #
# constants                                                                   #
# --------------------------------------------------------------------------- #

# Chains that need the geth/erigon “extraData” PoA middleware
_POA_CHAINS: set[int] = {99, 100, 77, 7766, 56, 11155111}


class MainCore:
    """High-level conductor that owns all sub-components and the main loop."""
    # set logger at MainCore Attribute
    logger = logger

    # --- life-cycle -------------------------------------------------------

    def __init__(self, configuration: Configuration) -> None:
        self.cfg = configuration

        self.web3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None

        self._bg: List[asyncio.Task[Any]] = []
        self._running_evt = asyncio.Event()          # True while run() active
        self._stop_evt = asyncio.Event()             # set by stop()

        # component registry
        self.components: Dict[str, Any] = {}
        self.component_health: Dict[str, bool] = {}

        # memory diff baseline
        tracemalloc.start()
        self._mem_snapshot = tracemalloc.take_snapshot()

    # --- top-level run/stop ----------------------------------------------

    async def run(self) -> None:
        """Construct components and start high-level tasks – blocks until stop()."""
        await self._bootstrap()
        self._running_evt.set()                      # signal Flask / tests

        # ── background tasks
        self._bg = [
            asyncio.create_task(self.components["txpool_monitor"].start_monitoring(), name="MM_run"),
            asyncio.create_task(self._tx_processor(),                                   name="TX_proc"),
            asyncio.create_task(self._heartbeat(),                                      name="Heartbeat"),
        ]

        try:
            await asyncio.shield(self._stop_evt.wait())     # wait until .stop() called
        finally:
            await self.stop()                               # double-safe
            logger.info("MainCore run() finished")

    async def stop(self) -> None:
        """Graceful tear-down; can be called multiple times."""
        if self._stop_evt.is_set():
            return                                            # idempotent
        self._stop_evt.set()

        logger.info("MainCore stopping…")
        # cancel bg tasks first
        for t in self._bg:
            t.cancel()
        await asyncio.gather(*self._bg, return_exceptions=True)
        self._bg.clear()

        # propagate stop() down
        for comp in self.components.values():
            stop = getattr(comp, "stop", None)
            if stop:
                try:
                    await stop()
                except Exception as exc:                       # pragma: no cover
                    logger.error("Component stop() failed: %s", exc)

        # close provider cleanly
        if self.web3 and hasattr(self.web3.provider, "disconnect"):
            with async_timeout.timeout(3):
                await self.web3.provider.disconnect()

        # snapshot memory diff (optional log)
        memory_log_delta = self.cfg.get("MEMORY_LOG_DELTA", False)
            
        if memory_log_delta:
            diff_kb = self._memory_delta_kb()
            if diff_kb > 5_000:
                logger.warning("Process grew by %.1f MB", diff_kb / 1024)

        tracemalloc.stop()
        logger.info("MainCore stopped.")

    async def start(self) -> None:
        """
        Start the MainCore (alias for run).
        
        This method exists for API compatibility with __main__.py.
        """
        await self.run()
        
    async def shutdown(self) -> None:
        """
        Shutdown the MainCore (alias for stop).
        
        This method exists for API compatibility with __main__.py.
        """
        await self.stop()

    # --- bootstrap helpers -----------------------------------------------

    async def _bootstrap(self) -> None:
        await self.cfg.load()

        # ── connect RPC ---------------------------------------------------
        self.web3 = await self._connect_web3()
        if not self.web3:
            raise RuntimeError("Unable to connect to any Web3 endpoint")

        # ── wallet --------------------------------------------------------
        self.account = Account.from_key(self.cfg.WALLET_KEY)
        balance_wei = await self.web3.eth.get_balance(self.account.address)
        if balance_wei == 0:
            logger.warning("Wallet %s has zero ETH!", self.account.address)

        # ── create components --------------------------------------------
        api_config   = await self._mk_api_config()
        nonce_core   = await self._mk_nonce_core()
        safety_net   = await self._mk_safety_net(api_config)
        marketmon   = await self._mk_market_monitor(api_config)
        txcore      = await self._mk_txcore(api_config, marketmon, nonce_core, safety_net)
        mempoolmon  = await self._mk_txpool_monitor(api_config, nonce_core, safety_net, marketmon)
        strategy_net = await self._mk_strategy_net(txcore, marketmon, safety_net, api_config)

        self.components = {
            "api_config": api_config,
            "nonce_core": nonce_core,
            "safety_net": safety_net,
            "market_monitor": marketmon,
            "transaction_core": txcore,
            "txpool_monitor": mempoolmon,
            "strategy_net": strategy_net,
        }

        self.component_health = {k: True for k in self.components}
        logger.info("All components initialised.")

    # --- Web3 connection --------------------------------------------------

    async def _connect_web3(self) -> Optional[AsyncWeb3]:
        """Attempts each configured provider with exponential back-off + jitter."""
        provs = self._provider_candidates()
        if not provs:
            logger.error("No Web3 providers configured. Please check your HTTP_ENDPOINT, WEBSOCKET_ENDPOINT, or IPC_ENDPOINT settings.")
            return None
            
        # Get connection timeout from config or environment variable
        connection_timeout = getattr(self.cfg, "CONNECTION_TIMEOUT", 
                                    int(os.getenv("CONNECTION_TIMEOUT", 10)))
        retry_delay = getattr(self.cfg, "CONNECTION_RETRY_DELAY", 
                            float(os.getenv("CONNECTION_RETRY_DELAY", 2.0)))
        
        logger.info("Attempting to connect to %d Web3 providers with max %d retries each", 
                   len(provs), self.cfg.WEB3_MAX_RETRIES)
                   
        for name, provider in provs:
            delay = retry_delay
            for attempt in range(1, self.cfg.WEB3_MAX_RETRIES + 1):
                try:
                    logger.info("Connecting to Web3 %s (attempt %d/%d)…", 
                               name, attempt, self.cfg.WEB3_MAX_RETRIES)
                    w3 = AsyncWeb3(provider, modules={"eth": (AsyncEth,)})
                    
                    # Test connection with timeout
                    async with async_timeout.timeout(connection_timeout):
                        is_connected = await w3.is_connected()
                        if not is_connected:
                            logger.warning("%s provider is not connected", name)
                            raise RuntimeError(f"{name} provider is_connected() returned False")
                            
                        # Get chain ID
                        chain_id = await w3.eth.chain_id
                        
                        # Apply middleware if needed
                        if isinstance(self.cfg.POA_CHAINS, set) and chain_id in self.cfg.POA_CHAINS:
                            logger.info("Applying POA middleware for chain %s", chain_id)
                            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                            
                        logger.info("✓ Successfully connected to %s (chain %s)", name, chain_id)
                        return w3
                        
                except asyncio.CancelledError:
                    logger.warning("Connection attempt cancelled")
                    raise
                    
                except asyncio.TimeoutError:
                    logger.warning("Connection to %s timed out after %s seconds", 
                                  name, connection_timeout)
                    
                except Exception as e:
                    logger.warning("Failed to connect to %s: %s", name, str(e))
                    
                if attempt < self.cfg.WEB3_MAX_RETRIES:
                    logger.debug("Retrying %s connection in %.1fs (attempt %d/%d)", 
                                name, delay, attempt+1, self.cfg.WEB3_MAX_RETRIES)
                    await asyncio.sleep(delay)
                    # Apply exponential backoff with some jitter
                    delay = delay * 1.5 + (random.random() * 0.5)
        return None

    async def connect(self) -> bool:
        """Connect to the Web3 provider.
        
        This method is primarily for testing the connection logic.
        The normal initialization happens in _bootstrap().
        
        Returns:
            bool: True if connected successfully, False otherwise.
        """
        self.web3 = await self._connect_web3()
        return self.web3 is not None and await self.web3.is_connected()

    async def connect_websocket(self) -> bool:
        """
        Establishes WebSocket connection with retry logic.
        Returns True if connection is successful, False otherwise.
        """
        if not self.cfg.WEBSOCKET_ENDPOINT:
            self.logger.warning("No WebSocket endpoint configured")
            return False
            
        retry_count = 0
        max_retries = self.cfg.WEB3_MAX_RETRIES or 3
        retry_delay = self.cfg.CONNECTION_RETRY_DELAY or 3.0

        while retry_count <= max_retries:
            try:
                provider = WebSocketProvider(self.cfg.WEBSOCKET_ENDPOINT)
                self.w3_ws = AsyncWeb3(provider)
                
                # Verify connection
                if await self.w3_ws.is_connected():
                    self.logger.info("WebSocket connection established")
                    return True
                else:
                    self.logger.warning("WebSocket connected but verification failed")
                    
            except Exception as e:
                self.logger.warning(f"WebSocketProvider failed: {str(e)}")
                
                # If we've reached max retries, give up
                if retry_count >= max_retries:
                    break
                    
                # Exponential backoff for retry
                wait_time = retry_delay * (2 ** retry_count) / 4
                self.logger.info(f"Retrying WebSocket connection in {wait_time:.1f}s (attempt {retry_count+1}/{max_retries})")
                await asyncio.sleep(wait_time)
                
            retry_count += 1
                
        self.logger.error("Failed to establish WebSocket connection after retries")
        return False

    def _provider_candidates(self) -> List[Tuple[str, object]]:
        out: List[Tuple[str, object]] = []
        
        # Try primary HTTP endpoint
        if self.cfg.HTTP_ENDPOINT:
            try:
                out.append(("http", AsyncHTTPProvider(self.cfg.HTTP_ENDPOINT)))
                logger.debug("Added primary HTTP endpoint: %s", self.cfg.HTTP_ENDPOINT)
            except Exception as e:
                logger.warning("Primary HTTPProvider failed: %s", e)
        
        # Try backup HTTP endpoints if configured
        backup_endpoints = getattr(self.cfg, "BACKUP_HTTP_ENDPOINTS", "")
        if backup_endpoints:
            endpoints = backup_endpoints.split(",") if isinstance(backup_endpoints, str) else backup_endpoints
            for i, endpoint in enumerate(endpoints):
                if not endpoint.strip():
                    continue
                try:
                    out.append((f"backup-http-{i+1}", AsyncHTTPProvider(endpoint.strip())))
                    logger.debug("Added backup HTTP endpoint: %s", endpoint.strip())
                except Exception as e:
                    logger.warning("Backup HTTP endpoint %s failed: %s", endpoint.strip(), e)
        
        # Try IPC endpoint if HTTP endpoints failed or not configured
        if getattr(self.cfg, "IPC_ENDPOINT", None):
            try:
                out.append(("ipc", IPCProvider(self.cfg.IPC_ENDPOINT)))
                logger.debug("Added IPC endpoint: %s", self.cfg.IPC_ENDPOINT)
            except Exception as e:
                logger.warning("IPCProvider failed: %s", e)

        # Try WebSocket endpoint as a last resort
        if getattr(self.cfg, "WEBSOCKET_ENDPOINT", None):
            try:
                out.append(("websocket", WebSocketProvider(self.cfg.WEBSOCKET_ENDPOINT)))
                logger.debug("Added WebSocket endpoint: %s", self.cfg.WEBSOCKET_ENDPOINT)
            except Exception as e:
                logger.warning("WebSocketProvider failed: %s", e)
                
        logger.info("Configured %d provider candidates", len(out))
        return out

    async def _mk_api_config(self) -> APIConfig:
        api = APIConfig(self.cfg)
        await api.initialize()
        return api

    async def _mk_nonce_core(self) -> NonceCore:
        nc = NonceCore(self.web3, self.cfg)
        await nc.initialize()
        return nc

    async def _mk_safety_net(self, apicfg: APIConfig) -> SafetyNet:
        sn = SafetyNet(
            web3=self.web3, 
            config=self.cfg, 
            account_address=self.account.address, 
            account=self.account, 
            api_config=apicfg
        )
        await sn.initialize()
        return sn

    async def _mk_market_monitor(self, apicfg: APIConfig) -> MarketMonitor:
        mm = MarketMonitor(config=self.cfg, api_config=apicfg)
        await mm.initialize()
        return mm

    async def _mk_txcore(
        self,
        apicfg: APIConfig,
        mm: MarketMonitor,
        nc: NonceCore,
        sn: SafetyNet,
    ) -> TransactionCore:
        tc = TransactionCore(self.web3, self.account, self.cfg, apicfg, mm, None, nc, sn)
        await tc.initialize()
        return tc

    async def _mk_txpool_monitor(
        self,
        apicfg: APIConfig,
        nc: NonceCore,
        sn: SafetyNet,
        mm: MarketMonitor,
    ) -> TxpoolMonitor:
        token_map = await self.cfg._load_json_safe(self.cfg.TOKEN_ADDRESSES, "TOKEN_ADDRESSES") or {}
        
        # Filter out any None or invalid token addresses
        valid_tokens = [addr for addr in token_map.values() if addr and isinstance(addr, str)]
        
        if not valid_tokens:
            # If no valid tokens are found, add some common tokens to monitor
            logger.warning("No valid tokens found in TOKEN_ADDRESSES, using default tokens")
            weth_addr = self.cfg.get("WETH_ADDRESS")
            usdc_addr = self.cfg.get("USDC_ADDRESS")
            usdt_addr = self.cfg.get("USDT_ADDRESS")
            wbtc_addr = self.cfg.get("WBTC_ADDRESS")
            
            valid_tokens = [addr for addr in [weth_addr, usdc_addr, usdt_addr, wbtc_addr] 
                           if addr and isinstance(addr, str)]
        
        logger.debug(f"Monitoring {len(valid_tokens)} tokens in TxpoolMonitor")
        
        mp = TxpoolMonitor(self.web3, sn, nc, apicfg, valid_tokens, self.cfg, mm)
        await mp.initialize()
        return mp

    async def _mk_strategy_net(
        self,
        tc: TransactionCore,
        mm: MarketMonitor,
        sn: SafetyNet,
        apicfg: APIConfig,
    ) -> StrategyNet:
        st = StrategyNet(tc, mm, sn, apicfg)
        await st.initialize()
        return st

    # --------------------------------------------------------------------- #
    # background tasks                                                      #
    # --------------------------------------------------------------------- #

    async def _tx_processor(self) -> None:
        """Drains profitable queue → StrategyNet."""
        mp: TxpoolMonitor = self.components["txpool_monitor"]
        st: StrategyNet = self.components["strategy_net"]

        while not self._stop_evt.is_set():
            try:
                item = await asyncio.wait_for(
                    mp.profitable_transactions.get(),
                    timeout=self.cfg.PROFITABLE_TX_PROCESS_TIMEOUT,
                )
                await st.execute_best_strategy(item, item.get("strategy_type", "front_run"))
                mp.profitable_transactions.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _heartbeat(self) -> None:
        """Simple component-health heartbeat; sets `component_health`."""
        while not self._stop_evt.is_set():
            for name, comp in list(self.components.items()):
                ok = True
                probe = getattr(comp, "is_healthy", None)
                if probe:
                    try:
                        ok = await probe()
                    except Exception:
                        ok = False
                self.component_health[name] = ok
            await asyncio.sleep(self.cfg.COMPONENT_HEALTH_CHECK_INTERVAL)

    # ------------------------------------------------------------------ #
    # utils                                                              #
    # ------------------------------------------------------------------ #

    def _memory_delta_kb(self) -> float:
        snap = tracemalloc.take_snapshot()
        diff = snap.compare_to(self._mem_snapshot, "filename")
        self._mem_snapshot = snap
        return sum(stat.size_diff for stat in diff) / 1024

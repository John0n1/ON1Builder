#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – TxpoolMonitor
===========================
Monitors the Ethereum mempool through pending transaction filters or
block polling. Surfaces profitable transactions for StrategyNet.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil
from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound

from on1builder.config.config import APIConfig, Configuration
from on1builder.core.nonce_core import NonceCore
from on1builder.engines.safety_net import SafetyNet
from on1builder.monitoring.market_monitor import MarketMonitor
from on1builder.utils.logger import get_logger

logger = get_logger(__name__)


class TxpoolMonitor:
    """Watches the mempool (or latest blocks as a fallback) and surfaces
    profitable transactions for StrategyNet."""

    def __init__(
        self,
        web3: AsyncWeb3,
        safety_net: SafetyNet,
        nonce_core: NonceCore,
        api_config: APIConfig,
        monitored_tokens: List[str],
        configuration: Configuration,
        market_monitor: MarketMonitor,
    ) -> None:
        self.web3 = web3
        self.safety_net = safety_net
        self.nonce_core = nonce_core
        self.api_config = api_config
        self.market_monitor = market_monitor
        self.configuration = configuration

        # Normalize token list to lowercase addresses
        self.monitored_tokens: Set[str] = set()
        for t in monitored_tokens:
            if t.startswith("0x"):
                self.monitored_tokens.add(t.lower())
            else:
                addr = api_config.get_token_address(t)
                if addr:
                    self.monitored_tokens.add(addr.lower())
                else:
                    logger.warning(f"Could not find address for token symbol: {t}, skipping")

        # Queues for hashes, analysis, and profitable txs
        self._tx_hash_queue: asyncio.Queue[str] = asyncio.Queue()
        self._tx_analysis_queue: asyncio.Queue[Tuple[int, str]] = asyncio.Queue()
        self.profitable_transactions: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        self._tasks: List[asyncio.Task[Any]] = []
        self._running: bool = False

        self._processed_hashes: Set[str] = set()
        self._tx_cache: Dict[str, Dict[str, Any]] = {}

        max_parallel = configuration.get("MEMPOOL_MAX_PARALLEL_TASKS", 10)
        self._semaphore = asyncio.Semaphore(max_parallel)

        self._stop_event = asyncio.Event()

        # Simple queue control
        self.processed_txs: Set[str] = set()
        self.tx_queue: List[Tuple[str, Dict[str, Any]]] = []
        self.min_gas: int = configuration.get("MIN_GAS", 0)
        self.max_queue_size: int = configuration.get("MAX_QUEUE_SIZE", 1000)
        self.queue_event: asyncio.Event = asyncio.Event()
        self.use_txpool_api: bool = configuration.get("USE_TXPOOL_API", False)

    async def initialize(self) -> None:
        """Prepare for monitoring; does not start background tasks yet."""
        logger.info("Initializing TxpoolMonitor...")
        
        # Set up internal data structures
        self._tx_hash_queue = asyncio.Queue()
        self._tx_analysis_queue = asyncio.Queue()
        self.profitable_transactions = asyncio.Queue()
        self._processed_hashes.clear()
        self._tx_cache.clear()
        self._running = False
        
        # Ensure we have a session for API access if needed
        self.client_session = None
        if self.api_config and not getattr(self.api_config, "session", None):
            try:
                import aiohttp
                self.client_session = aiohttp.ClientSession()
                setattr(self.api_config, "session", self.client_session)
                logger.debug("Created new client session for API access")
            except ImportError:
                logger.warning("aiohttp not available, external API access may be limited")
        
        # Verify we can connect to the node
        try:
            # Check basic connection by getting the latest block
            block_number = await self.web3.eth.block_number
            logger.info(f"Connected to node, current block: {block_number}")
            
            # Check what mempool monitoring capabilities are available
            txpool_supported = await self._check_txpool_support()
            if txpool_supported:
                logger.info("Node supports direct txpool access - optimal monitoring available")
                self.use_txpool_api = True
            else:
                logger.info("Node does not support direct txpool access - will use alternative methods")
                self.use_txpool_api = False
                
            # Check if pending filters are supported
            try:
                filt = await self.web3.eth.filter("pending")
                await filt.get_new_entries()  # Test if it works
                logger.info("Node supports pending transaction filters")
                # Store the filter for cleanup later
                self._pending_filter = filt
            except Exception as e:
                logger.info(f"Node doesn't support pending filters: {e}")
                logger.info("Will fall back to block polling if needed")
                self._pending_filter = None
                
        except Exception as e:
            logger.warning(f"Error during TxpoolMonitor initialization: {e}")
            logger.warning("Monitor will attempt to recover during start_monitoring")
        
        # Initialize memory for tracking transaction handling
        self._memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
        logger.info(f"Initial memory usage: {self._memory_usage:.2f} MB")
            
        logger.info("TxpoolMonitor initialization complete")

    async def start_monitoring(self) -> None:
        """Start background tasks to collect and analyze transactions."""
        if self._running:
            return
        self._running = True

        self._tasks = [
            asyncio.create_task(self._collect_hashes(), name="TXM_collect_hashes"),
            asyncio.create_task(self._analysis_dispatcher(), name="TXM_analysis"),
        ]
        logger.info(f"TxpoolMonitor: started {len(self._tasks)} background tasks")
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Stop all background tasks and clean up resources."""
        if not self._running:
            return
        self._running = False
        logger.info("TxpoolMonitor: stopping…")

        # Set stop event first to unblock any waiting tasks
        self._stop_event.set()
        
        # Cancel all background tasks
        for t in self._tasks:
            if not t.done() and not t.cancelled():
                try:
                    t.cancel()
                    logger.debug(f"Cancelled task: {t.get_name()}")
                except Exception as e:
                    logger.warning(f"Error cancelling task {t.get_name()}: {e}")
                
        # Wait for tasks to complete cancellation with timeout
        if self._tasks:
            try:
                await asyncio.wait(self._tasks, timeout=5.0)
                logger.debug("Tasks cancel wait completed")
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for tasks to cancel")
            except Exception as e:
                logger.error(f"Error waiting for tasks to cancel: {e}")
            
        # Clear all data structures
        try:
            # Clear queues
            while not self._tx_hash_queue.empty():
                try:
                    self._tx_hash_queue.get_nowait()
                    self._tx_hash_queue.task_done()
                except asyncio.QueueEmpty:
                    break
            
            while not self._tx_analysis_queue.empty():
                try:
                    self._tx_analysis_queue.get_nowait()
                    self._tx_analysis_queue.task_done()
                except asyncio.QueueEmpty:
                    break
                
            while not self.profitable_transactions.empty():
                try:
                    self.profitable_transactions.get_nowait()
                    self.profitable_transactions.task_done()
                except asyncio.QueueEmpty:
                    break
            
            # Clear sets and dictionaries
            self._processed_hashes.clear()
            self._tx_cache.clear()
            self.processed_txs.clear()
            self.tx_queue.clear()
            
            # Clear tasks list
            self._tasks.clear()
            
        except Exception as e:
            logger.error(f"Error clearing resources: {e}")
            
        # Close any web3 filters we might have created
        try:
            if hasattr(self, '_pending_filter') and self._pending_filter:
                await self.web3.eth.uninstall_filter(self._pending_filter.filter_id)
                logger.debug("Uninstalled pending filter")
        except Exception as e:
            logger.warning(f"Error uninstalling filter: {e}")
            
        # Close client session if we created it
        if hasattr(self, 'client_session') and self.client_session is not None:
            try:
                await self.client_session.close()
                logger.debug("Closed client session")
                self.client_session = None
                
                # Remove reference from api_config if we set it there
                if self.api_config and hasattr(self.api_config, "session"):
                    if getattr(self.api_config, "session", None) == self.client_session:
                        setattr(self.api_config, "session", None)
            except Exception as e:
                logger.warning(f"Error closing client session: {e}")
            
        logger.info("TxpoolMonitor: successfully stopped")

    async def _collect_hashes(self) -> None:
        """Collect tx hashes via pending-filter, direct txpool access, or block polling."""
        try:
            # Try multiple approaches in order of preference:
            # 1. Direct txpool access (most comprehensive)
            # 2. Pending transaction filter (standard Web3 approach)
            # 3. Block polling (fallback/most compatible)
            
            # First try direct txpool access
            txpool_supported = await self._check_txpool_support()
            
            if txpool_supported:
                logger.info("Using direct txpool_content API for mempool monitoring")
                await self._collect_from_txpool()
            else:
                # Try pending filter next
                try:
                    filt = await self.web3.eth.filter("pending")
                    logger.debug("Using pending-tx filter for mempool monitoring")
                    await self._collect_from_filter(filt)
                except Exception:
                    # Fall back to block polling as last resort
                    filt = None
                    logger.warning("No pending filters or txpool access—falling back to block polling")
                    await self._collect_from_blocks()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Fatal error in _collect_hashes: {e}")
            raise

    async def _check_txpool_support(self) -> bool:
        """Check if the connected node supports txpool_content RPC method.
        
        Returns:
            bool: True if txpool is supported, False otherwise
        """
        try:
            # Attempt to call txpool_content with empty params
            result = await self.web3.manager.coro_request(
                "txpool_content", []
            )
            # If we get a result with the expected structure, txpool is supported
            return result is not None and 'result' in result and 'pending' in result['result']
        except Exception as e:
            logger.debug(f"txpool_content not supported: {e}")
            return False

    async def _collect_from_txpool(self) -> None:
        """Collect transaction hashes directly from the txpool.
        
        This is the most direct method to monitor pending transactions,
        but requires a node that supports the txpool_content API.
        """
        while self._running:
            try:
                # Get all pending transactions from the txpool
                pending_txs = await self.get_pending_transactions()
                
                # Process each transaction
                for tx in pending_txs:
                    if 'hash' in tx and tx['hash']:
                        tx_hash = tx['hash']
                        if isinstance(tx_hash, bytes):
                            tx_hash = tx_hash.hex()
                            
                        # Store the transaction in our cache
                        self._tx_cache[tx_hash] = tx
                        
                        # Enqueue the hash for analysis
                        await self._enqueue_hash(tx_hash)
                        
                # Use an appropriate polling interval
                poll_interval = self.configuration.get("TXPOOL_POLL_INTERVAL", 2.0)
                await asyncio.sleep(poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error collecting from txpool: {e}")
                await asyncio.sleep(5)  # Wait longer on error

    async def _collect_from_filter(self, filt: Any) -> None:
        while self._running:
            try:
                entries = await filt.get_new_entries()
                for h in entries:
                    await self._enqueue_hash(h.hex())
            except Exception:
                await asyncio.sleep(1)

    async def _collect_from_blocks(self) -> None:
        last = await self.web3.eth.block_number
        while self._running:
            try:
                current = await self.web3.eth.block_number
                for n in range(last + 1, current + 1):
                    block = await self.web3.eth.get_block(n, full_transactions=True)
                    for tx in block.transactions:  # type: ignore[attr-defined]
                        txh = (tx.hash if hasattr(tx, "hash") else tx["hash"]).hex()
                        await self._enqueue_hash(txh)
                last = current
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _enqueue_hash(self, tx_hash: str) -> None:
        if tx_hash in self._processed_hashes:
            return
        self._processed_hashes.add(tx_hash)
        await self._tx_hash_queue.put(tx_hash)

    async def _analysis_dispatcher(self) -> None:
        """Dispatch analysis tasks for incoming hashes."""
        while not self._stop_event.is_set():
            try:
                tx_hash = await self._tx_hash_queue.get()
                await self._semaphore.acquire()
                asyncio.create_task(self._process_transaction_safe(tx_hash))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dispatcher error: {e}")

    async def _process_transaction_safe(self, tx_hash: str) -> None:
        """Wrapper that handles exceptions in analysis."""
        try:
            await self._analyse_transaction(tx_hash)
        except Exception as e:
            logger.error(f"Error analyzing {tx_hash}: {e}")
        finally:
            self._semaphore.release()
            self._tx_hash_queue.task_done()

    async def _analyse_transaction(self, tx_hash: str) -> None:
        """Fetch, prioritize, and check profitability of a tx."""
        tx = await self._fetch_transaction(tx_hash)
        if not tx:
            return

        priority = self._calc_priority(tx)
        await self._tx_analysis_queue.put((priority, tx_hash))

        result = await self._is_profitable(tx_hash, tx)
        if result:
            await self.profitable_transactions.put(result)

    async def _fetch_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve tx data, with retries on not-found.
        
        This method tries to get both confirmed and pending transactions from the mempool.
        """
        if tx_hash in self._tx_cache:
            return self._tx_cache[tx_hash]

        delay = self.configuration.get("MEMPOOL_RETRY_DELAY", 0.5)
        max_retries = self.configuration.get("MEMPOOL_MAX_RETRIES", 3)

        for _ in range(max_retries):
            # Try standard method first
            try:
                tx = await self.web3.eth.get_transaction(tx_hash)
                self._tx_cache[tx_hash] = tx
                return tx
            except TransactionNotFound:
                # If not found with standard method, try direct RPC call for pending txs
                try:
                    # Make sure the tx_hash has the 0x prefix required by Ethereum JSON-RPC
                    prefixed_hash = tx_hash if tx_hash.startswith('0x') else f'0x{tx_hash}'
                    
                    # Make a direct RPC call to get pending transaction
                    tx = await self.web3.manager.coro_request(
                        "eth_getTransactionByHash", [prefixed_hash]
                    )
                    if tx:
                        # Process the raw transaction result
                        processed_tx = self._process_raw_tx(tx)
                        if processed_tx:
                            self._tx_cache[tx_hash] = processed_tx
                            return processed_tx
                except Exception as inner_e:
                    logger.debug(f"Direct RPC call for tx {tx_hash} failed: {inner_e}")
                
                # Wait before retrying
                await asyncio.sleep(delay)
                delay *= 1.5
            except Exception as e:
                logger.debug(f"Fetch tx {tx_hash} error: {e}")
                break
        return None

    def _process_raw_tx(self, raw_tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a raw transaction response from JSON-RPC.
        
        Args:
            raw_tx: Raw transaction data from JSON-RPC
            
        Returns:
            Optional[Dict[str, Any]]: Processed transaction or None if invalid
        """
        try:
            if not raw_tx or 'result' not in raw_tx or not raw_tx['result']:
                return None
                
            # Extract the result part which contains the actual transaction data
            tx_data = raw_tx['result']
            
            # Convert hex values to integers where appropriate
            processed_tx = {}
            for key, value in tx_data.items():
                if key in ('blockNumber', 'gas', 'gasPrice', 'nonce', 'value', 'v') and value and value.startswith('0x'):
                    try:
                        processed_tx[key] = int(value, 16)
                    except ValueError:
                        processed_tx[key] = value
                else:
                    processed_tx[key] = value
                    
            # Add any derived fields
            if 'hash' in processed_tx:
                processed_tx['txHash'] = processed_tx['hash']
                
            return processed_tx
        except Exception as e:
            logger.debug(f"Error processing raw transaction: {e}")
            return None

    def _calc_priority(self, tx: Dict[str, Any]) -> int:
        """Lower integers = higher priority (negate gas price)."""
        gp_legacy = tx.get("gasPrice", 0) or 0
        gp_1559 = tx.get("maxFeePerGas", 0) or 0
        effective = max(gp_legacy, gp_1559)
        return -int(effective)

    async def _is_profitable(
        self, tx_hash: str, tx: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Lightweight profit check: filter by monitored tokens and value."""
        to_addr = (tx.get("to") or "").lower()
        if to_addr not in self.monitored_tokens:
            return None

        value = tx.get("value", 0)
        if value <= 0:
            return None

        gas_used = await self.safety_net.estimate_gas(tx)
        gp = tx.get("gasPrice", tx.get("maxFeePerGas", 0))
        gp_gwei = float(self.web3.from_wei(gp, "gwei"))

        tx_data = {
            "output_token": to_addr,
            "amountIn": float(self.web3.from_wei(value, "ether")),
            "amountOut": float(self.web3.from_wei(value, "ether")),
            "gas_price": gp_gwei,
            "gas_used": gas_used,
        }

        safe, details = await self.safety_net.check_transaction_safety(tx_data)
        profit_passed = details["check_details"].get("profit_check", {}).get("passed", False)
        if safe and profit_passed:
            return {
                "is_profitable": True,
                "tx_hash": tx_hash,
                "tx": tx,
                "analysis": details,
                "strategy_type": "front_run",
            }
        return None

    async def is_healthy(self) -> bool:
        """Check health of the txpool monitor."""
        try:
            if not await self.web3.is_connected():
                logger.warning("Web3 connection is down")
                return False

            if self.use_txpool_api:
                try:
                    await self.web3.geth.txpool.status()
                except Exception as e:
                    logger.warning(f"Txpool API unavailable: {e}")

            if not await self.safety_net.is_healthy():
                logger.warning("SafetyNet is unhealthy")
                return False

            if self._stop_event.is_set():
                logger.warning("TxpoolMonitor has been stopped")
                return False

            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def check_health(self) -> bool:
        """Check if this component is healthy and functioning properly.
        
        Returns:
            bool: True if healthy, False if unhealthy
        """
        try:
            # Check web3 connection
            if not await self.web3.is_connected():
                logger.warning("TxpoolMonitor health check failed: web3 connection issue")
                return False
            
            # Check if running
            if not self._running:
                # It's okay if we're not running yet - just report the status
                logger.debug("TxpoolMonitor not running (may be intentional)")
                return True
            
            # Check if tasks are alive
            if self._tasks:
                all_alive = True
                for task in self._tasks:
                    if task.done() or task.cancelled():
                        logger.warning(f"TxpoolMonitor task {task.get_name()} is not running")
                        all_alive = False
                if not all_alive:
                    return False
            
            # If we got this far, we're healthy
            return True
            
        except Exception as e:
            logger.error(f"TxpoolMonitor health check error: {e}")
            return False

    async def _monitor_memory(self) -> None:
        """Periodically clean caches based on memory pressure."""
        interval = self.configuration.get("MEMORY_CHECK_INTERVAL", 300)
        max_cache = self.configuration.get("MAX_TXPOOL_CACHE_SIZE", 10000)

        while not self._stop_event.is_set():
            await asyncio.sleep(interval)
            mem = psutil.virtual_memory().percent
            logger.debug(f"Memory usage: {mem}%")

            if mem > 80:
                logger.warning(f"High memory usage ({mem}%), clearing caches")
                self.processed_txs.clear()
                self._tx_cache.clear()
            elif len(self.processed_txs) > max_cache:
                kept = list(self.processed_txs)[-max_cache:]
                self.processed_txs = set(kept)
                logger.info(f"Trimmed processed_txs to {max_cache} entries")

            logger.debug(
                f"TxpoolMonitor memory stats: {len(self.processed_txs)} processed txs, "
                f"{len(self.tx_queue)} queued"
            )

    async def stop_monitoring(self) -> None:
        """Alias for stop()."""
        await self.stop()

    async def get_pending_transactions(self) -> List[Dict[str, Any]]:
        """Fetch all current pending transactions from the txpool.
        
        This method uses the geth-specific RPC method 'txpool_content' to get all
        pending transactions directly from the mempool.
        
        Returns:
            List of pending transactions
        """
        pending_txs = []
        
        try:
            # Call the non-standard RPC method to get txpool content
            txpool_content = await self.web3.manager.coro_request(
                "txpool_content", []
            )
            
            # Extract pending transactions from the result
            if txpool_content and 'result' in txpool_content:
                pending_data = txpool_content['result'].get('pending', {})
                
                # Process each pending transaction
                for sender_address, nonce_dict in pending_data.items():
                    for nonce, tx_data in nonce_dict.items():
                        # Get transaction hash and ensure it has 0x prefix
                        tx_hash = tx_data.get('hash', '')
                        if tx_hash and not tx_hash.startswith('0x'):
                            tx_hash = f'0x{tx_hash}'
                            
                        # Process the transaction data
                        processed_tx = {
                            'hash': tx_hash,
                            'from': sender_address,
                            'to': tx_data.get('to'),
                            'value': int(tx_data.get('value', '0x0'), 16),
                            'gasPrice': int(tx_data.get('gasPrice', '0x0'), 16),
                            'gas': int(tx_data.get('gas', '0x0'), 16),
                            'nonce': int(nonce, 16),  # Convert nonce from hex to int
                            'input': tx_data.get('input'),
                            'pending': True
                        }
                        
                        # Add gas_price for consistency with Web3.py naming
                        processed_tx['gas_price'] = processed_tx['gasPrice']
                        
                        # Add to our list
                        pending_txs.append(processed_tx)
                        
                        # Cache the transaction
                        if 'hash' in tx_data:
                            self._tx_cache[tx_data['hash']] = processed_tx
        except Exception as e:
            logger.warning(f"Failed to fetch txpool content: {e}")
            
        return pending_txs

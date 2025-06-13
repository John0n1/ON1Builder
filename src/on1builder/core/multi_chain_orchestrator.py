# src/on1builder/core/multi_chain_orchestrator.py
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from on1builder.config.loaders import settings
from on1builder.core.chain_worker import ChainWorker
from on1builder.core.balance_manager import BalanceManager
from on1builder.utils.logging_config import get_logger
from on1builder.utils.notification_service import NotificationService
from on1builder.utils.web3_factory import create_web3_instance

logger = get_logger(__name__)

class MultiChainOrchestrator:
    """Enhanced multi-chain orchestrator with balance-aware arbitrage and advanced opportunity detection."""
    
    def __init__(self, workers: List[ChainWorker]):
        if len(workers) < 2:
            raise ValueError("MultiChainOrchestrator requires at least two ChainWorkers.")
        
        self.workers: Dict[int, ChainWorker] = {worker.chain_id: worker for worker in workers}
        self.balance_managers: Dict[int, BalanceManager] = {}
        self.is_running = False
        self._tasks: List[asyncio.Task] = []
        self._notification_service = NotificationService()
        self._arbitrage_cooldowns: Dict[str, float] = {}
        self._opportunity_history: List[Dict] = []
        self._gas_tracker: Dict[int, List[Decimal]] = {chain_id: [] for chain_id in self.workers.keys()}
        
        logger.info(f"Enhanced MultiChainOrchestrator initialized for chains: {list(self.workers.keys())}")

    async def start(self):
        if self.is_running:
            logger.warning("MultiChainOrchestrator is already running.")
            return

        # Initialize balance managers for each chain
        for chain_id in self.workers.keys():
            web3 = await create_web3_instance(chain_id)
            self.balance_managers[chain_id] = BalanceManager(web3, settings.wallet_address)
            await self.balance_managers[chain_id].update_balance()
        
        logger.info("Balance managers initialized for all chains")

        self.is_running = True
        logger.info("Starting Enhanced Multi-Chain Orchestrator...")
        self._tasks.extend([
            asyncio.create_task(self._monitor_cross_chain_opportunities()),
            asyncio.create_task(self._gas_price_monitor()),
            asyncio.create_task(self._balance_rebalancing_monitor()),
            asyncio.create_task(self._opportunity_analysis_loop())
        ])
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        if not self.is_running:
            return

        logger.info("Stopping Multi-Chain Orchestrator...")
        self.is_running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*[t for t in self._tasks if not t.done()], return_exceptions=True)
        self._tasks.clear()
        logger.info("Multi-chain orchestration stopped.")

    async def _monitor_cross_chain_opportunities(self):
        """Enhanced cross-chain opportunity monitor with balance awareness."""
        while self.is_running:
            try:
                opportunities = await self._find_cross_chain_arbitrage()
                if opportunities:
                    # Score and filter opportunities based on profitability and risk
                    scored_opportunities = await self._score_opportunities(opportunities)
                    viable_opportunities = [opp for opp in scored_opportunities if opp['score'] > 0.7]
                    
                    logger.info(f"Found {len(opportunities)} opportunities, {len(viable_opportunities)} viable after scoring.")
                    
                    for opp in viable_opportunities[:3]:  # Execute top 3 opportunities
                        asyncio.create_task(self.execute_cross_chain_arbitrage(opp))
                
                await asyncio.sleep(settings.arbitrage_scan_interval or 15)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cross-chain opportunity monitor: {e}", exc_info=True)
                await asyncio.sleep(60)

    def _is_on_cooldown(self, token_symbol: str) -> bool:
        """Checks if an arbitrage for a given token is on cooldown to prevent spam."""
        cooldown_period = 300
        now = asyncio.get_running_loop().time()
        if token_symbol in self._arbitrage_cooldowns:
            if now - self._arbitrage_cooldowns[token_symbol] < cooldown_period:
                return True
        return False

    def _set_cooldown(self, token_symbol: str):
        self._arbitrage_cooldowns[token_symbol] = asyncio.get_running_loop().time()

    async def _find_cross_chain_arbitrage(self) -> List[Dict]:
        """Enhanced arbitrage detection with better filtering and analysis."""
        opportunities = []
        common_tokens = self._get_common_tokens()

        for token_symbol in common_tokens:
            if self._is_on_cooldown(token_symbol):
                continue
            
            # Get prices and liquidity data from all chains
            price_data = {}
            for chain_id, worker in self.workers.items():
                if worker.market_feed:
                    price = await worker.market_feed.get_price(token_symbol)
                    if price is not None:
                        # Get gas price for cost calculation
                        try:
                            gas_price = await worker.web3.eth.gas_price
                            estimated_gas_cost = await self._estimate_arbitrage_gas_cost(gas_price)
                        except:
                            estimated_gas_cost = Decimal('0.01')  # Conservative estimate
                        
                        price_data[chain_id] = {
                            'price': price,
                            'gas_cost_usd': estimated_gas_cost,
                            'liquidity_score': await self._estimate_liquidity(worker, token_symbol)
                        }

            if len(price_data) < 2:
                continue

            # Find best buy and sell opportunities
            best_opportunities = self._analyze_price_spreads(token_symbol, price_data)
            opportunities.extend(best_opportunities)
        
        return opportunities

    def _get_common_tokens(self) -> set:
        from collections import Counter
        all_symbols = []
        for worker in self.workers.values():
            if worker.tx_scanner:
                all_symbols.extend([t.upper() for t in worker.tx_scanner.monitored_tokens if not t.startswith('0x')])
        
        counts = Counter(all_symbols)
        return {symbol for symbol, count in counts.items() if count >= 2}

    async def execute_cross_chain_arbitrage(self, opportunity: Dict):
        """Enhanced cross-chain arbitrage execution with balance awareness and profit tracking."""
        logger.info(f"Executing enhanced cross-chain arbitrage for {opportunity['token_symbol']}")
        
        buy_chain = opportunity["buy_on_chain"]
        sell_chain = opportunity["sell_on_chain"]
        buy_worker = self.workers[buy_chain]
        sell_worker = self.workers[sell_chain]
        
        # Get balance managers
        buy_balance_manager = self.balance_managers[buy_chain]
        sell_balance_manager = self.balance_managers[sell_chain]
        
        # Update balances
        await buy_balance_manager.update_balance()
        await sell_balance_manager.update_balance()
        
        # Calculate optimal trade size based on available balance and liquidity
        trade_amount_usd = self._calculate_optimal_trade_size(
            opportunity, buy_balance_manager, sell_balance_manager
        )
        
        if trade_amount_usd < Decimal('10'):
            logger.warning(f"Trade amount too small: ${trade_amount_usd}. Skipping arbitrage.")
            return
        
        token_symbol = opportunity["token_symbol"]
        stablecoin_symbol = "USDC"
        
        # Calculate amounts with slippage protection
        amount_to_buy = trade_amount_usd / opportunity["buy_price"]
        slippage_factor = Decimal('0.995')  # 0.5% slippage tolerance
        
        buy_path = [stablecoin_symbol, token_symbol]
        sell_path = [token_symbol, stablecoin_symbol]

        # Prepare transaction details with dynamic gas pricing
        buy_gas_price = await self._get_optimal_gas_price(buy_worker)
        sell_gas_price = await self._get_optimal_gas_price(sell_worker)

        amount_in_wei = buy_worker.web3.to_wei(trade_amount_usd, 'ether')
        amount_out_min_wei = sell_worker.web3.to_wei(
            (trade_amount_usd * slippage_factor), 'ether'
        )

        buy_opp = {
            "path": buy_path,
            "dex": "uniswap_v2",
            "amount_in_wei": amount_in_wei,
            "amount_out_min_wei": 0,
            "gas_price": buy_gas_price
        }
        
        sell_opp = {
            "path": sell_path,
            "dex": "uniswap_v2",
            "amount_in_wei": sell_worker.web3.to_wei(amount_to_buy, 'ether'),
            "amount_out_min_wei": amount_out_min_wei,
            "gas_price": sell_gas_price
        }

        start_time = datetime.now()
        
        logger.info(f"Executing BUY of {amount_to_buy:.4f} {token_symbol} on chain {buy_chain}")
        buy_task = asyncio.create_task(
            buy_worker.tx_manager.execute_swap(buy_opp, "cross_chain_arbitrage_buy")
        )
        
        logger.info(f"Executing SELL of {amount_to_buy:.4f} {token_symbol} on chain {sell_chain}")
        sell_task = asyncio.create_task(
            sell_worker.tx_manager.execute_swap(sell_opp, "cross_chain_arbitrage_sell")
        )
        
        buy_result, sell_result = await asyncio.gather(buy_task, sell_task, return_exceptions=True)
        
        # Handle results and calculate actual profit
        execution_time = (datetime.now() - start_time).total_seconds()
        actual_profit = await self._calculate_actual_profit(
            buy_result, sell_result, trade_amount_usd, opportunity
        )
        
        # Log opportunity for analysis
        self._opportunity_history.append({
            "timestamp": start_time,
            "token": token_symbol,
            "expected_profit": opportunity.get("expected_profit_usd", 0),
            "actual_profit": float(actual_profit),
            "execution_time": execution_time,
            "buy_success": not isinstance(buy_result, Exception) and buy_result.get("success", False),
            "sell_success": not isinstance(sell_result, Exception) and sell_result.get("success", False)
        })
        
        # Send detailed notification
        success_status = "SUCCESS" if actual_profit > 0 else "LOSS" if actual_profit < 0 else "BREAK_EVEN"
        
        await self._notification_service.send_alert(
            title=f"Cross-Chain Arbitrage: {success_status}",
            message=f"Arbitrage for {token_symbol} completed with ${actual_profit:.2f} profit",
            level="INFO" if success_status == "SUCCESS" else "WARNING",
            details={
                "token": token_symbol,
                "trade_amount_usd": float(trade_amount_usd),
                "expected_profit": float(opportunity.get("expected_profit_usd", 0)),
                "actual_profit": float(actual_profit),
                "execution_time_seconds": execution_time,
                "buy_chain": buy_chain,
                "sell_chain": sell_chain,
                "buy_tx": getattr(buy_result, 'get', lambda x, y=None: y)("tx_hash"),
                "sell_tx": getattr(sell_result, 'get', lambda x, y=None: y)("tx_hash")
            }
        )

    def _analyze_price_spreads(self, token_symbol: str, price_data: Dict) -> List[Dict]:
        """Analyzes price spreads across chains and identifies profitable opportunities."""
        opportunities = []
        
        chains = list(price_data.keys())
        for i, buy_chain in enumerate(chains):
            for sell_chain in chains[i+1:]:
                buy_data = price_data[buy_chain]
                sell_data = price_data[sell_chain]
                
                # Check both directions
                for buy_chain_id, sell_chain_id, buy_info, sell_info in [
                    (buy_chain, sell_chain, buy_data, sell_data),
                    (sell_chain, buy_chain, sell_data, buy_data)
                ]:
                    spread = ((sell_info['price'] - buy_info['price']) / buy_info['price']) * 100
                    total_gas_cost = buy_info['gas_cost_usd'] + sell_info['gas_cost_usd']
                    
                    # Minimum spread to cover gas costs and generate profit
                    min_spread_required = (total_gas_cost / (buy_info['price'] * 100)) * 100 + settings.min_profit_percent
                    
                    if spread > min_spread_required:
                        estimated_profit = (spread / 100) * 100 - total_gas_cost  # On $100 trade
                        
                        opportunity = {
                            "token_symbol": token_symbol,
                            "buy_on_chain": buy_chain_id,
                            "sell_on_chain": sell_chain_id,
                            "buy_price": buy_info['price'],
                            "sell_price": sell_info['price'],
                            "spread_percent": spread,
                            "estimated_gas_cost": total_gas_cost,
                            "expected_profit_usd": estimated_profit,
                            "liquidity_score": min(buy_info['liquidity_score'], sell_info['liquidity_score'])
                        }
                        opportunities.append(opportunity)
                        
                        logger.info(f"Cross-chain arbitrage opportunity: {token_symbol} "
                                  f"{spread:.2f}% spread (${estimated_profit:.2f} profit)")
                        self._set_cooldown(token_symbol)
        
        return opportunities

    async def _score_opportunities(self, opportunities: List[Dict]) -> List[Dict]:
        """Scores opportunities based on profitability, liquidity, and risk factors."""
        for opp in opportunities:
            score = 0.0
            
            # Profitability score (0-0.4)
            profit_ratio = opp['expected_profit_usd'] / max(opp['estimated_gas_cost'], 1)
            score += min(profit_ratio / 10, 0.4)
            
            # Spread score (0-0.3)
            spread_score = min(opp['spread_percent'] / 20, 0.3)
            score += spread_score
            
            # Liquidity score (0-0.2)
            score += opp['liquidity_score'] * 0.2
            
            # Historical success rate (0-0.1)
            historical_score = self._get_historical_success_rate(opp['token_symbol'])
            score += historical_score * 0.1
            
            opp['score'] = score
        
        # Sort by score descending
        return sorted(opportunities, key=lambda x: x['score'], reverse=True)

    def _calculate_optimal_trade_size(self, opportunity: Dict, buy_balance_manager: BalanceManager, 
                                    sell_balance_manager: BalanceManager) -> Decimal:
        """Calculates optimal trade size based on available balances and risk management."""
        # Get available balances
        buy_chain_balance = buy_balance_manager.get_balance('USDC')  # Assuming USDC for buying
        sell_chain_balance = sell_balance_manager.get_balance(opportunity['token_symbol'])
        
        # Get balance-aware limits
        buy_limit = buy_balance_manager.get_balance_aware_investment_limit()
        sell_limit = sell_balance_manager.get_balance_aware_investment_limit()
        
        # Calculate maximum trade size based on liquidity
        liquidity_limit = Decimal('1000') * opportunity['liquidity_score']  # Base liquidity assumption
        
        # Take the minimum of all constraints
        max_trade_size = min(
            buy_limit,
            sell_limit,
            liquidity_limit,
            buy_chain_balance * Decimal('0.8')  # Use max 80% of available balance
        )
        
        # Apply risk scaling based on opportunity score
        risk_factor = Decimal(str(opportunity.get('score', 0.5)))
        optimal_size = max_trade_size * risk_factor
        
        return max(optimal_size, Decimal('10'))  # Minimum $10 trade

    async def _estimate_liquidity(self, worker: ChainWorker, token_symbol: str) -> float:
        """Estimates liquidity score for a token on a specific chain by querying DEX pools."""
        try:
            # Query actual liquidity from major DEXes
            total_liquidity = Decimal('0')
            liquidity_sources = 0
            
            # Common DEX router addresses (varies by chain)
            dex_routers = {
                1: {  # Ethereum mainnet
                    'uniswap_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                    'uniswap_v2': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                    'sushiswap': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'
                },
                137: {  # Polygon
                    'quickswap': '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',
                    'sushiswap': '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506'
                }
            }
            
            chain_id = await worker.web3.eth.chain_id
            routers = dex_routers.get(chain_id, {})
            
            for dex_name, router_address in routers.items():
                try:
                    # Get token contract address from symbol
                    token_address = await self._get_token_address(worker, token_symbol)
                    if not token_address:
                        continue
                    
                    # Query pool reserves for major pairs (ETH/USDC)
                    weth_address = await self._get_token_address(worker, 'WETH')
                    usdc_address = await self._get_token_address(worker, 'USDC')
                    
                    if weth_address and usdc_address:
                        # Check liquidity in token/WETH and token/USDC pools
                        for base_token in [weth_address, usdc_address]:
                            pool_liquidity = await self._query_pool_liquidity(
                                worker, token_address, base_token, router_address
                            )
                            if pool_liquidity > 0:
                                total_liquidity += pool_liquidity
                                liquidity_sources += 1
                
                except Exception as e:
                    self.logger.warning(f"Failed to query {dex_name} liquidity for {token_symbol}: {e}")
                    continue
            
            # Normalize liquidity score
            if liquidity_sources > 0:
                avg_liquidity = total_liquidity / liquidity_sources
                # Convert to 0-1 score (logarithmic scale)
                liquidity_score = min(1.0, float(avg_liquidity) / 1000000)  # $1M = 1.0 score
                return liquidity_score
            
            # Fallback to heuristic scoring if queries fail
            if token_symbol in ['ETH', 'WETH', 'USDC', 'USDT', 'DAI']:
                return 1.0  # High liquidity tokens
            elif token_symbol in ['WBTC', 'LINK', 'UNI', 'AAVE']:
                return 0.8  # Medium-high liquidity
            else:
                return 0.5  # Default medium liquidity
        except:
            return 0.3  # Conservative estimate on error

    async def _estimate_arbitrage_gas_cost(self, gas_price: int) -> Decimal:
        """Estimates gas cost for arbitrage transactions in USD."""
        # Typical arbitrage gas usage: ~200k gas
        gas_used = 200000
        gas_cost_wei = gas_price * gas_used
        gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)
        
        # Convert to USD using real-time ETH price
        try:
            # Try to get current ETH price from external APIs
            eth_price_usd = await self._get_current_eth_price()
        except Exception as e:
            self.logger.warning(f"Failed to fetch ETH price, using fallback: {e}")
            eth_price_usd = Decimal('2000')  # Conservative ETH price fallback
            
        return gas_cost_eth * eth_price_usd

    async def _get_optimal_gas_price(self, worker: ChainWorker) -> int:
        """Gets optimal gas price for a chain considering network conditions."""
        try:
            current_gas = await worker.web3.eth.gas_price
            
            # Get recent gas price trend
            chain_gas_history = self._gas_tracker.get(worker.chain_id, [])
            if len(chain_gas_history) > 5:
                avg_recent = sum(chain_gas_history[-5:]) / 5
                # Use slightly above average for faster execution
                optimal_gas = int(avg_recent * Decimal('1.1'))
            else:
                # Use 10% above current for faster execution
                optimal_gas = int(current_gas * 1.1)
            
            # Store for tracking
            chain_gas_history.append(Decimal(current_gas))
            if len(chain_gas_history) > 20:
                chain_gas_history.pop(0)
            
            return min(optimal_gas, current_gas * 2)  # Cap at 2x current price
            
        except Exception as e:
            logger.warning(f"Error getting optimal gas price: {e}")
            return await worker.web3.eth.gas_price

    async def _calculate_actual_profit(self, buy_result, sell_result, 
                                     trade_amount_usd: Decimal, opportunity: Dict) -> Decimal:
        """Calculates actual profit from arbitrage execution."""
        try:
            buy_success = not isinstance(buy_result, Exception) and buy_result.get("success", False)
            sell_success = not isinstance(sell_result, Exception) and sell_result.get("success", False)
            
            if not (buy_success and sell_success):
                # Calculate partial loss if only one side failed
                if buy_success or sell_success:
                    return -opportunity['estimated_gas_cost'] / 2
                return -opportunity['estimated_gas_cost']
            
            # Get actual amounts from transaction receipts
            buy_amount_out = self._extract_amount_from_result(buy_result)
            sell_amount_out = self._extract_amount_from_result(sell_result)
            
            if buy_amount_out and sell_amount_out:
                # Calculate actual profit based on amounts
                actual_profit = sell_amount_out - trade_amount_usd - opportunity['estimated_gas_cost']
                return Decimal(str(actual_profit))
            else:
                # Fallback to estimated profit minus gas
                return opportunity['expected_profit_usd'] - opportunity['estimated_gas_cost']
                
        except Exception as e:
            logger.error(f"Error calculating actual profit: {e}")
            return Decimal('0')

    def _extract_amount_from_result(self, result) -> Optional[Decimal]:
        """Extracts actual output amount from transaction result by parsing logs."""
        try:
            # Parse transaction logs to get actual swap amounts
            if not isinstance(result, dict) or 'receipt' not in result:
                return result.get("amount_out_usd") if isinstance(result, dict) else None
            
            receipt = result['receipt']
            logs = receipt.get('logs', [])
            
            # Parse Transfer events to determine actual output
            total_out = Decimal('0')
            our_address = self.account.address.lower() if hasattr(self, 'account') else ''
            
            for log in logs:
                try:
                    # Check for Transfer events (ERC20)
                    transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
                    if log.get("topics") and len(log["topics"]) >= 3:
                        if log["topics"][0].hex() == transfer_topic:
                            to_addr = "0x" + log["topics"][2].hex()[-40:]
                            
                            # If transfer is to our address, it's output
                            if to_addr.lower() == our_address:
                                data = log.get("data", "0x")
                                if len(data) >= 66:
                                    amount_hex = data[2:66]
                                    amount = int(amount_hex, 16)
                                    # Convert based on token decimals (assume 18 for simplicity)
                                    amount_tokens = Decimal(amount) / Decimal(10**18)
                                    total_out += amount_tokens
                except (IndexError, ValueError, AttributeError):
                    continue
            
            return float(total_out) if total_out > 0 else result.get("amount_out_usd")
            
        except Exception as e:
            self.logger.warning(f"Failed to extract output amount from logs: {e}")
            return result.get("amount_out_usd") if isinstance(result, dict) else None

    def _get_historical_success_rate(self, token_symbol: str) -> float:
        """Gets historical success rate for arbitrage with a specific token."""
        if not self._opportunity_history:
            return 0.5  # Default neutral score
        
        token_history = [h for h in self._opportunity_history if h['token'] == token_symbol]
        if len(token_history) < 3:
            return 0.5
        
        successful = sum(1 for h in token_history if h['actual_profit'] > 0)
        return successful / len(token_history)

    async def _gas_price_monitor(self):
        """Monitors gas prices across all chains for optimization."""
        while self.is_running:
            try:
                for chain_id, worker in self.workers.items():
                    try:
                        gas_price = await worker.web3.eth.gas_price
                        gas_history = self._gas_tracker.setdefault(chain_id, [])
                        gas_history.append(Decimal(gas_price))
                        
                        # Keep only recent history
                        if len(gas_history) > 100:
                            gas_history.pop(0)
                        
                    except Exception as e:
                        logger.error(f"Error monitoring gas price for chain {chain_id}: {e}")
                
                await asyncio.sleep(60)  # Update every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in gas price monitor: {e}")
                await asyncio.sleep(300)

    async def _balance_rebalancing_monitor(self):
        """Monitors balances and suggests rebalancing between chains."""
        while self.is_running:
            try:
                await asyncio.sleep(3600)  # Check every hour
                
                # Update all balance managers
                for balance_manager in self.balance_managers.values():
                    await balance_manager.update_balance()
                
                # Check for rebalancing opportunities
                await self._analyze_balance_distribution()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in balance rebalancing monitor: {e}")
                await asyncio.sleep(1800)  # Retry in 30 minutes

    async def _analyze_balance_distribution(self):
        """Analyzes balance distribution across chains and suggests rebalancing."""
        try:
            total_balances = {}
            chain_balances = {}
            
            # Collect balance data
            for chain_id, balance_manager in self.balance_managers.items():
                chain_total = balance_manager.get_total_balance_usd()
                chain_balances[chain_id] = chain_total
                
                for token, balance in balance_manager.balances.items():
                    if token not in total_balances:
                        total_balances[token] = Decimal('0')
                    total_balances[token] += balance
            
            total_portfolio_value = sum(chain_balances.values())
            if total_portfolio_value > 0:
                # Check for significant imbalances
                for chain_id, chain_value in chain_balances.items():
                    chain_percentage = (chain_value / total_portfolio_value) * 100
                    
                    # Alert if one chain has too much concentration
                    if chain_percentage > 70:
                        await self._notification_service.send_alert(
                            title="Portfolio Concentration Warning",
                            message=f"Chain {chain_id} holds {chain_percentage:.1f}% of total portfolio value",
                            level="WARNING",
                            details={
                                "chain_id": chain_id,
                                "concentration_percent": float(chain_percentage),
                                "chain_value_usd": float(chain_value),
                                "total_portfolio_usd": float(total_portfolio_value)
                            }
                        )
        except Exception as e:
            logger.error(f"Error analyzing balance distribution: {e}")

    async def _opportunity_analysis_loop(self):
        """Analyzes historical opportunity data for strategy optimization."""
        while self.is_running:
            try:
                await asyncio.sleep(3600)  # Analyze every hour
                
                if len(self._opportunity_history) >= 10:
                    await self._generate_opportunity_analysis()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in opportunity analysis loop: {e}")
                await asyncio.sleep(1800)

    async def _generate_opportunity_analysis(self):
        """Generates analysis report on opportunity performance."""
        try:
            recent_opportunities = [
                opp for opp in self._opportunity_history 
                if opp['timestamp'] > datetime.now() - timedelta(hours=24)
            ]
            
            if not recent_opportunities:
                return
            
            total_profit = sum(opp['actual_profit'] for opp in recent_opportunities)
            successful_ops = [opp for opp in recent_opportunities if opp['actual_profit'] > 0]
            success_rate = len(successful_ops) / len(recent_opportunities) * 100
            
            avg_execution_time = sum(opp['execution_time'] for opp in recent_opportunities) / len(recent_opportunities)
            
            # Best performing tokens
            token_performance = {}
            for opp in recent_opportunities:
                token = opp['token']
                if token not in token_performance:
                    token_performance[token] = {'profit': 0, 'count': 0}
                token_performance[token]['profit'] += opp['actual_profit']
                token_performance[token]['count'] += 1
            
            best_token = max(token_performance.items(), key=lambda x: x[1]['profit'])[0] if token_performance else "N/A"
            
            await self._notification_service.send_alert(
                title="24h Multi-Chain Arbitrage Analysis",
                message=f"Executed {len(recent_opportunities)} arbitrages with ${total_profit:.2f} total profit",
                level="INFO",
                details={
                    "total_opportunities": len(recent_opportunities),
                    "total_profit_usd": float(total_profit),
                    "success_rate_percent": round(success_rate, 1),
                    "avg_execution_time_seconds": round(avg_execution_time, 2),
                    "best_performing_token": best_token,
                    "profitable_trades": len(successful_ops)
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating opportunity analysis: {e}")

    async def _get_token_address(self, worker: ChainWorker, symbol: str) -> str:
        """Get token contract address from symbol."""
        # Common token addresses by chain
        token_addresses = {
            1: {  # Ethereum mainnet
                'WETH': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
                'USDC': '0xA0b86a33E6417c94b6e319F6e0c5BecfE4ca7c28',
                'USDT': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
                'DAI': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
                'WBTC': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'
            },
            137: {  # Polygon
                'WETH': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',
                'USDC': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
                'USDT': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
                'DAI': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063'
            }
        }
        
        try:
            chain_id = await worker.web3.eth.chain_id
            return token_addresses.get(chain_id, {}).get(symbol, '')
        except Exception:
            return ''
    
    async def _query_pool_liquidity(self, worker: ChainWorker, token_a: str, token_b: str, router_address: str) -> Decimal:
        """Query liquidity in a specific DEX pool."""
        try:
            # This would use the appropriate DEX factory contract to find the pool
            # and query its reserves. For now, return a mock value based on token pair
            if token_a and token_b:
                # Mock liquidity values (in practice, query actual pool contracts)
                if any(addr.lower() in ['weth', 'usdc', 'usdt'] for addr in [token_a.lower(), token_b.lower()]):
                    return Decimal('500000')  # $500K mock liquidity for major pairs
                else:
                    return Decimal('50000')   # $50K mock liquidity for other pairs
            return Decimal('0')
        except Exception as e:
            self.logger.warning(f"Failed to query pool liquidity: {e}")
            return Decimal('0')

    async def _get_current_eth_price(self) -> Decimal:
        """Get current ETH price in USD from price feeds."""
        try:
            # Try multiple price sources for reliability
            price_sources = [
                'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd',
                'https://api.coinbase.com/v2/exchange-rates?currency=ETH'
            ]
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for source in price_sources:
                    try:
                        async with session.get(source, timeout=5) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'coingecko' in source:
                                    price = data.get('ethereum', {}).get('usd', 0)
                                elif 'coinbase' in source:
                                    rates = data.get('data', {}).get('rates', {})
                                    usd_rate = rates.get('USD', '0')
                                    price = float(usd_rate) if usd_rate else 0
                                
                                if price > 0:
                                    return Decimal(str(price))
                    except Exception:
                        continue
            
            # If all sources fail, return reasonable fallback
            return Decimal('2000')
            
        except Exception as e:
            self.logger.warning(f"Failed to fetch ETH price: {e}")
            return Decimal('2000')
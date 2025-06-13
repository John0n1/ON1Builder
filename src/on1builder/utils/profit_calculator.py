# src/on1builder/utils/profit_calculator.py
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import json

from web3 import AsyncWeb3
from web3.types import TxReceipt

from on1builder.integrations.abi_registry import ABIRegistry
from on1builder.utils.logging_config import get_logger

logger = get_logger(__name__)

class ProfitCalculator:
    """Advanced profit calculation with transaction log parsing and flash loan analysis."""
    
    def __init__(self, web3: AsyncWeb3):
        self._web3 = web3
        self._abi_registry = ABIRegistry()
        self._token_decimals_cache: Dict[str, int] = {}
        self._price_cache: Dict[str, Decimal] = {}
        
        # Common DEX event signatures
        self._event_signatures = {
            'Transfer': '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',
            'Swap': '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822',  # Uniswap V2
            'SwapV3': '0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67',  # Uniswap V3
            'Sync': '0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1',
            'FlashLoan': '0x631042c832b07452973831137f2d73e395028b44b250dedc5abb0ee766e168ac'
        }
        
    async def calculate_transaction_profit(self, tx_hash: str, strategy_type: str,
                                         expected_tokens: List[str] = None) -> Dict[str, Any]:
        """
        Calculate actual profit from a transaction by parsing logs.
        
        Args:
            tx_hash: Transaction hash to analyze
            strategy_type: Type of strategy executed
            expected_tokens: List of tokens involved in the strategy
        """
        try:
            # Get transaction receipt
            receipt = await self._web3.eth.get_transaction_receipt(tx_hash)
            transaction = await self._web3.eth.get_transaction(tx_hash)
            
            if not receipt or not transaction:
                return {"error": "Transaction not found"}
            
            # Calculate gas cost
            gas_cost = self._calculate_gas_cost(receipt, transaction)
            
            # Parse logs for token movements
            token_movements = await self._parse_token_movements(receipt.logs)
            
            # Calculate net profit based on strategy type
            profit_analysis = await self._analyze_profit_by_strategy(
                token_movements, gas_cost, strategy_type, expected_tokens
            )
            
            return {
                "tx_hash": tx_hash,
                "strategy_type": strategy_type,
                "gas_cost_eth": float(gas_cost),
                "gas_cost_usd": float(await self._convert_eth_to_usd(gas_cost)),
                "token_movements": token_movements,
                "profit_analysis": profit_analysis,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating profit for {tx_hash}: {e}")
            return {"error": str(e)}

    def _calculate_gas_cost(self, receipt: TxReceipt, transaction: Any) -> Decimal:
        """Calculate gas cost in ETH."""
        gas_used = receipt.gasUsed
        gas_price = transaction.get('gasPrice', 0)
        
        # Handle EIP-1559 transactions
        if 'effectiveGasPrice' in receipt:
            gas_price = receipt['effectiveGasPrice']
        
        gas_cost_wei = gas_used * gas_price
        return Decimal(gas_cost_wei) / Decimal(10**18)

    async def _parse_token_movements(self, logs: List[Dict]) -> List[Dict[str, Any]]:
        """Parse transaction logs to extract token movements."""
        movements = []
        
        for log in logs:
            try:
                # Check if it's a Transfer event
                if len(log.topics) > 0 and log.topics[0].hex() == self._event_signatures['Transfer']:
                    movement = await self._parse_transfer_log(log)
                    if movement:
                        movements.append(movement)
                
                # Check if it's a Swap event
                elif len(log.topics) > 0 and log.topics[0].hex() in [
                    self._event_signatures['Swap'], 
                    self._event_signatures['SwapV3']
                ]:
                    swap = await self._parse_swap_log(log)
                    if swap:
                        movements.append(swap)
                
                # Check for FlashLoan events
                elif len(log.topics) > 0 and log.topics[0].hex() == self._event_signatures['FlashLoan']:
                    flash_loan = await self._parse_flash_loan_log(log)
                    if flash_loan:
                        movements.append(flash_loan)
                        
            except Exception as e:
                logger.debug(f"Error parsing log: {e}")
                continue
        
        return movements

    async def _parse_transfer_log(self, log: Dict) -> Optional[Dict[str, Any]]:
        """Parse ERC20 Transfer event."""
        try:
            if len(log.topics) < 3:
                return None
            
            token_address = log.address.lower()
            from_address = '0x' + log.topics[1].hex()[-40:]
            to_address = '0x' + log.topics[2].hex()[-40:]
            
            # Amount is in the data field
            amount_hex = log.data
            amount_wei = int(amount_hex, 16) if amount_hex else 0
            
            # Get token decimals
            decimals = await self._get_token_decimals(token_address)
            amount = Decimal(amount_wei) / Decimal(10**decimals)
            
            # Get token symbol
            token_symbol = self._abi_registry.get_token_symbol_by_address(token_address)
            
            return {
                "type": "transfer",
                "token_address": token_address,
                "token_symbol": token_symbol or "UNKNOWN",
                "from_address": from_address,
                "to_address": to_address,
                "amount": float(amount),
                "amount_usd": float(await self._convert_token_to_usd(amount, token_symbol))
            }
            
        except Exception as e:
            logger.debug(f"Error parsing transfer log: {e}")
            return None

    async def _parse_swap_log(self, log: Dict) -> Optional[Dict[str, Any]]:
        """Parse DEX swap event using proper ABI decoding."""
        try:
            # Known DEX swap event signatures
            swap_signatures = {
                # Uniswap V2 Swap event
                "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822": {
                    "name": "Swap",
                    "dex_type": "uniswap_v2",
                    "abi": ["uint256", "uint256", "uint256", "uint256", "address"]
                },
                # Uniswap V3 Swap event  
                "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67": {
                    "name": "Swap", 
                    "dex_type": "uniswap_v3",
                    "abi": ["int256", "int256", "uint160", "uint128", "int24"]
                },
                # SushiSwap (same as Uniswap V2)
                "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822": {
                    "name": "Swap",
                    "dex_type": "sushiswap", 
                    "abi": ["uint256", "uint256", "uint256", "uint256", "address"]
                }
            }
            
            if not log.topics or len(log.topics) == 0:
                return None
                
            event_signature = log.topics[0].hex()
            if event_signature not in swap_signatures:
                return None
                
            event_info = swap_signatures[event_signature]
            
            # Decode the swap data based on DEX type
            try:
                from eth_abi import decode_abi
                
                # Decode data field
                decoded_data = decode_abi(event_info["abi"], bytes.fromhex(log.data[2:]))
                
                if event_info["dex_type"] in ["uniswap_v2", "sushiswap"]:
                    # Uniswap V2/SushiSwap: (amount0In, amount1In, amount0Out, amount1Out, to)
                    amount0_in, amount1_in, amount0_out, amount1_out, to_addr = decoded_data
                    
                    return {
                        "type": "swap",
                        "dex_address": log.address.lower(),
                        "dex_type": event_info["dex_type"],
                        "block_number": log.blockNumber,
                        "transaction_hash": log.transactionHash.hex(),
                        "amount0_in": amount0_in,
                        "amount1_in": amount1_in, 
                        "amount0_out": amount0_out,
                        "amount1_out": amount1_out,
                        "to_address": to_addr.lower() if isinstance(to_addr, str) else "",
                        "log_index": log.logIndex
                    }
                    
                elif event_info["dex_type"] == "uniswap_v3":
                    # Uniswap V3: (amount0, amount1, sqrtPriceX96, liquidity, tick)
                    amount0, amount1, sqrt_price, liquidity, tick = decoded_data
                    
                    return {
                        "type": "swap",
                        "dex_address": log.address.lower(),
                        "dex_type": event_info["dex_type"],
                        "block_number": log.blockNumber,
                        "transaction_hash": log.transactionHash.hex(),
                        "amount0": amount0,
                        "amount1": amount1,
                        "sqrt_price": sqrt_price,
                        "liquidity": liquidity,
                        "tick": tick,
                        "log_index": log.logIndex
                    }
                    
            except Exception as decode_error:
                self.logger.debug(f"Failed to decode swap data: {decode_error}")
                return None
            
        except Exception as e:
            self.logger.debug(f"Error parsing swap log: {e}")
            return None

    async def _parse_flash_loan_log(self, log: Dict) -> Optional[Dict[str, Any]]:
        """Parse flash loan event."""
        try:
            return {
                "type": "flash_loan",
                "protocol_address": log.address.lower(),
                "block_number": log.blockNumber,
                "log_index": log.logIndex
            }
            
        except Exception as e:
            logger.debug(f"Error parsing flash loan log: {e}")
            return None

    async def _analyze_profit_by_strategy(self, movements: List[Dict[str, Any]], 
                                        gas_cost: Decimal, strategy_type: str,
                                        expected_tokens: List[str] = None) -> Dict[str, Any]:
        """Analyze profit based on strategy type and token movements."""
        try:
            from on1builder.config.loaders import get_settings
            settings = get_settings()
            wallet_address = settings.wallet_address.lower()
            
            # Calculate net token changes for our wallet
            net_changes = {}
            total_inflow_usd = Decimal('0')
            total_outflow_usd = Decimal('0')
            
            for movement in movements:
                if movement.get("type") != "transfer":
                    continue
                
                token_symbol = movement.get("token_symbol", "UNKNOWN")
                amount = Decimal(str(movement.get("amount", 0)))
                amount_usd = Decimal(str(movement.get("amount_usd", 0)))
                
                # Check if tokens moved to or from our wallet
                if movement.get("to_address", "").lower() == wallet_address:
                    # Inflow to our wallet
                    net_changes[token_symbol] = net_changes.get(token_symbol, Decimal('0')) + amount
                    total_inflow_usd += amount_usd
                    
                elif movement.get("from_address", "").lower() == wallet_address:
                    # Outflow from our wallet
                    net_changes[token_symbol] = net_changes.get(token_symbol, Decimal('0')) - amount
                    total_outflow_usd += amount_usd
            
            # Calculate gross profit (ignoring gas)
            gross_profit_usd = total_inflow_usd - total_outflow_usd
            
            # Calculate net profit (including gas)
            gas_cost_usd = await self._convert_eth_to_usd(gas_cost)
            net_profit_usd = gross_profit_usd - gas_cost_usd
            
            # Strategy-specific analysis
            strategy_analysis = await self._get_strategy_specific_analysis(
                strategy_type, movements, net_changes
            )
            
            return {
                "gross_profit_usd": float(gross_profit_usd),
                "net_profit_usd": float(net_profit_usd),
                "gas_cost_usd": float(gas_cost_usd),
                "total_inflow_usd": float(total_inflow_usd),
                "total_outflow_usd": float(total_outflow_usd),
                "net_token_changes": {k: float(v) for k, v in net_changes.items()},
                "strategy_analysis": strategy_analysis,
                "profit_margin_percent": float((net_profit_usd / max(total_outflow_usd, Decimal('1'))) * 100)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing profit: {e}")
            return {"error": str(e)}

    async def _get_strategy_specific_analysis(self, strategy_type: str, 
                                            movements: List[Dict], 
                                            net_changes: Dict[str, Decimal]) -> Dict[str, Any]:
        """Provide strategy-specific profit analysis."""
        analysis = {"strategy_type": strategy_type}
        
        try:
            if strategy_type == "arbitrage":
                # For arbitrage, we expect to end with more of the base token
                analysis["arbitrage_success"] = any(change > 0 for change in net_changes.values())
                analysis["tokens_involved"] = list(net_changes.keys())
                
            elif strategy_type == "flash_loan":
                # Flash loans should show borrowing and repayment in the same transaction
                flash_loan_movements = [m for m in movements if m.get("type") == "flash_loan"]
                analysis["flash_loan_detected"] = len(flash_loan_movements) > 0
                analysis["flash_loan_count"] = len(flash_loan_movements)
                
            elif strategy_type in ["front_run", "back_run", "sandwich"]:
                # MEV strategies should show profit extraction
                analysis["mev_profit_extracted"] = any(change > 0 for change in net_changes.values())
                analysis["victim_transactions"] = len([m for m in movements if m.get("type") == "swap"])
                
            elif strategy_type == "liquidation":
                # Liquidations should show asset acquisition at discount
                analysis["liquidation_bonus_estimated"] = any(change > 0 for change in net_changes.values())
                
        except Exception as e:
            logger.error(f"Error in strategy-specific analysis: {e}")
            analysis["error"] = str(e)
        
        return analysis

    async def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals with caching."""
        token_address = token_address.lower()
        
        if token_address in self._token_decimals_cache:
            return self._token_decimals_cache[token_address]
        
        try:
            # Try to get from ABI registry first
            token_info = self._abi_registry.get_token_info_by_address(token_address)
            if token_info and 'decimals' in token_info:
                decimals = token_info['decimals']
            else:
                # Call the contract directly using ERC20 standard ABI
                try:
                    # Standard ERC20 decimals() function signature
                    erc20_abi = [
                        {
                            "constant": True,
                            "inputs": [],
                            "name": "decimals",
                            "outputs": [{"name": "", "type": "uint8"}],
                            "type": "function"
                        }
                    ]
                    
                    token_contract = self._web3.eth.contract(
                        address=Web3.to_checksum_address(token_address),
                        abi=erc20_abi
                    )
                    
                    decimals = token_contract.functions.decimals().call()
                    
                except Exception as contract_error:
                    self.logger.debug(f"Failed to call decimals() for {token_address}: {contract_error}")
                    decimals = 18  # Default assumption for most ERC20 tokens
            
            self._token_decimals_cache[token_address] = decimals
            return decimals
            
        except Exception as e:
            logger.warning(f"Could not get decimals for {token_address}: {e}")
            return 18  # Default to 18 decimals

    async def _convert_token_to_usd(self, amount: Decimal, token_symbol: Optional[str]) -> Decimal:
        """Convert token amount to USD value using real-time price feeds."""
        if not token_symbol or amount == 0:
            return Decimal('0')
        
        try:
            # Try to get real-time price from external APIs
            price_usd = await self._get_token_price_usd(token_symbol)
            if price_usd > 0:
                return amount * Decimal(str(price_usd))
            
            # Fallback to conservative estimates for known tokens
            if token_symbol in ['ETH', 'WETH']:
                return amount * Decimal('2000')  # Conservative ETH price
            elif token_symbol in ['USDC', 'USDT', 'DAI']:
                return amount  # Stablecoins
            elif token_symbol == 'WBTC':
                return amount * Decimal('30000')  # Conservative BTC price
            else:
                return amount * Decimal('1')  # Default $1 for unknown tokens
                
        except Exception as e:
            logger.warning(f"Error converting {token_symbol} to USD: {e}")
            return Decimal('0')

    async def _convert_eth_to_usd(self, eth_amount: Decimal) -> Decimal:
        """Convert ETH amount to USD using real-time price."""
        try:
            # Get real-time ETH price
            eth_price = await self._get_token_price_usd('ETH')
            if eth_price > 0:
                eth_price_usd = Decimal(str(eth_price))
            else:
                eth_price_usd = Decimal('2000')  # Conservative fallback
                
            return eth_amount * eth_price_usd
        except Exception as e:
            self.logger.warning(f"Error converting ETH to USD: {e}")
            return Decimal('0')

    async def calculate_flash_loan_profit(self, tx_hash: str) -> Dict[str, Any]:
        """Specialized flash loan profit calculation."""
        try:
            base_analysis = await self.calculate_transaction_profit(tx_hash, "flash_loan")
            
            if "error" in base_analysis:
                return base_analysis
            
            # Additional flash loan specific metrics
            movements = base_analysis.get("token_movements", [])
            flash_loan_events = [m for m in movements if m.get("type") == "flash_loan"]
            
            flash_loan_analysis = {
                "flash_loans_used": len(flash_loan_events),
                "flash_loan_protocols": list(set(m.get("protocol_address") for m in flash_loan_events)),
                "compound_strategy": len(flash_loan_events) > 1,
                "execution_complexity": len(movements)
            }
            
            base_analysis["flash_loan_analysis"] = flash_loan_analysis
            return base_analysis
            
        except Exception as e:
            logger.error(f"Error calculating flash loan profit: {e}")
            return {"error": str(e)}

    async def get_profit_summary(self, tx_hashes: List[str]) -> Dict[str, Any]:
        """Generate profit summary for multiple transactions."""
        try:
            total_profit = Decimal('0')
            total_gas_cost = Decimal('0')
            successful_trades = 0
            failed_trades = 0
            strategy_profits = {}
            
            for tx_hash in tx_hashes:
                try:
                    analysis = await self.calculate_transaction_profit(tx_hash, "unknown")
                    
                    if "error" not in analysis:
                        profit = Decimal(str(analysis.get("profit_analysis", {}).get("net_profit_usd", 0)))
                        gas_cost = Decimal(str(analysis.get("gas_cost_usd", 0)))
                        strategy = analysis.get("strategy_type", "unknown")
                        
                        total_profit += profit
                        total_gas_cost += gas_cost
                        
                        if profit > 0:
                            successful_trades += 1
                        else:
                            failed_trades += 1
                        
                        if strategy not in strategy_profits:
                            strategy_profits[strategy] = {"profit": Decimal('0'), "count": 0}
                        strategy_profits[strategy]["profit"] += profit
                        strategy_profits[strategy]["count"] += 1
                        
                except Exception as e:
                    logger.error(f"Error analyzing transaction {tx_hash}: {e}")
                    failed_trades += 1
            
            success_rate = (successful_trades / max(successful_trades + failed_trades, 1)) * 100
            
            return {
                "total_profit_usd": float(total_profit),
                "total_gas_cost_usd": float(total_gas_cost),
                "net_profit_usd": float(total_profit - total_gas_cost),
                "successful_trades": successful_trades,
                "failed_trades": failed_trades,
                "success_rate_percent": round(success_rate, 2),
                "strategy_breakdown": {
                    strategy: {
                        "profit_usd": float(data["profit"]),
                        "trade_count": data["count"],
                        "avg_profit_per_trade": float(data["profit"] / max(data["count"], 1))
                    } for strategy, data in strategy_profits.items()
                },
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating profit summary: {e}")
            return {"error": str(e)}

    async def _get_token_price_usd(self, token_symbol: str) -> float:
        """Get real-time token price in USD from external APIs."""
        try:
            # Price API endpoints
            price_apis = [
                f'https://api.coingecko.com/api/v3/simple/price?ids={self._get_coingecko_id(token_symbol)}&vs_currencies=usd',
                f'https://api.coinbase.com/v2/exchange-rates?currency={token_symbol}'
            ]
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for api_url in price_apis:
                    try:
                        async with session.get(api_url, timeout=5) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                
                                if 'coingecko' in api_url:
                                    coin_id = self._get_coingecko_id(token_symbol)
                                    price = data.get(coin_id, {}).get('usd', 0)
                                elif 'coinbase' in api_url:
                                    rates = data.get('data', {}).get('rates', {})
                                    usd_rate = rates.get('USD', '0')
                                    price = float(usd_rate) if usd_rate else 0
                                
                                if price > 0:
                                    return price
                    except Exception:
                        continue
            
            return 0  # Return 0 if all APIs fail
            
        except Exception as e:
            self.logger.debug(f"Failed to fetch price for {token_symbol}: {e}")
            return 0
    
    def _get_coingecko_id(self, token_symbol: str) -> str:
        """Map token symbol to CoinGecko ID."""
        symbol_map = {
            'ETH': 'ethereum',
            'WETH': 'ethereum', 
            'BTC': 'bitcoin',
            'WBTC': 'bitcoin',
            'USDC': 'usd-coin',
            'USDT': 'tether',
            'DAI': 'dai',
            'LINK': 'chainlink',
            'UNI': 'uniswap',
            'AAVE': 'aave'
        }
        return symbol_map.get(token_symbol.upper(), token_symbol.lower())

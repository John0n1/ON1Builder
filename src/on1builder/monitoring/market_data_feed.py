# src/on1builder/monitoring/market_data_feed.py
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime, timedelta
import statistics

from cachetools import TTLCache

from on1builder.config.loaders import settings
from on1builder.integrations.external_apis import ExternalAPIManager
from on1builder.utils.logging_config import get_logger

logger = get_logger(__name__)

class MarketDataFeed:
    """Enhanced market data feed with volatility analysis, trend detection, and market sentiment."""
    
    def __init__(self, web3: Any):
        self._web3 = web3
        self._api_manager = ExternalAPIManager()
        self._price_cache: TTLCache = TTLCache(maxsize=1000, ttl=settings.heartbeat_interval / 2)
        self._price_history: Dict[str, List[Tuple[datetime, Decimal]]] = {}
        self._volatility_cache: TTLCache = TTLCache(maxsize=500, ttl=300)  # 5-minute volatility cache
        self._market_sentiment: Dict[str, float] = {}  # -1 to 1 scale
        self._failed_tokens: Set[str] = set()  # Blacklist for tokens that consistently fail
        self._token_failure_count: Dict[str, int] = {}  # Track failure counts
        self._is_running = False
        self._update_task: Optional[asyncio.Task] = None
        self._analysis_task: Optional[asyncio.Task] = None
        logger.info("Enhanced MarketDataFeed initialized.")

    async def start(self):
        if self._is_running:
            logger.warning("MarketDataFeed is already running.")
            return
            
        self._is_running = True
        logger.info("Starting Enhanced MarketDataFeed background updates...")
        self._update_task = asyncio.create_task(self._update_loop())
        self._analysis_task = asyncio.create_task(self._analysis_loop())
        
    async def stop(self):
        if not self._is_running:
            return
            
        self._is_running = False
        
        for task in [self._update_task, self._analysis_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        await self._api_manager.close()
        logger.info("Enhanced MarketDataFeed stopped.")
        
    async def get_price(self, token_symbol: str) -> Optional[Decimal]:
        """Get current price with automatic caching and history tracking."""
        symbol_upper = token_symbol.upper()
        
        # Check if token is blacklisted due to repeated failures
        if symbol_upper in self._failed_tokens:
            logger.debug(f"Skipping price lookup for blacklisted token: {symbol_upper}")
            return None
        
        cached_price = self._price_cache.get(symbol_upper)
        if cached_price is not None:
            logger.debug(f"Cache hit for price of {symbol_upper}.")
            return cached_price

        logger.debug(f"Cache miss for price of {symbol_upper}. Fetching from API.")
        
        try:
            price = await self._api_manager.get_price(token_symbol)
            
            if price is not None:
                price_decimal = Decimal(str(price))
                self._price_cache[symbol_upper] = price_decimal
                
                # Reset failure count on success
                if symbol_upper in self._token_failure_count:
                    del self._token_failure_count[symbol_upper]
                
                # Update price history
                self._update_price_history(symbol_upper, price_decimal)
                
                return price_decimal
            else:
                # Track failures and blacklist after 5 consecutive failures
                self._token_failure_count[symbol_upper] = self._token_failure_count.get(symbol_upper, 0) + 1
                
                if self._token_failure_count[symbol_upper] >= 5:
                    self._failed_tokens.add(symbol_upper)
                    logger.warning(f"Token {symbol_upper} blacklisted after 5 consecutive price lookup failures.")
                    del self._token_failure_count[symbol_upper]
                elif self._token_failure_count[symbol_upper] == 1:
                    # Only log warning on first failure to reduce spam
                    logger.warning(f"Could not retrieve price for {token_symbol}.")
                
                return None
                
        except Exception as e:
            # Track failures for exceptions too
            self._token_failure_count[symbol_upper] = self._token_failure_count.get(symbol_upper, 0) + 1
            
            if self._token_failure_count[symbol_upper] >= 5:
                self._failed_tokens.add(symbol_upper)
                logger.warning(f"Token {symbol_upper} blacklisted after 5 consecutive price lookup failures.")
                del self._token_failure_count[symbol_upper]
            elif self._token_failure_count[symbol_upper] == 1:
                logger.warning(f"Error retrieving price for {token_symbol}: {e}")
            
            return None

    def _update_price_history(self, symbol: str, price: Decimal):
        """Updates price history for volatility and trend analysis."""
        now = datetime.now()
        
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        
        self._price_history[symbol].append((now, price))
        
        # Keep only last 24 hours of data
        cutoff_time = now - timedelta(hours=24)
        self._price_history[symbol] = [
            (timestamp, price) for timestamp, price in self._price_history[symbol]
            if timestamp > cutoff_time
        ]

    async def get_volatility(self, token_symbol: str, timeframe_minutes: int = 60) -> Optional[float]:
        """Calculate volatility for a token over the specified timeframe."""
        symbol_upper = token_symbol.upper()
        cache_key = f"{symbol_upper}_{timeframe_minutes}m"
        
        cached_volatility = self._volatility_cache.get(cache_key)
        if cached_volatility is not None:
            return cached_volatility
        
        history = self._price_history.get(symbol_upper, [])
        if len(history) < 10:  # Need at least 10 data points
            return None
        
        # Filter to timeframe
        cutoff_time = datetime.now() - timedelta(minutes=timeframe_minutes)
        recent_prices = [
            float(price) for timestamp, price in history
            if timestamp > cutoff_time
        ]
        
        if len(recent_prices) < 5:
            return None
        
        # Calculate volatility as standard deviation of returns
        returns = []
        for i in range(1, len(recent_prices)):
            return_rate = (recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1]
            returns.append(return_rate)
        
        if len(returns) < 2:
            return None
        
        volatility = statistics.stdev(returns)
        self._volatility_cache[cache_key] = volatility
        
        return volatility

    async def get_price_trend(self, token_symbol: str, timeframe_minutes: int = 60) -> Optional[str]:
        """Determine price trend: 'bullish', 'bearish', or 'sideways'."""
        symbol_upper = token_symbol.upper()
        history = self._price_history.get(symbol_upper, [])
        
        if len(history) < 5:
            return None
        
        # Get prices for the timeframe
        cutoff_time = datetime.now() - timedelta(minutes=timeframe_minutes)
        recent_data = [
            (timestamp, float(price)) for timestamp, price in history
            if timestamp > cutoff_time
        ]
        
        if len(recent_data) < 5:
            return None
        
        # Calculate trend using simple moving average comparison
        prices = [price for _, price in recent_data]
        early_avg = statistics.mean(prices[:len(prices)//2])
        recent_avg = statistics.mean(prices[len(prices)//2:])
        
        trend_strength = (recent_avg - early_avg) / early_avg
        
        if trend_strength > 0.02:  # 2% increase
            return "bullish"
        elif trend_strength < -0.02:  # 2% decrease
            return "bearish"
        else:
            return "sideways"

    async def get_market_sentiment(self, token_symbol: str) -> float:
        """Get market sentiment score (-1 to 1) for a token."""
        symbol_upper = token_symbol.upper()
        return self._market_sentiment.get(symbol_upper, 0.0)

    async def get_optimal_slippage(self, token_symbol: str, trade_size_usd: Decimal) -> Decimal:
        """Calculate optimal slippage based on volatility and trade size."""
        volatility = await self.get_volatility(token_symbol, 30)  # 30-minute volatility
        
        if volatility is None:
            return Decimal('0.005')  # 0.5% default
        
        # Base slippage on volatility
        base_slippage = Decimal(str(volatility * 2))  # 2x volatility as base
        
        # Adjust for trade size (larger trades need more slippage)
        size_multiplier = Decimal('1') + (trade_size_usd / Decimal('10000'))  # +0.01% per $100
        
        optimal_slippage = base_slippage * size_multiplier
        
        # Cap between 0.1% and 5%
        return max(min(optimal_slippage, Decimal('0.05')), Decimal('0.001'))

    async def should_avoid_trading(self, token_symbol: str) -> bool:
        """Determine if trading should be avoided due to high volatility or poor sentiment."""
        volatility = await self.get_volatility(token_symbol, 60)
        sentiment = await self.get_market_sentiment(token_symbol)
        
        # Avoid trading if volatility is extremely high
        if volatility and volatility > 0.1:  # 10% volatility
            return True
        
        # Avoid trading if sentiment is extremely negative
        if sentiment < -0.8:
            return True
        
        return False

    async def get_prices(self, token_symbols: List[str]) -> Dict[str, Optional[Decimal]]:
        # Create tasks explicitly to avoid "Passing coroutines is forbidden" error
        tasks = [asyncio.create_task(self.get_price(symbol)) for symbol in token_symbols]
        results = await asyncio.gather(*tasks)
        return dict(zip(token_symbols, results))

    async def _update_loop(self):
        from on1builder.integrations.abi_registry import ABIRegistry
        
        registry = ABIRegistry()
        
        while self._is_running:
            try:
                all_symbols_to_update = set()
                for chain_id in settings.chains:
                    tokens_on_chain = registry.get_monitored_tokens(chain_id)
                    all_symbols_to_update.update(tokens_on_chain.keys())
                
                if all_symbols_to_update:
                    logger.debug(f"Updating prices for {len(all_symbols_to_update)} monitored tokens.")
                    await self.get_prices(list(all_symbols_to_update))
                
                await asyncio.sleep(settings.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MarketDataFeed update loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _analysis_loop(self):
        """Background loop for market analysis and sentiment calculation."""
        cleanup_counter = 0
        while self._is_running:
            try:
                await asyncio.sleep(300)  # Run analysis every 5 minutes
                await self._calculate_market_sentiment()
                await self._detect_market_anomalies()
                
                # Reset blacklist every hour (12 cycles of 5 minutes)
                cleanup_counter += 1
                if cleanup_counter >= 12:
                    self.reset_failed_tokens()
                    cleanup_counter = 0
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in market analysis loop: {e}", exc_info=True)
                await asyncio.sleep(300)

    async def _calculate_market_sentiment(self):
        """Calculate market sentiment based on price movements and volatility."""
        try:
            for symbol, history in self._price_history.items():
                if len(history) < 10:
                    continue
                
                # Get recent price movements
                recent_data = history[-10:]  # Last 10 data points
                prices = [float(price) for _, price in recent_data]
                
                # Calculate momentum (price change rate)
                momentum = (prices[-1] - prices[0]) / prices[0]
                
                # Calculate volatility factor
                volatility = await self.get_volatility(symbol, 60)
                volatility_factor = 1 - min(volatility or 0, 0.1) / 0.1 if volatility else 0.5
                
                # Combine momentum and volatility for sentiment
                # Positive momentum + low volatility = positive sentiment
                sentiment = momentum * volatility_factor * 10  # Scale to -1 to 1 range
                sentiment = max(min(sentiment, 1.0), -1.0)  # Clamp to range
                
                self._market_sentiment[symbol] = sentiment
                
                logger.debug(f"Market sentiment for {symbol}: {sentiment:.3f}")
                
        except Exception as e:
            logger.error(f"Error calculating market sentiment: {e}")

    async def _detect_market_anomalies(self):
        """Detect unusual market conditions that might indicate opportunities or risks."""
        try:
            anomalies = []
            
            for symbol, history in self._price_history.items():
                if len(history) < 20:
                    continue
                
                recent_prices = [float(price) for _, price in history[-20:]]
                
                # Detect sudden price spikes
                recent_change = (recent_prices[-1] - recent_prices[-5]) / recent_prices[-5]
                if abs(recent_change) > 0.05:  # 5% change in recent period
                    anomaly_type = "price_spike_up" if recent_change > 0 else "price_spike_down"
                    anomalies.append({
                        'symbol': symbol,
                        'type': anomaly_type,
                        'magnitude': recent_change,
                        'timestamp': datetime.now()
                    })
                
                # Detect unusual volatility
                volatility = await self.get_volatility(symbol, 30)
                if volatility and volatility > 0.08:  # 8% volatility threshold
                    anomalies.append({
                        'symbol': symbol,
                        'type': 'high_volatility',
                        'magnitude': volatility,
                        'timestamp': datetime.now()
                    })
            
            if anomalies:
                logger.info(f"Detected {len(anomalies)} market anomalies")
                for anomaly in anomalies:
                    logger.info(f"Anomaly: {anomaly['symbol']} - {anomaly['type']} "
                              f"(magnitude: {anomaly['magnitude']:.3f})")
                
        except Exception as e:
            logger.error(f"Error detecting market anomalies: {e}")

    def reset_failed_tokens(self):
        """Reset the blacklist of failed tokens. Useful for periodic cleanup."""
        cleared_count = len(self._failed_tokens)
        self._failed_tokens.clear()
        self._token_failure_count.clear()
        if cleared_count > 0:
            logger.info(f"Cleared blacklist of {cleared_count} failed tokens.")
    
    def get_failed_tokens(self) -> Set[str]:
        """Get the current set of blacklisted tokens."""
        return self._failed_tokens.copy()
    
    def remove_from_blacklist(self, token_symbol: str):
        """Manually remove a token from the blacklist."""
        symbol_upper = token_symbol.upper()
        if symbol_upper in self._failed_tokens:
            self._failed_tokens.remove(symbol_upper)
            if symbol_upper in self._token_failure_count:
                del self._token_failure_count[symbol_upper]
            logger.info(f"Removed {symbol_upper} from blacklist.")

    def get_market_data_summary(self) -> Dict[str, Any]:
        """Get comprehensive market data summary for monitoring."""
        summary = {
            'total_tracked_symbols': len(self._price_history),
            'cache_hit_ratio': len(self._price_cache) / max(len(self._price_history), 1),
            'avg_price_history_length': 0,
            'high_volatility_symbols': [],
            'sentiment_summary': {
                'bullish_count': 0,
                'bearish_count': 0,
                'neutral_count': 0
            }
        }
        
        if self._price_history:
            total_history_length = sum(len(history) for history in self._price_history.values())
            summary['avg_price_history_length'] = total_history_length / len(self._price_history)
        
        # Analyze sentiment distribution
        for symbol, sentiment in self._market_sentiment.items():
            if sentiment > 0.3:
                summary['sentiment_summary']['bullish_count'] += 1
            elif sentiment < -0.3:
                summary['sentiment_summary']['bearish_count'] += 1
            else:
                summary['sentiment_summary']['neutral_count'] += 1
        
        return summary
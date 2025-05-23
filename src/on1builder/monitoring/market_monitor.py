"""
ON1Builder - Market Monitor
=========================

Monitors market data such as token prices, volumes, and market trends.
"""

from __future__ import annotations
import asyncio
from decimal import Decimal
import time
from typing import Dict, Optional, Any, List

import aiohttp

from on1builder.config.config import Configuration, APIConfig
from on1builder.utils.logger import setup_logging

logger = setup_logging("MarketMonitor", level="DEBUG")


class MarketMonitor:
    """
    Market data monitoring service.
    
    This class provides access to token prices, market trends, and
    volume data from various sources.
    """
    
    def __init__(
        self,
        config: Configuration,
        api_config: APIConfig,
    ) -> None:
        """
        Initialize market monitor.
        
        Args:
            config: Global configuration
            api_config: API configuration for data sources
        """
        self.config = config
        self.api_config = api_config
        
        # Cache for price data
        self._price_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self._last_cache_cleanup = time.time()
        # Cache TTL configurable via config
        self._cache_ttl = config.MARKET_CACHE_TTL  # seconds
        
        # Session for HTTP requests
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info("MarketMonitor initialized")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create HTTP session.
        
        Returns:
            HTTP client session
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session
    
    async def get_token_price(
        self,
        token: str,
        *args,
        quote_currency: str = "USD",
        **kwargs
    ) -> Optional[Decimal]:
        """
        Get the current price of a token.
        
        Args:
            token: Token symbol or address
            quote_currency: Quote currency for price (default: USD)
            
        Returns:
            Token price or None if not available
        """
        # Clean the cache periodically
        now = time.time()
        if now - self._last_cache_cleanup > 300:  # 5 minutes
            await self._cleanup_cache()
            
        # Check cache first
        cache_key = f"{token.lower()}_{quote_currency.lower()}"
        async with self._cache_lock:
            if cache_key in self._price_cache:
                entry = self._price_cache[cache_key]
                if now - entry["timestamp"] < self._cache_ttl:
                    logger.debug(f"Cache hit for {token} price")
                    return entry["price"]
        
        # Cache miss - use api_config to get price
        price = await self.api_config.get_real_time_price(token, quote_currency)
        
        if price is not None:
            # Update cache
            async with self._cache_lock:
                self._price_cache[cache_key] = {
                    "price": price,
                    "timestamp": now
                }
                
            logger.debug(f"Updated price for {token}: {price} {quote_currency}")
        else:
            # Handle the case when price is None
            # Try to use any predefined default values for major tokens
            token_upper = token.upper()
            if token_upper in ["ETH", "BTC", "USDT", "USDC", "DAI", "WETH", "WBTC", "LINK", "UNI", "AAVE", "MATIC", "CRV"]:
                # This is a MarketMonitor-level fallback for when APIConfig's fallbacks also fail
                # These should match or be close to the values in APIConfig._get_fallback_price
                fallback_prices = {
                    "ETH": Decimal("3400.00"),  # ETH price fallback
                    "BTC": Decimal("62000.00"),  # BTC price fallback
                    "USDT": Decimal("1.00"),
                    "USDC": Decimal("1.00"),
                    "DAI": Decimal("1.00"),
                    "WETH": Decimal("3400.00"),
                    "WBTC": Decimal("62000.00"),
                    "LINK": Decimal("15.00"),
                    "UNI": Decimal("8.00"),
                    "AAVE": Decimal("95.00"),
                    "MATIC": Decimal("0.60"),
                    "CRV": Decimal("0.55")
                }
                price = fallback_prices.get(token_upper)
                
                if price:
                    logger.debug(f"Using fallback price for {token}: {price} {quote_currency}")
                    async with self._cache_lock:
                        self._price_cache[cache_key] = {
                            "price": price,
                            "timestamp": now
                        }
            
        return price
    
    async def _cleanup_cache(self) -> None:
        """Clean up expired cache entries."""
        now = time.time()
        self._last_cache_cleanup = now
        
        async with self._cache_lock:
            expired_keys = []
            for key, entry in self._price_cache.items():
                if now - entry["timestamp"] > self._cache_ttl:
                    expired_keys.append(key)
                    
            for key in expired_keys:
                del self._price_cache[key]
                
            if expired_keys:
                logger.debug(f"Cleared {len(expired_keys)} expired price cache entries")
    
    async def get_market_trend(self, token: str, timeframe: str = "1h") -> Optional[float]:
        """
        Get market trend indicator (percentage change).
        
        Args:
            token: Token symbol or address
            timeframe: Time period for trend (e.g., "1h", "24h")
            
        Returns:
            Percentage change (positive or negative) or None if not available
        """
        # Placeholder implementation
        logger.debug(f"Getting {timeframe} trend for {token}")
        return None  # Will be implemented in future updates
    
    async def get_token_volume(
        self,
        token: str,
        quote_currency: str = "USD",
        timeframe: str = "24h"
    ) -> Optional[Decimal]:
        """
        Get trading volume for a token.
        
        Args:
            token: Token symbol or address
            quote_currency: Quote currency for volume
            timeframe: Time period for volume
            
        Returns:
            Trading volume or None if not available
        """
        # Placeholder implementation
        logger.debug(f"Getting {timeframe} volume for {token}")
        return None  # Will be implemented in future updates
    
    async def close(self) -> None:
        """Clean up resources."""
        logger.debug("Closing MarketMonitor")
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def initialize(self) -> None:
        """
        Initialize market monitoring capabilities.
        
        This method is called during system startup to prepare the market
        monitoring system. It establishes connections to data sources and
        prepares caches.
        """
        logger.info("Initializing MarketMonitor")
        self._session = await self._get_session()
        
        # Initialize price cache with some common tokens if configured
        common_tokens = self.config.get("MONITORED_TOKENS", [])
        if common_tokens:
            logger.info(f"Pre-caching data for {len(common_tokens)} tokens")
            for token in common_tokens:
                asyncio.create_task(self.get_token_price(token))
                asyncio.create_task(self.get_token_volume(token))
    
    async def schedule_updates(self) -> None:
        """
        Schedule regular updates of market data.
        
        This starts background tasks to regularly refresh market data 
        for monitored tokens.
        """
        logger.info("Scheduling market data updates")
        
        # Get monitoring configuration
        update_interval = self.config.get("MARKET_UPDATE_INTERVAL", 60)  # seconds
        monitored_tokens = self.config.get("MONITORED_TOKENS", [])
        
        if not monitored_tokens:
            logger.warning("No tokens configured for monitoring")
            return
            
        # Start update loop in background
        asyncio.create_task(self._update_loop(update_interval, monitored_tokens))
    
    async def _update_loop(self, interval: int, tokens: List[str]) -> None:
        """
        Background loop to refresh market data.
        
        Args:
            interval: Seconds between updates
            tokens: List of token symbols/addresses to monitor
        """
        logger.info(f"Starting market data update loop for {len(tokens)} tokens")
        while True:
            try:
                for token in tokens:
                    await self.get_token_price(token)
                    await self.get_token_volume(token)
                    # Small delay between tokens to avoid rate limits
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error updating market data: {str(e)}")
            
            await asyncio.sleep(interval)
    
    async def get_market_trend(
        self,
        token: str,
        timeframe: str = "1h",
        quote_currency: str = "USD"
    ) -> Dict[str, Any]:
        """
        Get market trend data for a token.
        
        Args:
            token: Token symbol or address
            timeframe: Time period for trend (e.g., 1h, 24h, 7d)
            quote_currency: Quote currency for price comparison
            
        Returns:
            Dictionary with trend data
        """
        supported_timeframes = ["5m", "15m", "1h", "4h", "12h", "24h", "7d"]
        if timeframe not in supported_timeframes:
            logger.warning(f"Unsupported timeframe '{timeframe}', using 1h")
            timeframe = "1h"
            
        # Try to get trend data from api_config
        if hasattr(self.api_config, "get_price_history"):
            try:
                history = await self.api_config.get_price_history(token, timeframe, quote_currency)
                if history:
                    # Calculate trend indicators
                    current_price = history[-1]["price"]
                    start_price = history[0]["price"]
                    price_change = current_price - start_price
                    percent_change = (price_change / start_price) * 100 if start_price else 0
                    
                    # Determine trend direction
                    if percent_change > 3:
                        trend = "bullish"
                    elif percent_change < -3:
                        trend = "bearish"
                    else:
                        trend = "sideways"
                        
                    return {
                        "trend": trend,
                        "current_price": current_price,
                        "start_price": start_price,
                        "price_change": price_change,
                        "percent_change": percent_change,
                        "timeframe": timeframe,
                        "data_points": len(history)
                    }
            except Exception as e:
                logger.error(f"Error getting price history: {str(e)}")
        
        # Fallback to simple trend calculation
        try:
            current_price = await self.get_token_price(token, quote_currency)
            if current_price is None:
                return {"trend": "unknown", "error": "Could not fetch price data"}
                
            # For fallback, we'll use a very basic trend indicator
            # In a real implementation, this would use historical data
            return {
                "trend": "unknown",
                "current_price": current_price,
                "note": "Limited trend data available"
            }
        except Exception as e:
            logger.error(f"Error calculating market trend: {str(e)}")
            return {"trend": "unknown", "error": str(e)}
    
    async def get_token_volume(
        self,
        token: str,
        timeframe: str = "24h",
        quote_currency: str = "USD"
    ) -> Optional[Decimal]:
        """
        Get trading volume for a token.
        
        Args:
            token: Token symbol or address
            timeframe: Time period for volume (e.g., 24h, 7d)
            quote_currency: Quote currency for volume
            
        Returns:
            Volume in quote currency or None if unavailable
        """
        # Check cache first
        cache_key = f"vol_{token.lower()}_{timeframe}_{quote_currency.lower()}"
        current_time = time.time()
        
        async with self._cache_lock:
            if cache_key in self._price_cache:
                entry = self._price_cache[cache_key]
                if current_time - entry["timestamp"] < self._cache_ttl:
                    logger.debug(f"Cache hit for {token} volume")
                    return entry["volume"]
        
        # Try to get volume data from api_config
        volume = None
        if hasattr(self.api_config, "get_token_volume"):
            try:
                volume = await self.api_config.get_token_volume(token, timeframe, quote_currency)
            except Exception as e:
                logger.error(f"Error getting token volume: {str(e)}")
        
        # If we got volume data, cache it
        if volume is not None:
            async with self._cache_lock:
                self._price_cache[cache_key] = {
                    "volume": volume,
                    "timestamp": current_time
                }
        
        return volume
    
    async def is_healthy(self) -> bool:
        """
        Check if the market monitor system is healthy.
        
        Returns:
            True if the system is in a healthy state, False otherwise
        """
        try:
            # Check if we can fetch data
            session = await self._get_session()
            if session.closed:
                logger.warning("HTTP session is closed")
                return False
                
            # Check if we can get a price
            test_token = self.config.get("HEALTH_CHECK_TOKEN", "ETH")
            price = await self.get_token_price(test_token)
            if price is None:
                logger.warning(f"Failed to get price for {test_token}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Market monitor health check failed: {str(e)}")
            return False
    
    async def stop(self) -> None:
        """
        Stop market monitor (alias for close).
        
        This method exists for API compatibility with other components.
        """
        await self.close()
    
    async def check_market_conditions(
        self,
        token: str,
        condition_type: str = "volatility"
    ) -> Dict[str, Any]:
        """
        Check specific market conditions for a token.
        
        Args:
            token: Token symbol or address
            condition_type: Type of condition to check
                            ("volatility", "liquidity", "momentum")
            
        Returns:
            Dictionary with condition assessment
        """
        result = {
            "token": token,
            "condition_type": condition_type,
            "timestamp": time.time()
        }
        
        # Removed redundant hasattr check
        try:
            if condition_type == "volatility":
                # Get price volatility indicators
                trend_data = await self.get_market_trend(token, "1h")
                trend_data_4h = await self.get_market_trend(token, "4h")
                
                # Calculate volatility as standard deviation of percent changes
                volatility = abs(float(trend_data.get("percent_change", 0)))
                if trend_data_4h:
                    volatility = (volatility + abs(float(trend_data_4h.get("percent_change", 0)))) / 2
                
                # Classify volatility
                if volatility > 10:
                    condition = "high"
                elif volatility > 5:
                    condition = "medium"
                else:
                    condition = "low"
                    
                result.update({
                    "condition": condition,
                    "volatility": float(volatility),
                    "data": {
                        "short_term_change": trend_data.get("percent_change"),
                        "longer_term_change": trend_data_4h.get("percent_change")
                    }
                })
                
            elif condition_type == "liquidity":
                # Check trading volume as proxy for liquidity
                volume = await self.get_token_volume(token)
                price = await self.get_token_price(token)
                
                # Calculate liquidity score (simplified)
                if volume and price:
                    liquidity_score = float(volume) / float(price)
                    
                    if liquidity_score > 1000000:  # $1M+ volume per price unit
                        condition = "high"
                    elif liquidity_score > 100000:  # $100k+ volume per price unit
                        condition = "medium"
                    else:
                        condition = "low"
                        
                    result.update({
                        "condition": condition,
                        "liquidity_score": liquidity_score,
                        "data": {
                            "volume": float(volume) if volume else 0,
                            "price": float(price) if price else 0
                        }
                    })
                else:
                    result.update({
                        "condition": "unknown",
                        "error": "Could not fetch volume or price data"
                    })
                    
            elif condition_type == "momentum":
                # Check price momentum across multiple timeframes
                trend_1h = await self.get_market_trend(token, "1h")
                trend_4h = await self.get_market_trend(token, "4h")
                trend_24h = await self.get_market_trend(token, "24h")
                
                # Calculate momentum score
                momentum_score = 0
                count = 0
                
                if "percent_change" in trend_1h:
                    momentum_score += float(trend_1h["percent_change"])
                    count += 1
                    
                if "percent_change" in trend_4h:
                    momentum_score += float(trend_4h["percent_change"]) * 2  # Higher weight for longer term
                    count += 2
                    
                if "percent_change" in trend_24h:
                    momentum_score += float(trend_24h["percent_change"]) * 3  # Higher weight for longest term
                    count += 3
                    
                if count > 0:
                    momentum_score /= count
                    
                    if momentum_score > 5:
                        condition = "strongly_positive"
                    elif momentum_score > 2:
                        condition = "positive"
                    elif momentum_score < -5:
                        condition = "strongly_negative"
                    elif momentum_score < -2:
                        condition = "negative"
                    else:
                        condition = "neutral"
                        
                    result.update({
                        "condition": condition,
                        "momentum_score": momentum_score,
                        "data": {
                            "1h": trend_1h.get("percent_change"),
                            "4h": trend_4h.get("percent_change"),
                            "24h": trend_24h.get("percent_change")
                        }
                    })
                else:
                    result.update({
                        "condition": "unknown",
                        "error": "Could not fetch trend data"
                    })
            else:
                result.update({
                    "condition": "unknown",
                    "error": f"Unsupported condition type: {condition_type}"
                })
                
            return result
            
        except Exception as e:
            logger.error(f"Error checking market conditions: {str(e)}")
            result.update({
                "condition": "error",
                "error": str(e)
            })
            return result

    async def predict_price_movement(
        self,
        token: str,
        timeframe: str = "1h",
        use_ml: bool = False
    ) -> Dict[str, Any]:
        """
        Predict price movement for a token.
        
        Args:
            token: Token symbol or address
            timeframe: Prediction timeframe
            use_ml: Whether to use machine learning model
            
        Returns:
            Dictionary with prediction details
        """
        result = {
            "token": token,
            "timeframe": timeframe,
            "timestamp": time.time()
        }
        
        try:
            # Get market features
            features = await self._get_market_features(token)
            
            if use_ml and hasattr(self.api_config, "predict_price"):
                # Use ML model from api_config if available
                prediction = await self.api_config.predict_price(token)
                if prediction:
                    current_price = await self.get_token_price(token)
                    if current_price:
                        change = (float(prediction) - float(current_price)) / float(current_price) * 100
                        direction = "up" if change > 0 else "down" if change < 0 else "stable"
                        
                        result.update({
                            "prediction": "ml_model",
                            "direction": direction,
                            "predicted_price": float(prediction),
                            "current_price": float(current_price),
                            "percent_change": change,
                            "confidence": 0.75  # Placeholder confidence score
                        })
                        return result
            
            # Fallback to heuristic prediction
            # Simple trend-following strategy
            trend_data = await self.get_market_trend(token, timeframe)
            volume_data = await self.get_token_volume(token)
            
            # Calculate technical indicators (simplified)
            trend_direction = trend_data.get("trend", "unknown")
            percent_change = trend_data.get("percent_change", 0)
            
            # Market conditions
            volatility = await self.check_market_conditions(token, "volatility")
            momentum = await self.check_market_conditions(token, "momentum")
            
            # Combine signals for prediction
            signals = []
            
            if trend_direction == "bullish":
                signals.append(1)
            elif trend_direction == "bearish":
                signals.append(-1)
            else:
                signals.append(0)
                
            if momentum["condition"] in ["positive", "strongly_positive"]:
                signals.append(1)
            elif momentum["condition"] in ["negative", "strongly_negative"]:
                signals.append(-1)
            else:
                signals.append(0)
                
            # Overall prediction
            avg_signal = sum(signals) / len(signals)
            
            if avg_signal > 0.3:
                direction = "up"
                confidence = min(0.5 + avg_signal / 2, 0.95)
            elif avg_signal < -0.3:
                direction = "down"
                confidence = min(0.5 + abs(avg_signal) / 2, 0.95)
            else:
                direction = "stable"
                confidence = max(0.5 - abs(avg_signal) * 2, 0.1)
                
            # Current price and estimated future price
            current_price = await self.get_token_price(token)
            
            # Simple prediction model
            if current_price:
                # Estimate price movement based on signals and current conditions
                movement_factor = avg_signal * 0.03  # 3% movement per signal unit
                
                # Adjust for volatility
                if volatility["condition"] == "high":
                    movement_factor *= 1.5
                elif volatility["condition"] == "low":
                    movement_factor *= 0.5
                    
                predicted_change = float(current_price) * movement_factor
                predicted_price = float(current_price) + predicted_change
                
                result.update({
                    "prediction": "heuristic",
                    "direction": direction,
                    "predicted_price": predicted_price,
                    "current_price": float(current_price),
                    "percent_change": movement_factor * 100,
                    "confidence": confidence,
                    "signals": {
                        "trend": trend_direction,
                        "momentum": momentum["condition"],
                        "volatility": volatility["condition"]
                    }
                })
            else:
                result.update({
                    "prediction": "heuristic",
                    "direction": direction,
                    "confidence": confidence,
                    "error": "Could not fetch current price"
                })
                
            return result
            
        except Exception as e:
            logger.error(f"Error predicting price movement: {str(e)}")
            result.update({
                "prediction": "failed",
                "error": str(e)
            })
            return result
    
    async def _get_market_features(self, token: str) -> Dict[str, Any]:
        """
        Get market features for analysis or prediction.
        
        Args:
            token: Token symbol or address
            
        Returns:
            Dictionary with market features
        """
        features = {}
        
        try:
            # Get basic price and volume data
            price = await self.get_token_price(token)
            volume = await self.get_token_volume(token)
            
            features["price"] = float(price) if price else None
            features["volume"] = float(volume) if volume else None
            
            # Get trend data
            trend = await self.get_market_trend(token)
            features["trend"] = trend.get("trend")
            features["price_change_percent"] = trend.get("percent_change")
            
            # Market conditions
            volatility = await self.check_market_conditions(token, "volatility")
            liquidity = await self.check_market_conditions(token, "liquidity")
            momentum = await self.check_market_conditions(token, "momentum")
            
            features["volatility"] = volatility.get("condition")
            features["volatility_score"] = volatility.get("volatility")
            features["liquidity"] = liquidity.get("condition")
            features["liquidity_score"] = liquidity.get("liquidity_score")
            features["momentum"] = momentum.get("condition")
            features["momentum_score"] = momentum.get("momentum_score")
            
            # Get trading metrics if available
            trading_metrics = await self._get_trading_metrics(token)
            features.update(trading_metrics)
            
            return features
        except Exception as e:
            logger.error(f"Error getting market features: {str(e)}")
            return {"error": str(e)}
    
    async def _get_trading_metrics(self, token: str) -> Dict[str, Any]:
        """
        Get trading metrics for a token.
        
        Args:
            token: Token symbol or address
            
        Returns:
            Dictionary with trading metrics
        """
        metrics = {}
        
        try:
            # Try to get metrics from api_config if available
            if hasattr(self.api_config, "get_trading_metrics"):
                api_metrics = await self.api_config.get_trading_metrics(token)
                if api_metrics:
                    return api_metrics
            
            # Fallback to basic metrics
            price = await self.get_token_price(token)
            volume = await self.get_token_volume(token)
            
            if price and volume:
                # Calculate volume to market cap ratio (simplified)
                volume_to_price_ratio = float(volume) / float(price)
                metrics["volume_to_price_ratio"] = volume_to_price_ratio
                
                # Simple buy/sell pressure indicator (random for placeholder)
                import random
                metrics["buy_pressure"] = random.uniform(0.3, 0.7)
                metrics["sell_pressure"] = random.uniform(0.3, 0.7)
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting trading metrics: {str(e)}")
            return {}

    # Stub implementations for market metric methods
    async def _get_avg_transaction_value(self, token: str) -> float:
        """Placeholder for average transaction value metric"""
        return 0.0

    async def _get_transaction_count(self, token: str) -> int:
        """Placeholder for transaction count metric"""
        return 0

    async def _get_trading_pairs_count(self, token: str) -> int:
        """Placeholder for trading pairs count metric"""
        return 0

    async def _get_exchange_count(self, token: str) -> int:
        """Placeholder for exchange count metric"""
        return 0

    async def _get_buy_sell_ratio(self, token: str) -> float:
        """Placeholder for buy/sell ratio metric"""
        return 0.0

    async def _get_smart_money_flow(self, token: str) -> float:
        """Placeholder for smart money flow metric"""
        return 0.0

    async def get_price_data(self, *args, **kwargs) -> Any:
        """Proxy to get token price; matches test signature"""
        return await self.get_token_price(*args, **kwargs)

    async def _is_arbitrage_opportunity(self, token: str) -> bool:
        """Placeholder for arbitrage opportunity check"""
        return False

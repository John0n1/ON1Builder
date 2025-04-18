# File: python/marketmonitor.py

import asyncio
import os
import time
import joblib
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from sklearn.linear_model import LinearRegression
from cachetools import TTLCache
from web3 import AsyncWeb3

from apiconfig import APIConfig
from configuration import Configuration
from loggingconfig import setup_logging
import logging

logger = setup_logging("MarketMonitor", level=logging.DEBUG)

class MarketMonitor:
    """
    Monitors market data in real-time and predicts price movement using a linear regression model.
    It periodically updates training data and retrains the model as needed.
    """
    VOLATILITY_THRESHOLD: float = 0.05  # 5% volatility threshold
    LIQUIDITY_THRESHOLD: float = 100_000  # Minimum volume threshold
    PRICE_EMA_SHORT_PERIOD: int = 12
    PRICE_EMA_LONG_PERIOD: int = 26

    def __init__(
        self,
        web3: AsyncWeb3,
        configuration: Configuration,
        apiconfig: APIConfig,
        transactioncore: Optional[Any] = None,
    ) -> None:
        self.web3 = web3
        self.configuration = configuration
        self.apiconfig = apiconfig
        self.transactioncore = transactioncore

        self.price_model: Optional[LinearRegression] = None
        self.last_training_time: float = 0.0
        self.model_accuracy: float = 0.0
        self.RETRAINING_INTERVAL: int = self.configuration.MODEL_RETRAINING_INTERVAL
        self.MIN_TRAINING_SAMPLES: int = self.configuration.MIN_TRAINING_SAMPLES

        # Cache for recent market data
        self.price_cache: TTLCache = TTLCache(maxsize=2000, ttl=300)
        self.update_scheduler: Dict[str, float] = {
            "training_data": 0.0,
            "model": 0.0,
            "model_retraining_interval": self.configuration.MODEL_RETRAINING_INTERVAL,
        }

        # Paths for the ML model and training data
        self.linear_regression_path: str = self.configuration.LINEAR_REGRESSION_PATH
        self.model_path: str = self.configuration.MODEL_PATH
        self.training_data_path: str = self.configuration.TRAINING_DATA_PATH

        # Ensure the training directory exists (using a blocking call offloaded to a thread)
        os.makedirs(self.linear_regression_path, exist_ok=True)

    async def initialize(self) -> None:
        """
        Initialize MarketMonitor by loading or training a price model and historical data.
        Schedules updates for training data and model retraining.
        """
        try:
            if os.path.exists(self.model_path):
                try:
                    # Loading a model is blocking so run in a thread.
                    self.price_model = await asyncio.to_thread(joblib.load, self.model_path)
                    logger.debug("Loaded existing price model.")
                except Exception as e:
                    logger.warning(f"Loading model failed: {e}; creating a new model.")
                    self.price_model = LinearRegression()
                    await asyncio.to_thread(joblib.dump, self.price_model, self.model_path)
            else:
                self.price_model = LinearRegression()
                await asyncio.to_thread(joblib.dump, self.price_model, self.model_path)

            if os.path.exists(self.training_data_path):
                try:
                    self.historical_data = await asyncio.to_thread(pd.read_csv, self.training_data_path)
                    logger.debug(f"Loaded {len(self.historical_data)} training data points.")
                except Exception as e:
                    logger.warning(f"Failed to load training data: {e}")
                    self.historical_data = pd.DataFrame()
            else:
                self.historical_data = pd.DataFrame()

            # If sufficient training data exists, train the model.
            if len(self.historical_data) >= self.MIN_TRAINING_SAMPLES:
                try:
                    await self.train_price_model()
                    logger.debug("Trained price model with available historical data.")
                except Exception as e:
                    logger.warning(f"Model training failed: {e}")
                    self.price_model = LinearRegression()
                    await asyncio.to_thread(joblib.dump, self.price_model, self.model_path)
                    self.historical_data = pd.DataFrame()
            else:
                logger.debug("Insufficient historical data for training; model remains unchanged.")

            logger.info("MarketMonitor initialized successfully.")
            asyncio.create_task(self.schedule_updates())
        except Exception as e:
            logger.critical(f"MarketMonitor initialization failed: {e}", exc_info=True)
            raise

    async def schedule_updates(self) -> None:
        """
        Periodically update training data and retrain the price model.
        """
        while True:
            try:
                current_time = time.time()
                if current_time - self.update_scheduler["training_data"] >= self.update_scheduler["model_retraining_interval"]:
                    await self.update_training_data()
                    self.update_scheduler["training_data"] = current_time
                if current_time - self.update_scheduler["model"] >= self.update_scheduler["model_retraining_interval"]:
                    await self.train_price_model()
                    self.update_scheduler["model"] = current_time
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                logger.info("MarketMonitor update scheduler cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in update scheduler: {e}", exc_info=True)
                await asyncio.sleep(300)

    async def check_market_conditions(self, token_address: str) -> Dict[str, bool]:
        """
        Evaluate market conditions for the given token based on historical price data and volume.
        """
        market_conditions = {
            "high_volatility": False,
            "bullish_trend": False,
            "bearish_trend": False,
            "low_liquidity": False,
        }
        
        if not token_address:
            logger.debug("Token address is None or empty")
            return market_conditions
            
        # Get token symbol from APIConfig.
        symbol = self.apiconfig.get_token_symbol(token_address)
        if not symbol:
            logger.debug(f"Unable to determine token symbol for {token_address} in market conditions check.")
            return market_conditions
        try:
            api_symbol = symbol.upper()
            prices = await self.apiconfig.get_token_price_data(api_symbol, "historical", timeframe=1, vs_currency="usd")
            if not prices or len(prices) < 2:
                logger.debug(f"Not enough price data for {symbol}.")
                return market_conditions

            volatility = np.std(prices) / np.mean(prices)
            if volatility > self.VOLATILITY_THRESHOLD:
                market_conditions["high_volatility"] = True

            avg_price = np.mean(prices)
            if prices[-1] > avg_price:
                market_conditions["bullish_trend"] = True
            elif prices[-1] < avg_price:
                market_conditions["bearish_trend"] = True

            volume = await self.apiconfig.get_token_volume(api_symbol)
            if volume < self.LIQUIDITY_THRESHOLD:
                market_conditions["low_liquidity"] = True

            logger.debug(f"Market conditions for {symbol}: {market_conditions}")
        except Exception as e:
            logger.error(f"Error checking market conditions for {symbol}: {e}", exc_info=True)
        return market_conditions

    async def predict_price_movement(self, token_symbol: str) -> float:
        """
        Predict future price movement for the given token using the trained model.
        Returns the predicted price.
        """
        try:
            cache_key = f"prediction_{token_symbol}"
            if cache_key in self.apiconfig.prediction_cache:
                return self.apiconfig.prediction_cache[cache_key]
            prediction = await self.apiconfig.predict_price(token_symbol)
            self.apiconfig.prediction_cache[cache_key] = prediction
            return prediction
        except Exception as e:
            logger.error(f"Error predicting price for {token_symbol}: {e}")
            return 0.0

    async def get_token_price_data(
        self,
        token_symbol: str,
        data_type: str = "current",
        timeframe: int = 1,
        vs_currency: str = "eth"
    ) -> Union[float, List[float]]:
        """
        Retrieve token price data either as a current price or historical data.
        """
        return await self.apiconfig.get_token_price_data(token_symbol, data_type, timeframe, vs_currency)

    async def update_training_data(self) -> None:
        """
        Update the training data CSV with new market information.
        This method fetches the latest historical prices, volume, and metadata for each monitored token,
        computes derived features, and appends the data to the training_data.csv.
        """
        logger.info("Updating training data...")
        training_file = self.training_data_path

        # Attempt to load existing training data
        try:
            existing_df = pd.read_csv(training_file)
        except Exception:
            existing_df = pd.DataFrame()

        # Collect new data rows in a list
        new_rows = []
        # Get all monitored token symbols from APIConfig mapping
        token_symbols = list(self.apiconfig.token_symbol_to_address.keys())
        for token in token_symbols:
            try:
                # Historical prices (assume this returns a list of price values in USD)
                historical_prices: List[float] = await self.apiconfig.get_token_price_data(token, "historical", timeframe=1, vs_currency="usd")
                if not historical_prices:
                    logger.debug(f"No historical prices for token {token}. Skipping.")
                    continue

                current_price = historical_prices[-1]
                avg_price = np.mean(historical_prices)
                volatility = float(np.std(historical_prices) / avg_price) if avg_price > 0 else 0.0
                percent_change_24h = ((historical_prices[-1] - historical_prices[0]) / historical_prices[0] * 100) if historical_prices[0] != 0 else 0.0
                price_momentum = ((historical_prices[-1] - historical_prices[0]) / historical_prices[0]) if historical_prices[0] != 0 else 0.0

                # Get 24h volume from APIConfig (in USD)
                volume_24h = await self.apiconfig.get_token_volume(token)

                # Get token metadata (including market cap, total/circulating supply, etc.)
                metadata: Dict[str, Any] = await self.apiconfig.get_token_metadata(token)
                market_cap = metadata.get("market_cap", 0)
                total_supply = metadata.get("total_supply", 0)
                circulating_supply = metadata.get("circulating_supply", 0)
                trading_pairs = metadata.get("trading_pairs", 0)
                exchange_count = metadata.get("exchange_count", 0)

                # Compute liquidity ratio if market cap is available
                liquidity_ratio = (volume_24h / market_cap) if market_cap > 0 else 0.0

                # For avg_transaction_value, buy_sell_ratio, smart_money_flow, assume
                # we compute neutral values as 0.0 (for production you would call proper endpoints)
                avg_transaction_value = 0.0
                buy_sell_ratio = 1.0  # Neutral ratio (1.0 means balanced)
                smart_money_flow = 0.0

                row = {
                    "timestamp": int(datetime.utcnow().timestamp()),
                    "symbol": token,
                    "price_usd": current_price,
                    "market_cap": market_cap,
                    "volume_24h": volume_24h,
                    "percent_change_24h": percent_change_24h,
                    "total_supply": total_supply,
                    "circulating_supply": circulating_supply,
                    "volatility": volatility,
                    "liquidity_ratio": liquidity_ratio,
                    "avg_transaction_value": avg_transaction_value,
                    "trading_pairs": trading_pairs,
                    "exchange_count": exchange_count,
                    "price_momentum": price_momentum,
                    "buy_sell_ratio": buy_sell_ratio,
                    "smart_money_flow": smart_money_flow
                }
                new_rows.append(row)
                logger.debug(f"Token {token} data appended: {row}")
            except Exception as e:
                logger.error(f"Error updating training data for token {token}: {e}", exc_info=True)

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            if not existing_df.empty:
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df.drop_duplicates(subset=["timestamp", "symbol"], inplace=True)
                combined_df.sort_values("timestamp", inplace=True)
            else:
                combined_df = new_df
            # Save the updated CSV file
            combined_df.to_csv(training_file, index=False)
            logger.info(f"Training data updated with {len(new_rows)} new samples. Total samples: {len(combined_df)}")
        else:
            logger.info("No new training data was fetched.")

    async def train_price_model(self) -> None:
        """
        Train a linear regression model for price prediction using available training data.
        """
        try:
            training_data_path = self.configuration.TRAINING_DATA_PATH
            model_path = self.configuration.MODEL_PATH
            if not os.path.exists(training_data_path):
                logger.warning("Training data file not found; skipping training.")
                return
            df = await asyncio.to_thread(pd.read_csv, training_data_path)
            if len(df) < self.MIN_TRAINING_SAMPLES:
                logger.warning(f"Insufficient training samples: {len(df)} (required: {self.MIN_TRAINING_SAMPLES}).")
                return
            features = ['price_usd', 'volume_24h', 'market_cap', 'volatility', 'liquidity_ratio', 'price_momentum']
            X = df[features].fillna(0)
            y = df['price_usd'].fillna(0)
            model = LinearRegression()
            model.fit(X, y)
            await asyncio.to_thread(joblib.dump, model, model_path)
            self.price_model = model
            logger.info(f"Price model trained and saved to {model_path}.")
        except Exception as e:
            logger.error(f"Error training price model: {e}", exc_info=True)

    async def stop(self) -> None:
        """
        Stop MarketMonitor operations by clearing caches.
        """
        try:
            self.price_cache.clear()
            logger.info("MarketMonitor stopped.")
        except Exception as e:
            logger.error(f"Error stopping MarketMonitor: {e}", exc_info=True)

# market_monitor.py
import asyncio
import os
import time
import joblib
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GridSearchCV
from cachetools import TTLCache
from web3 import AsyncWeb3
from api_config import APIConfig
from configuration import Configuration
from logger_on1 import setup_logging
import logging

logger = setup_logging("MarketMonitor", level=logging.DEBUG)


class MarketMonitor:
    VOLATILITY_THRESHOLD = 0.05
    LIQUIDITY_THRESHOLD = 100_000

    def __init__(
            self,
            web3: AsyncWeb3,
            configuration: Configuration,
            api_config: APIConfig,
            transaction_core: Optional[Any] = None):
        self.web3 = web3
        self.configuration = configuration
        self.api_config = api_config
        self.transaction_core = transaction_core
        self.model_path = self.configuration.MODEL_PATH
        self.training_data_path = self.configuration.TRAINING_DATA_PATH
        self.price_cache = TTLCache(maxsize=2000, ttl=300)
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

    async def initialize(self) -> None:
        if os.path.exists(self.model_path):
            try:
                self.price_model = await asyncio.to_thread(joblib.load, self.model_path)
            except Exception:
                self.price_model = LinearRegression()
                await asyncio.to_thread(joblib.dump, self.price_model, self.model_path)
        else:
            self.price_model = LinearRegression()
            await asyncio.to_thread(joblib.dump, self.price_model, self.model_path)
        if os.path.exists(self.training_data_path):
            try:
                self.historical_data = await asyncio.to_thread(pd.read_csv, self.training_data_path)
            except Exception:
                self.historical_data = pd.DataFrame()
        else:
            self.historical_data = pd.DataFrame()
        if len(self.historical_data) >= self.configuration.MIN_TRAINING_SAMPLES:
            await self.train_price_model()
        asyncio.create_task(self.schedule_updates())

    async def schedule_updates(self) -> None:
        interval = self.configuration.MODEL_RETRAINING_INTERVAL
        while True:
            now = time.time()
            if now - getattr(self, "_last_update", 0.0) >= interval:
                await self.update_training_data()
                await self.train_price_model()
                self._last_update = now
            await asyncio.sleep(60)

    async def check_market_conditions(
            self, token_address: str) -> Dict[str, bool]:
        conditions = {"high_volatility": False, "bullish_trend": False,
                      "bearish_trend": False, "low_liquidity": False}
        symbol = self.api_config.get_token_symbol(token_address)
        if not symbol:
            return conditions
        prices = await self.api_config.get_token_price_data(symbol, "historical", timeframe=1, vs="usd")
        if not prices or len(prices) < 2:
            return conditions
        volatility = float(np.std(prices) / np.mean(prices))
        if volatility > self.VOLATILITY_THRESHOLD:
            conditions["high_volatility"] = True
        avg = float(np.mean(prices))
        if prices[-1] > avg:
            conditions["bullish_trend"] = True
        elif prices[-1] < avg:
            conditions["bearish_trend"] = True
        volume = await self.api_config.get_token_volume(symbol)
        if volume < self.LIQUIDITY_THRESHOLD:
            conditions["low_liquidity"] = True
        return conditions

    async def predict_price_movement(self, token_symbol: str) -> float:
        cache_key = f"prediction:{token_symbol}"
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
        prediction = await self.api_config.predict_price(token_symbol)
        self.price_cache[cache_key] = prediction
        return prediction

    async def get_token_price_data(self,
                                   token_symbol: str,
                                   data_type: str = "current",
                                   timeframe: int = 1,
                                   vs: str = "eth") -> Union[float,
                                                             List[float]]:
        return await self.api_config.get_token_price_data(token_symbol, data_type, timeframe, vs)

    async def update_training_data(self) -> None:
        if os.path.exists(self.training_data_path):
            try:
                existing = await asyncio.to_thread(pd.read_csv, self.training_data_path)
            except Exception:
                existing = pd.DataFrame()
        else:
            existing = pd.DataFrame()
        rows = []
        for token in list(self.api_config.token_symbol_to_address.keys()):
            try:
                prices = await self.api_config.get_token_price_data(token, "historical", timeframe=1, vs="usd")
                if not prices:
                    continue
                current_price = float(prices[-1])
                avg_price = float(np.mean(prices))
                volatility = float(
                    np.std(prices) / avg_price) if avg_price else 0.0
                percent_change = (
                    (prices[-1] - prices[0]) / prices[0] * 100) if prices[0] else 0.0
                volume = await self.api_config.get_token_volume(token)
                row = {
                    "timestamp": int(datetime.utcnow().timestamp()),
                    "symbol": token,
                    "price_usd": current_price,
                    "market_cap": 0.0,
                    "volume_24h": volume,
                    "percent_change_24h": percent_change,
                    "total_supply": 0.0,
                    "circulating_supply": 0.0,
                    "volatility": volatility,
                    "liquidity_ratio": volume,
                    "price_momentum": (prices[-1] - prices[0]) / prices[0] if prices[0] else 0.0,
                }
                rows.append(row)
            except Exception:
                continue
        if not rows:
            return
        new_df = pd.DataFrame(rows)
        if not existing.empty:
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined.drop_duplicates(
                subset=["timestamp", "symbol"], inplace=True)
        else:
            combined = new_df
        await asyncio.to_thread(combined.to_csv, self.training_data_path, index=False)

    async def train_price_model(self) -> None:
        if not os.path.exists(self.training_data_path):
            return
        df = await asyncio.to_thread(pd.read_csv, self.training_data_path)
        if len(df) < self.configuration.MIN_TRAINING_SAMPLES:
            return
        features = ["price_usd", "volume_24h", "market_cap",
                    "volatility", "liquidity_ratio", "price_momentum"]
        X = df[features].fillna(0)
        y = df["price_usd"].fillna(0)

        # Experiment with different models
        models = {
            "LinearRegression": LinearRegression(),
            "RandomForest": RandomForestRegressor()
        }

        best_model = None
        best_score = -np.inf

        for name, model in models.items():
            model.fit(X, y)
            score = model.score(X, y)
            if score > best_score:
                best_score = score
                best_model = model

        # Perform hyperparameter tuning for the best model
        if isinstance(best_model, RandomForestRegressor):
            param_grid = {
                "n_estimators": [50, 100, 200],
                "max_depth": [None, 10, 20, 30],
                "min_samples_split": [2, 5, 10]
            }
            grid_search = GridSearchCV(best_model, param_grid, cv=5)
            grid_search.fit(X, y)
            best_model = grid_search.best_estimator_

        await asyncio.to_thread(joblib.dump, best_model, self.model_path)
        self.price_model = best_model

    async def stop(self) -> None:
        self.price_cache.clear()
        await asyncio.sleep(0)

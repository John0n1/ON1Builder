# src/on1builder/config/settings.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class APISettings(BaseModel):
    """Configuration for external APIs."""
    etherscan_api_key: Optional[str] = None
    coingecko_api_key: Optional[str] = None
    coinmarketcap_api_key: Optional[str] = None
    cryptocompare_api_key: Optional[str] = None
    infura_project_id: Optional[str] = None


class ContractAddressSettings(BaseModel):
    """Manages chain-specific contract addresses, loaded from JSON strings in .env."""
    uniswap_v2_router: Dict[str, str] = Field(default_factory=dict)
    sushiswap_router: Dict[str, str] = Field(default_factory=dict)
    aave_v3_pool: Dict[str, str] = Field(default_factory=dict)
    simple_flashloan_contract: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='before')
    def parse_json_strings(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Parses fields that are expected to be JSON strings from the environment."""
        parsed_values = values.copy()
        for field, value in values.items():
            if isinstance(value, str) and value.strip().startswith('{'):
                try:
                    parsed_values[field] = json.loads(value)
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid JSON string for contract address field: {field}")
        return parsed_values


class NotificationSettings(BaseModel):
    """Configuration for the notification service."""
    channels: List[str] = Field(default_factory=list)
    min_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    slack_webhook_url: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    alert_email: Optional[str] = None

    @field_validator('min_level', mode='before')
    def normalize_level(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v
    
    @field_validator('channels', mode='before')
    def split_str(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(',')]
        return v


class DatabaseSettings(BaseModel):
    """Configuration for the database connection."""
    url: str = "sqlite+aiosqlite:///on1builder_data.db"


class GlobalSettings(BaseModel):
    """The master configuration model for the entire application."""
    model_config = ConfigDict(extra="allow", case_sensitive=False)

    # General
    debug: bool = False
    base_path: Path = Field(default_factory=Path.cwd, description="The root directory of the project.")

    # Wallet
    wallet_key: str
    wallet_address: str
    profit_receiver_address: Optional[str] = None

    # Chains
    chains: List[int] = Field(default=[1])
    poa_chains: List[int] = Field(default_factory=list)

    @field_validator('chains', 'poa_chains', mode='before')
    def split_chain_ids(cls, v):
        if isinstance(v, str):
            return [int(item.strip()) for item in v.split(',') if item.strip().isdigit()]
        return v

    # RPC Endpoints (will be populated by the loader)
    rpc_urls: Dict[int, str] = Field(default_factory=dict)
    websocket_urls: Dict[int, str] = Field(default_factory=dict)

    # Transaction & Gas
    transaction_retry_count: int = Field(default=3, gt=0)
    transaction_retry_delay: float = Field(default=2.0, gt=0)
    max_gas_price_gwei: int = Field(default=200, gt=0)
    gas_price_multiplier: float = Field(default=1.1, gt=0)
    default_gas_limit: int = Field(default=500000, ge=21000)
    fallback_gas_price_gwei: int = Field(default=50, gt=0)
    min_wallet_balance: float = Field(default=0.05, ge=0)

    # Strategy & Profit - Enhanced with dynamic thresholds
    min_profit_eth: float = Field(default=0.005, ge=0)
    min_profit_percentage: float = Field(default=0.1, ge=0)  # Minimum profit as % of investment
    dynamic_profit_scaling: bool = Field(default=True)  # Scale profit requirements based on balance
    balance_risk_ratio: float = Field(default=0.3, ge=0.1, le=0.9)  # Max % of balance to risk per trade
    slippage_tolerance: float = Field(default=0.5, ge=0, le=10)
    monitored_tokens_path: Path = Field(default=Path("src/on1builder/resources/tokens/all_chains_tokens.json"))
    
    # Flashloan Configuration
    flashloan_enabled: bool = Field(default=True)
    flashloan_min_profit_multiplier: float = Field(default=2.0, ge=1.0)  # Higher profit requirement for flashloans
    flashloan_max_amount_eth: float = Field(default=1000.0)  # Max flashloan amount
    flashloan_buffer_percentage: float = Field(default=0.1, ge=0.01)  # Safety buffer for flashloan repayment
    
    # ML Strategy Configuration
    ml_enabled: bool = Field(default=True)
    ml_learning_rate: float = Field(default=0.01, gt=0)
    ml_exploration_rate: float = Field(default=0.1, ge=0, le=1)
    ml_decay_rate: float = Field(default=0.995, gt=0, lt=1)
    ml_update_frequency: int = Field(default=100, gt=0)  # Update weights every N transactions
    
    # Balance Management
    emergency_balance_threshold: float = Field(default=0.01, ge=0)  # Emergency stop threshold
    low_balance_threshold: float = Field(default=0.05, ge=0)  # Switch to conservative strategies
    high_balance_threshold: float = Field(default=1.0, ge=0)  # Enable more aggressive strategies
    profit_reinvestment_percentage: float = Field(default=80.0, ge=0, le=100)  # % of profit to reinvest
    
    # Gas Optimization
    dynamic_gas_pricing: bool = Field(default=True)
    gas_price_percentile: int = Field(default=75, ge=10, le=95)  # Target gas price percentile
    max_gas_fee_percentage: float = Field(default=10.0, ge=1.0, le=50.0)  # Max gas as % of expected profit

    # System & Performance
    memory_check_interval: int = Field(default=300, gt=0)
    heartbeat_interval: int = Field(default=30, gt=0)
    connection_retry_count: int = Field(default=5, gt=0)
    connection_retry_delay: float = Field(default=5.0, gt=0)

    # Enhanced arbitrage settings
    arbitrage_scan_interval: int = Field(default=15, gt=0)
    
    # Performance monitoring  
    performance_report_interval: int = Field(default=3600, gt=0)  # 1 hour
    
    # Market sentiment
    use_market_sentiment: bool = Field(default=True)
    sentiment_weight: float = Field(default=0.3, ge=0, le=1.0)
    
    # MEV settings
    mev_strategies_enabled: bool = Field(default=True)
    front_running_enabled: bool = Field(default=True)
    back_running_enabled: bool = Field(default=True)
    sandwich_attacks_enabled: bool = Field(default=False)  # Requires careful consideration
    
    # Risk management
    max_position_size_percent: float = Field(default=20.0, gt=0, le=100)  # Max % of portfolio per trade
    daily_loss_limit_percent: float = Field(default=5.0, gt=0, le=100)   # Stop trading if daily loss exceeds %
    
    # Cross-chain settings
    cross_chain_enabled: bool = Field(default=True)
    bridge_monitoring_enabled: bool = Field(default=True)

    # Nested Settings Models
    api: APISettings = Field(default_factory=APISettings)
    contracts: ContractAddressSettings = Field(default_factory=ContractAddressSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
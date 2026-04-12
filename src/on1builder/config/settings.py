#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


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
    uniswap_v3_router: Dict[str, str] = Field(default_factory=dict)
    sushiswap_router: Dict[str, str] = Field(default_factory=dict)
    aave_v3_pool: Dict[str, str] = Field(default_factory=dict)
    simple_flashloan_contract: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    def parse_json_strings(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Parses fields that are expected to be JSON strings from the environment."""
        parsed_values = values.copy()
        for field, value in values.items():
            if isinstance(value, str) and value.strip().startswith("{"):
                try:
                    parsed_values[field] = json.loads(value)
                except json.JSONDecodeError:
                    raise ValueError(
                        f"Invalid JSON string for contract address field: {field}"
                    )
        return parsed_values


class NotificationSettings(BaseModel):
    """Configuration for the notification service."""

    channels: List[str] = Field(default_factory=list)
    min_level: str = Field(
        default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"
    )
    slack_webhook_url: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    alert_email: Optional[str] = None

    @field_validator("min_level", mode="before")
    def normalize_level(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v

    @field_validator("channels", mode="before")
    def split_str(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


class DatabaseSettings(BaseModel):
    """Configuration for the database connection."""

    url: str = "sqlite+aiosqlite:///on1builder_data.db"


class GlobalSettings(BaseModel):
    """The master configuration model for the entire application."""

    model_config = ConfigDict(extra="allow", case_sensitive=False)

    # General
    debug: bool = False
    base_path: Path = Field(
        default_factory=Path.cwd, description="The root directory of the project."
    )

    # Wallet
    wallet_key: str
    wallet_address: str
    profit_receiver_address: Optional[str] = None
    wallet_keys: Dict[int, str] = Field(default_factory=dict)
    wallet_addresses: Dict[int, str] = Field(default_factory=dict)

    # Chains
    chains: List[int] = Field(default=[1])
    poa_chains: List[int] = Field(default_factory=list)

    @field_validator("chains", "poa_chains", mode="before")
    @classmethod
    def split_chain_ids(cls, v):
        """Split comma-separated chain IDs and validate them."""
        if isinstance(v, str):
            chain_ids = [
                int(item.strip()) for item in v.split(",") if item.strip().isdigit()
            ]
            if not chain_ids and v.strip():
                raise ValueError(f"No valid chain IDs found in: {v}")
            return chain_ids
        return v

    @field_validator("wallet_address", mode="after")
    @classmethod
    def validate_wallet_address(cls, v):
        """Validate wallet address format using the validation framework."""
        from .validation import ConfigValidator

        return ConfigValidator.validate_wallet_address(v)

    @field_validator("wallet_key", mode="after")
    @classmethod
    def validate_wallet_key(cls, v):
        """Validate private key format using the validation framework."""
        from .validation import ConfigValidator

        return ConfigValidator.validate_private_key(v)

    @field_validator("wallet_keys", mode="after")
    @classmethod
    def validate_wallet_keys(cls, v):
        """Validate per-chain wallet keys."""
        if not v:
            return v
        from .validation import ConfigValidator

        validated = {}
        for chain_id, key in v.items():
            validated[int(chain_id)] = ConfigValidator.validate_private_key(key)
        return validated

    @field_validator("wallet_addresses", mode="after")
    @classmethod
    def validate_wallet_addresses(cls, v):
        """Validate per-chain wallet addresses."""
        if not v:
            return v
        from .validation import ConfigValidator

        validated = {}
        for chain_id, address in v.items():
            validated[int(chain_id)] = ConfigValidator.validate_wallet_address(address)
        return validated

    @field_validator("chains", "poa_chains", mode="after")
    @classmethod
    def validate_chain_list(cls, v):
        """Validate chain IDs using the validation framework."""
        if v:  # Only validate if not empty
            from .validation import ConfigValidator

            return ConfigValidator.validate_chain_ids(v)
        return v

    @model_validator(mode="after")
    def validate_balance_thresholds(self):
        """Validate balance threshold ordering using the validation framework."""
        from .validation import ConfigValidator

        ConfigValidator.validate_balance_thresholds(
            self.emergency_balance_threshold,
            self.low_balance_threshold,
            self.high_balance_threshold,
        )
        return self

    @model_validator(mode="after")
    def validate_gas_settings(self):
        """Validate gas-related settings using the validation framework."""
        from .validation import ConfigValidator

        ConfigValidator.validate_gas_settings(
            self.max_gas_price_gwei, self.gas_price_multiplier, self.default_gas_limit
        )
        return self

    @model_validator(mode="after")
    def validate_complete_settings(self):
        """Perform complete validation using the validation framework."""
        try:
            from .validation import validate_complete_config

            # Convert to dict for validation
            config_dict = self.model_dump()

            # Validate complete configuration
            validated_config = validate_complete_config(config_dict)

            # Update any normalized values
            for key, value in validated_config.items():
                if hasattr(self, key) and getattr(self, key) != value:
                    current = getattr(self, key)
                    if isinstance(current, BaseModel) and isinstance(value, dict):
                        try:
                            value = current.__class__(**value)
                        except Exception as e:
                            logger.debug(
                                "Could not coerce validated value for %s: %s", key, e
                            )
                            continue
                    setattr(self, key, value)

        except ImportError:
            # Validation module not available, skip ON1Builder validation
            pass
        except Exception as e:
            logger.warning(f"ON1Builder validation failed: {e}")

        return self

    # RPC Endpoints (will be populated by the loader)
    rpc_urls: Dict[int, str] = Field(default_factory=dict)
    websocket_urls: Dict[int, str] = Field(default_factory=dict)

    # Transaction & Gas
    transaction_retry_count: int = Field(default=3, gt=0)
    transaction_retry_delay: float = Field(default=2.0, gt=0)
    max_gas_price_gwei: int = Field(default=200, gt=0)
    gas_price_multiplier: float = Field(default=1.1, gt=0)
    default_gas_limit: int = Field(default=500000, ge=21000)
    allow_unsimulated_trades: bool = Field(
        default=False,
        description="Require opportunities to be simulated unless explicitly bypassed.",
    )
    simulation_backend: str = Field(
        default="eth_call",
        description="Simulation backend to use (eth_call, anvil, tenderly).",
    )
    simulation_concurrency: int = Field(
        default=5, description="Maximum concurrent simulations in the pipeline."
    )
    submission_mode: str = Field(
        default="public",
        description="Transaction submission mode: public, private, or bundle (MEV-Boost/Flashbots).",
    )
    private_rpc_url: Optional[str] = Field(
        default=None,
        description="Optional private RPC endpoint (e.g., Flashbots Protect) used when submission_mode=private.",
    )
    tenderly_base_url: str = Field(
        default="https://api.tenderly.co/api/v1",
        description="Tenderly API base URL for simulation.",
    )
    tenderly_account_slug: Optional[str] = Field(
        default=None, description="Tenderly account slug for simulation."
    )
    tenderly_project_slug: Optional[str] = Field(
        default=None, description="Tenderly project slug for simulation."
    )
    tenderly_access_token: Optional[str] = Field(
        default=None, description="Tenderly access token for simulation."
    )
    bundle_relay_url: Optional[str] = Field(
        default=None,
        description="MEV-Boost/Flashbots bundle relay URL when submission_mode=bundle.",
    )
    bundle_relay_auth_token: Optional[str] = Field(
        default=None, description="Auth token if required by the bundle relay."
    )
    bundle_signer_key: Optional[str] = Field(
        default=None,
        description="Private key used to sign bundle payloads for relays (auto-generated if missing).",
    )
    bundle_signer_key_path: Path = Field(
        default_factory=lambda: Path.home() / ".on1builder" / "bundle_signer.key",
        description="Path to persist the bundle signer key.",
    )
    bundle_target_block_offset: int = Field(
        default=1, description="Target block offset for bundle submission."
    )
    bundle_timeout_seconds: int = Field(
        default=30, description="Max seconds to keep bundle valid."
    )
    fallback_gas_price_gwei: int = Field(default=50, gt=0)
    min_wallet_balance: float = Field(default=0.05, ge=0)
    allow_insufficient_funds_tests: bool = Field(
        default=False,
        description="Bypass local balance checks for startup test transactions.",
    )
    startup_test_transaction: bool = Field(
        default=False,
        description="Attempt a startup test transaction for diagnostics.",
    )

    # Strategy & Profit - ON1Builder with dynamic thresholds
    min_profit_eth: float = Field(default=0.005, ge=0)
    min_profit_percentage: float = Field(
        default=0.1, ge=0
    )  # Minimum profit as % of investment
    profit_analysis_enabled: bool = Field(
        default=False,
        description="Enable detailed post-trade profit analysis (extra RPC/API calls).",
    )
    dynamic_profit_scaling: bool = Field(
        default=True
    )  # Scale profit requirements based on balance
    balance_risk_ratio: float = Field(
        default=0.3, ge=0.1, le=0.9
    )  # Max % of balance to risk per trade
    slippage_tolerance: float = Field(default=0.5, ge=0, le=10)
    monitored_tokens_path: Path = Field(
        default=Path("src/on1builder/resources/tokens/all_chains_tokens.json")
    )

    # Flashloan Configuration
    flashloan_enabled: bool = Field(default=True)
    flashloan_min_profit_multiplier: float = Field(
        default=2.0, ge=1.0
    )  # Higher profit requirement for flashloans
    flashloan_max_amount_eth: float = Field(default=1000.0)  # Max flashloan amount
    flashloan_buffer_percentage: float = Field(
        default=0.1, ge=0.01
    )  # Safety buffer for flashloan repayment

    # ML Strategy Configuration
    ml_enabled: bool = Field(default=True)
    ml_learning_rate: float = Field(default=0.01, gt=0)
    ml_exploration_rate: float = Field(default=0.1, ge=0, le=1)
    ml_decay_rate: float = Field(default=0.995, gt=0, lt=1)
    ml_update_frequency: int = Field(
        default=100, gt=0
    )  # Update weights every N transactions

    # Balance Management
    emergency_balance_threshold: float = Field(
        default=0.01, ge=0
    )  # Emergency stop threshold
    low_balance_threshold: float = Field(
        default=0.05, ge=0
    )  # Switch to conservative strategies
    high_balance_threshold: float = Field(
        default=1.0, ge=0
    )  # Enable more aggressive strategies
    profit_reinvestment_percentage: float = Field(
        default=80.0, ge=0, le=100
    )  # % of profit to reinvest

    # Gas Optimization
    dynamic_gas_pricing: bool = Field(default=True)
    gas_price_percentile: int = Field(
        default=75, ge=10, le=95
    )  # Target gas price percentile
    max_gas_fee_percentage: float = Field(
        default=10.0, ge=1.0, le=50.0
    )  # Max gas as % of expected profit

    # System & Performance
    memory_check_interval: int = Field(default=300, gt=0)
    heartbeat_interval: int = Field(default=30, gt=0)
    connection_retry_count: int = Field(default=5, gt=0)
    connection_retry_delay: float = Field(default=5.0, gt=0)

    # - arbitrage settings
    arbitrage_scan_interval: int = Field(default=15, gt=0)

    # Performance monitoring
    performance_report_interval: int = Field(default=3600, gt=0)  # 1 hour

    # Market sentiment
    use_market_sentiment: bool = Field(default=True)
    sentiment_weight: float = Field(default=0.3, ge=0, le=1.0)
    market_price_persist_interval: int = Field(default=60, ge=0)

    # MEV settings
    mev_strategies_enabled: bool = Field(default=True)
    front_running_enabled: bool = Field(default=True)
    back_running_enabled: bool = Field(default=True)
    sandwich_attacks_enabled: bool = Field(
        default=False
    )  # Requires careful consideration

    # Risk management
    max_position_size_percent: float = Field(
        default=20.0, gt=0, le=100
    )  # Max % of portfolio per trade
    daily_loss_limit_percent: float = Field(
        default=5.0, gt=0, le=100
    )  # Stop trading if daily loss exceeds %

    # Cross-chain settings
    cross_chain_enabled: bool = Field(default=True)
    bridge_monitoring_enabled: bool = Field(default=True)

    # Oracle feeds (chain_id -> symbol -> feed address)
    oracle_feeds: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    oracle_stale_seconds: int = Field(
        default=3600,
        gt=0,
        description="Max age in seconds for oracle prices before treating as stale.",
    )

    # Nested Settings Models
    api: APISettings = Field(default_factory=APISettings)
    contracts: ContractAddressSettings = Field(default_factory=ContractAddressSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

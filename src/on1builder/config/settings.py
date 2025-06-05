"""
Pydantic configuration models for ON1Builder.
"""

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class APISettings(BaseModel):
    """Configuration for external APIs."""

    model_config = ConfigDict(extra="allow")

    coingecko_api_key: Optional[str] = None
    coinmarketcap_api_key: Optional[str] = None
    cryptocompare_api_key: Optional[str] = None
    etherscan_api_key: Optional[str] = None
    infura_project_id: Optional[str] = None
    infura_api_key: Optional[str] = None
    graph_api_key: Optional[str] = None
    uniswap_v2_subgraph_id: Optional[str] = None


class ChainSettings(BaseModel):
    """Configuration for a specific blockchain."""

    model_config = ConfigDict(extra="allow")

    name: str
    chain_id: int
    http_endpoint: str
    websocket_endpoint: Optional[str] = None
    ipc_endpoint: Optional[str] = None
    max_gas_price_gwei: float = Field(default=100, gt=0)
    gas_multiplier: float = Field(default=1.1, gt=0)
    is_poa: bool = False


class GlobalSettings(BaseModel):
    """Global configuration settings for ON1Builder."""

    model_config = ConfigDict(extra="allow")

    # Debug settings
    debug: bool = False

    # Base paths
    base_path: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent.parent
    )

    # Trading settings
    min_profit: float = Field(default=0.001, gt=0)
    wallet_key: Optional[str] = None

    # Monitoring settings
    monitored_tokens: List[str] = Field(default_factory=list)
    market_cache_ttl: int = Field(default=60, gt=0)

    # Connection settings
    connection_retry_count: int = Field(default=3, ge=1)
    connection_retry_delay: float = Field(default=2.0, gt=0)
    web3_max_retries: int = Field(default=3, ge=1)

    # Transaction settings
    transaction_retry_count: int = Field(default=3, ge=1)
    transaction_retry_delay: float = Field(default=1.0, gt=0)

    # Gas settings
    default_gas_limit: int = Field(default=100000, ge=1)
    fallback_gas_price: int = Field(default=50 * 10**9, ge=0)
    gas_price_multiplier: float = Field(default=1.1, gt=0)

    # Mempool settings
    mempool_retry_delay: float = Field(default=0.5, gt=0)
    mempool_max_retries: int = Field(default=3, ge=1)
    mempool_max_parallel_tasks: int = Field(default=10, ge=1)

    # Safety net settings
    safetynet_cache_ttl: int = Field(default=60, gt=0)
    safetynet_gas_price_ttl: int = Field(default=10, gt=0)
    min_balance: float = Field(default=0.001, gt=0)
    max_gas_price: int = Field(default=500_000_000_000, gt=0)
    min_gas_price_gwei: float = Field(default=1.0, gt=0)
    max_gas_price_gwei: float = Field(default=500.0, gt=0)
    
    # Slippage settings
    slippage_low_congestion: float = Field(default=0.1, ge=0)
    slippage_medium_congestion: float = Field(default=0.5, ge=0)
    slippage_high_congestion: float = Field(default=1.0, ge=0)
    slippage_extreme_congestion: float = Field(default=2.0, ge=0)
    slippage_default: float = Field(default=0.5, ge=0)
    min_slippage: float = Field(default=0.05, ge=0)
    max_slippage: float = Field(default=5.0, ge=0)
    
    # Profit settings
    profit_safety_margin: float = Field(default=0.9, gt=0)
    primary_token: Optional[str] = None
    
    # Strategy settings
    strategy_decay_factor: float = Field(default=0.95, gt=0, le=1)
    strategy_learning_rate: float = Field(default=0.01, gt=0)
    strategy_exploration_rate: float = Field(default=0.10, ge=0, le=1)
    strategy_min_weight: float = Field(default=0.10, gt=0)
    strategy_max_weight: float = Field(default=10.0, gt=0)
    strategy_market_weight: float = Field(default=1.0, gt=0)
    strategy_gas_weight: float = Field(default=1.0, gt=0)
    strategy_save_interval: int = Field(default=100, gt=0)
    
    # Market data settings
    price_cache_ttl: int = Field(default=300, gt=0)
    cache_cleanup_interval: int = Field(default=300, gt=0)
    market_update_interval: int = Field(default=60, gt=0)
    health_check_token: str = Field(default="ETH")
    
    # Chain worker settings
    heartbeat_interval: float = Field(default=30.0, gt=0)
    min_wallet_balance: float = Field(default=0.01, gt=0)

    # System settings
    memory_check_interval: int = Field(default=300, gt=0)

    # Database settings
    database_url: str = Field(default="sqlite+aiosqlite:///on1builder.db")

    # Contract addresses and deployment settings
    profit_receiver: Optional[str] = None
    flashloan_contract_address: Optional[str] = None
    aave_pool_address: Optional[str] = None
    max_flashloan_amount: int = Field(default=10**12, gt=0)

    # API settings
    api: APISettings = Field(default_factory=APISettings)

    # Chain configurations
    chains: Dict[str, ChainSettings] = Field(default_factory=dict)

    # POA chain IDs
    poa_chains: set = Field(default_factory=lambda: {99, 100, 77, 7766, 56, 11155111})


class MultiChainSettings(GlobalSettings):
    """Multi-chain configuration extending global settings."""

    active_chains: List[str] = Field(default_factory=list)

    def get_chain_config(self, chain_name: str) -> Optional[ChainSettings]:
        """Get configuration for a specific chain."""
        return self.chains.get(chain_name)

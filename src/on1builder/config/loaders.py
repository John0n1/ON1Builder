# src/on1builder/config/loaders.py
import os
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .settings import (
    GlobalSettings,
    APISettings,
    ContractAddressSettings,
    NotificationSettings,
    DatabaseSettings
)
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

def find_dotenv() -> Path | None:
    """Find the .env file by searching upwards from the current file."""
    current_dir = Path(__file__).resolve().parent
    for _ in range(5):  # Search up to 5 levels
        env_path = current_dir / ".env"
        if env_path.exists():
            return env_path
        current_dir = current_dir.parent
    return None

class _EnvSettings(BaseSettings):
    """
    A Pydantic BaseSettings model to automatically read from .env and environment.
    This intermediate model helps in gathering all variables before passing
    them to the main GlobalSettings model for final parsing and validation.
    """
    model_config = SettingsConfigDict(
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='allow'
    )

    # Re-declare all fields from GlobalSettings and its nested models
    # to ensure they are picked up from the environment by pydantic-settings.
    debug: bool = False
    base_path: Path = Path.cwd()
    wallet_key: str
    wallet_address: str
    profit_receiver_address: Optional[str] = None
    chains: str = "1"
    poa_chains: str = ""
    transaction_retry_count: int = 3
    transaction_retry_delay: float = 2.0
    max_gas_price_gwei: int = 200
    gas_price_multiplier: float = 1.1
    default_gas_limit: int = 500000
    fallback_gas_price_gwei: int = 50
    min_wallet_balance: float = 0.05
    min_profit_eth: float = 0.005
    min_profit_percentage: float = 0.1
    dynamic_profit_scaling: bool = True
    balance_risk_ratio: float = 0.3
    slippage_tolerance: float = 0.5
    monitored_tokens_path: Path = Path("src/on1builder/resources/tokens/all_chains_tokens.json")
    
    # Flashloan settings
    flashloan_enabled: bool = True
    flashloan_min_profit_multiplier: float = 2.0
    flashloan_max_amount_eth: float = 1000.0
    flashloan_buffer_percentage: float = 0.1
    
    # ML settings
    ml_enabled: bool = True
    ml_learning_rate: float = 0.01
    ml_exploration_rate: float = 0.1
    ml_decay_rate: float = 0.995
    ml_update_frequency: int = 100
    
    # Balance management
    emergency_balance_threshold: float = 0.01
    low_balance_threshold: float = 0.05
    high_balance_threshold: float = 1.0
    profit_reinvestment_percentage: float = 80.0
    
    # Gas optimization
    dynamic_gas_pricing: bool = True
    gas_price_percentile: int = 75
    max_gas_fee_percentage: float = 10.0
    
    memory_check_interval: int = 300
    heartbeat_interval: int = 30
    connection_retry_count: int = 5
    connection_retry_delay: float = 5.0
    
    # Enhanced arbitrage settings
    arbitrage_scan_interval: int = 15
    
    # Performance monitoring
    performance_report_interval: int = 3600
    
    # Market sentiment
    use_market_sentiment: bool = True
    sentiment_weight: float = 0.3
    
    # MEV settings
    mev_strategies_enabled: bool = True
    front_running_enabled: bool = True
    back_running_enabled: bool = True
    sandwich_attacks_enabled: bool = False
    
    # Risk management
    max_position_size_percent: float = 20.0
    daily_loss_limit_percent: float = 5.0
    
    # Cross-chain settings
    cross_chain_enabled: bool = True
    bridge_monitoring_enabled: bool = True

    # Nested Models as flat prefixes
    etherscan_api_key: Optional[str] = Field(None, alias="ETHERSCAN_API_KEY")
    coingecko_api_key: Optional[str] = Field(None, alias="COINGECKO_API_KEY")
    coinmarketcap_api_key: Optional[str] = Field(None, alias="COINMARKETCAP_API_KEY")
    cryptocompare_api_key: Optional[str] = Field(None, alias="CRYPTOCOMPARE_API_KEY")
    infura_project_id: Optional[str] = Field(None, alias="INFURA_PROJECT_ID")

    uniswap_v2_router_addresses: str = Field('{}', alias="UNISWAP_V2_ROUTER_ADDRESSES")
    sushiswap_router_addresses: str = Field('{}', alias="SUSHISWAP_ROUTER_ADDRESSES")
    aave_v3_pool_addresses: str = Field('{}', alias="AAVE_V3_POOL_ADDRESSES")
    simple_flashloan_contract_addresses: str = Field('{}', alias="SIMPLE_FLASHLOAN_CONTRACT_ADDRESSES")

    notification_channels: str = Field("", alias="NOTIFICATION_CHANNELS")
    min_notification_level: str = Field("INFO", alias="MIN_NOTIFICATION_LEVEL")
    slack_webhook_url: Optional[str] = Field(None, alias="SLACK_WEBHOOK_URL")
    telegram_bot_token: Optional[str] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, alias="TELEGRAM_CHAT_ID")
    discord_webhook_url: Optional[str] = Field(None, alias="DISCORD_WEBHOOK_URL")
    smtp_server: Optional[str] = Field(None, alias="SMTP_SERVER")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(None, alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(None, alias="SMTP_PASSWORD")
    alert_email: Optional[str] = Field(None, alias="ALERT_EMAIL")

    database_url: str = Field("sqlite+aiosqlite:///on1builder_data.db", alias="DATABASE_URL")


def _gather_dynamic_env_vars() -> Dict[str, Any]:
    """
    Gathers environment variables that have dynamic keys, like RPC URLs.
    """
    dynamic_vars = {
        "rpc_urls": {},
        "websocket_urls": {}
    }
    for key, value in os.environ.items():
        if key.startswith("RPC_URL_"):
            try:
                chain_id = int(key.split('_')[-1])
                dynamic_vars["rpc_urls"][chain_id] = value
            except (ValueError, IndexError):
                logger.warning(f"Could not parse chain ID from env var: {key}")
        elif key.startswith("WEBSOCKET_URL_"):
            try:
                chain_id = int(key.split('_')[-1])
                dynamic_vars["websocket_urls"][chain_id] = value
            except (ValueError, IndexError):
                logger.warning(f"Could not parse chain ID from env var: {key}")

    return dynamic_vars

def load_settings() -> GlobalSettings:
    """
    Loads, validates, and returns the application's configuration settings.

    This is the primary function to be called by the application to get its config.

    Returns:
        GlobalSettings: A validated and type-safe configuration object.
    """
    env_path = find_dotenv()
    if env_path:
        logger.info(f"Loading environment variables from: {env_path}")
        load_dotenv(dotenv_path=env_path)
    else:
        logger.warning("No .env file found. Relying on system environment variables.")

    # Load settings from environment using the intermediate model
    env_settings = _EnvSettings()

    # Manually structure the nested models
    api_settings = APISettings(
        etherscan_api_key=env_settings.etherscan_api_key,
        coingecko_api_key=env_settings.coingecko_api_key,
        coinmarketcap_api_key=env_settings.coinmarketcap_api_key,
        cryptocompare_api_key=env_settings.cryptocompare_api_key,
        infura_project_id=env_settings.infura_project_id
    )

    contract_settings = ContractAddressSettings(
        uniswap_v2_router=env_settings.uniswap_v2_router_addresses,
        sushiswap_router=env_settings.sushiswap_router_addresses,
        aave_v3_pool=env_settings.aave_v3_pool_addresses,
        simple_flashloan_contract=env_settings.simple_flashloan_contract_addresses
    )

    notification_settings = NotificationSettings(
        channels=env_settings.notification_channels,
        min_level=env_settings.min_notification_level,
        slack_webhook_url=env_settings.slack_webhook_url,
        telegram_bot_token=env_settings.telegram_bot_token,
        telegram_chat_id=env_settings.telegram_chat_id,
        discord_webhook_url=env_settings.discord_webhook_url,
        smtp_server=env_settings.smtp_server,
        smtp_port=env_settings.smtp_port,
        smtp_username=env_settings.smtp_username,
        smtp_password=env_settings.smtp_password,
        alert_email=env_settings.alert_email
    )

    database_settings = DatabaseSettings(url=env_settings.database_url)

    # Gather all static and dynamic data
    final_config_data = env_settings.model_dump()
    final_config_data.update(_gather_dynamic_env_vars())

    # Populate nested models
    final_config_data['api'] = api_settings
    final_config_data['contracts'] = contract_settings
    final_config_data['notifications'] = notification_settings
    final_config_data['database'] = database_settings

    # Instantiate the final GlobalSettings model
    try:
        global_settings = GlobalSettings(**final_config_data)
        logger.info("Configuration loaded and validated successfully.")
        return global_settings
    except Exception as e:
        logger.critical(f"Failed to create GlobalSettings: {e}", exc_info=True)
        raise ValueError(f"Configuration validation failed: {e}") from e

# Global instance of the settings - lazy loaded
_settings: Optional[GlobalSettings] = None

def get_settings() -> GlobalSettings:
    """
    Get the global settings instance, loading it if not already loaded.
    This prevents circular import issues.
    """
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings

# Create a module-level property for backward compatibility
class _SettingsProxy:
    def __getattr__(self, name):
        return getattr(get_settings(), name)

settings = _SettingsProxy()
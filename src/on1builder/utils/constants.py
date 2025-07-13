# src/on1builder/utils/constants.py
"""Application-wide constants for ON1Builder."""

from __future__ import annotations
from decimal import Decimal

# =============================================================================
# NETWORK AND CHAIN CONSTANTS
# =============================================================================

# Supported chain IDs and their names
CHAIN_NAMES = {
    1: "Ethereum Mainnet",
    137: "Polygon",
    42161: "Arbitrum One", 
    10: "Optimism",
    56: "BSC",
    43114: "Avalanche",
    250: "Fantom",
    5: "Goerli",
    80001: "Mumbai",
    421613: "Arbitrum Goerli"
}

# Network block times (in seconds)
BLOCK_TIMES = {
    1: 12,      # Ethereum
    137: 2,     # Polygon
    42161: 1,   # Arbitrum
    10: 2,      # Optimism
    56: 3,      # BSC
    43114: 2,   # Avalanche
    250: 1      # Fantom
}

# =============================================================================
# TRANSACTION AND GAS CONSTANTS
# =============================================================================

# Gas-related constants
DEFAULT_GAS_LIMIT = 250000
MAX_GAS_LIMIT = 8000000
MIN_GAS_PRICE_GWEI = 1
DEFAULT_PRIORITY_FEE_GWEI = 2
GAS_PRICE_BUFFER_MULTIPLIER = Decimal("1.1")

# Transaction retry settings
DEFAULT_TRANSACTION_RETRY_COUNT = 3
DEFAULT_TRANSACTION_RETRY_DELAY = 2.0  # seconds
TRANSACTION_TIMEOUT = 120  # seconds

# Nonce management
NONCE_SYNC_INTERVAL = 300  # seconds

# =============================================================================
# MEV AND STRATEGY CONSTANTS
# =============================================================================

# Profit thresholds
MIN_PROFIT_THRESHOLD_ETH = Decimal("0.001")
MIN_PROFIT_PERCENTAGE = Decimal("0.5")  # 0.5%
DUST_THRESHOLD_ETH = Decimal("0.0001")

# Strategy execution limits
MAX_CONCURRENT_OPPORTUNITIES = 3
OPPORTUNITY_EXECUTION_TIMEOUT = 60  # seconds
SANDWICH_ATTACK_DELAY = 2  # seconds between front-run and back-run

# Balance management tiers (in ETH)
BALANCE_TIER_THRESHOLDS = {
    "dust": Decimal("0.01"),
    "small": Decimal("0.1"), 
    "medium": Decimal("0.5"),
    "large": Decimal("2.0"),
    "whale": Decimal("10.0")
}

# Risk management
MAX_POSITION_SIZE_PERCENTAGE = 20  # % of total balance
STOP_LOSS_PERCENTAGE = 5  # %
EMERGENCY_STOP_LOSS_PERCENTAGE = 10  # %

# =============================================================================
# CACHING AND PERFORMANCE CONSTANTS
# =============================================================================

# Cache durations (in seconds)
BALANCE_CACHE_DURATION = 30
TOKEN_PRICE_CACHE_DURATION = 10
GAS_PRICE_CACHE_DURATION = 15
MARKET_DATA_CACHE_DURATION = 60
ABI_CACHE_DURATION = 3600  # 1 hour
TOKEN_INFO_CACHE_DURATION = 1800  # 30 minutes

# Performance thresholds
MAX_MEMORY_USAGE_MB = 512
GC_THRESHOLD_MB = 256
CLEANUP_INTERVAL_SECONDS = 300
MEMORY_WARNING_THRESHOLD_PERCENTAGE = 80

# API rate limiting
DEFAULT_API_RATE_LIMIT = 100  # requests per minute
API_RETRY_ATTEMPTS = 3
API_RETRY_DELAY = 1.0  # seconds

# =============================================================================
# DATABASE AND PERSISTENCE CONSTANTS
# =============================================================================

# Database connection
DB_CONNECTION_TIMEOUT = 30  # seconds
DB_QUERY_TIMEOUT = 10  # seconds
DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10

# Data retention
TRANSACTION_RETENTION_DAYS = 90
PROFIT_RECORD_RETENTION_DAYS = 365
PERFORMANCE_METRICS_RETENTION_DAYS = 30

# =============================================================================
# MONITORING AND ALERTING CONSTANTS
# =============================================================================

# Monitoring intervals (in seconds)
PERFORMANCE_MONITORING_INTERVAL = 60
MARKET_DATA_UPDATE_INTERVAL = 10
TXPOOL_SCAN_INTERVAL = 1
BALANCE_CHECK_INTERVAL = 30
SYSTEM_HEALTH_CHECK_INTERVAL = 120

# Alert thresholds
LOW_BALANCE_THRESHOLD_ETH = Decimal("0.05")
HIGH_GAS_PRICE_THRESHOLD_GWEI = 100
FAILED_TRANSACTION_ALERT_COUNT = 5
PROFIT_LOSS_ALERT_THRESHOLD_ETH = Decimal("0.01")

# Notification rate limiting
MAX_NOTIFICATIONS_PER_HOUR = 20
NOTIFICATION_COOLDOWN_SECONDS = 300  # 5 minutes

# =============================================================================
# DEX AND PROTOCOL CONSTANTS
# =============================================================================

# Known DEX router addresses (chain-agnostic identifiers)
DEX_ROUTER_IDENTIFIERS = {
    "uniswap_v2": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
    "uniswap_v3": "0xe592427a0aece92de3edee1f18e0157c05861564",
    "sushiswap": "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",
    "1inch": "0x1111111254fb6c44bac0bed2854e76f90643097d",
    "pancakeswap": "0x10ed43c718714eb63d5aa57b78b54704e256024e"
}

# Flash loan providers
FLASHLOAN_PROVIDERS = {
    "aave_v3": "aave_flashloan",
    "uniswap_v3": "uniswap_flashloan",
    "dydx": "dydx_flashloan"
}

# Slippage tolerance (in basis points)
DEFAULT_SLIPPAGE_BPS = 50  # 0.5%
MAX_SLIPPAGE_BPS = 300  # 3%

# =============================================================================
# LOGGING AND DEBUGGING CONSTANTS
# =============================================================================

# Log levels
DEFAULT_LOG_LEVEL = "INFO"
DEBUG_LOG_LEVEL = "DEBUG"

# Log file rotation
LOG_FILE_MAX_SIZE = 50 * 1024 * 1024  # 50MB
LOG_FILE_BACKUP_COUNT = 5
LOG_ROTATION_INTERVAL = "midnight"

# Debug flags
ENABLE_TRACE_LOGGING = False
ENABLE_PERFORMANCE_LOGGING = True
ENABLE_TRANSACTION_LOGGING = True

# =============================================================================
# SECURITY CONSTANTS
# =============================================================================

# Encryption and security
MIN_PASSWORD_LENGTH = 12
SESSION_TIMEOUT_MINUTES = 30
API_KEY_LENGTH = 32

# Validation patterns (as strings to avoid import issues)
ETHEREUM_ADDRESS_PATTERN = r'^0x[a-fA-F0-9]{40}$'
TRANSACTION_HASH_PATTERN = r'^0x[a-fA-F0-9]{64}$'
PRIVATE_KEY_PATTERN = r'^0x[a-fA-F0-9]{64}$'

# =============================================================================
# MARKET DATA CONSTANTS
# =============================================================================

# Price data
PRICE_DECIMAL_PLACES = 18
USD_DECIMAL_PLACES = 6
PERCENTAGE_DECIMAL_PLACES = 4

# Volatility calculation
VOLATILITY_WINDOW_MINUTES = 60
MIN_PRICE_SAMPLES = 10

# Market condition thresholds
HIGH_VOLATILITY_THRESHOLD = 0.05  # 5%
EXTREME_VOLATILITY_THRESHOLD = 0.15  # 15%
LOW_LIQUIDITY_THRESHOLD = 10000  # USD

# =============================================================================
# FILE AND PATH CONSTANTS
# =============================================================================

# Default file names
DEFAULT_ENV_FILE = ".env"
DEFAULT_LOG_FILE = "on1builder.log"
DEFAULT_DB_FILE = "on1builder.db"

# Resource directories
ABI_DIR = "abi"
TOKENS_DIR = "tokens" 
CONTRACTS_DIR = "contracts"
ML_MODELS_DIR = "ml_models"

# Configuration file names
MAIN_TOKEN_FILE = "all_chains_tokens.json"
STRATEGY_WEIGHTS_FILE = "strategy_weights.json"

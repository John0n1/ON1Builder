# src/on1builder/config/manager.py
"""Enhanced configuration management for ON1Builder."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .loaders import load_settings, get_settings
from .validation import ConfigValidator
from ..utils.logging_config import get_logger
from ..utils.custom_exceptions import ConfigurationError
from ..utils.constants import DEFAULT_ENV_FILE

logger = get_logger(__name__)


class ConfigurationManager:
    """Centralized configuration management with validation and monitoring."""
    
    def __init__(self):
        self._config = None
        self._last_loaded: Optional[datetime] = None
        self._config_file_path: Optional[Path] = None
        self._validation_errors: List[str] = []
        self._validator = ConfigValidator()
    
    def initialize(self, config_path: Optional[str] = None, force_reload: bool = False) -> None:
        """
        Initialize configuration with validation and error checking.
        
        Args:
            config_path: Path to configuration file (defaults to .env)
            force_reload: Force reload even if already loaded
        """
        if self._config is not None and not force_reload:
            logger.debug("Configuration already loaded. Use force_reload=True to reload.")
            return
            
        try:
            # Determine config file path
            if config_path:
                self._config_file_path = Path(config_path)
            else:
                self._config_file_path = self._find_config_file()
            
            if not self._config_file_path.exists():
                raise ConfigurationError(
                    f"Configuration file not found: {self._config_file_path}",
                    details={"searched_path": str(self._config_file_path)}
                )
            
            logger.info(f"Loading configuration from: {self._config_file_path}")
            
            # Load and validate configuration
            self._config = load_settings()
            self._last_loaded = datetime.now()
            
            # Perform comprehensive validation
            self._validate_configuration()
            
            # Log configuration summary (without sensitive data)
            self._log_configuration_summary()
            
            logger.info("Configuration loaded and validated successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize configuration: {e}")
            raise ConfigurationError(f"Configuration initialization failed: {e}", cause=e)
    
    def _find_config_file(self) -> Path:
        """Find configuration file in standard locations."""
        search_paths = [
            Path.cwd() / DEFAULT_ENV_FILE,
            Path.cwd().parent / DEFAULT_ENV_FILE,
            Path.home() / f".{DEFAULT_ENV_FILE}",
            Path("/etc/on1builder") / DEFAULT_ENV_FILE
        ]
        
        for path in search_paths:
            if path.exists():
                logger.debug(f"Found configuration file at: {path}")
                return path
        
        # Default to current directory
        return Path.cwd() / DEFAULT_ENV_FILE
    
    def _validate_configuration(self) -> None:
        """Perform comprehensive configuration validation."""
        self._validation_errors.clear()
        
        try:
            # Convert config to dict for validation
            config_dict = self._config.model_dump() if self._config else {}
            
            # Perform validation
            validated_config = self._validator.validate_complete_config(config_dict)
            
            # Check for critical missing values
            self._check_critical_requirements(validated_config)
            
            # Validate chain-specific configurations
            self._validate_chain_configurations(validated_config)
            
            # Validate API configurations
            self._validate_api_configurations(validated_config)
            
        except Exception as e:
            error_msg = f"Configuration validation failed: {e}"
            self._validation_errors.append(error_msg)
            raise ConfigurationError(error_msg, cause=e)
    
    def _check_critical_requirements(self, config: Dict[str, Any]) -> None:
        """Check for critical configuration requirements."""
        critical_fields = [
            ("wallet_key", "Wallet private key is required"),
            ("wallet_address", "Wallet address is required"),
            ("chains", "At least one chain must be configured")
        ]
        
        for field, error_msg in critical_fields:
            if not config.get(field):
                self._validation_errors.append(error_msg)
        
        # Check chains configuration
        chains = config.get("chains", [])
        if not chains:
            self._validation_errors.append("No chains configured")
        elif not isinstance(chains, list) or len(chains) == 0:
            self._validation_errors.append("Chains must be a non-empty list")
        
        if self._validation_errors:
            raise ConfigurationError(
                "Critical configuration requirements not met",
                details={"errors": self._validation_errors}
            )
    
    def _validate_chain_configurations(self, config: Dict[str, Any]) -> None:
        """Validate chain-specific configurations."""
        chains = config.get("chains", [])
        rpc_urls = config.get("rpc_urls", {})
        
        missing_rpcs = []
        for chain_id in chains:
            chain_str = str(chain_id)
            if chain_str not in rpc_urls or not rpc_urls[chain_str]:
                missing_rpcs.append(chain_id)
        
        if missing_rpcs:
            self._validation_errors.append(
                f"Missing RPC URLs for chains: {missing_rpcs}"
            )
            logger.warning(f"Missing RPC URLs for chains: {missing_rpcs}")
    
    def _validate_api_configurations(self, config: Dict[str, Any]) -> None:
        """Validate API configurations."""
        api_config = config.get("api", {})
        
        # Check for at least one price API
        price_apis = [
            api_config.get("coingecko_api_key"),
            api_config.get("coinmarketcap_api_key"),
            api_config.get("cryptocompare_api_key")
        ]
        
        if not any(price_apis):
            self._validation_errors.append(
                "At least one price API key should be configured for better market data"
            )
            logger.warning("No price API keys configured - using free tier with rate limits")
    
    def _log_configuration_summary(self) -> None:
        """Log configuration summary without sensitive data."""
        if not self._config:
            return
            
        config_dict = self._config.model_dump()
        
        summary = {
            "chains_configured": len(config_dict.get("chains", [])),
            "wallet_configured": bool(config_dict.get("wallet_address")),
            "api_keys_configured": sum(1 for key in config_dict.get("api", {}).values() if key),
            "notifications_enabled": bool(config_dict.get("notifications", {}).get("enabled")),
            "debug_mode": config_dict.get("debug", False),
            "config_file": str(self._config_file_path) if self._config_file_path else "unknown"
        }
        
        logger.info(f"Configuration summary: {summary}")
    
    def get_config(self):
        """Get the current configuration."""
        if self._config is None:
            raise ConfigurationError("Configuration not initialized. Call initialize() first.")
        return self._config
    
    def reload_configuration(self) -> None:
        """Reload configuration from file."""
        logger.info("Reloading configuration...")
        self.initialize(force_reload=True)
    
    def validate_runtime_requirements(self) -> Dict[str, bool]:
        """Validate runtime requirements and return status."""
        if not self._config:
            return {"initialized": False}
        
        checks = {
            "initialized": True,
            "wallet_configured": bool(self._config.wallet_address),
            "chains_configured": len(self._config.chains) > 0,
            "rpc_connections": self._check_rpc_connections(),
            "api_access": self._check_api_access(),
            "file_permissions": self._check_file_permissions()
        }
        
        return checks
    
    def _check_rpc_connections(self) -> bool:
        """Check if RPC connections are properly configured."""
        try:
            for chain_id in self._config.chains:
                rpc_url = self._config.rpc_urls.get(str(chain_id))
                if not rpc_url:
                    return False
                # Additional connectivity check could be added here
            return True
        except Exception:
            return False
    
    def _check_api_access(self) -> bool:
        """Check if API access is properly configured."""
        try:
            api_config = self._config.api
            # Check if at least one API key is configured
            return any([
                api_config.etherscan_api_key,
                api_config.coingecko_api_key,
                api_config.coinmarketcap_api_key
            ])
        except Exception:
            return False
    
    def _check_file_permissions(self) -> bool:
        """Check file system permissions."""
        try:
            if self._config_file_path:
                return os.access(self._config_file_path, os.R_OK)
            return True
        except Exception:
            return False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of configuration."""
        return {
            "status": "healthy" if not self._validation_errors else "unhealthy",
            "last_loaded": self._last_loaded.isoformat() if self._last_loaded else None,
            "config_file": str(self._config_file_path) if self._config_file_path else None,
            "validation_errors": self._validation_errors.copy(),
            "runtime_checks": self.validate_runtime_requirements()
        }
    
    def export_safe_config(self) -> Dict[str, Any]:
        """Export configuration with sensitive data redacted."""
        if not self._config:
            return {}
        
        from ..utils.config_redactor import ConfigRedactor
        config_dict = self._config.model_dump()
        return ConfigRedactor.redact_config(config_dict, show_sensitive=False)


# Global configuration manager instance
_config_manager: Optional[ConfigurationManager] = None

def get_config_manager() -> ConfigurationManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager()
    return _config_manager


def initialize_global_config(config_path: Optional[str] = None, force_reload: bool = False) -> None:
    """Initialize the global configuration."""
    manager = get_config_manager()
    manager.initialize(config_path, force_reload)


def get_validated_config():
    """Get the validated configuration instance."""
    manager = get_config_manager()
    return manager.get_config()

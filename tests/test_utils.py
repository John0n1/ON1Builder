#!/usr/bin/env python3
"""
Tests for utility modules.
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

def test_gas_optimizer_initialization():
    """Test GasOptimizer basic initialization."""
    try:
        from on1builder.utils.gas_optimizer import GasOptimizer
        
        # Mock web3 object
        mock_web3 = MagicMock()
        
        optimizer = GasOptimizer(mock_web3)
        assert optimizer is not None
        assert hasattr(optimizer, 'get_gas_analytics')
        
    except ImportError:
        pytest.skip("GasOptimizer requires web3 dependencies")

def test_profit_calculator_initialization():
    """Test ProfitCalculator basic initialization."""
    try:
        from on1builder.utils.profit_calculator import ProfitCalculator
        
        # Mock external dependencies
        mock_web3 = MagicMock()
        mock_settings = MagicMock()
        
        calculator = ProfitCalculator(mock_web3, mock_settings)
        assert calculator is not None
        
    except ImportError:
        pytest.skip("ProfitCalculator requires web3 dependencies")

def test_logging_config():
    """Test that logging configuration works."""
    from on1builder.utils.logging_config import get_logger
    
    logger = get_logger("test")
    assert logger is not None
    assert hasattr(logger, 'info')
    assert hasattr(logger, 'error')
    assert hasattr(logger, 'warning')
    assert hasattr(logger, 'debug')

def test_notification_service_basic():
    """Test NotificationService basic functionality."""
    try:
        from on1builder.utils.notification_service import NotificationService
        
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.notification = MagicMock()
        mock_settings.notification.email_enabled = False
        mock_settings.notification.discord_enabled = False
        
        service = NotificationService(mock_settings)
        assert service is not None
        
    except ImportError:
        pytest.skip("NotificationService requires additional dependencies")

def test_container_basic():
    """Test Container utility basic functionality."""
    try:
        from on1builder.utils.container import Container
        
        container = Container()
        assert container is not None
        
    except ImportError:
        pytest.skip("Container utility not available")

if __name__ == "__main__":
    pytest.main([__file__])
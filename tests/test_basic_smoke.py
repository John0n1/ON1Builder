#!/usr/bin/env python3
"""
Simplified smoke tests without external dependencies.
"""

import pytest
from pathlib import Path

def test_package_version():
    """Test that the package has correct version."""
    import on1builder
    assert on1builder.__version__ == "2.2.0"
    assert on1builder.__author__ == "john0n1"

def test_logging_initialization():
    """Test that logging can be initialized."""
    from on1builder.utils.logging_config import get_logger
    
    logger = get_logger("test")
    assert logger is not None
    assert hasattr(logger, 'info')
    assert hasattr(logger, 'error')

def test_container_utility():
    """Test basic container functionality."""
    from on1builder.utils.container import Container
    
    container = Container()
    assert container is not None

def test_basic_module_structure():
    """Test that basic module structure is intact."""
    # Test that main modules exist
    import on1builder.utils
    import on1builder.core  
    import on1builder.config
    import on1builder.engines
    import on1builder.monitoring
    
    # Basic sanity checks
    assert hasattr(on1builder.utils, '__file__')
    assert hasattr(on1builder.core, '__file__')

def test_pyproject_exists():
    """Test that pyproject.toml exists and has correct version."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    assert pyproject_path.exists()
    
    content = pyproject_path.read_text()
    assert 'version = "2.2.0"' in content

if __name__ == "__main__":
    pytest.main([__file__])
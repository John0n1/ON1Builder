"""Configuration management module."""

# Ensure alias modules are recognized
# filepath: src/on1builder/config/__init__.py
from .config import *
from .config import APIConfig, Configuration

try:
    from .configuration import *
except ImportError:
    pass

__all__ = ["Configuration", "APIConfig"]

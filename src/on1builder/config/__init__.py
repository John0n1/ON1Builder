"""Configuration management module."""

from .config import Configuration, APIConfig

# Ensure alias modules are recognized
# filepath: src/on1builder/config/__init__.py
from .config import *
try:
    from .configuration import *
except ImportError:
    pass

__all__ = ["Configuration", "APIConfig"]
"""
ON1Builder - Multi-chain blockchain transaction execution framework
==================================================================

A high-performance framework for building, signing, simulating, and dispatching
blockchain transactions across multiple chains, with a focus on MEV strategies.

This package provides tools for:
- Multi-chain transaction management
- Mempool monitoring
- Market data analysis
- Price prediction and MEV opportunity detection
- Transaction safety verification
- Gas optimization
- Strategy execution
- Performance monitoring
"""

__title__ = "ON1Builder"
__description__ = "Multi-chain blockchain transaction execution framework"
__url__ = "https://on1.no"
__version_info__ = (2, 1, 0)
__version_short__ = "2.1"
__version__ = "2.1.0"
__author__ = "ON1Builder Team"
__author_email__ = "john@on1.no"
__maintainer__ = "ON1Builder Team"
__maintainer_email__ = "john@on1.no"
__email__ = "builder@on1.no"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2023 ON1Builder Team"

from on1builder.core import *
from on1builder.config.config import *
from on1builder.engines import *
from on1builder.monitoring import *
from on1builder.utils import *
from on1builder.persistence import *
from on1builder.config import *
from on1builder.cli import *

__all__ = [
    "ON1Builder",
    "ON1BuilderConfig",
    "ON1BuilderEngine",
    "ON1BuilderMonitoring",
    "ON1BuilderPersistence",
    "ON1BuilderCLI",
]

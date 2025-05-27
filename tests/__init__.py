"""
Test initialization module.
This ensures that the source code is in the Python path when running tests.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path if not already there
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

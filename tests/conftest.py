"""
Shared setup for the tests. pytest reads this file automatically.

It does two things:
  1. Lets the tests find the core/ folder, wherever you run them from.
  2. Registers the "live" label, used on tests that need real Yahoo data.
     Skip those with:  python -m pytest tests -m "not live"
"""
import sys
from pathlib import Path

# The project folder (one level up from tests/), so "from core import ..." works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs the internet (real Yahoo data)")

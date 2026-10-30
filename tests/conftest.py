"""
Shared setup for the tests. pytest reads this file automatically.

It does three things:
  1. Lets the tests find the core/ folder, wherever you run them from.
  2. Registers the "live" label, used on tests that need real Yahoo data.
     Skip those with:  python -m pytest tests -m "not live"
  3. Registers the "ai" label, used on tests that call the real Claude.
     They cost a little money, so they're skipped unless you add --ai:
         python -m pytest tests/test_coach_cases.py --ai -s
"""
import sys
from pathlib import Path

import pytest

# The project folder (one level up from tests/), so "from core import ..." works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_addoption(parser):
    # Adds the --ai switch to the pytest command.
    parser.addoption("--ai", action="store_true",
                     help="also run the coach's base cases against the real Claude (about 10 cents)")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs the internet (real Yahoo data)")
    config.addinivalue_line("markers", "ai: calls the real Claude and costs a little money; runs only with --ai")


def pytest_collection_modifyitems(config, items):
    # Without --ai, every test labelled "ai" is skipped, so nobody spends
    # money just by running the normal checks.
    if config.getoption("--ai"):
        return
    skip = pytest.mark.skip(reason="calls the real Claude (costs money): add --ai to run it")
    for item in items:
        if "ai" in item.keywords:
            item.add_marker(skip)

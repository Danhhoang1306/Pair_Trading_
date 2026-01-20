"""
Pair Trading Pro - Professional Pair Trading System with MetaTrader 5

A sophisticated pair trading system that automatically:
- Detects trading opportunities based on Z-score
- Executes entries/exits with dynamic hedge ratios
- Pyramids positions when trends are favorable
- Auto-adjusts hedge when ratios drift
- Manages risk with 3-layer protection (Setup, Portfolio, Daily)
- Provides real-time GUI with charts

Author: Pair Trading Pro Team
License: MIT
"""

__version__ = "2.0.0"
__author__ = "Pair Trading Pro Team"
__license__ = "MIT"

# Version info tuple for programmatic access
VERSION_INFO = tuple(int(x) for x in __version__.split("."))

# Package metadata
__title__ = "pair-trading-pro"
__description__ = "Professional Pair Trading System with MetaTrader 5"
__url__ = "https://github.com/your-username/pair-trading-pro"

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "VERSION_INFO",
]

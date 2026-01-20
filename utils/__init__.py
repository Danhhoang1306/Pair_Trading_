"""Utility modules"""

# Make logger available
try:
    from .logger import setup_logging
    __all__ = ['setup_logging']
except ImportError:
    __all__ = []

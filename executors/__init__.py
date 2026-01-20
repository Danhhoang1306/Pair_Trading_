"""
Executors Package - Refactored execution logic

Extracted from main_cli.py for better organization and testability.

System 1: EntryExecutor - Opens new spread positions based on z-score signals
System 2: PyramidingExecutor - Scales into existing positions (grid)
System 3: VolumeRebalancer - Adjusts volumes to maintain hedge ratio (single leg)
"""

from .entry_executor import EntryExecutor
from .exit_executor import ExitExecutor
from .pyramiding_executor import PyramidingExecutor
from .volume_rebalancer import VolumeRebalancer

# Backward compatibility (deprecated)
from .hedge_executor import HedgeExecutor

__all__ = [
    'EntryExecutor',
    'ExitExecutor',
    'PyramidingExecutor',
    'VolumeRebalancer',
    'HedgeExecutor',  # Deprecated - use VolumeRebalancer
]

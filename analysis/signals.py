"""
Qt Signals for Analysis Engine
Thread-safe communication between worker and GUI
"""

from PyQt6.QtCore import QObject, pyqtSignal


class AnalysisSignals(QObject):
    """
    Signals for communicating analysis progress and results
    All signals are thread-safe
    """
    
    # Progress updates (0-100%)
    progress = pyqtSignal(float)  # Current progress percentage
    
    # Phase changes (string description)
    phase_change = pyqtSignal(str)  # "Loading Data", "Calculating Correlations", etc.
    
    # Detailed status updates
    status_update = pyqtSignal(dict)  # {phase, current_item, total_items, message}
    
    # Partial result (one pair analyzed)
    partial_result = pyqtSignal(dict)  # Single pair analysis result
    
    # Final results (all pairs)
    completed = pyqtSignal(list)  # List of all analysis results
    
    # Errors
    error = pyqtSignal(str)  # Error message
    
    # Warnings
    warning = pyqtSignal(str)  # Warning message
    
    # Log messages
    log = pyqtSignal(str)  # General log message

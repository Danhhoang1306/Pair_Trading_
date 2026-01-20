"""Core trading modules"""

# Export main classes for convenience
try:
    from .data_manager import DataManager
    from .mt5_connector import MT5Connector
    from .mt5_trade_executor import MT5TradeExecutor
    __all__ = ['DataManager', 'MT5Connector', 'MT5TradeExecutor']
except ImportError:
    __all__ = []

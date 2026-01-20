"""
TradingSystem - Isolated from main_cli
Import this to get TradingSystem without triggering main_cli module load until needed
"""

# Simple delayed import - imports main_cli only when TradingSystem is first used
def TradingSystem(*args, **kwargs):
    """
    Factory function that imports and creates TradingSystem
    This way main_cli is only imported when TradingSystem() is called, not when this module is imported
    """
    from main_cli import TradingSystem as ActualTradingSystem
    # Replace ourselves with the actual class for future imports
    import sys
    sys.modules[__name__].TradingSystem = ActualTradingSystem
    # Create and return instance
    return ActualTradingSystem(*args, **kwargs)



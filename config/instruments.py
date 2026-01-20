"""
Instrument specifications
"""

# Trading instruments
INSTRUMENTS = {
    'gold': {
        'symbol': 'XAUUSD',
        'contract_size': 100,  # ounces
        'tick_size': 0.01,
        'tick_value': 1.0,
        'min_lot': 0.01,
        'max_lot': 100.0,
        'lot_step': 0.01,
    },
    'silver': {
        'symbol': 'XAGUSD',
        'contract_size': 5000,  # ounces
        'tick_size': 0.001,
        'tick_value': 5.0,
        'min_lot': 0.01,
        'max_lot': 100.0,
        'lot_step': 0.01,
    }
}

# Data settings
DATA_CONFIG = {
    'timeframe': 'H1',  # M1, M5, M15, M30, H1, H4, D1
    'bars_to_load': 500,
    'warmup_bars': 252,  # Minimum bars needed for calculations
}

# Timeframe mappings for MT5
TIMEFRAME_MAP = {
    'M1': 1,
    'M5': 5,
    'M15': 15,
    'M30': 30,
    'H1': 16385,
    'H4': 16388,
    'D1': 16408,
}

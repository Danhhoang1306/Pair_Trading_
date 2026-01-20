"""
Configuration package
Backward compatible with old imports while supporting new YAML config
"""

__version__ = "2.0.0"

import os
from pathlib import Path
# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# ============================================================
# OLD CONFIG (For backward compatibility)
# ============================================================

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
STATE_DIR = DATA_DIR / "state"
HISTORY_DIR = DATA_DIR / "history"
POSITION_DIR = DATA_DIR / "positions"

# Ensure directories exist
for dir_path in [DATA_DIR, LOG_DIR, STATE_DIR, HISTORY_DIR, POSITION_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# MT5 Configuration
MT5_CONFIG = {
    'login': int(os.getenv('MT5_LOGIN', '0')),
    'password': os.getenv('MT5_PASSWORD', ''),
    'server': os.getenv('MT5_SERVER', ''),
    'timeout': 60000,
    'portable': False,
    'path': '',  # MT5 installation path (if needed)
}

# Data Configuration
DATA_CONFIG = {
    'default_timeframe': 'H1',
    'lookback_days': 90,
    'min_data_points': 100,
}

# Logging
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '[%(levelname)s] %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'simple',
            'stream': 'ext://sys.stdout'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'encoding': 'utf-8',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': str(LOG_DIR / 'trading.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'encoding': 'utf-8',
            'level': 'ERROR',
            'formatter': 'detailed',
            'filename': str(LOG_DIR / 'errors.log'),
            'maxBytes': 10485760,
            'backupCount': 5
        }
    },
    'loggers': {
        '': {  # Root logger
            'level': 'DEBUG',
            'handlers': ['console', 'file', 'error_file']
        }
    }
}

# Application settings
APP_CONFIG = {
    'version': '2.0.0',
    'name': 'Pair Trading System - Professional',
    'update_interval': 1000,  # ms for UI updates
    'save_state_interval': 300,  # seconds
    'check_connection_interval': 10,  # seconds
}

# Import instruments and risk limits (if they exist)
try:
    from .instruments import INSTRUMENTS
except ImportError:
    # Define basic instruments if not found
    INSTRUMENTS = {
        'XAUUSD': {
            'symbol': 'XAUUSD',
            'description': 'Gold vs US Dollar',
            'contract_size': 100.0,
            'min_lot': 0.01,
            'max_lot': 100.0,
            'lot_step': 0.01,
            'digits': 2,
        },
        'XAGUSD': {
            'symbol': 'XAGUSD',
            'description': 'Silver vs US Dollar',
            'contract_size': 5000.0,
            'min_lot': 0.01,
            'max_lot': 100.0,
            'lot_step': 0.01,
            'digits': 3,
        },
        'NAS100.r': {
            'symbol': 'NAS100.r',
            'description': 'Nasdaq 100 Index',
            'contract_size': 1.0,
            'min_lot': 0.01,
            'max_lot': 100.0,
            'lot_step': 0.01,
            'digits': 2,
        },
        'SP500.r': {
            'symbol': 'SP500.r',
            'description': 'S&P 500 Index',
            'contract_size': 1.0,
            'min_lot': 0.01,
            'max_lot': 100.0,
            'lot_step': 0.01,
            'digits': 2,
        },
    }

try:
    from .risk_limits import RISK_LIMITS
except ImportError:
    # Define basic risk limits if not found
    RISK_LIMITS = {
        'max_position_size': 10.0,  # lots
        'max_daily_loss': 5000.0,  # USD
        'max_drawdown': 0.20,  # 20%
        'max_positions': 10,
    }

# ============================================================
# NEW CONFIG (YAML-based, for GUI)
# ============================================================

try:
    from .settings import get_config, ConfigManager, PairConfig, SymbolConfig
    __all__ = [
        # Old exports (backward compatible)
        'MT5_CONFIG', 'DATA_CONFIG', 'LOGGING_CONFIG', 'APP_CONFIG',
        'INSTRUMENTS', 'RISK_LIMITS',
        'BASE_DIR', 'DATA_DIR', 'LOG_DIR', 'STATE_DIR', 'HISTORY_DIR', 'POSITION_DIR',
        # New exports (for GUI)
        'get_config', 'ConfigManager', 'PairConfig', 'SymbolConfig'
    ]
except ImportError:
    # If new config system not available, only export old
    __all__ = [
        'MT5_CONFIG', 'DATA_CONFIG', 'LOGGING_CONFIG', 'APP_CONFIG',
        'INSTRUMENTS', 'RISK_LIMITS',
        'BASE_DIR', 'DATA_DIR', 'LOG_DIR', 'STATE_DIR', 'HISTORY_DIR', 'POSITION_DIR',
    ]

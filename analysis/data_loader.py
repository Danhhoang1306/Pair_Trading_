"""
Data Loader Module
Fetch historical data from MT5 with caching
Uses MT5Manager singleton for connection
"""

from core.mt5_manager import get_mt5_manager
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import pickle
import logging

logger = logging.getLogger(__name__)


class MT5DataLoader:
    """
    Load historical data from MT5
    Uses MT5Manager singleton - NO separate connection
    Includes caching to avoid repeated downloads
    """

    def __init__(self, cache_dir="analysis_cache/"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.connected = False
        self.mt5_manager = get_mt5_manager()
        self.mt5 = None

    def connect(self):
        """Connect to MT5 (using MT5Manager singleton)"""
        try:
            # Initialize MT5Manager if not already done
            if not self.mt5_manager.is_initialized:
                if not self.mt5_manager.initialize():
                    logger.error("MT5 initialization failed via MT5Manager")
                    return False

            # Check connection
            if not self.mt5_manager.is_connected():
                logger.error("MT5Manager not connected")
                return False

            # Get MT5 instance
            self.mt5 = self.mt5_manager.mt5
            self.connected = True
            logger.info("✓ MT5 connected for analysis")
            return True

        except Exception as e:
            logger.error(f"MT5 connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from MT5 (actually does nothing - MT5Manager handles connection)"""
        # Don't shutdown MT5 - MT5Manager owns the connection
        self.connected = False
        logger.info("MT5 disconnected")
    
    def get_available_symbols(self):
        """
        Get all available symbols from MT5
        
        Returns:
            list: Symbol names
        """
        if not self.connected:
            if not self.connect():
                return []
        
        try:
            symbols = self.mt5.symbols_get()
            if symbols is None:
                logger.error("Failed to get symbols")
                return []
            
            # Filter visible symbols only
            symbol_names = [s.name for s in symbols if s.visible]
            logger.info(f"Found {len(symbol_names)} symbols")
            return symbol_names
            
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
            return []
    
    def load_historical_data(self, symbol, timeframe=None,
                            start_date=None, end_date=None, bars=None,
                            use_cache=True):
        """
        Load historical data for a symbol
        
        Args:
            symbol: Symbol name (e.g., 'BTCUSD')
            timeframe: MT5 timeframe constant (default H1)
            start_date: Start date (datetime or string)
            end_date: End date (datetime or string)
            bars: Number of bars (if not using dates)
            use_cache: Use cached data if available
            
        Returns:
            pd.DataFrame: OHLCV data with index as datetime
        """
        # Check cache first
        # Set default timeframe if not specified
        if timeframe is None:
            if self.mt5 is None:
                if not self.connect():
                    logger.error("Cannot load data - MT5 not connected")
                    return pd.DataFrame()
            timeframe = self.mt5.TIMEFRAME_H1  # Default to H1

        if use_cache:
            cached_data = self._load_from_cache(symbol, timeframe, start_date, end_date, bars)
            if cached_data is not None:
                logger.info(f"Loaded {symbol} from cache ({len(cached_data)} bars)")
                return cached_data

        # Connect if not connected
        if not self.connected:
            if not self.connect():
                logger.error("Cannot load data - MT5 not connected")
                return pd.DataFrame()

        try:
            # Fetch data
            if bars is not None:
                # Get last N bars
                rates = self.mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
            else:
                # Get data between dates
                if isinstance(start_date, str):
                    start_date = datetime.strptime(start_date, '%Y-%m-%d')
                if isinstance(end_date, str):
                    end_date = datetime.strptime(end_date, '%Y-%m-%d')
                
                if start_date is None:
                    start_date = datetime.now() - timedelta(days=365)
                if end_date is None:
                    end_date = datetime.now()
                
                rates = self.mt5.copy_rates_range(symbol, timeframe, start_date, end_date)
            
            if rates is None or len(rates) == 0:
                logger.warning(f"No data received for {symbol}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Save to cache
            if use_cache:
                self._save_to_cache(symbol, timeframe, start_date, end_date, bars, df)
            
            logger.info(f"Loaded {symbol}: {len(df)} bars from {df.index[0]} to {df.index[-1]}")
            return df
            
        except Exception as e:
            logger.error(f"Error loading data for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_symbol_info(self, symbol):
        """
        Get symbol information
        
        Args:
            symbol: Symbol name
            
        Returns:
            dict: Symbol info
        """
        if not self.connected:
            if not self.connect():
                return {}
        
        try:
            info = self.mt5.symbol_info(symbol)
            if info is None:
                return {}
            
            return {
                'name': info.name,
                'description': info.description,
                'point': info.point,
                'digits': info.digits,
                'spread': info.spread,
                'volume_min': info.volume_min,
                'volume_max': info.volume_max,
                'visible': info.visible,
                'trade_mode': info.trade_mode
            }
            
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return {}
    
    def _get_cache_key(self, symbol, timeframe, start_date, end_date, bars):
        """Generate cache key"""
        if bars is not None:
            key = f"{symbol}_{timeframe}_bars{bars}"
        else:
            # Handle both string and datetime objects
            if isinstance(start_date, str):
                start_str = start_date.replace('-', '')
            elif start_date:
                start_str = start_date.strftime('%Y%m%d')
            else:
                start_str = 'none'
            
            if isinstance(end_date, str):
                end_str = end_date.replace('-', '')
            elif end_date:
                end_str = end_date.strftime('%Y%m%d')
            else:
                end_str = 'none'
            
            key = f"{symbol}_{timeframe}_{start_str}_{end_str}"
        return key
    
    def _load_from_cache(self, symbol, timeframe, start_date, end_date, bars):
        """Load data from cache if available and fresh"""
        try:
            cache_key = self._get_cache_key(symbol, timeframe, start_date, end_date, bars)
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            
            if not cache_file.exists():
                return None
            
            # Check if cache is too old (> 24 hours)
            file_age = datetime.now().timestamp() - cache_file.stat().st_mtime
            if file_age > 86400:  # 24 hours
                logger.info(f"Cache expired for {symbol}")
                return None
            
            # Load from cache
            with open(cache_file, 'rb') as f:
                df = pickle.load(f)
            
            return df
            
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None
    
    def _save_to_cache(self, symbol, timeframe, start_date, end_date, bars, df):
        """Save data to cache"""
        try:
            cache_key = self._get_cache_key(symbol, timeframe, start_date, end_date, bars)
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            
            with open(cache_file, 'wb') as f:
                pickle.dump(df, f)
            
            logger.debug(f"Saved {symbol} to cache")
            
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def clear_cache(self):
        """Clear all cached data"""
        try:
            count = 0
            for cache_file in self.cache_dir.glob("*.pkl"):
                cache_file.unlink()
                count += 1
            logger.info(f"Cleared {count} cache files")
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
    
    def __del__(self):
        """Auto-cleanup on deletion"""
        self.disconnect()

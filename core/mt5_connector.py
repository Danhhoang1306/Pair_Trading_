"""
MT5 Connection and Data Handler
Full-featured data fetching with customizable parameters

DEPRECATED: This connector is kept for backwards compatibility only.
Recommend using MT5Manager + get_mt5() for new code.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Optional, Tuple, List, Dict, Union
from enum import Enum
from config import MT5_CONFIG, INSTRUMENTS, DATA_CONFIG
from core.mt5_manager import get_mt5, get_mt5_manager

logger = logging.getLogger(__name__)

# Get MT5 constants after import
def _get_mt5_constants():
    """Get MT5 constants dynamically"""
    try:
        mt5 = get_mt5()
        return {
            'M1': mt5.TIMEFRAME_M1,
            'M2': mt5.TIMEFRAME_M2,
            'M3': mt5.TIMEFRAME_M3,
            'M4': mt5.TIMEFRAME_M4,
            'M5': mt5.TIMEFRAME_M5,
            'M6': mt5.TIMEFRAME_M6,
            'M10': mt5.TIMEFRAME_M10,
            'M12': mt5.TIMEFRAME_M12,
            'M15': mt5.TIMEFRAME_M15,
            'M20': mt5.TIMEFRAME_M20,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H2': mt5.TIMEFRAME_H2,
            'H3': mt5.TIMEFRAME_H3,
            'H4': mt5.TIMEFRAME_H4,
            'H6': mt5.TIMEFRAME_H6,
            'H8': mt5.TIMEFRAME_H8,
            'H12': mt5.TIMEFRAME_H12,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }
    except:
        return {}

class TimeFrame(Enum):
    """Available timeframes - Values loaded dynamically"""
    M1 = 1
    M2 = 2
    M3 = 3
    M4 = 4
    M5 = 5
    M6 = 6
    M10 = 10
    M12 = 12
    M15 = 15
    M20 = 20
    M30 = 30
    H1 = 16385
    H2 = 16386
    H3 = 16387
    H4 = 16388
    H6 = 16390
    H8 = 16392
    H12 = 16396
    D1 = 16408
    W1 = 32769
    MN1 = 49153


class PriceType(Enum):
    """Price types for data fetching"""
    BID = 'bid'
    ASK = 'ask'
    LAST = 'last'
    MID = 'mid'  # (bid + ask) / 2


class MT5Connector:
    """
    Comprehensive MT5 connection and data handler
    
    Features:
    - Multiple timeframes support
    - Flexible date range queries
    - Bid/Ask/Last price selection
    - Data validation and cleaning
    - Resampling capabilities
    - Cache management
    """
    
    def __init__(self,
                 primary_symbol: Optional[str] = None,
                 secondary_symbol: Optional[str] = None,
                 default_timeframe: str = 'H1',
                 use_cache: bool = True,
                 cache_duration: int = 300):  # seconds
        """
        Initialize MT5 connector

        Args:
            primary_symbol: Primary symbol (default: XAUUSD)
            secondary_symbol: Secondary symbol (default: XAGUSD)
            default_timeframe: Default timeframe (M1, M5, H1, etc.)
            use_cache: Enable data caching
            cache_duration: Cache duration in seconds
        """
        self.initialized = False
        # Use provided symbols or fallback to XAUUSD/XAGUSD
        self.primary_symbol = primary_symbol or 'BTCUSD'
        self.secondary_symbol = secondary_symbol or 'ETHUSD'
        self.default_timeframe = self._parse_timeframe(default_timeframe)
        self.account_info = None

        # MT5 instance
        self.mt5 = None

        # Cache settings
        self.use_cache = use_cache
        self.cache_duration = cache_duration
        self._cache: Dict[str, Dict] = {}

        # Symbol info cache
        self._symbol_info: Dict[str, any] = {}
        
    def _parse_timeframe(self, tf: Union[str, int, TimeFrame]) -> int:
        """
        Parse timeframe to MT5 constant
        
        Args:
            tf: Timeframe as string, int, or TimeFrame enum
            
        Returns:
            MT5 timeframe constant
        """
        if isinstance(tf, TimeFrame):
            return tf.value
        
        if isinstance(tf, int):
            return tf
        
        if isinstance(tf, str):
            tf = tf.upper()
            try:
                return TimeFrame[tf].value
            except KeyError:
                logger.warning(f"Unknown timeframe {tf}, using H1")
                return TimeFrame.H1.value
        
        return TimeFrame.H1.value
    
    def initialize(self,
                   login: Optional[int] = None,
                   password: Optional[str] = None,
                   server: Optional[str] = None,
                   path: Optional[str] = None) -> bool:
        """
        Initialize MT5 connection

        DEPRECATED: Use MT5Manager instead
        This method now delegates to MT5Manager for compatibility

        Args:
            login: MT5 account number (default from config)
            password: MT5 password (default from config)
            server: MT5 server (default from config)
            path: MT5 terminal path (optional)

        Returns:
            True if successful
        """
        try:
            # Use MT5Manager singleton
            mt5_mgr = get_mt5_manager()
            if not mt5_mgr.is_initialized:
                if not mt5_mgr.initialize(login, password, server, path):
                    return False

            # Get MT5 instance
            self.mt5 = mt5_mgr.mt5

            # Get account info
            self.account_info = self.mt5.account_info()
            if self.account_info is None:
                logger.error("Failed to get account info")
                return False

            # Get terminal info
            terminal_info = self.mt5.terminal_info()
            if terminal_info:
                logger.info(f"Terminal: {terminal_info.name} | Build: {terminal_info.build}")

            # Check and enable symbols
            if not self._check_and_enable_symbols([self.primary_symbol, self.secondary_symbol]):
                return False

            self.initialized = True
            logger.info(f"[OK] MT5 Connected | Account: {self.account_info.login} | "
                       f"Server: {self.account_info.server} | "
                       f"Balance: ${self.account_info.balance:.2f} | "
                       f"Leverage: 1:{self.account_info.leverage}")
            return True

        except Exception as e:
            logger.error(f"Error initializing MT5: {e}")
            return False
    
    def _check_and_enable_symbols(self, symbols: List[str]) -> bool:
        """
        Check and enable required symbols
        
        Args:
            symbols: List of symbol names
            
        Returns:
            True if all symbols are available
        """
        for symbol in symbols:
            # Check if symbol exists
            symbol_info = self.mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"Symbol {symbol} not found")
                # Try to show all available symbols
                all_symbols = self.mt5.symbols_get()
                if all_symbols:
                    similar = [s.name for s in all_symbols if symbol.lower() in s.name.lower()]
                    if similar:
                        logger.info(f"Similar symbols found: {similar[:5]}")
                return False
            
            # Enable symbol if not visible
            if not symbol_info.visible:
                if not self.mt5.symbol_select(symbol, True):
                    logger.error(f"Failed to enable symbol {symbol}")
                    return False
            
            # Cache symbol info
            self._symbol_info[symbol] = symbol_info
            
            logger.info(f"[OK] Symbol: {symbol} | Digits: {symbol_info.digits} | "
                       f"Spread: {symbol_info.spread} | "
                       f"Trade Mode: {symbol_info.trade_mode}")
        
        return True
    
    def get_symbol_info(self, symbol: str) -> Optional[any]:
        """
        Get detailed symbol information
        
        Args:
            symbol: Symbol name
            
        Returns:
            Symbol info object or None
        """
        if symbol in self._symbol_info:
            return self._symbol_info[symbol]
        
        info = self.mt5.symbol_info(symbol)
        if info:
            self._symbol_info[symbol] = info
        return info
    
    def shutdown(self):
        """Shutdown MT5 connection and clear cache"""
        if self.initialized:
            # Don't shutdown - MT5Manager handles this
            pass
            self.initialized = False
            self._cache.clear()
            self._symbol_info.clear()
            logger.info("MT5 connection closed")
    
    def is_connected(self) -> bool:
        """
        Check if MT5 is connected and responsive
        
        Returns:
            True if connected
        """
        if not self.initialized:
            return False
        
        try:
            # Try to get account info
            info = self.mt5.account_info()
            return info is not None
        except:
            return False
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect to MT5
        
        Returns:
            True if reconnection successful
        """
        logger.info("Attempting to reconnect to MT5...")
        self.shutdown()
        return self.initialize()
    
    # ========================================
    # DATA FETCHING METHODS
    # ========================================
    
    def get_bars(self,
                 symbol: str,
                 timeframe: Union[str, int, TimeFrame] = None,
                 count: int = None,
                 start_date: datetime = None,
                 end_date: datetime = None,
                 price_type: Union[str, PriceType] = PriceType.BID,
                 validate: bool = True,
                 fill_gaps: bool = False) -> Optional[pd.DataFrame]:
        """
        Get OHLCV bars with flexible parameters
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe (default: self.default_timeframe)
            count: Number of bars (if start_date not provided)
            start_date: Start datetime
            end_date: End datetime (default: now)
            price_type: BID, ASK, LAST, or MID
            validate: Validate data quality
            fill_gaps: Fill missing data gaps
            
        Returns:
            DataFrame with columns: time, open, high, low, close, tick_volume, spread, real_volume
            
        Example:
            # Get last 500 H1 bars
            df = connector.get_bars('XAUUSD', 'H1', count=500)
            
            # Get specific date range
            df = connector.get_bars('XAUUSD', 'H1', 
                                   start_date=datetime(2024, 1, 1),
                                   end_date=datetime(2024, 12, 31))
        """
        if not self.initialized:
            logger.error("MT5 not initialized")
            return None
        
        # Parse timeframe
        tf = self._parse_timeframe(timeframe) if timeframe else self.default_timeframe
        
        # Parse price type
        if isinstance(price_type, str):
            try:
                price_type = PriceType[price_type.upper()]
            except KeyError:
                price_type = PriceType.BID
        
        # Check cache
        cache_key = f"{symbol}_{tf}_{count}_{start_date}_{end_date}_{price_type.value}"
        if self.use_cache and cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if (datetime.now() - cache_entry['timestamp']).seconds < self.cache_duration:
                logger.debug(f"Using cached data for {symbol}")
                return cache_entry['data'].copy()
        
        try:
            # Fetch data based on method
            if start_date is not None:
                # Date range method
                if end_date is None:
                    end_date = datetime.now()
                rates = self.mt5.copy_rates_range(symbol, tf, start_date, end_date)
            else:
                # Count method (from current)
                if count is None:
                    count = DATA_CONFIG.get('bars_to_load', 500)
                rates = self.mt5.copy_rates_from_pos(symbol, tf, 0, count)
            
            if rates is None or len(rates) == 0:
                error = self.mt5.last_error()
                logger.error(f"No data received for {symbol}: {error}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            
            # Adjust for price type
            if price_type == PriceType.ASK:
                # Add spread to bid prices
                symbol_info = self.get_symbol_info(symbol)
                if symbol_info:
                    point = symbol_info.point
                    df['open'] += df['spread'] * point
                    df['high'] += df['spread'] * point
                    df['low'] += df['spread'] * point
                    df['close'] += df['spread'] * point
            
            elif price_type == PriceType.MID:
                # Calculate mid price
                symbol_info = self.get_symbol_info(symbol)
                if symbol_info:
                    point = symbol_info.point
                    spread_value = df['spread'] * point / 2
                    df['open'] += spread_value
                    df['high'] += spread_value
                    df['low'] += spread_value
                    df['close'] += spread_value
            
            # Validate data
            if validate:
                df = self._validate_data(df, symbol)
            
            # Fill gaps
            if fill_gaps:
                df = self._fill_gaps(df)
            
            # Cache data
            if self.use_cache:
                self._cache[cache_key] = {
                    'data': df.copy(),
                    'timestamp': datetime.now()
                }
            
            logger.debug(f"Loaded {len(df)} bars for {symbol} ({timeframe})")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def get_current_tick(self, symbol: str) -> Optional[Dict]:
        """
        Get current tick data
        
        Args:
            symbol: Symbol name
            
        Returns:
            Dict with tick data: time, bid, ask, last, volume
        """
        try:
            tick = self.mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            return {
                'time': datetime.fromtimestamp(tick.time),
                'bid': tick.bid,
                'ask': tick.ask,
                'last': tick.last,
                'volume': tick.volume,
                'spread': tick.ask - tick.bid,
                'flags': tick.flags
            }
        except Exception as e:
            logger.error(f"Error getting tick for {symbol}: {e}")
            return None
    
    def get_current_prices(self, 
                          price_type: Union[str, PriceType] = PriceType.BID) -> Optional[Tuple[float, float]]:
        """
        Get current prices for primary and secondary
        
        Args:
            price_type: BID, ASK, LAST, or MID
            
        Returns:
            Tuple of (primary_price, secondary_price) or None
        """
        try:
            # Parse price type
            if isinstance(price_type, str):
                try:
                    price_type = PriceType[price_type.upper()]
                except KeyError:
                    price_type = PriceType.BID
            
            primary_tick = self.mt5.symbol_info_tick(self.primary_symbol)
            secondary_tick = self.mt5.symbol_info_tick(self.secondary_symbol)
            
            if primary_tick is None or secondary_tick is None:
                logger.error("Failed to get current prices")
                return None
            
            # Get price based on type
            if price_type == PriceType.BID:
                primary_price = primary_tick.bid
                secondary_price = secondary_tick.bid
            elif price_type == PriceType.ASK:
                primary_price = primary_tick.ask
                secondary_price = secondary_tick.ask
            elif price_type == PriceType.LAST:
                primary_price = primary_tick.last
                secondary_price = secondary_tick.last
            else:  # MID
                primary_price = (primary_tick.bid + primary_tick.ask) / 2
                secondary_price = (secondary_tick.bid + secondary_tick.ask) / 2
            
            return (primary_price, secondary_price)
            
        except Exception as e:
            logger.error(f"Error getting current prices: {e}")
            return None
    
    def get_pair_data(self,
                     timeframe: Union[str, int, TimeFrame] = None,
                     count: int = None,
                     start_date: datetime = None,
                     end_date: datetime = None,
                     price_type: Union[str, PriceType] = PriceType.BID,
                     align_timestamps: bool = True) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Get synchronized data for both primary and secondary
        
        Args:
            timeframe: Timeframe
            count: Number of bars
            start_date: Start datetime
            end_date: End datetime
            price_type: Price type
            align_timestamps: Ensure timestamps are aligned
            
        Returns:
            Tuple of (primary_df, secondary_df) or None
        """
        # Get data for both symbols
        primary_df = self.get_bars(self.primary_symbol, timeframe, count, 
                               start_date, end_date, price_type)
        secondary_df = self.get_bars(self.secondary_symbol, timeframe, count, 
                                 start_date, end_date, price_type)
        
        if primary_df is None or secondary_df is None:
            return None
        
        # Align timestamps if requested
        if align_timestamps:
            primary_df, secondary_df = self._align_dataframes(primary_df, secondary_df)
        
        logger.info(f"Loaded pair data: primary={len(primary_df)} bars, secondary={len(secondary_df)} bars")
        return (primary_df, secondary_df)
    
    def get_ticks(self,
                  symbol: str,
                  start_date: datetime,
                  end_date: datetime = None,
                  flags: int = None) -> Optional[pd.DataFrame]:
        """
        Get tick data (for detailed analysis)
        
        Args:
            symbol: Symbol name
            start_date: Start datetime
            end_date: End datetime (default: now)
            flags: COPY_TICKS_ALL, COPY_TICKS_INFO, COPY_TICKS_TRADE
            
        Returns:
            DataFrame with tick data
        """
        try:
            if end_date is None:
                end_date = datetime.now()
            
            ticks = self.mt5.copy_ticks_range(symbol, start_date, end_date, flags)
            
            if ticks is None or len(ticks) == 0:
                logger.error(f"No tick data for {symbol}")
                return None
            
            df = pd.DataFrame(ticks)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df['time_msc'] = pd.to_datetime(df['time_msc'], unit='ms')
            
            logger.debug(f"Loaded {len(df)} ticks for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching ticks for {symbol}: {e}")
            return None
    
    # ========================================
    # DATA PROCESSING METHODS
    # ========================================
    
    def _validate_data(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Validate and clean data
        
        Args:
            df: DataFrame to validate
            symbol: Symbol name
            
        Returns:
            Cleaned DataFrame
        """
        original_len = len(df)
        
        # Remove rows with zero/negative prices
        df = df[(df['open'] > 0) & (df['high'] > 0) & 
                (df['low'] > 0) & (df['close'] > 0)]
        
        # Check OHLC consistency
        df = df[(df['high'] >= df['low']) & 
                (df['high'] >= df['open']) & 
                (df['high'] >= df['close']) &
                (df['low'] <= df['open']) & 
                (df['low'] <= df['close'])]
        
        # Remove extreme outliers (>20% move in one bar - adjust as needed)
        df['returns'] = df['close'].pct_change()
        df = df[abs(df['returns']) < 0.20]
        df = df.drop('returns', axis=1)
        
        # Check for duplicate timestamps
        df = df.drop_duplicates(subset=['time'], keep='last')
        
        # Sort by time
        df = df.sort_values('time').reset_index(drop=True)
        
        removed = original_len - len(df)
        if removed > 0:
            logger.warning(f"Removed {removed} invalid bars from {symbol} data")
        
        return df
    
    def _fill_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Fill missing data gaps with forward fill
        
        Args:
            df: DataFrame with potential gaps
            
        Returns:
            DataFrame with filled gaps
        """
        # Set time as index
        df = df.set_index('time')
        
        # Forward fill missing values
        df = df.fillna(method='ffill')
        
        # Reset index
        df = df.reset_index()
        
        return df
    
    def _align_dataframes(self, df1: pd.DataFrame, df2: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Align two dataframes by timestamp
        
        Args:
            df1: First DataFrame
            df2: Second DataFrame
            
        Returns:
            Tuple of aligned DataFrames
        """
        # Merge on time and keep only matching timestamps
        merged = df1.merge(df2[['time']], on='time', how='inner')
        df1_aligned = merged
        
        merged = df2.merge(df1[['time']], on='time', how='inner')
        df2_aligned = merged
        
        return (df1_aligned, df2_aligned)
    
    def resample_data(self, 
                     df: pd.DataFrame, 
                     target_timeframe: str) -> pd.DataFrame:
        """
        Resample data to different timeframe
        
        Args:
            df: DataFrame with OHLCV data
            target_timeframe: Target timeframe (e.g., '5T', '1H', '1D')
            
        Returns:
            Resampled DataFrame
        """
        df = df.set_index('time')
        
        resampled = df.resample(target_timeframe).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'tick_volume': 'sum',
            'spread': 'mean',
            'real_volume': 'sum'
        })
        
        resampled = resampled.dropna()
        resampled = resampled.reset_index()
        
        return resampled
    
    def clear_cache(self):
        """Clear data cache"""
        self._cache.clear()
        logger.info("Data cache cleared")
    
    # ========================================
    # UTILITY METHODS
    # ========================================
    
    def get_available_symbols(self, search: str = '') -> List[str]:
        """
        Get list of available symbols
        
        Args:
            search: Search string (case-insensitive)
            
        Returns:
            List of symbol names
        """
        symbols = self.mt5.symbols_get()
        if symbols is None:
            return []
        
        if search:
            symbols = [s for s in symbols if search.upper() in s.name.upper()]
        
        return [s.name for s in symbols]
    
    def print_account_info(self):
        """Print detailed account information"""
        if not self.account_info:
            logger.error("No account info available")
            return
        
        info = self.account_info
        print("\n" + "="*60)
        print("ACCOUNT INFORMATION")
        print("="*60)
        print(f"Login:          {info.login}")
        print(f"Server:         {info.server}")
        print(f"Currency:       {info.currency}")
        print(f"Balance:        ${info.balance:,.2f}")
        print(f"Equity:         ${info.equity:,.2f}")
        print(f"Margin:         ${info.margin:,.2f}")
        print(f"Free Margin:    ${info.margin_free:,.2f}")
        print(f"Margin Level:   {info.margin_level:.2f}%")
        print(f"Leverage:       1:{info.leverage}")
        print(f"Profit:         ${info.profit:,.2f}")
        print("="*60 + "\n")
    
    def __enter__(self):
        """Context manager entry"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.shutdown()
    
    def __repr__(self):
        """String representation"""
        status = "Connected" if self.is_connected() else "Disconnected"
        return f"MT5Connector(status={status}, primary={self.primary_symbol}, secondary={self.secondary_symbol})"

"""
Data Manager - High-level data fetching and management
Simplifies data operations with automatic validation and caching
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
import logging
from pathlib import Path
import pickle

from core.mt5_connector import MT5Connector, TimeFrame, PriceType
from config import DATA_CONFIG, INSTRUMENTS

logger = logging.getLogger(__name__)


class DataManager:
    """
    High-level data manager for pair trading
    
    Features:
    - Simple API for fetching pair data
    - Automatic timestamp synchronization
    - Data validation
    - Intelligent caching
    - Missing data handling
    - Quality checks
    """
    
    def __init__(self,
                 primary_symbol: str = None,
                 secondary_symbol: str = None,
                 default_timeframe: str = 'H1',
                 cache_dir: str = 'data/cache',
                 enable_cache: bool = True):
        """
        Initialize Data Manager
        
        Args:
            primary_symbol: Primary symbol (default: XAUUSD)
            secondary_symbol: Secondary symbol (default: XAGUSD)
            default_timeframe: Default timeframe
            cache_dir: Directory for caching data
            enable_cache: Enable file-based caching
        """
        # Use provided symbols or fallback to XAUUSD/XAGUSD
        # Note: In runtime, these will be overridden by TradingSystem
        self.primary_symbol = primary_symbol or 'XAUUSD'
        self.secondary_symbol = secondary_symbol or 'XAGUSD'
        self.default_timeframe = default_timeframe
        self.enable_cache = enable_cache
        
        # Setup cache directory
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # MT5 Connector
        self.connector = None
        self._connector_initialized = False
        
        # Data quality metrics
        self.last_quality_check = None
        
    def _ensure_connected(self):
        """Ensure MT5 connector is initialized"""
        if not self._connector_initialized:
            self.connector = MT5Connector(
                primary_symbol=self.primary_symbol,
                secondary_symbol=self.secondary_symbol,
                default_timeframe=self.default_timeframe,
                use_cache=True  # Use MT5 connector's cache
            )
            
            if not self.connector.initialize():
                raise ConnectionError("Failed to initialize MT5 connection")
            
            self._connector_initialized = True
            logger.info("[OK] Data Manager connected to MT5")
    
    def get_pair_data(self,
                     timeframe: str = None,
                     days: int = None,
                     count: int = None,
                     start_date: datetime = None,
                     end_date: datetime = None,
                     price_type: str = 'MID',
                     validate: bool = True,
                     use_cache: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Get synchronized pair data (Primary & secondary)
        
        Args:
            timeframe: Timeframe (M5, M15, H1, H4, D1)
            days: Number of days of history (alternative to count)
            count: Number of bars (alternative to days)
            start_date: Start date (alternative to days/count)
            end_date: End date (if using start_date)
            price_type: BID, ASK, MID, LAST
            validate: Validate data quality
            use_cache: Use cached data if available
            
        Returns:
            Tuple of (primary_df, secondary_df) with aligned timestamps
            
        Example:
            # Get last 30 days of H1 data
            primary_df, secondary_df = manager.get_pair_data(days=30)
            
            # Get last 500 H1 bars
            primary_df, secondary_df = manager.get_pair_data(count=500)
            
            # Get specific date range
            primary_df, secondary_df = manager.get_pair_data(
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 12, 31)
            )
        """
        # Ensure connection
        self._ensure_connected()
        
        # Use default timeframe if not specified
        if timeframe is None:
            timeframe = self.default_timeframe
        
        # Calculate count from days if specified
        if days is not None and count is None:
            count = self._days_to_bars(days, timeframe)
            logger.debug(f"Converting {days} days to ~{count} bars")
        
        # Generate cache key
        cache_key = self._generate_cache_key(
            timeframe, count, start_date, end_date, price_type
        )
        
        # Try to load from cache
        if use_cache and self.enable_cache:
            cached_data = self._load_from_cache(cache_key)
            if cached_data is not None:
                logger.info(f"[OK] Loaded pair data from cache ({timeframe})")
                return cached_data
        
        # Fetch fresh data
        logger.info(f"Fetching pair data: {timeframe}, count={count}, days={days}")
        
        result = self.connector.get_pair_data(
            timeframe=timeframe,
            count=count,
            start_date=start_date,
            end_date=end_date,
            price_type=price_type,
            align_timestamps=True
        )
        
        if result is None:
            raise ValueError("Failed to fetch pair data from MT5")
        
        primary_df, secondary_df = result
        
        # Validate data
        if validate:
            self._validate_pair_data(primary_df, secondary_df)
        
        # Add metadata
        primary_df = self._add_metadata(primary_df, self.primary_symbol, timeframe)
        secondary_df = self._add_metadata(secondary_df, self.secondary_symbol, timeframe)
        
        # Cache data
        if self.enable_cache:
            self._save_to_cache(cache_key, (primary_df, secondary_df))
        
        logger.info(f"[OK] Fetched {len(primary_df)} bars for pair ({timeframe})")
        return primary_df, secondary_df
    
    def get_single_data(self,
                       symbol: str = None,
                       timeframe: str = None,
                       days: int = None,
                       count: int = None,
                       price_type: str = 'MID',
                       validate: bool = True) -> pd.DataFrame:
        """
        Get data for single symbol
        
        Args:
            symbol: Symbol name (default: primary_symbol)
            timeframe: Timeframe
            days: Number of days
            count: Number of bars
            price_type: Price type
            validate: Validate data
            
        Returns:
            DataFrame with OHLCV data
        """
        self._ensure_connected()
        
        if symbol is None:
            symbol = self.primary_symbol
        
        if timeframe is None:
            timeframe = self.default_timeframe
        
        if days is not None and count is None:
            count = self._days_to_bars(days, timeframe)
        
        df = self.connector.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            count=count,
            price_type=price_type,
            validate=validate
        )
        
        if df is None:
            raise ValueError(f"Failed to fetch data for {symbol}")
        
        df = self._add_metadata(df, symbol, timeframe)
        
        logger.info(f"[OK] Fetched {len(df)} bars for {symbol} ({timeframe})")
        return df
    
    def get_current_prices(self, 
                          price_type: str = 'MID') -> Dict[str, float]:
        """
        Get current prices for both symbols
        
        Args:
            price_type: BID, ASK, MID, LAST
            
        Returns:
            Dict with 'primary' and 'secondary' prices
            
        Example:
            prices = manager.get_current_prices()
            print(f"Primary: {prices['primary']}, Secondary: {prices['secondary']}")
        """
        self._ensure_connected()
        
        result = self.connector.get_current_prices(price_type=price_type)
        
        if result is None:
            raise ValueError("Failed to get current prices")
        
        primary_price, secondary_price = result
        
        return {
            'primary': primary_price,
            'secondary': secondary_price,
            'timestamp': datetime.now(),
            'price_type': price_type
        }
    
    def refresh_data(self,
                    timeframe: str = None,
                    days: int = None,
                    price_type: str = 'MID') -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Refresh data from MT5 (bypass cache)
        
        Args:
            timeframe: Timeframe
            days: Number of days
            price_type: Price type
            
        Returns:
            Fresh pair data
        """
        logger.info("Refreshing data from MT5 (bypass cache)")
        return self.get_pair_data(
            timeframe=timeframe,
            days=days,
            price_type=price_type,
            use_cache=False
        )
    
    def clear_cache(self):
        """Clear all cached data"""
        if self.cache_dir.exists():
            for file in self.cache_dir.glob('*.pkl'):
                file.unlink()
            logger.info("[OK] Cache cleared")
    
    def get_data_quality(self, 
                        primary_df: pd.DataFrame,
                        secondary_df: pd.DataFrame) -> Dict:
        """
        Get data quality metrics
        
        Args:
            primary_df: Primary dataframe
            secondary_df: Secondary dataframe
            
        Returns:
            Dict with quality metrics
        """
        quality = {
            'primary_bars': len(primary_df),
            'secondary_bars': len(secondary_df),
            'aligned': len(primary_df) == len(secondary_df),
            'primary_missing': primary_df.isnull().sum().sum(),
            'secondary_missing': secondary_df.isnull().sum().sum(),
            'timestamp_match': (primary_df['time'] == secondary_df['time']).all() if len(primary_df) == len(secondary_df) else False,
            'date_range': {
                'start': primary_df['time'].min(),
                'end': primary_df['time'].max(),
                'days': (primary_df['time'].max() - primary_df['time'].min()).days
            },
            'primary_price_range': {
                'min': primary_df['close'].min(),
                'max': primary_df['close'].max(),
                'mean': primary_df['close'].mean()
            },
            'secondary_price_range': {
                'min': secondary_df['close'].min(),
                'max': secondary_df['close'].max(),
                'mean': secondary_df['close'].mean()
            }
        }
        
        # Calculate quality score (0-100)
        score = 100
        if not quality['aligned']:
            score -= 20
        if quality['primary_missing'] > 0:
            score -= 10
        if quality['secondary_missing'] > 0:
            score -= 10
        if not quality['timestamp_match']:
            score -= 20
        
        quality['quality_score'] = max(0, score)
        
        self.last_quality_check = quality
        return quality
    
    def print_data_summary(self,
                          primary_df: pd.DataFrame,
                          secondary_df: pd.DataFrame):
        """
        Print formatted data summary
        
        Args:
            primary_df: Primary dataframe
            secondary_df: Secondary dataframe
        """
        quality = self.get_data_quality(primary_df, secondary_df)
        
        print("\n" + "="*70)
        print("DATA SUMMARY")
        print("="*70)
        
        print(f"\n[DATA] Data Size:")
        print(f"  Primary:   {quality['primary_bars']} bars")
        print(f"  Secondary: {quality['secondary_bars']} bars")
        print(f"  Aligned: {'[OK]' if quality['aligned'] else '[X]'}")
        
        print(f"\n📅 Date Range:")
        print(f"  Start: {quality['date_range']['start']}")
        print(f"  End:   {quality['date_range']['end']}")
        print(f"  Days:  {quality['date_range']['days']}")
        
        print(f"\n[USD] Price Range (Close):")
        print(f"  Primary:   ${quality['primary_price_range']['min']:.2f} - ${quality['primary_price_range']['max']:.2f}")
        print(f"  Secondary: ${quality['secondary_price_range']['min']:.4f} - ${quality['secondary_price_range']['max']:.4f}")
        
        print(f"\n[UP] Data Quality:")
        print(f"  Missing values (primary):   {quality['primary_missing']}")
        print(f"  Missing values (secondary): {quality['secondary_missing']}")
        print(f"  Timestamp aligned: {'[OK]' if quality['timestamp_match'] else '[X]'}")
        print(f"  Quality Score: {quality['quality_score']}/100")
        
        if quality['quality_score'] >= 90:
            print(f"  Status: [DONE] EXCELLENT")
        elif quality['quality_score'] >= 70:
            print(f"  Status: [OK] GOOD")
        elif quality['quality_score'] >= 50:
            print(f"  Status: [WARN] ACCEPTABLE")
        else:
            print(f"  Status: [FAIL] POOR")
        
        print("="*70 + "\n")
    
    # ========================================
    # PRIVATE METHODS
    # ========================================
    
    def _days_to_bars(self, days: int, timeframe: str) -> int:
        """
        Convert days to approximate number of bars
        
        Args:
            days: Number of days
            timeframe: Timeframe string
            
        Returns:
            Approximate number of bars
        """
        # Bars per day (approximate, accounting for weekends/holidays)
        bars_per_day = {
            'M1': 1440 * 0.7,   # 70% uptime
            'M5': 288 * 0.7,
            'M15': 96 * 0.7,
            'M30': 48 * 0.7,
            'H1': 24 * 0.7,
            'H4': 6 * 0.7,
            'D1': 1 * 0.7
        }
        
        bars = int(days * bars_per_day.get(timeframe, 24))
        return max(bars, 10)  # Minimum 10 bars
    
    def _validate_pair_data(self,
                           primary_df: pd.DataFrame,
                           secondary_df: pd.DataFrame):
        """
        Validate pair data quality
        
        Args:
            primary_df: Primary dataframe
            secondary_df: Secondary dataframe
            
        Raises:
            ValueError: If data quality is insufficient
        """
        # Check if dataframes are empty
        if len(primary_df) == 0 or len(secondary_df) == 0:
            raise ValueError("One or both dataframes are empty")
        
        # Check if lengths match
        if len(primary_df) != len(secondary_df):
            logger.warning(f"Length mismatch: primary={len(primary_df)}, secondary={len(secondary_df)}")
        
        # Check for minimum data (flexible for different pairs)
        min_bars = DATA_CONFIG.get('min_bars_required', 30)
        
        # If we got very few bars, it might be a weekend/holiday or new pair
        # Reduce requirement to be more flexible
        if len(primary_df) < 30:
            min_bars = max(7, min(len(primary_df), 10))  # At least 7 bars
            logger.warning(f"Limited data available ({len(primary_df)} bars), "
                         f"using reduced minimum ({min_bars} bars)")
        
        if len(primary_df) < min_bars:
            raise ValueError(f"Insufficient data: {len(primary_df)} bars (minimum: {min_bars})")
        
        # Check for missing values
        primary_missing = primary_df.isnull().sum().sum()
        secondary_missing = secondary_df.isnull().sum().sum()
        
        if primary_missing > 0:
            logger.warning(f"Primary data has {primary_missing} missing values")
        if secondary_missing > 0:
            logger.warning(f"Secondary data has {secondary_missing} missing values")
        
        # Check timestamp alignment
        if len(primary_df) == len(secondary_df):
            if not (primary_df['time'] == secondary_df['time']).all():
                logger.warning("Timestamps are not perfectly aligned")
        
        logger.debug("[OK] Data validation passed")
    
    def _add_metadata(self,
                     df: pd.DataFrame,
                     symbol: str,
                     timeframe: str) -> pd.DataFrame:
        """
        Add metadata columns to dataframe
        
        Args:
            df: Dataframe
            symbol: Symbol name
            timeframe: Timeframe
            
        Returns:
            Dataframe with metadata
        """
        df = df.copy()
        df.attrs['symbol'] = symbol
        df.attrs['timeframe'] = timeframe
        df.attrs['fetched_at'] = datetime.now()
        return df
    
    def _generate_cache_key(self,
                           timeframe: str,
                           count: Optional[int],
                           start_date: Optional[datetime],
                           end_date: Optional[datetime],
                           price_type: str) -> str:
        """
        Generate cache key for data
        
        Args:
            timeframe: Timeframe
            count: Bar count
            start_date: Start date
            end_date: End date
            price_type: Price type
            
        Returns:
            Cache key string
        """
        parts = [
            'pair',
            self.primary_symbol,
            self.secondary_symbol,
            timeframe,
            price_type
        ]
        
        if count is not None:
            parts.append(f'count_{count}')
        if start_date is not None:
            parts.append(start_date.strftime('%Y%m%d'))
        if end_date is not None:
            parts.append(end_date.strftime('%Y%m%d'))
        
        return '_'.join(parts) + '.pkl'
    
    def _save_to_cache(self, cache_key: str, data: Tuple[pd.DataFrame, pd.DataFrame]):
        """
        Save data to cache
        
        Args:
            cache_key: Cache key
            data: Tuple of dataframes
        """
        try:
            cache_path = self.cache_dir / cache_key
            with open(cache_path, 'wb') as f:
                pickle.dump({
                    'data': data,
                    'timestamp': datetime.now(),
                    'version': '1.0'
                }, f)
            logger.debug(f"[OK] Saved to cache: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _load_from_cache(self, cache_key: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Load data from cache
        
        Args:
            cache_key: Cache key
            
        Returns:
            Cached data or None
        """
        try:
            cache_path = self.cache_dir / cache_key
            
            if not cache_path.exists():
                return None
            
            # Check cache age
            cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
            max_age = timedelta(hours=DATA_CONFIG.get('cache_max_age_hours', 24))
            
            if cache_age > max_age:
                logger.debug(f"Cache expired: {cache_key}")
                return None
            
            with open(cache_path, 'rb') as f:
                cached = pickle.load(f)
            
            logger.debug(f"[OK] Loaded from cache: {cache_key} (age: {cache_age})")
            return cached['data']
            
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None
    
    def __enter__(self):
        """Context manager entry"""
        self._ensure_connected()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.connector:
            self.connector.shutdown()
            self._connector_initialized = False
    
    def __repr__(self):
        """String representation"""
        status = "Connected" if self._connector_initialized else "Disconnected"
        return f"DataManager(status={status}, symbols={self.primary_symbol}/{self.secondary_symbol})"

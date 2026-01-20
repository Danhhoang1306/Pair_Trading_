"""
Data Preprocessor - Clean, normalize, and prepare data for analysis
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, List
import logging
from scipy import stats

logger = logging.getLogger(__name__)


class DataPreprocessor:
    """
    Data preprocessing and cleaning
    
    Features:
    - Outlier detection and removal
    - Missing data handling
    - Data normalization
    - Return calculation
    - Statistical transformations
    """
    
    def __init__(self,
                 outlier_method: str = 'iqr',
                 outlier_threshold: float = 3.0,
                 fill_method: str = 'ffill'):
        """
        Initialize Data Preprocessor
        
        Args:
            outlier_method: Method for outlier detection ('iqr', 'zscore', 'mad')
            outlier_threshold: Threshold for outlier detection
            fill_method: Method for filling missing values ('ffill', 'bfill', 'interpolate')
        """
        self.outlier_method = outlier_method
        self.outlier_threshold = outlier_threshold
        self.fill_method = fill_method
        
        self.preprocessing_stats = {}
    
    def preprocess_pair(self,
                       primary_df: pd.DataFrame,
                       secondary_df: pd.DataFrame,
                       remove_outliers: bool = True,
                       fill_missing: bool = True,
                       add_returns: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Preprocess pair data (main method)
        
        Args:
            primary_df: primary dataframe
            secondary_df: secondary dataframe
            remove_outliers: Remove outliers
            fill_missing: Fill missing values
            add_returns: Add return columns
            
        Returns:
            Tuple of cleaned (primary_df, secondary_df)
            
        Example:
            processor = DataPreprocessor()
            primary_clean, secondary_clean = processor.preprocess_pair(primary_df, secondary_df)
        """
        logger.info("Preprocessing pair data...")
        
        # Make copies
        primary_df = primary_df.copy()
        secondary_df = secondary_df.copy()
        
        # Store original length
        original_len = len(primary_df)
        
        # 1. Fill missing values
        if fill_missing:
            primary_df = self.fill_missing_values(primary_df)
            secondary_df = self.fill_missing_values(secondary_df)
        
        # 2. Remove outliers
        if remove_outliers:
            primary_df, secondary_df = self.remove_outliers_pair(primary_df, secondary_df)
        
        # 3. Re-align after outlier removal
        primary_df, secondary_df = self._align_dataframes(primary_df, secondary_df)
        
        # 4. Add returns
        if add_returns:
            primary_df = self.add_returns(primary_df)
            secondary_df = self.add_returns(secondary_df)
        
        # 5. Sort by time
        primary_df = primary_df.sort_values('time').reset_index(drop=True)
        secondary_df = secondary_df.sort_values('time').reset_index(drop=True)
        
        # Store stats
        removed = original_len - len(primary_df)
        self.preprocessing_stats = {
            'original_length': original_len,
            'final_length': len(primary_df),
            'removed_bars': removed,
            'removal_rate': removed / original_len if original_len > 0 else 0
        }
        
        logger.info(f"[OK] Preprocessing complete: {original_len} -> {len(primary_df)} bars ({removed} removed)")
        
        return primary_df, secondary_df
    
    def fill_missing_values(self,
                           df: pd.DataFrame,
                           method: str = None) -> pd.DataFrame:
        """
        Fill missing values in dataframe
        
        Args:
            df: Dataframe with potential missing values
            method: Fill method ('ffill', 'bfill', 'interpolate', None=use default)
            
        Returns:
            Dataframe with filled values
        """
        if method is None:
            method = self.fill_method
        
        df = df.copy()
        missing_before = df.isnull().sum().sum()
        
        if missing_before == 0:
            return df
        
        if method == 'ffill':
            # Forward fill
            df = df.fillna(method='ffill')
            # Backward fill any remaining
            df = df.fillna(method='bfill')
            
        elif method == 'bfill':
            # Backward fill
            df = df.fillna(method='bfill')
            # Forward fill any remaining
            df = df.fillna(method='ffill')
            
        elif method == 'interpolate':
            # Linear interpolation for OHLC
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].interpolate(method='linear')
            # Fill any remaining with forward fill
            df = df.fillna(method='ffill').fillna(method='bfill')
        
        missing_after = df.isnull().sum().sum()
        
        if missing_before > 0:
            logger.debug(f"Filled {missing_before - missing_after} missing values using {method}")
        
        return df
    
    def remove_outliers_pair(self,
                            primary_df: pd.DataFrame,
                            secondary_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Remove outliers from pair data (synchronized removal)
        
        Args:
            primary_df: primary dataframe
            secondary_df: secondary dataframe
            
        Returns:
            Tuple of cleaned dataframes
        """
        primary_df = primary_df.copy()
        secondary_df = secondary_df.copy()
        
        # Detect outliers in both
        primary_mask = self.detect_outliers(primary_df['close'])
        secondary_mask = self.detect_outliers(secondary_df['close'])
        
        # Combine masks (remove if outlier in either)
        combined_mask = ~(primary_mask | secondary_mask)
        
        # Apply mask
        primary_df = primary_df[combined_mask].reset_index(drop=True)
        secondary_df = secondary_df[combined_mask].reset_index(drop=True)
        
        outliers_removed = (~combined_mask).sum()
        if outliers_removed > 0:
            logger.debug(f"Removed {outliers_removed} outlier bars from pair")
        
        return primary_df, secondary_df
    
    def detect_outliers(self,
                       series: pd.Series,
                       method: str = None) -> pd.Series:
        """
        Detect outliers in a series
        
        Args:
            series: Data series
            method: Detection method ('iqr', 'zscore', 'mad')
            
        Returns:
            Boolean series (True = outlier)
        """
        if method is None:
            method = self.outlier_method
        
        if method == 'iqr':
            # Interquartile Range method
            Q1 = series.quantile(0.25)
            Q3 = series.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - self.outlier_threshold * IQR
            upper_bound = Q3 + self.outlier_threshold * IQR
            outliers = (series < lower_bound) | (series > upper_bound)
            
        elif method == 'zscore':
            # Z-score method
            z_scores = np.abs(stats.zscore(series, nan_policy='omit'))
            outliers = z_scores > self.outlier_threshold
            
        elif method == 'mad':
            # Median Absolute Deviation method
            median = series.median()
            mad = np.median(np.abs(series - median))
            modified_z_scores = 0.6745 * (series - median) / mad
            outliers = np.abs(modified_z_scores) > self.outlier_threshold
            
        else:
            raise ValueError(f"Unknown outlier detection method: {method}")
        
        return outliers
    
    def add_returns(self,
                   df: pd.DataFrame,
                   price_col: str = 'close',
                   log_returns: bool = True) -> pd.DataFrame:
        """
        Add return columns to dataframe
        
        Args:
            df: Dataframe
            price_col: Column to calculate returns from
            log_returns: Use log returns (True) or simple returns (False)
            
        Returns:
            Dataframe with return columns added
        """
        df = df.copy()
        
        if log_returns:
            # Log returns: ln(P_t / P_t-1)
            df['returns'] = np.log(df[price_col] / df[price_col].shift(1))
        else:
            # Simple returns: (P_t - P_t-1) / P_t-1
            df['returns'] = df[price_col].pct_change()
        
        # Remove infinite values
        df['returns'] = df['returns'].replace([np.inf, -np.inf], np.nan)
        
        # Forward fill first NaN (from shift/pct_change)
        df['returns'] = df['returns'].bfill()  # Use bfill() instead of fillna(method='bfill')
        
        return df
    
    def normalize_prices(self,
                        df: pd.DataFrame,
                        method: str = 'zscore',
                        columns: List[str] = None) -> pd.DataFrame:
        """
        Normalize price columns
        
        Args:
            df: Dataframe
            method: Normalization method ('zscore', 'minmax', 'robust')
            columns: Columns to normalize (default: OHLC)
            
        Returns:
            Dataframe with normalized columns (suffix: _norm)
        """
        if columns is None:
            columns = ['open', 'high', 'low', 'close']
        
        df = df.copy()
        
        for col in columns:
            if col not in df.columns:
                continue
            
            if method == 'zscore':
                # Z-score normalization: (x - mean) / std
                mean = df[col].mean()
                std = df[col].std()
                df[f'{col}_norm'] = (df[col] - mean) / std
                
            elif method == 'minmax':
                # Min-max normalization: (x - min) / (max - min)
                min_val = df[col].min()
                max_val = df[col].max()
                df[f'{col}_norm'] = (df[col] - min_val) / (max_val - min_val)
                
            elif method == 'robust':
                # Robust normalization: (x - median) / IQR
                median = df[col].median()
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                df[f'{col}_norm'] = (df[col] - median) / IQR
        
        return df
    
    def add_rolling_stats(self,
                         df: pd.DataFrame,
                         windows: List[int] = [20, 50],
                         columns: List[str] = ['close']) -> pd.DataFrame:
        """
        Add rolling statistics
        
        Args:
            df: Dataframe
            windows: Window sizes for rolling calculations
            columns: Columns to calculate stats for
            
        Returns:
            Dataframe with rolling statistics
        """
        df = df.copy()
        
        for col in columns:
            if col not in df.columns:
                continue
            
            for window in windows:
                # Rolling mean
                df[f'{col}_ma{window}'] = df[col].rolling(window=window).mean()
                
                # Rolling std
                df[f'{col}_std{window}'] = df[col].rolling(window=window).std()
                
                # Rolling min/max
                df[f'{col}_min{window}'] = df[col].rolling(window=window).min()
                df[f'{col}_max{window}'] = df[col].rolling(window=window).max()
        
        return df
    
    def remove_first_n_bars(self,
                           primary_df: pd.DataFrame,
                           secondary_df: pd.DataFrame,
                           n: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Remove first N bars (useful after adding indicators that need warmup)
        
        Args:
            primary_df: primary dataframe
            secondary_df: secondary dataframe
            n: Number of bars to remove
            
        Returns:
            Tuple of dataframes with first N bars removed
        """
        if n <= 0:
            return primary_df, secondary_df
        
        primary_df = primary_df.iloc[n:].reset_index(drop=True)
        secondary_df = secondary_df.iloc[n:].reset_index(drop=True)
        
        logger.debug(f"Removed first {n} bars (warmup period)")
        return primary_df, secondary_df
    
    def check_stationarity(self,
                          series: pd.Series,
                          max_diff: int = 2) -> Dict:
        """
        Check if series is stationary (quick check using variance ratio)
        
        Args:
            series: Data series
            max_diff: Maximum differencing to try
            
        Returns:
            Dict with stationarity info
        """
        from scipy import stats as scipy_stats
        
        result = {
            'original_stationary': False,
            'differences_needed': None,
            'final_variance': None
        }
        
        # Simple variance ratio test
        # Stationary series should have relatively stable variance
        rolling_var = series.rolling(window=min(50, len(series)//4)).var()
        var_ratio = rolling_var.max() / rolling_var.min() if rolling_var.min() > 0 else np.inf
        
        if var_ratio < 5:  # Arbitrary threshold
            result['original_stationary'] = True
            result['differences_needed'] = 0
            result['final_variance'] = series.var()
            return result
        
        # Try differencing
        diff_series = series
        for d in range(1, max_diff + 1):
            diff_series = diff_series.diff().dropna()
            rolling_var = diff_series.rolling(window=min(50, len(diff_series)//4)).var()
            var_ratio = rolling_var.max() / rolling_var.min() if rolling_var.min() > 0 else np.inf
            
            if var_ratio < 5:
                result['differences_needed'] = d
                result['final_variance'] = diff_series.var()
                break
        
        return result
    
    def get_preprocessing_summary(self) -> Dict:
        """
        Get summary of preprocessing operations
        
        Returns:
            Dict with preprocessing statistics
        """
        return self.preprocessing_stats.copy() if self.preprocessing_stats else {}
    
    def print_preprocessing_summary(self):
        """Print formatted preprocessing summary"""
        if not self.preprocessing_stats:
            print("No preprocessing performed yet")
            return
        
        stats = self.preprocessing_stats
        
        print("\n" + "="*60)
        print("PREPROCESSING SUMMARY")
        print("="*60)
        print(f"Original bars:     {stats['original_length']}")
        print(f"Final bars:        {stats['final_length']}")
        print(f"Removed:           {stats['removed_bars']} ({stats['removal_rate']*100:.2f}%)")
        print("="*60 + "\n")
    
    # ========================================
    # PRIVATE METHODS
    # ========================================
    
    def _align_dataframes(self,
                         df1: pd.DataFrame,
                         df2: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Align two dataframes by timestamp
        
        Args:
            df1: First dataframe
            df2: Second dataframe
            
        Returns:
            Tuple of aligned dataframes
        """
        if len(df1) == 0 or len(df2) == 0:
            return df1, df2
        
        # Merge on time and keep only matching timestamps
        merged1 = df1.merge(df2[['time']], on='time', how='inner')
        merged2 = df2.merge(df1[['time']], on='time', how='inner')
        
        return merged1, merged2
    
    def __repr__(self):
        """String representation"""
        return (f"DataPreprocessor(outlier_method={self.outlier_method}, "
                f"threshold={self.outlier_threshold}, fill_method={self.fill_method})")

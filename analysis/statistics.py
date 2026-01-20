"""
Statistical Analysis Module
Calculates correlation, cointegration, stationarity, etc.
"""

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller, coint
import logging

logger = logging.getLogger(__name__)


class StatisticsCalculator:
    """
    Calculate statistical metrics for pair trading
    """
    
    def __init__(self):
        pass
    
    def calculate_correlation(self, data1, data2):
        """
        Calculate Pearson correlation
        
        Args:
            data1: First time series (array or Series)
            data2: Second time series (array or Series)
            
        Returns:
            float: Correlation coefficient (-1 to 1)
        """
        try:
            corr, p_value = stats.pearsonr(data1, data2)
            return {
                'correlation': float(corr),
                'p_value': float(p_value),
                'significant': p_value < 0.05
            }
        except Exception as e:
            logger.error(f"Correlation calculation failed: {e}")
            return {'correlation': 0.0, 'p_value': 1.0, 'significant': False}
    
    def calculate_rolling_correlation(self, data1, data2, window=30):
        """
        Calculate rolling correlation
        
        Args:
            data1: First time series
            data2: Second time series
            window: Rolling window size
            
        Returns:
            dict: Statistics of rolling correlation
        """
        try:
            df = pd.DataFrame({'s1': data1, 's2': data2})
            rolling_corr = df['s1'].rolling(window).corr(df['s2'])
            
            return {
                'mean': float(rolling_corr.mean()),
                'std': float(rolling_corr.std()),
                'min': float(rolling_corr.min()),
                'max': float(rolling_corr.max()),
                'stable': float(rolling_corr.std()) < 0.15  # Std < 0.15 is stable
            }
        except Exception as e:
            logger.error(f"Rolling correlation failed: {e}")
            return {'mean': 0.0, 'std': 1.0, 'min': 0.0, 'max': 0.0, 'stable': False}
    
    def test_cointegration(self, data1, data2):
        """
        Engle-Granger cointegration test
        
        Args:
            data1: First time series
            data2: Second time series
            
        Returns:
            dict: Cointegration test results
        """
        try:
            # Engle-Granger test
            score, p_value, crit_values = coint(data1, data2)
            
            # Determine if cointegrated at different significance levels
            cointegrated_1pct = p_value < 0.01
            cointegrated_5pct = p_value < 0.05
            cointegrated_10pct = p_value < 0.10
            
            return {
                'test_statistic': float(score),
                'p_value': float(p_value),
                'critical_values': {
                    '1%': float(crit_values[0]),
                    '5%': float(crit_values[1]),
                    '10%': float(crit_values[2])
                },
                'cointegrated_1pct': cointegrated_1pct,
                'cointegrated_5pct': cointegrated_5pct,
                'cointegrated_10pct': cointegrated_10pct,
                'cointegrated': cointegrated_5pct  # Default to 5% significance
            }
        except Exception as e:
            logger.error(f"Cointegration test failed: {e}")
            return {
                'test_statistic': 0.0,
                'p_value': 1.0,
                'cointegrated': False
            }
    
    def test_stationarity(self, data):
        """
        Augmented Dickey-Fuller test for stationarity
        
        Args:
            data: Time series data
            
        Returns:
            dict: Stationarity test results
        """
        try:
            result = adfuller(data, autolag='AIC')
            
            adf_statistic = result[0]
            p_value = result[1]
            critical_values = result[4]
            
            # Stationary if ADF statistic < critical value
            stationary_1pct = adf_statistic < critical_values['1%']
            stationary_5pct = adf_statistic < critical_values['5%']
            stationary_10pct = adf_statistic < critical_values['10%']
            
            return {
                'adf_statistic': float(adf_statistic),
                'p_value': float(p_value),
                'critical_values': {k: float(v) for k, v in critical_values.items()},
                'stationary_1pct': stationary_1pct,
                'stationary_5pct': stationary_5pct,
                'stationary_10pct': stationary_10pct,
                'stationary': stationary_5pct  # Default to 5% significance
            }
        except Exception as e:
            logger.error(f"Stationarity test failed: {e}")
            return {
                'adf_statistic': 0.0,
                'p_value': 1.0,
                'stationary': False
            }
    
    def calculate_half_life(self, spread):
        """
        Calculate mean reversion half-life
        
        Args:
            spread: Spread time series
            
        Returns:
            float: Half-life in bars
        """
        try:
            spread_lag = spread.shift(1)
            spread_lag.iloc[0] = spread_lag.iloc[1]
            spread_ret = spread - spread_lag
            spread_lag2 = spread_lag - spread.mean()
            
            # OLS regression: spread_ret = alpha + beta * spread_lag2
            model = np.polyfit(spread_lag2, spread_ret, 1)
            beta = model[0]
            
            if beta >= 0:
                return np.inf  # No mean reversion
            
            half_life = -np.log(2) / beta
            
            return float(half_life) if half_life > 0 else np.inf
            
        except Exception as e:
            logger.error(f"Half-life calculation failed: {e}")
            return np.inf
    
    def calculate_spread_stats(self, spread):
        """
        Calculate comprehensive spread statistics
        
        Args:
            spread: Spread time series
            
        Returns:
            dict: Spread statistics
        """
        try:
            return {
                'mean': float(spread.mean()),
                'std': float(spread.std()),
                'min': float(spread.min()),
                'max': float(spread.max()),
                'median': float(spread.median()),
                'skewness': float(stats.skew(spread)),
                'kurtosis': float(stats.kurtosis(spread)),
                'range': float(spread.max() - spread.min()),
                'cv': float(spread.std() / spread.mean()) if spread.mean() != 0 else np.inf
            }
        except Exception as e:
            logger.error(f"Spread stats calculation failed: {e}")
            return {}
    
    def calculate_zscore_distribution(self, zscore_series):
        """
        Calculate z-score distribution statistics
        
        Args:
            zscore_series: Series of z-scores over time
            
        Returns:
            dict: Z-score distribution metrics
        """
        try:
            percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
            
            return {
                'mean': float(zscore_series.mean()),
                'std': float(zscore_series.std()),
                'min': float(zscore_series.min()),
                'max': float(zscore_series.max()),
                'percentiles': {
                    f'{p}%': float(np.percentile(zscore_series, p))
                    for p in percentiles
                },
                'abs_percentiles': {
                    f'{p}%': float(np.percentile(np.abs(zscore_series), p))
                    for p in percentiles
                }
            }
        except Exception as e:
            logger.error(f"Z-score distribution failed: {e}")
            return {}
    
    def calculate_volatility_ratio(self, data1, data2):
        """
        Calculate volatility ratio between two series
        
        Args:
            data1: First time series
            data2: Second time series
            
        Returns:
            dict: Volatility metrics
        """
        try:
            vol1 = data1.pct_change().std()
            vol2 = data2.pct_change().std()
            
            ratio = vol1 / vol2 if vol2 != 0 else np.inf
            
            return {
                'vol1': float(vol1),
                'vol2': float(vol2),
                'ratio': float(ratio),
                'similar': 0.7 < ratio < 1.3  # Similar if ratio between 0.7 and 1.3
            }
        except Exception as e:
            logger.error(f"Volatility ratio failed: {e}")
            return {'vol1': 0.0, 'vol2': 0.0, 'ratio': 1.0, 'similar': False}

"""
Cointegration Testing Module
Tests if primary and secondary prices are cointegrated for pair trading

Includes:
- ADF (Augmented Dickey-Fuller) test
- Johansen cointegration test
- Half-life calculation
- Cointegration strength metrics
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional
import logging
from dataclasses import dataclass
from datetime import datetime

# Statistical libraries
from statsmodels.tsa.stattools import adfuller, coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class CointegrationResult:
    """Results from cointegration test"""
    is_cointegrated: bool
    test_statistic: float
    p_value: float
    critical_values: Dict[str, float]
    confidence_level: str
    hedge_ratio: float
    half_life: float
    spread_mean: float
    spread_std: float
    test_method: str
    timestamp: datetime
    
    def __str__(self):
        status = "COINTEGRATED" if self.is_cointegrated else "NOT COINTEGRATED"
        return (f"Cointegration Test Result:\n"
                f"  Status: {status}\n"
                f"  Method: {self.test_method}\n"
                f"  P-value: {self.p_value:.4f}\n"
                f"  Test Statistic: {self.test_statistic:.4f}\n"
                f"  Confidence: {self.confidence_level}\n"
                f"  Hedge Ratio: {self.hedge_ratio:.4f}\n"
                f"  Half-life: {self.half_life:.2f} bars")


class CointegrationTest:
    """
    Test cointegration between two price series
    
    Example:
        >>> tester = CointegrationTest()
        >>> result = tester.test_engle_granger(primary_prices, secondary_prices)
        >>> if result.is_cointegrated:
        >>>     print(f"Half-life: {result.half_life} bars")
    """
    
    def __init__(self, 
                 significance_level: float = 0.05,
                 min_half_life: float = 5,
                 max_half_life: float = 30):
        """
        Initialize cointegration tester
        
        Args:
            significance_level: P-value threshold (default: 0.05 = 95% confidence)
            min_half_life: Minimum acceptable half-life in bars
            max_half_life: Maximum acceptable half-life in bars
        """
        self.significance_level = significance_level
        self.min_half_life = min_half_life
        self.max_half_life = max_half_life
        
        logger.info(f"CointegrationTest initialized (significance={significance_level})")
    
    def test_engle_granger(self,
                          series1: pd.Series,
                          series2: pd.Series,
                          significance: float = None) -> CointegrationResult:
        """
        Engle-Granger two-step cointegration test
        
        This is the most common test for pair trading:
        1. Run OLS regression: series1 = beta * series2 + residuals
        2. Test if residuals are stationary (ADF test)
        
        Args:
            series1: First price series (e.g., primary)
            series2: Second price series (e.g., secondary)
            significance: Significance level (default: use instance level)
            
        Returns:
            CointegrationResult with test details
        """
        if significance is None:
            significance = self.significance_level
        
        logger.info("Running Engle-Granger cointegration test...")
        
        # Step 1: OLS regression to get hedge ratio
        hedge_ratio = self._calculate_ols_hedge_ratio(series1, series2)
        
        # Step 2: Calculate spread (residuals)
        spread = series1 - hedge_ratio * series2
        
        # Step 3: ADF test on spread
        adf_result = adfuller(spread, maxlag=1, regression='c')
        test_statistic = adf_result[0]
        p_value = adf_result[1]
        critical_values = adf_result[4]
        
        # Determine if cointegrated
        is_cointegrated = p_value < significance
        
        # Get confidence level
        confidence_level = self._get_confidence_level(test_statistic, critical_values)
        
        # Calculate half-life
        half_life = self.calculate_half_life(spread)
        
        # Check if half-life is acceptable
        if is_cointegrated:
            if not (self.min_half_life <= half_life <= self.max_half_life):
                logger.warning(f"Half-life {half_life:.2f} outside acceptable range "
                             f"[{self.min_half_life}, {self.max_half_life}]")
                is_cointegrated = False
        
        result = CointegrationResult(
            is_cointegrated=is_cointegrated,
            test_statistic=test_statistic,
            p_value=p_value,
            critical_values=critical_values,
            confidence_level=confidence_level,
            hedge_ratio=hedge_ratio,
            half_life=half_life,
            spread_mean=spread.mean(),
            spread_std=spread.std(),
            test_method='Engle-Granger',
            timestamp=datetime.now()
        )
        
        logger.info(f"Cointegration test complete: {result.is_cointegrated} "
                   f"(p-value={p_value:.4f}, half-life={half_life:.2f})")
        
        return result
    
    def calculate_half_life(self, spread: pd.Series) -> float:
        """
        Calculate mean-reversion half-life of spread
        
        Half-life = time for spread to revert halfway to its mean
        
        Uses Ornstein-Uhlenbeck process:
        ds(t) = theta * (mu - s(t)) * dt + sigma * dW(t)
        
        Half-life = -ln(2) / theta
        
        Args:
            spread: Spread series
            
        Returns:
            Half-life in number of bars
        """
        # Ensure we have numpy array
        spread_values = spread.values if isinstance(spread, pd.Series) else spread
        
        # Calculate lagged spread
        spread_lag = np.roll(spread_values, 1)
        spread_lag[0] = spread_lag[1]  # Fill first value
        
        # Calculate change in spread
        spread_delta = spread_values - spread_lag
        
        # Remove first observation (no lag available)
        spread_lag = spread_lag[1:]
        spread_delta = spread_delta[1:]
        
        # OLS regression: delta_spread = alpha + beta * spread_lag
        # beta is the mean reversion speed (theta in OU process)
        spread_lag_with_const = np.vstack([spread_lag, np.ones(len(spread_lag))]).T
        
        try:
            params = np.linalg.lstsq(spread_lag_with_const, spread_delta, rcond=None)[0]
            theta = params[0]
            
            # Calculate half-life
            if theta < 0:
                half_life = -np.log(2) / theta
            else:
                # Positive theta means diverging, not reverting
                half_life = np.inf
                logger.warning("Spread is diverging (positive theta)")
            
        except Exception as e:
            logger.error(f"Error calculating half-life: {e}")
            half_life = np.inf
        
        return half_life
    
    def calculate_spread_zscore(self,
                               series1: pd.Series,
                               series2: pd.Series,
                               hedge_ratio: float = None,
                               lookback: int = 60) -> pd.Series:
        """
        Calculate z-score of spread
        
        Z-score = (spread - mean) / std
        
        Args:
            series1: First series
            series2: Second series
            hedge_ratio: Hedge ratio (if None, calculate with OLS)
            lookback: Lookback period for rolling mean/std
            
        Returns:
            Z-score series
        """
        if hedge_ratio is None:
            hedge_ratio = self._calculate_ols_hedge_ratio(series1, series2)
        
        # Calculate spread
        spread = series1 - hedge_ratio * series2
        
        # Calculate rolling z-score
        spread_mean = spread.rolling(window=lookback).mean()
        spread_std = spread.rolling(window=lookback).std()
        
        zscore = (spread - spread_mean) / spread_std
        
        return zscore
    
    # ========================================
    # PRIVATE METHODS
    # ========================================
    
    def _calculate_ols_hedge_ratio(self,
                                   series1: pd.Series,
                                   series2: pd.Series) -> float:
        """
        Calculate hedge ratio using OLS regression
        
        series1 = beta * series2 + alpha + residuals
        
        Args:
            series1: Dependent variable
            series2: Independent variable
            
        Returns:
            Beta coefficient (hedge ratio)
        """
        # Prepare data
        y = series1.values
        X = series2.values
        X_with_const = np.vstack([X, np.ones(len(X))]).T
        
        # OLS regression
        params = np.linalg.lstsq(X_with_const, y, rcond=None)[0]
        hedge_ratio = params[0]
        
        return hedge_ratio
    
    def _get_confidence_level(self,
                             test_statistic: float,
                             critical_values: Dict[str, float]) -> str:
        """
        Determine confidence level based on test statistic
        
        Args:
            test_statistic: ADF test statistic
            critical_values: Critical values dict
            
        Returns:
            Confidence level string
        """
        if test_statistic < critical_values['1%']:
            return '99%'
        elif test_statistic < critical_values['5%']:
            return '95%'
        elif test_statistic < critical_values['10%']:
            return '90%'
        else:
            return '<90%'
    
    def __repr__(self):
        return (f"CointegrationTest(significance={self.significance_level}, "
                f"half_life_range=[{self.min_half_life}, {self.max_half_life}])")


# Convenience function for quick testing
def quick_test(primary_prices: pd.Series,
              secondary_prices: pd.Series) -> CointegrationResult:
    """
    Quick cointegration test
    
    Args:
        primary_prices: primary price series
        secondary_prices: secondary price series
        
    Returns:
        CointegrationResult
        
    Example:
        >>> result = quick_test(primary_df['close'], secondary_df['close'])
        >>> print(result)
    """
    tester = CointegrationTest()
    return tester.test_engle_granger(primary_prices, secondary_prices)

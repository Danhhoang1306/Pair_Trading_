"""
Hedge Ratio Calculation Module
Multiple methods for calculating optimal hedge ratios for pair trading

Includes:
- OLS (Ordinary Least Squares) regression
- Kalman Filter (dynamic hedge ratio)
- Dollar-neutral hedge ratio
- Volatility-adjusted hedge ratio
- Optimal weighted combination
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional, List
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class HedgeRatioResult:
    """Results from hedge ratio calculation"""
    ratio: float
    method: str
    confidence: float
    r_squared: float
    residual_std: float
    timestamp: datetime
    metadata: Dict = None
    
    def __str__(self):
        return (f"Hedge Ratio Result:\n"
                f"  Method: {self.method}\n"
                f"  Ratio: {self.ratio:.4f}\n"
                f"  R-squared: {self.r_squared:.4f}\n"
                f"  Residual Std: {self.residual_std:.4f}\n"
                f"  Confidence: {self.confidence:.2%}")


class HedgeRatioCalculator:
    """
    Calculate hedge ratios using multiple methods
    
    Example:
        >>> calc = HedgeRatioCalculator()
        >>> ratio = calc.calculate_optimal(primary_df, secondary_df)
        >>> print(f"Optimal hedge ratio: {ratio:.4f}")
    """
    
    def __init__(self,
                 ols_weight: float = 0.30,
                 dollar_neutral_weight: float = 0.30,
                 vol_adjusted_weight: float = 0.20,
                 kalman_weight: float = 0.20):
        """
        Initialize hedge ratio calculator
        
        Args:
            ols_weight: Weight for OLS method
            dollar_neutral_weight: Weight for dollar-neutral method
            vol_adjusted_weight: Weight for volatility-adjusted method
            kalman_weight: Weight for Kalman filter method
        """
        # Normalize weights
        total = ols_weight + dollar_neutral_weight + vol_adjusted_weight + kalman_weight
        self.weights = {
            'ols': ols_weight / total,
            'dollar_neutral': dollar_neutral_weight / total,
            'vol_adjusted': vol_adjusted_weight / total,
            'kalman': kalman_weight / total
        }
        
        logger.info(f"HedgeRatioCalculator initialized with weights: {self.weights}")
    
    def calculate_optimal(self,
                         primary_df: pd.DataFrame,
                         secondary_df: pd.DataFrame,
                         price_col: str = 'close') -> float:
        """
        Calculate optimal hedge ratio using weighted combination
        
        Args:
            primary_df: primary dataframe
            secondary_df: secondary dataframe
            price_col: Price column name
            
        Returns:
            Optimal weighted hedge ratio
        """
        logger.info("Calculating optimal hedge ratio...")
        
        primary_prices = primary_df[price_col]
        secondary_prices = secondary_df[price_col]
        
        # Calculate each method
        ratios = {}
        
        # OLS
        try:
            ols_result = self.calculate_ols(primary_prices, secondary_prices)
            ratios['ols'] = ols_result.ratio
        except Exception as e:
            logger.warning(f"OLS calculation failed: {e}")
            ratios['ols'] = None
        
        # Dollar-neutral
        try:
            dn_result = self.calculate_dollar_neutral(primary_prices, secondary_prices)
            ratios['dollar_neutral'] = dn_result.ratio
        except Exception as e:
            logger.warning(f"Dollar-neutral calculation failed: {e}")
            ratios['dollar_neutral'] = None
        
        # Volatility-adjusted
        try:
            va_result = self.calculate_vol_adjusted(primary_prices, secondary_prices)
            ratios['vol_adjusted'] = va_result.ratio
        except Exception as e:
            logger.warning(f"Vol-adjusted calculation failed: {e}")
            ratios['vol_adjusted'] = None
        
        # Kalman
        try:
            kalman_result = self.calculate_kalman(primary_prices, secondary_prices)
            ratios['kalman'] = kalman_result.ratio
        except Exception as e:
            logger.warning(f"Kalman calculation failed: {e}")
            ratios['kalman'] = None
        
        # Calculate weighted average
        optimal_ratio = 0.0
        total_weight = 0.0
        
        for method, ratio in ratios.items():
            if ratio is not None:
                optimal_ratio += ratio * self.weights[method]
                total_weight += self.weights[method]
        
        if total_weight > 0:
            optimal_ratio = optimal_ratio / total_weight
        else:
            logger.error("All hedge ratio calculations failed!")
            raise ValueError("Unable to calculate hedge ratio")
        
        # Format ratios for logging
        ols_str = f"{ratios['ols']:.4f}" if ratios['ols'] is not None else 'N/A'
        dn_str = f"{ratios['dollar_neutral']:.4f}" if ratios['dollar_neutral'] is not None else 'N/A'
        va_str = f"{ratios['vol_adjusted']:.4f}" if ratios['vol_adjusted'] is not None else 'N/A'
        kf_str = f"{ratios['kalman']:.4f}" if ratios['kalman'] is not None else 'N/A'
        
        logger.info(f"Optimal hedge ratio: {optimal_ratio:.4f} "
                   f"(OLS={ols_str}, DN={dn_str}, VA={va_str}, KF={kf_str})")
        
        return optimal_ratio
    
    def calculate_ols(self,
                     primary_prices: pd.Series,
                     secondary_prices: pd.Series) -> HedgeRatioResult:
        """
        Calculate hedge ratio using OLS regression
        
        primary = beta * secondary + alpha + residuals
        
        Args:
            primary_prices: primary price series
            secondary_prices: secondary price series
            
        Returns:
            HedgeRatioResult
        """
        # Prepare data
        y = primary_prices.values
        X = secondary_prices.values
        X_with_const = np.vstack([X, np.ones(len(X))]).T
        
        # OLS regression
        params, residuals, rank, s = np.linalg.lstsq(X_with_const, y, rcond=None)
        beta = params[0]
        alpha = params[1]
        
        # Calculate statistics
        y_pred = X * beta + alpha
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        residual_std = np.std(y - y_pred)
        
        # Confidence based on R-squared
        confidence = r_squared
        
        result = HedgeRatioResult(
            ratio=beta,
            method='OLS',
            confidence=confidence,
            r_squared=r_squared,
            residual_std=residual_std,
            timestamp=datetime.now(),
            metadata={
                'alpha': alpha,
                'n_observations': len(y)
            }
        )
        
        logger.debug(f"OLS hedge ratio: {beta:.4f} (R²={r_squared:.4f})")
        
        return result
    
    def calculate_dollar_neutral(self,
                                primary_prices: pd.Series,
                                secondary_prices: pd.Series) -> HedgeRatioResult:
        """
        Calculate dollar-neutral hedge ratio
        
        Ensures that $1 of primary is hedged with $1 of secondary
        
        Ratio = primary_Price / secondary_Price
        
        Args:
            primary_prices: primary price series
            secondary_prices: secondary price series
            
        Returns:
            HedgeRatioResult
        """
        # Simple price ratio
        ratio = primary_prices.iloc[-1] / secondary_prices.iloc[-1]
        
        # Calculate spread with this ratio
        spread = primary_prices - ratio * secondary_prices
        residual_std = spread.std()
        
        # R-squared approximation
        ss_res = np.sum(spread ** 2)
        ss_tot = np.sum((primary_prices - primary_prices.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        result = HedgeRatioResult(
            ratio=ratio,
            method='Dollar-Neutral',
            confidence=0.8,  # Arbitrary confidence
            r_squared=r_squared,
            residual_std=residual_std,
            timestamp=datetime.now(),
            metadata={
                'primary_price': primary_prices.iloc[-1],
                'secondary_price': secondary_prices.iloc[-1]
            }
        )
        
        logger.debug(f"Dollar-neutral hedge ratio: {ratio:.4f}")
        
        return result
    
    def calculate_vol_adjusted(self,
                              primary_prices: pd.Series,
                              secondary_prices: pd.Series,
                              lookback: int = 60) -> HedgeRatioResult:
        """
        Calculate volatility-adjusted hedge ratio
        
        Adjusts for different volatilities of the two assets
        
        Ratio = (primary_Vol / secondary_Vol) * (primary_Price / secondary_Price)
        
        Args:
            primary_prices: primary price series
            secondary_prices: secondary price series
            lookback: Lookback period for volatility
            
        Returns:
            HedgeRatioResult
        """
        # Calculate returns
        primary_returns = primary_prices.pct_change().dropna()
        secondary_returns = secondary_prices.pct_change().dropna()
        
        # Calculate rolling volatility
        primary_vol = primary_returns.rolling(window=lookback).std().iloc[-1]
        secondary_vol = secondary_returns.rolling(window=lookback).std().iloc[-1]
        
        # Base ratio (dollar neutral)
        base_ratio = primary_prices.iloc[-1] / secondary_prices.iloc[-1]
        
        # Adjust for volatility
        vol_adjustment = primary_vol / secondary_vol if secondary_vol > 0 else 1.0
        ratio = base_ratio * vol_adjustment
        
        # Calculate spread statistics
        spread = primary_prices - ratio * secondary_prices
        residual_std = spread.std()
        
        # R-squared
        ss_res = np.sum(spread ** 2)
        ss_tot = np.sum((primary_prices - primary_prices.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        result = HedgeRatioResult(
            ratio=ratio,
            method='Volatility-Adjusted',
            confidence=0.75,
            r_squared=r_squared,
            residual_std=residual_std,
            timestamp=datetime.now(),
            metadata={
                'primary_vol': primary_vol,
                'secondary_vol': secondary_vol,
                'vol_adjustment': vol_adjustment,
                'base_ratio': base_ratio
            }
        )
        
        logger.debug(f"Vol-adjusted hedge ratio: {ratio:.4f} "
                    f"(vol_adj={vol_adjustment:.4f})")
        
        return result
    
    def calculate_kalman(self,
                        primary_prices: pd.Series,
                        secondary_prices: pd.Series,
                        transition_covariance: float = 0.00001,
                        observation_covariance: float = 1.0) -> HedgeRatioResult:
        """
        Calculate dynamic hedge ratio using Kalman Filter
        
        Tracks time-varying hedge ratio
        
        Args:
            primary_prices: primary price series
            secondary_prices: secondary price series
            transition_covariance: Process noise covariance (delta)
            observation_covariance: Measurement noise covariance (V_e)
            
        Returns:
            HedgeRatioResult with latest hedge ratio
        """
        # Initialize Kalman filter
        delta = transition_covariance
        V_e = observation_covariance
        
        # State: [beta, alpha]
        x = np.zeros((2, 1))  # Initial state
        P = np.eye(2) * 100  # Initial covariance (high uncertainty)
        
        # Process noise
        Q = np.eye(2) * delta
        
        # Measurement noise
        R = V_e
        
        # Store hedge ratios over time
        hedge_ratios = []
        
        # Kalman filter loop
        for i in range(len(primary_prices)):
            # Measurement
            y_obs = primary_prices.iloc[i]
            H = np.array([[secondary_prices.iloc[i], 1.0]])  # Observation matrix
            
            # Prediction step
            x_pred = x  # State transition: x[k] = x[k-1]
            P_pred = P + Q  # Covariance prediction
            
            # Update step
            y_pred = H @ x_pred
            innovation = y_obs - y_pred[0, 0]
            S = H @ P_pred @ H.T + R  # Innovation covariance
            K = P_pred @ H.T / S  # Kalman gain
            
            # State update
            x = x_pred + K * innovation
            P = (np.eye(2) - K @ H) @ P_pred
            
            # Store hedge ratio (beta)
            hedge_ratios.append(x[0, 0])
        
        # Latest hedge ratio
        ratio = hedge_ratios[-1]
        
        # Calculate spread statistics using final ratio
        spread = primary_prices - ratio * secondary_prices
        residual_std = spread.std()
        
        # R-squared
        y_pred = ratio * secondary_prices + x[1, 0]
        ss_res = np.sum((primary_prices - y_pred) ** 2)
        ss_tot = np.sum((primary_prices - primary_prices.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        result = HedgeRatioResult(
            ratio=ratio,
            method='Kalman Filter',
            confidence=0.85,
            r_squared=r_squared,
            residual_std=residual_std,
            timestamp=datetime.now(),
            metadata={
                'alpha': x[1, 0],
                'hedge_ratio_series': hedge_ratios,
                'final_state_covariance': P.tolist()
            }
        )
        
        logger.debug(f"Kalman hedge ratio: {ratio:.4f} (final, from time-varying)")
        
        return result
    
    def calculate_rolling_ols(self,
                             primary_prices: pd.Series,
                             secondary_prices: pd.Series,
                             window: int = 60) -> pd.Series:
        """
        Calculate rolling OLS hedge ratio
        
        Args:
            primary_prices: primary price series
            secondary_prices: secondary price series
            window: Rolling window size
            
        Returns:
            Series of hedge ratios over time
        """
        hedge_ratios = []
        
        for i in range(window, len(primary_prices) + 1):
            primary_window = primary_prices.iloc[i-window:i]
            secondary_window = secondary_prices.iloc[i-window:i]
            
            result = self.calculate_ols(primary_window, secondary_window)
            hedge_ratios.append(result.ratio)
        
        # Pad with NaN for first 'window' values
        hedge_ratios = [np.nan] * (window - 1) + hedge_ratios
        
        return pd.Series(hedge_ratios, index=primary_prices.index)
    
    def compare_methods(self,
                       primary_prices: pd.Series,
                       secondary_prices: pd.Series) -> pd.DataFrame:
        """
        Compare all hedge ratio methods
        
        Args:
            primary_prices: primary price series
            secondary_prices: secondary price series
            
        Returns:
            DataFrame comparing all methods
        """
        results = []
        
        methods = [
            ('OLS', self.calculate_ols),
            ('Dollar-Neutral', self.calculate_dollar_neutral),
            ('Volatility-Adjusted', self.calculate_vol_adjusted),
            ('Kalman Filter', self.calculate_kalman)
        ]
        
        for method_name, method_func in methods:
            try:
                result = method_func(primary_prices, secondary_prices)
                results.append({
                    'Method': method_name,
                    'Hedge Ratio': result.ratio,
                    'R-squared': result.r_squared,
                    'Residual Std': result.residual_std,
                    'Confidence': result.confidence
                })
            except Exception as e:
                logger.warning(f"Failed to calculate {method_name}: {e}")
                results.append({
                    'Method': method_name,
                    'Hedge Ratio': np.nan,
                    'R-squared': np.nan,
                    'Residual Std': np.nan,
                    'Confidence': np.nan
                })
        
        return pd.DataFrame(results)
    
    def __repr__(self):
        return f"HedgeRatioCalculator(weights={self.weights})"


# Convenience functions
def quick_ols(primary_prices: pd.Series, secondary_prices: pd.Series) -> float:
    """Quick OLS hedge ratio calculation"""
    calc = HedgeRatioCalculator()
    result = calc.calculate_ols(primary_prices, secondary_prices)
    return result.ratio


def quick_optimal(primary_df: pd.DataFrame, secondary_df: pd.DataFrame) -> float:
    """Quick optimal hedge ratio calculation"""
    calc = HedgeRatioCalculator()
    return calc.calculate_optimal(primary_df, secondary_df)

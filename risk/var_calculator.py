"""
Value at Risk (VaR) Calculator Module
Calculate VaR using multiple methods for risk management

Includes:
- Historical VaR
- Parametric VaR (Variance-Covariance)
- Monte Carlo VaR
- CVaR (Conditional VaR / Expected Shortfall)
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional
import logging
from dataclasses import dataclass
from datetime import datetime
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class VaRResult:
    """Results from VaR calculation"""
    var_value: float
    cvar_value: float
    confidence_level: float
    method: str
    currency: str
    timestamp: datetime
    metadata: Dict = None
    
    def __str__(self):
        return (f"VaR Result ({self.method}):\n"
                f"  Confidence: {self.confidence_level:.1%}\n"
                f"  VaR: {self.currency}{self.var_value:,.2f}\n"
                f"  CVaR: {self.currency}{self.cvar_value:,.2f}")


class VaRCalculator:
    """
    Calculate Value at Risk using multiple methods
    
    VaR answers: "What is the maximum loss over a given time period 
    at a given confidence level?"
    
    Example:
        >>> calc = VaRCalculator()
        >>> result = calc.calculate_historical_var(returns, confidence=0.95)
        >>> print(f"95% VaR: ${result.var_value:,.2f}")
    """
    
    def __init__(self,
                 currency: str = "USD",
                 annual_trading_days: int = 252):
        """
        Initialize VaR calculator
        
        Args:
            currency: Currency symbol for display
            annual_trading_days: Trading days per year
        """
        self.currency = currency
        self.annual_trading_days = annual_trading_days
        
        logger.info(f"VaRCalculator initialized (currency={currency})")
    
    def calculate_historical_var(self,
                                 returns: pd.Series,
                                 confidence: float = 0.95,
                                 portfolio_value: float = 100000) -> VaRResult:
        """
        Calculate Historical VaR
        
        Uses actual historical returns distribution
        
        Args:
            returns: Return series
            confidence: Confidence level (0.95 = 95%)
            portfolio_value: Portfolio value in currency
            
        Returns:
            VaRResult
        """
        logger.info(f"Calculating Historical VaR (confidence={confidence:.1%})...")
        
        returns_clean = returns.dropna()
        
        # Calculate percentile (lower tail)
        alpha = 1 - confidence
        var_percentile = returns_clean.quantile(alpha)
        
        # Convert to dollar amount
        var_dollar = abs(var_percentile * portfolio_value)
        
        # Calculate CVaR (average of all losses beyond VaR)
        tail_losses = returns_clean[returns_clean <= var_percentile]
        cvar_percentile = tail_losses.mean() if len(tail_losses) > 0 else var_percentile
        cvar_dollar = abs(cvar_percentile * portfolio_value)
        
        result = VaRResult(
            var_value=var_dollar,
            cvar_value=cvar_dollar,
            confidence_level=confidence,
            method='Historical',
            currency=self.currency,
            timestamp=datetime.now(),
            metadata={
                'var_return': var_percentile,
                'cvar_return': cvar_percentile,
                'n_observations': len(returns_clean),
                'portfolio_value': portfolio_value
            }
        )
        
        logger.debug(f"Historical VaR: {self.currency}{var_dollar:,.2f}")
        
        return result
    
    def calculate_parametric_var(self,
                                 returns: pd.Series,
                                 confidence: float = 0.95,
                                 portfolio_value: float = 100000) -> VaRResult:
        """
        Calculate Parametric VaR (assumes normal distribution)
        
        VaR = mean + z_score * std
        
        Args:
            returns: Return series
            confidence: Confidence level
            portfolio_value: Portfolio value
            
        Returns:
            VaRResult
        """
        logger.info(f"Calculating Parametric VaR (confidence={confidence:.1%})...")
        
        returns_clean = returns.dropna()
        
        # Calculate statistics
        mean_return = returns_clean.mean()
        std_return = returns_clean.std()
        
        # Get z-score
        alpha = 1 - confidence
        z_score = stats.norm.ppf(alpha)
        
        # Calculate VaR
        var_return = mean_return + z_score * std_return
        var_dollar = abs(var_return * portfolio_value)
        
        # CVaR for parametric (analytical formula)
        pdf_z = stats.norm.pdf(z_score)
        cvar_return = mean_return - std_return * (pdf_z / alpha)
        cvar_dollar = abs(cvar_return * portfolio_value)
        
        result = VaRResult(
            var_value=var_dollar,
            cvar_value=cvar_dollar,
            confidence_level=confidence,
            method='Parametric (Normal)',
            currency=self.currency,
            timestamp=datetime.now(),
            metadata={
                'var_return': var_return,
                'cvar_return': cvar_return,
                'mean_return': mean_return,
                'std_return': std_return,
                'z_score': z_score,
                'portfolio_value': portfolio_value
            }
        )
        
        logger.debug(f"Parametric VaR: {self.currency}{var_dollar:,.2f}")
        
        return result
    
    def calculate_monte_carlo_var(self,
                                  returns: pd.Series,
                                  confidence: float = 0.95,
                                  portfolio_value: float = 100000,
                                  n_simulations: int = 10000) -> VaRResult:
        """
        Calculate Monte Carlo VaR
        
        Simulates future returns using historical parameters
        
        Args:
            returns: Return series
            confidence: Confidence level
            portfolio_value: Portfolio value
            n_simulations: Number of Monte Carlo simulations
            
        Returns:
            VaRResult
        """
        logger.info(f"Calculating Monte Carlo VaR ({n_simulations} sims)...")
        
        returns_clean = returns.dropna()
        
        # Calculate statistics
        mean_return = returns_clean.mean()
        std_return = returns_clean.std()
        
        # Generate simulated returns
        simulated_returns = np.random.normal(
            loc=mean_return,
            scale=std_return,
            size=n_simulations
        )
        
        # Calculate VaR from simulations
        alpha = 1 - confidence
        var_return = np.percentile(simulated_returns, alpha * 100)
        var_dollar = abs(var_return * portfolio_value)
        
        # Calculate CVaR
        tail_losses = simulated_returns[simulated_returns <= var_return]
        cvar_return = tail_losses.mean()
        cvar_dollar = abs(cvar_return * portfolio_value)
        
        result = VaRResult(
            var_value=var_dollar,
            cvar_value=cvar_dollar,
            confidence_level=confidence,
            method='Monte Carlo',
            currency=self.currency,
            timestamp=datetime.now(),
            metadata={
                'var_return': var_return,
                'cvar_return': cvar_return,
                'n_simulations': n_simulations,
                'portfolio_value': portfolio_value
            }
        )
        
        logger.debug(f"Monte Carlo VaR: {self.currency}{var_dollar:,.2f}")
        
        return result
    
    def compare_methods(self,
                       returns: pd.Series,
                       confidence: float = 0.95,
                       portfolio_value: float = 100000) -> pd.DataFrame:
        """
        Compare all VaR methods in a DataFrame
        
        Args:
            returns: Return series
            confidence: Confidence level
            portfolio_value: Portfolio value
            
        Returns:
            DataFrame with comparison
        """
        results = {}
        
        # Historical
        try:
            results['Historical'] = self.calculate_historical_var(
                returns, confidence, portfolio_value
            )
        except Exception as e:
            logger.warning(f"Historical VaR failed: {e}")
        
        # Parametric
        try:
            results['Parametric'] = self.calculate_parametric_var(
                returns, confidence, portfolio_value
            )
        except Exception as e:
            logger.warning(f"Parametric VaR failed: {e}")
        
        # Monte Carlo
        try:
            results['Monte Carlo'] = self.calculate_monte_carlo_var(
                returns, confidence, portfolio_value
            )
        except Exception as e:
            logger.warning(f"Monte Carlo VaR failed: {e}")
        
        comparison = []
        for method, result in results.items():
            comparison.append({
                'Method': method,
                'VaR': result.var_value,
                'CVaR': result.cvar_value,
                'VaR %': (result.var_value / portfolio_value) * 100,
                'CVaR %': (result.cvar_value / portfolio_value) * 100
            })
        
        return pd.DataFrame(comparison)
    
    def __repr__(self):
        return f"VaRCalculator(currency={self.currency})"


# Convenience functions
def quick_var(returns: pd.Series,
             portfolio_value: float = 100000,
             confidence: float = 0.95) -> float:
    """Quick Historical VaR calculation"""
    calc = VaRCalculator()
    result = calc.calculate_historical_var(returns, confidence, portfolio_value)
    return result.var_value

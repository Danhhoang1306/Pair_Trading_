"""
Position Sizing Module
Calculate optimal position sizes using multiple methods

Includes:
- Kelly Criterion
- Fixed Fractional
- Volatility-based sizing
- Risk-based sizing
- Max position limits
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional, Any
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PositionSizeResult:
    """Results from position sizing calculation"""
    position_size: float
    position_units: float
    risk_amount: float
    method: str
    timestamp: datetime
    metadata: Dict = None
    
    def __str__(self):
        return (f"Position Size Result ({self.method}):\n"
                f"  Position Size: {self.position_size:.4f} (fraction of capital)\n"
                f"  Units: {self.position_units:.2f}\n"
                f"  Risk Amount: ${self.risk_amount:,.2f}")


class PositionSizer:
    """
    Calculate position sizes using multiple methods
    
    Example:
        >>> sizer = PositionSizer(account_balance=100000)
        >>> result = sizer.calculate_kelly(win_rate=0.55, avg_win=100, avg_loss=50)
        >>> print(f"Kelly size: {result.position_size:.2%}")
    """
    
    def __init__(self,
                 account_balance: float = 100000,
                 max_position_pct: float = 20.0,      # Percentage (20%)
                 max_risk_pct: float = 2.0,           # Percentage (2%)
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize position sizer
        
        Args:
            account_balance: Total account balance
            max_position_pct: Maximum position as percentage (20.0 = 20%)
            max_risk_pct: Maximum risk per trade as percentage (2.0 = 2%)
            config: Optional config dict to override params
        """
        # Extract from config if provided
        if config:
            max_position_pct = config.get('max_position_pct', max_position_pct)
            max_risk_pct = config.get('max_risk_pct', max_risk_pct)
        
        self.account_balance = account_balance
        self.max_position_pct = max_position_pct
        self.max_risk_pct = max_risk_pct
        
        # Convert to fractions for internal calculations
        self.max_position_size = max_position_pct / 100.0
        self.max_risk_per_trade = max_risk_pct / 100.0
        
        logger.info(f"PositionSizer initialized (balance=${account_balance:,.0f}, "
                   f"max_pos={max_position_pct}%, max_risk={max_risk_pct}%)")
    
    def calculate_kelly(self,
                       win_rate: float,
                       avg_win: float,
                       avg_loss: float,
                       kelly_fraction: float = 0.5) -> PositionSizeResult:
        """
        Calculate Kelly Criterion position size
        
        Kelly % = W - [(1-W) / R]
        where:
            W = win rate
            R = avg_win / avg_loss (reward/risk ratio)
        
        Args:
            win_rate: Historical win rate (0.0 to 1.0)
            avg_win: Average winning trade size
            avg_loss: Average losing trade size
            kelly_fraction: Fraction of Kelly to use (0.5 = half Kelly, more conservative)
            
        Returns:
            PositionSizeResult
        """
        logger.info(f"Calculating Kelly position (win_rate={win_rate:.2%}, "
                   f"avg_win={avg_win:.2f}, avg_loss={avg_loss:.2f})...")
        
        # Calculate reward/risk ratio
        if avg_loss <= 0:
            logger.warning("avg_loss must be positive, using absolute value")
            avg_loss = abs(avg_loss)
        
        reward_risk_ratio = avg_win / avg_loss
        
        # Kelly formula
        kelly_pct = win_rate - ((1 - win_rate) / reward_risk_ratio)
        
        # Apply Kelly fraction (conservative adjustment)
        kelly_pct = kelly_pct * kelly_fraction
        
        # Ensure non-negative
        kelly_pct = max(0, kelly_pct)
        
        # Apply max position limit
        position_size = min(kelly_pct, self.max_position_size)
        
        # Calculate position in units and risk
        position_units = (position_size * self.account_balance) / avg_win if avg_win > 0 else 0
        risk_amount = position_size * self.account_balance
        
        result = PositionSizeResult(
            position_size=position_size,
            position_units=position_units,
            risk_amount=risk_amount,
            method='Kelly Criterion',
            timestamp=datetime.now(),
            metadata={
                'kelly_full': kelly_pct / kelly_fraction if kelly_fraction > 0 else 0,
                'kelly_fraction': kelly_fraction,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'reward_risk_ratio': reward_risk_ratio,
                'capped_by_max': position_size < kelly_pct
            }
        )
        
        logger.debug(f"Kelly position: {position_size:.2%} of capital")
        
        return result
    
    def calculate_fixed_fractional(self,
                                   fraction: float = 0.02,
                                   entry_price: float = None,
                                   stop_loss_price: float = None) -> PositionSizeResult:
        """
        Calculate Fixed Fractional position size
        
        Simple method: risk fixed percentage per trade
        
        Position = (Account * Fraction) / Stop Loss Distance
        
        Args:
            fraction: Fraction of account to risk (0.02 = 2%)
            entry_price: Entry price (optional, for unit calculation)
            stop_loss_price: Stop loss price (optional, for unit calculation)
            
        Returns:
            PositionSizeResult
        """
        logger.info(f"Calculating Fixed Fractional position (fraction={fraction:.2%})...")
        
        # Apply max risk limit
        fraction = min(fraction, self.max_risk_per_trade)
        
        # Risk amount
        risk_amount = self.account_balance * fraction
        
        # Calculate position units if prices provided
        if entry_price and stop_loss_price:
            stop_distance = abs(entry_price - stop_loss_price)
            position_units = risk_amount / stop_distance if stop_distance > 0 else 0
            position_size = (position_units * entry_price) / self.account_balance
        else:
            position_units = 0
            position_size = fraction  # As fraction of capital
        
        result = PositionSizeResult(
            position_size=position_size,
            position_units=position_units,
            risk_amount=risk_amount,
            method='Fixed Fractional',
            timestamp=datetime.now(),
            metadata={
                'fraction': fraction,
                'entry_price': entry_price,
                'stop_loss_price': stop_loss_price,
                'capped_by_max': fraction < self.max_risk_per_trade
            }
        )
        
        logger.debug(f"Fixed Fractional position: ${risk_amount:,.2f} at risk")
        
        return result
    
    def calculate_volatility_based(self,
                                   volatility: float,
                                   target_volatility: float = 0.15,
                                   base_position: float = 0.10) -> PositionSizeResult:
        """
        Calculate Volatility-based position size
        
        Adjust position size based on current vs target volatility
        
        Position = Base Position * (Target Vol / Current Vol)
        
        Args:
            volatility: Current volatility (annualized)
            target_volatility: Target portfolio volatility
            base_position: Base position size
            
        Returns:
            PositionSizeResult
        """
        logger.info(f"Calculating Volatility-based position "
                   f"(vol={volatility:.2%}, target={target_volatility:.2%})...")
        
        # Volatility adjustment
        if volatility > 0:
            vol_adjustment = target_volatility / volatility
        else:
            vol_adjustment = 1.0
        
        # Calculate position size
        position_size = base_position * vol_adjustment
        
        # Apply max position limit
        position_size = min(position_size, self.max_position_size)
        
        # Calculate units and risk
        position_value = position_size * self.account_balance
        risk_amount = position_value * self.max_risk_per_trade
        position_units = position_value  # In dollars
        
        result = PositionSizeResult(
            position_size=position_size,
            position_units=position_units,
            risk_amount=risk_amount,
            method='Volatility-based',
            timestamp=datetime.now(),
            metadata={
                'volatility': volatility,
                'target_volatility': target_volatility,
                'vol_adjustment': vol_adjustment,
                'base_position': base_position,
                'capped_by_max': position_size < (base_position * vol_adjustment)
            }
        )
        
        logger.debug(f"Volatility-based position: {position_size:.2%} "
                    f"(vol_adj={vol_adjustment:.2f})")
        
        return result
    
    def calculate_optimal(self,
                         win_rate: float,
                         avg_win: float,
                         avg_loss: float,
                         volatility: float,
                         kelly_weight: float = 0.40,
                         fixed_weight: float = 0.30,
                         vol_weight: float = 0.30) -> PositionSizeResult:
        """
        Calculate optimal position using weighted combination
        
        Combines Kelly, Fixed Fractional, and Volatility methods
        
        Args:
            win_rate: Win rate
            avg_win: Average win
            avg_loss: Average loss
            volatility: Current volatility
            kelly_weight: Weight for Kelly method
            fixed_weight: Weight for Fixed Fractional
            vol_weight: Weight for Volatility-based
            
        Returns:
            PositionSizeResult with optimal size
        """
        logger.info("Calculating optimal position (weighted combination)...")
        
        # Normalize weights
        total_weight = kelly_weight + fixed_weight + vol_weight
        kelly_weight /= total_weight
        fixed_weight /= total_weight
        vol_weight /= total_weight
        
        # Calculate each method
        kelly_result = self.calculate_kelly(win_rate, avg_win, avg_loss, kelly_fraction=0.5)
        fixed_result = self.calculate_fixed_fractional(self.max_risk_per_trade)
        vol_result = self.calculate_volatility_based(volatility)
        
        # Weighted average
        optimal_size = (
            kelly_result.position_size * kelly_weight +
            fixed_result.position_size * fixed_weight +
            vol_result.position_size * vol_weight
        )
        
        # Apply max limit
        optimal_size = min(optimal_size, self.max_position_size)
        
        # Calculate units and risk
        position_value = optimal_size * self.account_balance
        risk_amount = position_value * self.max_risk_per_trade
        
        result = PositionSizeResult(
            position_size=optimal_size,
            position_units=position_value,
            risk_amount=risk_amount,
            method='Optimal (Weighted)',
            timestamp=datetime.now(),
            metadata={
                'kelly_size': kelly_result.position_size,
                'fixed_size': fixed_result.position_size,
                'vol_size': vol_result.position_size,
                'kelly_weight': kelly_weight,
                'fixed_weight': fixed_weight,
                'vol_weight': vol_weight
            }
        )
        
        logger.info(f"Optimal position: {optimal_size:.2%} "
                   f"(Kelly={kelly_result.position_size:.2%}, "
                   f"Fixed={fixed_result.position_size:.2%}, "
                   f"Vol={vol_result.position_size:.2%})")
        
        return result
    
    def calculate_max_loss_sizing(self,
                                  entry_price: float,
                                  stop_loss_price: float,
                                  max_loss: float = None) -> PositionSizeResult:
        """
        Calculate position size based on maximum acceptable loss
        
        Position Units = Max Loss / Stop Distance
        
        Args:
            entry_price: Entry price
            stop_loss_price: Stop loss price
            max_loss: Maximum loss in dollars (if None, use max_risk_per_trade)
            
        Returns:
            PositionSizeResult
        """
        if max_loss is None:
            max_loss = self.account_balance * self.max_risk_per_trade
        
        logger.info(f"Calculating Max Loss position (max_loss=${max_loss:,.2f})...")
        
        # Calculate stop distance
        stop_distance = abs(entry_price - stop_loss_price)
        
        if stop_distance == 0:
            logger.error("Stop distance is zero!")
            raise ValueError("Stop loss must be different from entry price")
        
        # Calculate position units
        position_units = max_loss / stop_distance
        
        # Calculate position size
        position_value = position_units * entry_price
        position_size = position_value / self.account_balance
        
        # Apply max limit
        if position_size > self.max_position_size:
            logger.warning(f"Position size {position_size:.2%} exceeds max "
                         f"{self.max_position_size:.2%}, capping")
            position_size = self.max_position_size
            position_value = position_size * self.account_balance
            position_units = position_value / entry_price
        
        result = PositionSizeResult(
            position_size=position_size,
            position_units=position_units,
            risk_amount=max_loss,
            method='Max Loss',
            timestamp=datetime.now(),
            metadata={
                'entry_price': entry_price,
                'stop_loss_price': stop_loss_price,
                'stop_distance': stop_distance,
                'max_loss': max_loss
            }
        )
        
        logger.debug(f"Max Loss position: {position_units:.2f} units")
        
        return result
    
    def compare_methods(self,
                       win_rate: float = 0.55,
                       avg_win: float = 100,
                       avg_loss: float = 50,
                       volatility: float = 0.20,
                       entry_price: float = 100,
                       stop_loss_price: float = 98) -> pd.DataFrame:
        """
        Compare all position sizing methods
        
        Args:
            win_rate: Win rate
            avg_win: Average win
            avg_loss: Average loss
            volatility: Volatility
            entry_price: Entry price
            stop_loss_price: Stop loss price
            
        Returns:
            DataFrame with comparison
        """
        results = {}
        
        # Kelly
        try:
            results['Kelly'] = self.calculate_kelly(win_rate, avg_win, avg_loss)
        except Exception as e:
            logger.warning(f"Kelly failed: {e}")
        
        # Fixed Fractional
        try:
            results['Fixed Fractional'] = self.calculate_fixed_fractional(
                self.max_risk_per_trade, entry_price, stop_loss_price
            )
        except Exception as e:
            logger.warning(f"Fixed Fractional failed: {e}")
        
        # Volatility-based
        try:
            results['Volatility-based'] = self.calculate_volatility_based(volatility)
        except Exception as e:
            logger.warning(f"Volatility-based failed: {e}")
        
        # Max Loss
        try:
            results['Max Loss'] = self.calculate_max_loss_sizing(
                entry_price, stop_loss_price
            )
        except Exception as e:
            logger.warning(f"Max Loss failed: {e}")
        
        # Optimal
        try:
            results['Optimal'] = self.calculate_optimal(
                win_rate, avg_win, avg_loss, volatility
            )
        except Exception as e:
            logger.warning(f"Optimal failed: {e}")
        
        comparison = []
        for method, result in results.items():
            comparison.append({
                'Method': method,
                'Position Size': f"{result.position_size:.2%}",
                'Units': result.position_units,
                'Risk Amount': result.risk_amount,
                'Capital Used': result.position_size * self.account_balance
            })
        
        return pd.DataFrame(comparison)
    
    def update_balance(self, new_balance: float):
        """Update account balance"""
        logger.info(f"Updating balance: ${self.account_balance:,.0f} -> ${new_balance:,.0f}")
        self.account_balance = new_balance
    
    def __repr__(self):
        return (f"PositionSizer(balance=${self.account_balance:,.0f}, "
                f"max_pos={self.max_position_size:.1%})")


# Convenience functions
def quick_kelly(win_rate: float,
               avg_win: float,
               avg_loss: float,
               account_balance: float = 100000) -> float:
    """Quick Kelly Criterion calculation"""
    sizer = PositionSizer(account_balance)
    result = sizer.calculate_kelly(win_rate, avg_win, avg_loss)
    return result.position_size


def quick_fixed(fraction: float = 0.02,
               account_balance: float = 100000) -> float:
    """Quick Fixed Fractional calculation"""
    sizer = PositionSizer(account_balance)
    result = sizer.calculate_fixed_fractional(fraction)
    return result.position_size

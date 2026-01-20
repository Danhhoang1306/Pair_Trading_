"""
Drawdown Monitoring Module
Track and analyze drawdowns for risk management

Includes:
- Real-time drawdown tracking
- Maximum drawdown calculation
- Recovery metrics
- Drawdown alerts
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional, List, Any
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DrawdownMetrics:
    """Drawdown metrics"""
    current_drawdown: float
    current_drawdown_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    max_dd_start: datetime
    max_dd_end: datetime
    max_dd_duration: int
    current_peak: float
    peak_balance: float  # Added for tracking peak balance
    is_in_drawdown: bool
    recovery_factor: float
    timestamp: datetime
    
    def __str__(self):
        return (f"Drawdown Metrics:\n"
                f"  Current DD: ${self.current_drawdown:,.2f} ({self.current_drawdown_pct:.2%})\n"
                f"  Max DD: ${self.max_drawdown:,.2f} ({self.max_drawdown_pct:.2%})\n"
                f"  In Drawdown: {self.is_in_drawdown}\n"
                f"  Recovery Factor: {self.recovery_factor:.2f}")


class DrawdownMonitor:
    """
    Monitor and track drawdowns in real-time
    
    Example:
        >>> monitor = DrawdownMonitor(initial_balance=100000)
        >>> monitor.update(95000)  # Update with current balance
        >>> metrics = monitor.get_metrics()
        >>> print(f"Current DD: {metrics.current_drawdown_pct:.2%}")
    """
    
    def __init__(self,
                 account_balance: float = None,      # For compatibility
                 initial_balance: float = None,       # Legacy param
                 daily_loss_limit: float = None,      # Dollar amount ($5000)
                 max_drawdown_limit: float = None,    # Fraction (0.20)
                 max_drawdown_pct: float = None,      # Percentage (20.0)
                 alert_threshold: float = 0.10,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize drawdown monitor
        
        Args:
            account_balance: Account balance (preferred)
            initial_balance: Legacy param (same as account_balance)
            daily_loss_limit: Max loss in dollars (e.g., 5000.0)
            max_drawdown_limit: Max drawdown as fraction (e.g., 0.20)
            max_drawdown_pct: Max drawdown as percentage (e.g., 20.0)
            alert_threshold: Alert level as fraction
            config: Optional config dict
        
        Priority: config > daily_loss_limit > max_drawdown_pct > max_drawdown_limit
        """
        # Extract from config if provided
        if config:
            daily_loss_limit = config.get('daily_loss_limit', daily_loss_limit)
            max_drawdown_pct = config.get('max_drawdown_pct', max_drawdown_pct)
        
        # Determine balance
        balance = account_balance or initial_balance or 100000.0
        self.initial_balance = balance
        
        # Determine max drawdown limit (multiple formats supported)
        if daily_loss_limit is not None:
            # Dollar amount → convert to fraction
            self.max_drawdown_limit = daily_loss_limit / balance
            logger.info(f"Using daily loss limit: ${daily_loss_limit:,.0f} ({self.max_drawdown_limit:.1%})")
        elif max_drawdown_pct is not None:
            # Percentage → convert to fraction
            self.max_drawdown_limit = max_drawdown_pct / 100.0
        elif max_drawdown_limit is not None:
            # Already a fraction
            self.max_drawdown_limit = max_drawdown_limit
        else:
            # Default 20%
            self.max_drawdown_limit = 0.20
        
        self.alert_threshold = alert_threshold
        
        # Track equity curve
        self.equity_curve = [balance]
        self.timestamps = [datetime.now()]
        
        # Peak tracking
        self.current_peak = balance
        self.peak_date = datetime.now()
        
        # Drawdown tracking
        self.max_drawdown = 0.0
        self.max_drawdown_pct = 0.0
        self.max_dd_start = None
        self.max_dd_end = None
        
        logger.info(f"DrawdownMonitor initialized (balance=${balance:,.0f}, "
                   f"max_dd_limit={self.max_drawdown_limit:.1%})")
    
    def update(self, current_balance: float) -> DrawdownMetrics:
        """
        Update with new balance and calculate metrics
        
        Args:
            current_balance: Current account balance
            
        Returns:
            DrawdownMetrics
        """
        timestamp = datetime.now()
        
        # Add to equity curve
        self.equity_curve.append(current_balance)
        self.timestamps.append(timestamp)
        
        # Update peak if new high
        if current_balance > self.current_peak:
            self.current_peak = current_balance
            self.peak_date = timestamp
        
        # Calculate current drawdown
        current_drawdown = self.current_peak - current_balance
        current_drawdown_pct = current_drawdown / self.current_peak if self.current_peak > 0 else 0
        
        # Update max drawdown
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown
            self.max_drawdown_pct = current_drawdown_pct
            self.max_dd_start = self.peak_date
            self.max_dd_end = timestamp
        
        # Check if in drawdown
        is_in_drawdown = current_drawdown > 0
        
        # Calculate recovery factor
        if self.max_drawdown > 0:
            recovery_factor = (current_balance - self.initial_balance) / self.max_drawdown
        else:
            recovery_factor = 0.0
        
        # Calculate duration
        if self.max_dd_start and self.max_dd_end:
            max_dd_duration = (self.max_dd_end - self.max_dd_start).days
        else:
            max_dd_duration = 0
        
        metrics = DrawdownMetrics(
            current_drawdown=current_drawdown,
            current_drawdown_pct=current_drawdown_pct,
            max_drawdown=self.max_drawdown,
            max_drawdown_pct=self.max_drawdown_pct,
            max_dd_start=self.max_dd_start,
            max_dd_end=self.max_dd_end,
            max_dd_duration=max_dd_duration,
            current_peak=self.current_peak,
            peak_balance=self.current_peak,  # Added - peak balance same as current peak
            is_in_drawdown=is_in_drawdown,
            recovery_factor=recovery_factor,
            timestamp=timestamp
        )
        
        # Check alerts
        if current_drawdown_pct >= self.alert_threshold:
            logger.warning(f"[ALERT] Drawdown {current_drawdown_pct:.2%} "
                         f">= threshold {self.alert_threshold:.2%}")
        
        if current_drawdown_pct >= self.max_drawdown_limit:
            logger.error(f"[CRITICAL] Drawdown {current_drawdown_pct:.2%} "
                       f">= limit {self.max_drawdown_limit:.2%}")
        
        return metrics
    
    def get_metrics(self) -> DrawdownMetrics:
        """Get current drawdown metrics"""
        if len(self.equity_curve) == 0:
            raise ValueError("No data available")
        
        return self.update(self.equity_curve[-1])
    
    def calculate_underwater_chart(self) -> pd.Series:
        """
        Calculate underwater (drawdown) chart
        
        Shows drawdown percentage at each point in time
        
        Returns:
            Series of drawdown percentages
        """
        equity_series = pd.Series(self.equity_curve, index=self.timestamps)
        
        # Calculate running maximum (peak)
        running_max = equity_series.expanding().max()
        
        # Calculate drawdown
        drawdown = (equity_series - running_max) / running_max
        
        return drawdown
    
    def get_drawdown_periods(self, min_drawdown: float = 0.05) -> List[Dict]:
        """
        Get all significant drawdown periods
        
        Args:
            min_drawdown: Minimum drawdown to consider (0.05 = 5%)
            
        Returns:
            List of drawdown periods
        """
        if len(self.equity_curve) < 2:
            return []
        
        equity_series = pd.Series(self.equity_curve, index=self.timestamps)
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max
        
        periods = []
        in_drawdown = False
        start_idx = None
        
        for i, dd in enumerate(drawdown):
            if dd < -min_drawdown and not in_drawdown:
                # Start of drawdown
                in_drawdown = True
                start_idx = i
            elif dd >= 0 and in_drawdown:
                # End of drawdown (new peak)
                in_drawdown = False
                
                # Calculate period metrics
                period_dd = drawdown[start_idx:i]
                max_dd_in_period = period_dd.min()
                
                periods.append({
                    'start': self.timestamps[start_idx],
                    'end': self.timestamps[i],
                    'duration_days': (self.timestamps[i] - self.timestamps[start_idx]).days,
                    'max_drawdown': max_dd_in_period,
                    'recovery': True
                })
        
        # Check if still in drawdown
        if in_drawdown:
            period_dd = drawdown[start_idx:]
            periods.append({
                'start': self.timestamps[start_idx],
                'end': self.timestamps[-1],
                'duration_days': (self.timestamps[-1] - self.timestamps[start_idx]).days,
                'max_drawdown': period_dd.min(),
                'recovery': False
            })
        
        return periods
    
    def check_risk_limit(self) -> Tuple[bool, str]:
        """
        Check if current drawdown exceeds risk limit
        
        Returns:
            (within_limit, message)
        """
        metrics = self.get_metrics()
        
        if metrics.current_drawdown_pct >= self.max_drawdown_limit:
            msg = (f"RISK LIMIT EXCEEDED: Drawdown {metrics.current_drawdown_pct:.2%} "
                   f">= limit {self.max_drawdown_limit:.2%}")
            return (False, msg)
        
        return (True, "Within risk limits")
    
    def reset(self, new_balance: float = None):
        """
        Reset monitor with new starting balance
        
        Args:
            new_balance: New starting balance (if None, use current)
        """
        if new_balance is None:
            new_balance = self.equity_curve[-1] if self.equity_curve else self.initial_balance
        
        logger.info(f"Resetting DrawdownMonitor with balance=${new_balance:,.0f}")
        
        self.initial_balance = new_balance
        self.equity_curve = [new_balance]
        self.timestamps = [datetime.now()]
        self.current_peak = new_balance
        self.peak_date = datetime.now()
        self.max_drawdown = 0.0
        self.max_drawdown_pct = 0.0
        self.max_dd_start = None
        self.max_dd_end = None
    
    def get_statistics(self) -> Dict:
        """Get comprehensive drawdown statistics"""
        if len(self.equity_curve) < 2:
            return {}
        
        metrics = self.get_metrics()
        periods = self.get_drawdown_periods(min_drawdown=0.01)
        
        return {
            'current_balance': self.equity_curve[-1],
            'initial_balance': self.initial_balance,
            'total_return': (self.equity_curve[-1] - self.initial_balance) / self.initial_balance,
            'current_peak': self.current_peak,
            'current_drawdown_pct': metrics.current_drawdown_pct,
            'max_drawdown_pct': metrics.max_drawdown_pct,
            'num_drawdown_periods': len(periods),
            'avg_drawdown_duration': np.mean([p['duration_days'] for p in periods]) if periods else 0,
            'recovery_factor': metrics.recovery_factor,
            'is_in_drawdown': metrics.is_in_drawdown
        }
    
    def __repr__(self):
        return (f"DrawdownMonitor(balance=${self.equity_curve[-1]:,.0f}, "
                f"max_dd={self.max_drawdown_pct:.2%})")


def calculate_max_drawdown(equity_curve: pd.Series) -> Tuple[float, datetime, datetime]:
    """
    Calculate maximum drawdown from equity curve
    
    Args:
        equity_curve: Series of account values
        
    Returns:
        (max_drawdown_pct, start_date, end_date)
    """
    # Calculate running maximum
    running_max = equity_curve.expanding().max()
    
    # Calculate drawdown
    drawdown = (equity_curve - running_max) / running_max
    
    # Find maximum drawdown
    max_dd = drawdown.min()
    max_dd_idx = drawdown.idxmin()
    
    # Find start (peak before max dd)
    start_idx = equity_curve[:max_dd_idx].idxmax()
    
    return (abs(max_dd), start_idx, max_dd_idx)


def calculate_calmar_ratio(returns: pd.Series,
                           periods_per_year: int = 252) -> float:
    """
    Calculate Calmar Ratio
    
    Calmar = Annual Return / Max Drawdown
    
    Args:
        returns: Return series
        periods_per_year: Periods per year
        
    Returns:
        Calmar ratio
    """
    # Annual return
    total_return = (1 + returns).prod() - 1
    n_periods = len(returns)
    years = n_periods / periods_per_year
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    
    # Max drawdown
    equity = (1 + returns).cumprod()
    max_dd, _, _ = calculate_max_drawdown(equity)
    
    # Calmar ratio
    if max_dd > 0:
        calmar = annual_return / max_dd
    else:
        calmar = 0.0
    
    return calmar

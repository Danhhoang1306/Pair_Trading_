"""
Risk Checker Module
Pre-trade validation and risk monitoring

Includes:
- Pre-trade checks
- Position limits
- Correlation limits
- Exposure monitoring
- Circuit breakers
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional, List, Any
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level enumeration"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskCheckResult:
    """Results from risk check"""
    passed: bool
    risk_level: RiskLevel
    checks_passed: List[str]
    checks_failed: List[str]
    warnings: List[str]
    timestamp: datetime
    metadata: Dict = None
    
    def __str__(self):
        status = "PASSED" if self.passed else "FAILED"
        return (f"Risk Check: {status} ({self.risk_level.value})\n"
                f"  Passed: {len(self.checks_passed)} checks\n"
                f"  Failed: {len(self.checks_failed)} checks\n"
                f"  Warnings: {len(self.warnings)}")


class RiskChecker:
    """
    Pre-trade risk validation and monitoring
    
    Example:
        >>> checker = RiskChecker(max_position_size=0.20)
        >>> result = checker.check_trade(
        >>>     position_size=0.15,
        >>>     account_balance=100000,
        >>>     current_drawdown=0.08
        >>> )
        >>> if result.passed:
        >>>     print("Trade approved")
    """
    
    def __init__(self,
                 max_position_pct: float = 20.0,        # Percentage
                 max_portfolio_risk: float = 10.0,      # Percentage
                 max_drawdown_pct: float = 20.0,        # Percentage
                 max_correlation: float = 0.80,
                 daily_loss_limit_pct: float = 5.0,            # Percentage (default 5%)
                 min_risk_reward: float = 1.5,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize risk checker
        
        Args:
            max_position_pct: Max position as percentage (20.0 = 20%)
            max_portfolio_risk: Max portfolio risk percentage (10.0 = 10%)
            max_drawdown_pct: Max drawdown percentage (20.0 = 20%)
            max_correlation: Max correlation between positions (0.80)
            max_daily_loss: Max daily loss percentage (5.0 = 5%)
            min_risk_reward: Minimum risk/reward ratio (1.5)
            config: Optional config dict
        """
        # Extract from config if provided
        if config:
            max_position_pct = config.get('max_position_pct', max_position_pct)
            max_drawdown_pct = config.get('max_drawdown_pct', max_drawdown_pct)
            # daily_loss_limit in dollars → convert to percentage
            daily_loss_limit = config.get('daily_loss_limit')
            daily_loss_limit_pct = config.get('daily_loss_limit_pct',daily_loss_limit_pct)
            if daily_loss_limit is not None:
                # We don't have balance here, so use percentage from config
                # This will be overridden by TradingSystem with actual calculation
                pass
        
        # Store percentages
        self.max_position_pct = max_position_pct
        self.max_portfolio_risk_pct = max_portfolio_risk
        self.max_drawdown_pct = max_drawdown_pct

        
        # Convert to fractions for internal use
        self.max_position_size = max_position_pct / 100.0
        self.max_portfolio_risk = max_portfolio_risk / 100.0
        self.max_drawdown_limit = max_drawdown_pct / 100.0
        self.max_daily_loss = daily_loss_limit_pct / 100.0
        
        self.max_correlation = max_correlation
        self.min_risk_reward = min_risk_reward
        
        # Track daily stats
        self.daily_pnl = 0.0
        self.daily_start_balance = None
        self.last_reset_date = datetime.now().date()
        
        logger.info(f"RiskChecker initialized (max_pos={max_position_pct}%, "
                   f"max_dd={max_drawdown_pct}%)")
    
    def check_trade(self,
                   position_size: float,
                   account_balance: float,
                   current_drawdown: float,
                   entry_price: float = None,
                   stop_loss: float = None,
                   take_profit: float = None,
                   existing_positions: int = 0,
                   portfolio_risk: float = 0.0) -> RiskCheckResult:
        """
        Comprehensive pre-trade risk check
        
        Args:
            position_size: Proposed position size (fraction)
            account_balance: Current account balance
            current_drawdown: Current drawdown (fraction)
            entry_price: Entry price (optional)
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            existing_positions: Number of existing positions
            portfolio_risk: Current portfolio risk
            
        Returns:
            RiskCheckResult
        """
        logger.info(f"Running risk check (pos_size={position_size:.2%}, "
                   f"balance=${account_balance:,.0f})...")
        
        checks_passed = []
        checks_failed = []
        warnings = []
        
        # Check 1: Position Size Limit
        if position_size <= self.max_position_size:
            checks_passed.append(f"Position size {position_size:.2%} "
                               f"<= limit {self.max_position_size:.2%}")
        else:
            checks_failed.append(f"Position size {position_size:.2%} "
                               f"> limit {self.max_position_size:.2%}")
        
        # Check 2: Drawdown Limit
        if current_drawdown <= self.max_drawdown_limit:
            checks_passed.append(f"Drawdown {current_drawdown:.2%} "
                               f"<= limit {self.max_drawdown_limit:.2%}")
        else:
            checks_failed.append(f"Drawdown {current_drawdown:.2%} "
                               f"> limit {self.max_drawdown_limit:.2%}")
        
        # Check 3: Portfolio Risk
        total_risk = portfolio_risk + (position_size * account_balance)
        risk_pct = total_risk / account_balance
        
        if risk_pct <= self.max_portfolio_risk:
            checks_passed.append(f"Portfolio risk {risk_pct:.2%} "
                               f"<= limit {self.max_portfolio_risk:.2%}")
        else:
            checks_failed.append(f"Portfolio risk {risk_pct:.2%} "
                               f"> limit {self.max_portfolio_risk:.2%}")
        
        # Check 4: Daily Loss Limit
        self._update_daily_stats(account_balance)
        
        if self.daily_start_balance:
            daily_loss_pct = abs(self.daily_pnl / self.daily_start_balance)
            
            if daily_loss_pct < self.max_daily_loss:
                checks_passed.append(f"Daily loss {daily_loss_pct:.2%} "
                                   f"< limit {self.max_daily_loss:.2%}")
            else:
                checks_failed.append(f"Daily loss {daily_loss_pct:.2%} "
                                   f">= limit {self.max_daily_loss:.2%}")
        
        # Check 5: Risk/Reward Ratio
        if entry_price and stop_loss and take_profit:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            
            if risk > 0:
                rr_ratio = reward / risk
                
                if rr_ratio >= self.min_risk_reward:
                    checks_passed.append(f"Risk/Reward {rr_ratio:.2f} "
                                       f">= minimum {self.min_risk_reward:.2f}")
                else:
                    warnings.append(f"Risk/Reward {rr_ratio:.2f} "
                                  f"< minimum {self.min_risk_reward:.2f}")
        
        # Check 6: Account Balance
        if account_balance > 0:
            checks_passed.append("Account balance positive")
        else:
            checks_failed.append("Account balance is zero or negative")
        
        # Check 7: Position concentration
        if existing_positions > 0:
            avg_position_size = portfolio_risk / account_balance / existing_positions
            
            if position_size > avg_position_size * 2:
                warnings.append(f"New position {position_size:.2%} is 2x larger "
                              f"than average {avg_position_size:.2%}")
        
        # Determine overall result
        passed = len(checks_failed) == 0
        
        # Determine risk level
        if not passed:
            risk_level = RiskLevel.CRITICAL
        elif len(warnings) >= 2:
            risk_level = RiskLevel.HIGH
        elif len(warnings) == 1:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        result = RiskCheckResult(
            passed=passed,
            risk_level=risk_level,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            warnings=warnings,
            timestamp=datetime.now(),
            metadata={
                'position_size': position_size,
                'account_balance': account_balance,
                'current_drawdown': current_drawdown,
                'portfolio_risk_pct': risk_pct,
                'daily_loss_pct': daily_loss_pct if self.daily_start_balance else 0
            }
        )
        
        # Log result
        if passed:
            logger.info(f"[OK] Risk check PASSED ({risk_level.value})")
        else:
            logger.error(f"[FAIL] Risk check FAILED: {', '.join(checks_failed)}")
        
        for warning in warnings:
            logger.warning(f"[WARN] {warning}")
        
        return result
    
    def check_correlation(self,
                         returns1: pd.Series,
                         returns2: pd.Series) -> Tuple[bool, float]:
        """
        Check correlation between two positions
        
        Args:
            returns1: Returns of position 1
            returns2: Returns of position 2
            
        Returns:
            (within_limit, correlation)
        """
        correlation = returns1.corr(returns2)
        within_limit = abs(correlation) <= self.max_correlation
        
        if not within_limit:
            logger.warning(f"Correlation {correlation:.2f} "
                         f"> limit {self.max_correlation:.2f}")
        
        return (within_limit, correlation)
    
    def check_circuit_breaker(self,
                             current_balance: float,
                             starting_balance: float) -> Tuple[bool, str]:
        """
        Check if circuit breaker should trigger
        
        Circuit breaker stops trading if loss exceeds threshold
        
        Args:
            current_balance: Current balance
            starting_balance: Starting balance for period
            
        Returns:
            (should_halt, reason)
        """
        if starting_balance <= 0:
            return (False, "Starting balance invalid")
        
        loss = starting_balance - current_balance
        loss_pct = loss / starting_balance
        
        # Halt if daily loss exceeds limit
        if loss_pct >= self.max_daily_loss:
            reason = (f"Daily loss {loss_pct:.2%} >= limit {self.max_daily_loss:.2%}. "
                     f"Trading halted.")
            logger.critical(f"[CIRCUIT BREAKER] {reason}")
            return (True, reason)
        
        return (False, "Within limits")
    
    def update_daily_pnl(self, pnl: float):
        """Update daily P&L"""
        self._update_daily_stats()
        self.daily_pnl += pnl
        
        logger.debug(f"Daily P&L updated: ${self.daily_pnl:,.2f}")
    
    def _update_daily_stats(self, balance: float = None):
        """Update daily statistics (internal)"""
        current_date = datetime.now().date()
        
        # Reset if new day
        if current_date != self.last_reset_date:
            logger.info(f"Resetting daily stats (new day: {current_date})")
            self.daily_pnl = 0.0
            self.daily_start_balance = balance
            self.last_reset_date = current_date
        elif self.daily_start_balance is None and balance:
            self.daily_start_balance = balance
    
    def get_daily_stats(self) -> Dict:
        """Get daily statistics"""
        if self.daily_start_balance:
            daily_return = self.daily_pnl / self.daily_start_balance
        else:
            daily_return = 0.0
        
        return {
            'daily_pnl': self.daily_pnl,
            'daily_start_balance': self.daily_start_balance,
            'daily_return': daily_return,
            'remaining_risk': self.max_daily_loss - abs(daily_return),
            'date': self.last_reset_date
        }
    
    def reset_daily(self, balance: float):
        """Reset daily statistics manually"""
        logger.info(f"Manually resetting daily stats (balance=${balance:,.0f})")
        self.daily_pnl = 0.0
        self.daily_start_balance = balance
        self.last_reset_date = datetime.now().date()
    
    def __repr__(self):
        return (f"RiskChecker(max_pos={self.max_position_size:.1%}, "
                f"max_dd={self.max_drawdown_limit:.1%})")


# Convenience function
def quick_check(position_size: float,
               account_balance: float,
               current_drawdown: float = 0.0) -> bool:
    """Quick risk check"""
    checker = RiskChecker()
    result = checker.check_trade(position_size, account_balance, current_drawdown)
    return result.passed

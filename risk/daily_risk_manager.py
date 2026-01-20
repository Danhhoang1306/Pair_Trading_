"""
Daily Risk Manager
Manages two separate risk systems:
1. Max Risk (Open Positions) - Real-time unrealized P&L check
2. Daily Loss Limit - Session-based total P&L check
"""

import logging
from datetime import datetime, time
from typing import Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass
from core.mt5_manager import get_mt5

if TYPE_CHECKING:
    from risk.trading_lock_manager import TradingLockManager

logger = logging.getLogger(__name__)


@dataclass
class RiskStatus:
    """Current risk status"""
    # Open positions risk
    unrealized_pnl: float
    max_risk_limit: float
    max_risk_breached: bool

    # Daily loss tracking (NEW FORMULA)
    starting_balance: float          # Balance at session start (equity - net_pnl)
    net_realized_pnl: float          # Profit - Commission (closed trades)
    total_commission: float          # Total commission paid
    session_unrealized_pnl: float    # Unrealized P&L (open positions)
    daily_total_pnl: float           # Net realized + Unrealized
    daily_loss_limit: float          # Starting balance × daily risk %
    daily_limit_breached: bool
    remaining_until_daily_limit: float  # Daily limit + Net P&L + Unrealized

    # Trading status
    trading_locked: bool
    lock_reason: str
    
    def __str__(self):
        status = []
        status.append(f"=== RISK STATUS ===")
        status.append(f"Unrealized P&L: ${self.unrealized_pnl:,.2f}")
        status.append(f"Max Risk Limit: ${self.max_risk_limit:,.2f}")
        status.append(f"Max Risk Breached: {self.max_risk_breached}")
        status.append(f"")
        status.append(f"Session Realized P&L: ${self.session_realized_pnl:,.2f}")
        status.append(f"Daily Total P&L: ${self.daily_total_pnl:,.2f}")
        status.append(f"Daily Loss Limit: ${self.daily_loss_limit:,.2f}")
        status.append(f"Remaining: ${self.remaining_until_daily_limit:,.2f}")
        status.append(f"Daily Limit Breached: {self.daily_limit_breached}")
        status.append(f"")
        status.append(f"Trading Locked: {self.trading_locked}")
        if self.trading_locked:
            status.append(f"Lock Reason: {self.lock_reason}")
        return "\n".join(status)


class DailyRiskManager:
    """
    Manages two independent risk systems:
    
    1. MAX RISK (Open Positions):
       - Monitors unrealized P&L of open positions
       - If breached → Close all positions
       - System continues trading if new signals
    
    2. DAILY LOSS LIMIT:
       - Tracks total P&L for the session (realized + unrealized)
       - Loads history on startup
       - If breached → Lock trading system
       - Reset at session start time
    """
    
    def __init__(self,
                 account_balance: float,
                 max_risk_pct: float,
                 daily_loss_limit_pct: float,
                 session_start_time: str = "00:00",
                 session_end_time: str = "23:59",
                 magic_number: int = 234000,
                 trading_lock_manager: Optional['TradingLockManager'] = None):
        """
        Initialize daily risk manager

        Args:
            account_balance: Account balance (for max_risk_limit only)
            max_risk_pct: Max risk % for open positions (e.g., 0.5)
            daily_loss_limit_pct: Daily loss limit as PERCENTAGE (e.g., 10.0 for 10%)
            session_start_time: Session start time "HH:MM"
            session_end_time: Session end time "HH:MM"
            magic_number: EA magic number for filtering
            trading_lock_manager: TradingLockManager instance for persisting lock state
        """
        self.account_balance = account_balance
        self.max_risk_pct = max_risk_pct / 100.0  # Convert to fraction
        self.daily_loss_limit_pct = daily_loss_limit_pct  # Store as percentage
        self.magic_number = magic_number
        self.trading_lock_manager = trading_lock_manager

        # Session times
        self.session_start_time = self._parse_time(session_start_time)
        self.session_end_time = self._parse_time(session_end_time)

        # Calculate limits
        self.max_risk_limit = 0.0

        # Daily tracking (NEW FORMULA)
        self.starting_balance = 0.0       # Balance at session start
        self.net_realized_pnl = 0.0       # Profit - Commission
        self.total_commission = 0.0       # Total commission paid
        self.session_start_datetime = None
        self.trading_locked = False
        self.lock_reason = ""
        
        logger.info(f"DailyRiskManager initialized:")
        logger.info(f"  Account Balance: ${account_balance:,.2f}")
        logger.info(f"  Max Risk (Open): {max_risk_pct:.2f}% = ${self.max_risk_limit:,.2f}")
        logger.info(f"  Daily Loss Limit: {daily_loss_limit_pct:.1f}% (calculated from starting balance)")
        logger.info(f"  Session Time: {session_start_time} - {session_end_time}")
        
        # Load session history
        self._load_session_history()
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string HH:MM"""
        try:
            h, m = map(int, time_str.split(':'))
            return time(hour=h, minute=m)
        except:
            logger.error(f"Invalid time format: {time_str}, using 00:00")
            return time(hour=0, minute=0)
    
    def _get_session_start_datetime(self) -> datetime:
        """Get current session start datetime"""
        now = datetime.now()
        current_time = now.time()
        
        # If current time < session_start_time → use yesterday's session
        if current_time < self.session_start_time:
            session_date = now.date()
            from datetime import timedelta
            session_date = session_date - timedelta(days=1)
        else:
            session_date = now.date()
        
        return datetime.combine(session_date, self.session_start_time)
    
    def _load_session_history(self):
        """Load realized P&L from current session"""
        try:
            # Get session start
            self.session_start_datetime = self._get_session_start_datetime()
            
            logger.info(f"Loading session history from: {self.session_start_datetime}")
            
            # Get deals history from session start to now
            mt5 = get_mt5()
            deals = mt5.history_deals_get(
                self.session_start_datetime,
                datetime.now()
            )
            
            if deals is None:
                logger.warning("Failed to get MT5 deals history")
                self.session_realized_pnl = 0.0
                return
            
            # Filter by magic number and calculate P&L
            session_pnl = 0.0
            deal_count = 0
            
            for deal in deals:
                # Only count deals from our EA
                if deal.magic != self.magic_number:
                    continue
                
                # Only count OUT deals (position closures)
                if deal.entry == mt5.DEAL_ENTRY_OUT:
                    session_pnl += deal.profit
                    deal_count += 1
            
            self.session_realized_pnl = session_pnl
            
            logger.info(f"Session history loaded:")
            logger.info(f"  Deals: {deal_count}")
            logger.info(f"  Realized P&L: ${session_pnl:,.2f}")
            
            # Check if already breached (need starting_balance first, skip for now)
            # This check will be done in check_risk() after starting_balance is loaded
            pass
        
        except Exception as e:
            logger.error(f"Error loading session history: {e}")
            self.session_realized_pnl = 0.0
    
    def check_risk(self, open_positions_pnl: float) -> RiskStatus:
        """
        Check both risk systems - NEW FORMULA

        Args:
            open_positions_pnl: Current unrealized P&L of open positions

        Returns:
            RiskStatus with all risk info
        """
        # NEW FORMULA:
        # Daily Total P&L = Net Realized P&L + Unrealized P&L
        daily_total_pnl = self.net_realized_pnl + open_positions_pnl

        daily_loss_limit_amount = self.starting_balance * (self.daily_loss_limit_pct / 100.0)

        # Remaining = Daily Limit + Net P&L + Unrealized
        remaining = daily_loss_limit_amount + self.net_realized_pnl + open_positions_pnl

        # DEBUG LOGGING
        logger.debug(f"[DAILY-RISK-CHECK]")
        logger.debug(f"  Starting Balance: ${self.starting_balance:.2f}")
        logger.debug(f"  Daily Limit %: {self.daily_loss_limit_pct:.1f}%")
        logger.debug(f"  Daily Limit $: ${daily_loss_limit_amount:.2f}")
        logger.debug(f"  Net Realized P&L: ${self.net_realized_pnl:.2f}")
        logger.debug(f"  Unrealized P&L: ${open_positions_pnl:.2f}")
        logger.debug(f"  Daily Total P&L: ${daily_total_pnl:.2f}")
        logger.debug(f"  Remaining: ${remaining:.2f}")

        # Check max risk (open positions)
        max_risk_breached = open_positions_pnl < -self.max_risk_limit

        # Check daily limit
        daily_limit_breached = daily_total_pnl < -daily_loss_limit_amount

        # Update trading lock status
        if daily_limit_breached and not self.trading_locked:
            self.trading_locked = True
            self.lock_reason = f"Daily limit breached: ${daily_total_pnl:,.2f}"
            logger.critical(f"🔒 TRADING LOCKED: {self.lock_reason}")

            # CRITICAL: Persist lock state to file via TradingLockManager
            if self.trading_lock_manager:
                self.trading_lock_manager.lock_trading(
                    reason=self.lock_reason,
                    daily_pnl=daily_total_pnl,
                    daily_limit=daily_loss_limit_amount
                )
                logger.critical("✅ Lock state persisted to trading_lock.json")
            else:
                logger.warning("⚠️ TradingLockManager not available - lock NOT persisted!")

        # Create status with NEW FIELDS
        status = RiskStatus(
            unrealized_pnl=open_positions_pnl,
            max_risk_limit=self.max_risk_limit,
            max_risk_breached=max_risk_breached,
            starting_balance=self.starting_balance,
            net_realized_pnl=self.net_realized_pnl,
            total_commission=self.total_commission,
            session_unrealized_pnl=open_positions_pnl,
            daily_total_pnl=daily_total_pnl,
            daily_loss_limit=daily_loss_limit_amount,
            daily_limit_breached=daily_limit_breached,
            remaining_until_daily_limit=remaining,
            trading_locked=self.trading_locked,
            lock_reason=self.lock_reason
        )

        return status
    
    def should_close_positions(self, open_positions_pnl: float) -> bool:
        """Check if should close all positions (max risk breached)"""
        return open_positions_pnl < -self.max_risk_limit
    
    def can_trade(self) -> bool:
        """
        Check if trading is allowed (not locked by daily limit)

        Checks both internal flag AND TradingLockManager for persistence
        """
        # Check TradingLockManager first (source of truth from file)
        if self.trading_lock_manager:
            if self.trading_lock_manager.is_locked():
                self.trading_locked = True  # Sync internal state
                return False

        # Fallback to internal flag
        return not self.trading_locked
    
    def reset_session(self):
        """Reset for new session - NEW FORMULA"""
        logger.info("Resetting session...")
        self.net_realized_pnl = 0.0
        self.total_commission = 0.0
        self.starting_balance = 0.0
        self.session_start_datetime = self._get_session_start_datetime()
        self.trading_locked = False
        self.lock_reason = ""

        # CRITICAL: Unlock via TradingLockManager (persist to file)
        if self.trading_lock_manager:
            self.trading_lock_manager.unlock_trading(reason="Session reset")
            logger.info("✅ Trading unlocked via TradingLockManager")

        logger.info("✅ Session reset complete")

    def update_realized_pnl(self, closed_profit: float, closed_commission: float):
        """
        Update realized P&L when position closes - NEW FORMULA

        Args:
            closed_profit: Profit from closed trade
            closed_commission: Commission paid
        """
        self.net_realized_pnl += (closed_profit - abs(closed_commission))
        self.total_commission += abs(closed_commission)
        logger.info(f"Updated: Net P&L=${self.net_realized_pnl:,.2f}, "
                   f"Commission=${self.total_commission:,.2f}")
    
    def load_daily_history(self, current_equity: float):
        """
        Load today's closed trades - NEW FORMULA
        NO magic number filter - calculate ALL trades

        Args:
            current_equity: Current account equity from MT5

        Returns:
            dict: {
                'starting_balance': float,
                'net_realized_pnl': float,
                'total_commission': float,
                'trade_count': int
            }
        """
        from datetime import datetime, time

        logger.info("=" * 70)
        logger.info("LOADING DAILY HISTORY (NEW FORMULA - ALL TRADES)")
        logger.info("=" * 70)

        try:
            # Get session date range
            session_start = self._get_session_start_datetime()
            end_time = datetime.now()

            logger.info(f"Session period: {session_start} → {end_time}")

            # Get history from MT5
            mt5 = get_mt5()

            # Get ALL deals (NO magic filter)
            deals = mt5.history_deals_get(session_start, end_time)

            if deals is None:
                logger.warning("Failed to retrieve history deals from MT5")
                return {
                    'starting_balance': current_equity,
                    'net_realized_pnl': 0.0,
                    'total_commission': 0.0,
                    'trade_count': 0
                }

            # Calculate profit and commission (NO FILTER)
            total_profit = 0.0
            total_commission = 0.0
            count = 0

            for deal in deals:
                # Only count OUT (close) deals, not IN (open)
                if deal.entry == 1:  # OUT = close position
                    total_profit += deal.profit
                    total_commission += deal.commission
                    count += 1

                    logger.debug(f"  Deal #{deal.ticket}: "
                               f"{deal.symbol} P&L=${deal.profit:.2f} "
                               f"Comm=${deal.commission:.2f}")

            # Calculate net P&L
            net_realized_pnl = total_profit - abs(total_commission)

            # Calculate starting balance
            # Starting Balance = Current Equity - Net P&L
            starting_balance = current_equity - net_realized_pnl

            # Update internal state
            self.starting_balance = starting_balance
            self.max_risk_limit = starting_balance * self.max_risk_pct
            self.net_realized_pnl = net_realized_pnl
            self.total_commission = abs(total_commission)

            logger.info("=" * 70)
            logger.info("DAILY HISTORY LOADED:")
            logger.info(f"  Closed trades: {count}")
            logger.info(f"  Total Profit: ${total_profit:,.2f}")
            logger.info(f"  Total Commission: ${abs(total_commission):,.2f}")
            logger.info(f"  Net Realized P&L: ${net_realized_pnl:,.2f}")
            logger.info(f"  Current Equity: ${current_equity:,.2f}")
            logger.info(f"  Starting Balance: ${starting_balance:,.2f}")
            logger.info("=" * 70)

            if net_realized_pnl != 0:
                logger.warning(f"⚠️ Continuing from earlier session with ${net_realized_pnl:,.2f} net P&L")

            return {
                'starting_balance': starting_balance,
                'net_realized_pnl': net_realized_pnl,
                'total_commission': abs(total_commission),
                'trade_count': count
            }

        except Exception as e:
            logger.error(f"Failed to load daily history: {e}")
            return {
                'starting_balance': current_equity,
                'net_realized_pnl': 0.0,
                'total_commission': 0.0,
                'trade_count': 0
            }

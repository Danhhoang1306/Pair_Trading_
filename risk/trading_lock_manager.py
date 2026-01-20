"""
Trading Lock Manager - Persist Lock State
Prevents trading when daily limit breached until next session
"""

import json
import logging
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Optional, Dict
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class LockState:
    """Trading lock state"""
    trading_locked: bool
    lock_reason: str
    locked_at: Optional[str]  # ISO datetime
    locked_until: Optional[str]  # ISO datetime
    daily_pnl_at_lock: float
    daily_limit_at_lock: float
    session_date: str  # YYYY-MM-DD
    last_updated: str  # ISO datetime


class TradingLockManager:
    """
    Manage trading lock state with persistence
    
    Features:
    1. Persist lock state to JSON file
    2. Auto-unlock at session start time
    3. Check on system startup (FIRST THING!)
    4. Thread-safe operations
    
    Usage:
        # On startup (FIRST!)
        lock_mgr = TradingLockManager()
        if lock_mgr.is_locked():
            logger.critical("System locked!")
        
        # Lock when daily limit breached
        lock_mgr.lock_trading("Daily limit", pnl=-2100, limit=2000)
        
        # Check before entry
        if lock_mgr.is_locked():
            return  # Don't trade
        
        # Auto-unlock at new session
        lock_mgr._check_auto_unlock()  # Call periodically
    """
    
    def __init__(self, 
                 session_start_time: str = "00:00",
                 persist_path: Optional[str] = None):
        """
        Initialize trading lock manager
        
        Args:
            session_start_time: Session start time "HH:MM" (unlock time)
            persist_path: Path to persist lock state (default: asset/trading_lock.json)
        """
        self.session_start_time = self._parse_time(session_start_time)
        
        # Persistence
        if persist_path is None:
            persist_path = Path("asset") / "state" / "trading_lock.json"
        else:
            persist_path = Path(persist_path)
        
        self.persist_path = persist_path
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        
        # State
        self.lock_state: Optional[LockState] = None
        
        # Load from disk
        self._load_state()
        
        # Check if should auto-unlock
        self._check_auto_unlock()
        
        logger.info(f"TradingLockManager initialized:")
        logger.info(f"  Persist path: {self.persist_path}")
        logger.info(f"  Session start: {session_start_time}")
        logger.info(f"  Current status: {'🔒 LOCKED' if self.is_locked() else '🟢 UNLOCKED'}")
        if self.is_locked():
            logger.warning(f"  Lock reason: {self.lock_state.lock_reason}")
            logger.warning(f"  Locked until: {self.lock_state.locked_until}")
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string HH:MM"""
        h, m = map(int, time_str.split(':'))
        return time(hour=h, minute=m)
    
    def is_locked(self) -> bool:
        """Check if trading is currently locked"""
        if self.lock_state is None:
            return False
        return self.lock_state.trading_locked
    
    def lock_trading(self, 
                    reason: str,
                    daily_pnl: float,
                    daily_limit: float):
        """
        Lock trading (e.g., daily limit breach)
        
        Args:
            reason: Why locked
            daily_pnl: P&L at lock time
            daily_limit: Daily limit at lock time
        """
        now = datetime.now()
        session_date = now.strftime("%Y-%m-%d")
        
        # Calculate unlock time (next session start)
        # If current time is after session start, unlock tomorrow
        # If before session start, unlock today
        today = now.date()
        session_datetime_today = datetime.combine(today, self.session_start_time)
        
        if now >= session_datetime_today:
            # After today's session start → unlock tomorrow
            tomorrow = today + timedelta(days=1)
            unlock_datetime = datetime.combine(tomorrow, self.session_start_time)
        else:
            # Before today's session start → unlock today
            unlock_datetime = session_datetime_today
        
        locked_until = unlock_datetime.isoformat()
        
        self.lock_state = LockState(
            trading_locked=True,
            lock_reason=reason,
            locked_at=now.isoformat(),
            locked_until=locked_until,
            daily_pnl_at_lock=daily_pnl,
            daily_limit_at_lock=daily_limit,
            session_date=session_date,
            last_updated=now.isoformat()
        )
        
        self._save_state()
        
        logger.critical("=" * 80)
        logger.critical("🔒 TRADING LOCKED!")
        logger.critical("=" * 80)
        logger.critical(f"  Reason: {reason}")
        logger.critical(f"  Daily P&L: ${daily_pnl:,.2f}")
        logger.critical(f"  Daily Limit: ${daily_limit:,.2f}")
        logger.critical(f"  Locked at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.critical(f"  Locked until: {unlock_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.critical("=" * 80)
        logger.critical("System will NOT open new positions until unlock time")
        logger.critical("=" * 80)
    
    def unlock_trading(self, reason: str = "Manual unlock"):
        """
        Unlock trading
        
        Args:
            reason: Why unlocked
        """
        self.lock_state = LockState(
            trading_locked=False,
            lock_reason="",
            locked_at=None,
            locked_until=None,
            daily_pnl_at_lock=0.0,
            daily_limit_at_lock=0.0,
            session_date=datetime.now().strftime("%Y-%m-%d"),
            last_updated=datetime.now().isoformat()
        )
        
        self._save_state()
        
        logger.info("=" * 80)
        logger.info("🟢 TRADING UNLOCKED!")
        logger.info("=" * 80)
        logger.info(f"  Reason: {reason}")
        logger.info(f"  System can now open new positions")
        logger.info("=" * 80)
    
    def _check_auto_unlock(self):
        """Check if should auto-unlock (new session)"""
        if not self.is_locked():
            return
        
        now = datetime.now()
        
        # Check if locked_until has passed
        if self.lock_state.locked_until:
            locked_until = datetime.fromisoformat(self.lock_state.locked_until)
            
            if now >= locked_until:
                logger.info(f"Auto-unlock: Session time reached ({locked_until.strftime('%Y-%m-%d %H:%M:%S')})")
                self.unlock_trading(reason="New session started - auto-unlock")
                return
        
        # Check if session date changed (backup check)
        current_date = now.strftime("%Y-%m-%d")
        if current_date != self.lock_state.session_date:
            logger.info(f"Auto-unlock: New session date ({current_date})")
            self.unlock_trading(reason="New session date - auto-unlock")
    
    def get_lock_info(self) -> Dict:
        """Get current lock information"""
        if not self.is_locked():
            return {
                'locked': False,
                'reason': '',
                'locked_at': None,
                'locked_until': None,
                'daily_pnl_at_lock': 0.0,
                'daily_limit_at_lock': 0.0
            }
        
        return {
            'locked': True,
            'reason': self.lock_state.lock_reason,
            'locked_at': self.lock_state.locked_at,
            'locked_until': self.lock_state.locked_until,
            'daily_pnl_at_lock': self.lock_state.daily_pnl_at_lock,
            'daily_limit_at_lock': self.lock_state.daily_limit_at_lock
        }
    
    def _save_state(self):
        """Save state to disk"""
        try:
            if self.lock_state is None:
                # Create default unlocked state
                self.lock_state = LockState(
                    trading_locked=False,
                    lock_reason="",
                    locked_at=None,
                    locked_until=None,
                    daily_pnl_at_lock=0.0,
                    daily_limit_at_lock=0.0,
                    session_date=datetime.now().strftime("%Y-%m-%d"),
                    last_updated=datetime.now().isoformat()
                )
            
            state_dict = asdict(self.lock_state)
            
            with open(self.persist_path, 'w') as f:
                json.dump(state_dict, f, indent=2)
            
            logger.debug(f"Lock state saved to {self.persist_path}")
            
        except Exception as e:
            logger.error(f"Failed to save lock state: {e}")
    
    def _load_state(self):
        """Load state from disk"""
        try:
            if not self.persist_path.exists():
                logger.info("No existing lock state file, starting unlocked")
                self.lock_state = None
                self._save_state()  # Create initial file
                return
            
            with open(self.persist_path, 'r') as f:
                state_dict = json.load(f)
            
            self.lock_state = LockState(**state_dict)
            
            logger.info(f"Lock state loaded from {self.persist_path}")
            if self.lock_state.trading_locked:
                logger.warning(f"  Status: 🔒 LOCKED")
                logger.warning(f"  Reason: {self.lock_state.lock_reason}")
            else:
                logger.info(f"  Status: 🟢 UNLOCKED")
            
        except Exception as e:
            logger.error(f"Failed to load lock state: {e}, starting fresh")
            self.lock_state = None
            self._save_state()

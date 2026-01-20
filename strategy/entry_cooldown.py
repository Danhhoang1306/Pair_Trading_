"""
Entry Cooldown Manager - Z-Score Delta Approach
Prevents duplicate entries by tracking last entry z-score

Based on flowchart logic:
- Track last_z_entry for each direction
- Allow entry only if: current_z >= last_z_entry + scale_interval
- Optionally enforce minimum time between entries (safety)

Example:
    Entry 1: z=-2.0 ✅ (first entry)
             last_z_entry = -2.0
    
    Try:     z=-2.2 🚫 (Δz=0.2 < 0.5) - blocked
    Try:     z=-2.4 🚫 (Δz=0.4 < 0.5) - blocked
    Entry 2: z=-2.5 ✅ (Δz=0.5 >= 0.5) - allowed!
             last_z_entry = -2.5
"""

import logging
import time
import json
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class EntryRecord:
    """Record of last entry"""
    direction: str  # 'LONG' or 'SHORT'
    zscore: float
    timestamp: float
    

class EntryCooldownManager:
    """
    Z-Score Delta Entry Manager
    
    PRIMARY RULE: Z-score spacing
    - Block entry if |current_z - last_z| < scale_interval
    
    SECONDARY RULE: Minimum time (safety)
    - Block entry if time_since_entry < min_time_between
    
    Rules align with pyramiding logic for consistency.
    """
    
    def __init__(self, 
                 scale_interval: float = 0.5,
                 min_time_between: int = 60,
                 persist_path: Optional[str] = None):
        """
        Initialize Z-delta entry manager
        
        Args:
            scale_interval: Minimum z-score movement to allow entry (default 0.5)
            min_time_between: Minimum time between entries in seconds (default 60s, safety)
            persist_path: Path to persist last_z_entry (default: asset/last_z_entry.json)
        """
        self.scale_interval = scale_interval
        self.min_time_between = min_time_between
        
        # Persistence
        if persist_path is None:
            persist_path = Path("asset") / "state" / "last_z_entry.json"
        else:
            persist_path = Path(persist_path)
        
        self.persist_path = persist_path
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        
        # State
        self.last_long_entry: Optional[EntryRecord] = None
        self.last_short_entry: Optional[EntryRecord] = None
        
        # Load from disk
        self._load_state()
        
        logger.info(f"EntryCooldownManager initialized (Z-Delta Approach):")
        logger.info(f"  Scale interval: {scale_interval} (minimum Δz for entry)")
        logger.info(f"  Min time between: {min_time_between}s (safety)")
        logger.info(f"  Persist path: {self.persist_path}")
        
        if self.last_long_entry:
            logger.info(f"  Loaded LONG: last_z={self.last_long_entry.zscore:.3f}")
        if self.last_short_entry:
            logger.info(f"  Loaded SHORT: last_z={self.last_short_entry.zscore:.3f}")
    
    def can_enter(self, direction: str, current_z: float) -> bool:
        """
        Check if entry is allowed (PRIMARY: Z-delta, SECONDARY: time)
        
        Args:
            direction: 'LONG' or 'SHORT'
            current_z: Current z-score
            
        Returns:
            True if entry allowed, False if blocked
        """
        current_time = time.time()
        
        if direction == 'LONG':
            last_entry = self.last_long_entry
        elif direction == 'SHORT':
            last_entry = self.last_short_entry
        else:
            logger.warning(f"Invalid direction: {direction}")
            return False
        
        # No previous entry - allow
        if last_entry is None:
            logger.debug(f"First {direction} entry - allowed")
            return True
        
        # ========== PRIMARY RULE: Z-SCORE SPACING ==========
        z_delta = abs(current_z - last_entry.zscore)
        
        if z_delta < self.scale_interval:
            logger.info(f"🚫 Entry BLOCKED - insufficient z-score movement:")
            logger.info(f"   Direction: {direction}")
            logger.info(f"   Last z: {last_entry.zscore:.3f} → Current z: {current_z:.3f}")
            logger.info(f"   Δz: {z_delta:.3f} < {self.scale_interval} (need {self.scale_interval - z_delta:.3f} more)")
            logger.info(f"   Rule: Z-DELTA SPACING")
            return False
        
        # ========== SECONDARY RULE: MIN TIME (SAFETY) ==========
        time_since_entry = current_time - last_entry.timestamp
        
        if time_since_entry < self.min_time_between:
            logger.info(f"🚫 Entry BLOCKED - too soon (safety check):")
            logger.info(f"   Direction: {direction}")
            logger.info(f"   Time since last: {time_since_entry:.0f}s < {self.min_time_between}s")
            logger.info(f"   Wait: {self.min_time_between - time_since_entry:.0f}s")
            logger.info(f"   Rule: MIN TIME SAFETY")
            return False
        
        # Both checks passed
        logger.info(f"✅ Entry ALLOWED:")
        logger.info(f"   Direction: {direction}")
        logger.info(f"   Last z: {last_entry.zscore:.3f} → Current z: {current_z:.3f}")
        logger.info(f"   Δz: {z_delta:.3f} >= {self.scale_interval} ✅")
        logger.info(f"   Time: {time_since_entry:.0f}s >= {self.min_time_between}s ✅")
        return True
    
    def mark_entry(self, direction: str, zscore: float):
        """
        Mark entry execution - save last_z_entry
        
        Args:
            direction: 'LONG' or 'SHORT'
            zscore: Entry z-score
        """
        entry_record = EntryRecord(
            direction=direction,
            zscore=zscore,
            timestamp=time.time()
        )
        
        if direction == 'LONG':
            self.last_long_entry = entry_record
            logger.info(f"📝 Marked LONG entry: last_z_entry = {zscore:.3f}")
        elif direction == 'SHORT':
            self.last_short_entry = entry_record
            logger.info(f"📝 Marked SHORT entry: last_z_entry = {zscore:.3f}")
        
        # Persist to disk
        self._save_state()
    
    def reset(self, direction: Optional[str] = None):
        """
        Reset last_z_entry (e.g., after position close)
        
        Args:
            direction: Reset specific direction, or None for all
        """
        if direction == 'LONG' or direction is None:
            self.last_long_entry = None
            logger.info("🔄 Reset LONG: last_z_entry = None")
        
        if direction == 'SHORT' or direction is None:
            self.last_short_entry = None
            logger.info("🔄 Reset SHORT: last_z_entry = None")
        
        # Persist to disk
        self._save_state()
    
    def get_status(self, direction: str) -> Dict:
        """Get current status"""
        if direction == 'LONG':
            last_entry = self.last_long_entry
        else:
            last_entry = self.last_short_entry
        
        if last_entry is None:
            return {
                'has_last_entry': False,
                'last_zscore': None,
                'last_timestamp': None,
                'time_since_entry': None
            }
        
        time_since_entry = time.time() - last_entry.timestamp
        
        return {
            'has_last_entry': True,
            'last_zscore': last_entry.zscore,
            'last_timestamp': datetime.fromtimestamp(last_entry.timestamp),
            'time_since_entry': time_since_entry
        }
    
    def _save_state(self):
        """Save state to disk"""
        try:
            state = {
                'long': asdict(self.last_long_entry) if self.last_long_entry else None,
                'short': asdict(self.last_short_entry) if self.last_short_entry else None,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.persist_path, 'w') as f:
                json.dump(state, f, indent=2)
            
            logger.debug(f"State saved to {self.persist_path}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def _load_state(self):
        """Load state from disk"""
        try:
            if not self.persist_path.exists():
                logger.debug("No previous state found - starting fresh")
                return
            
            with open(self.persist_path, 'r') as f:
                state = json.load(f)
            
            # Restore LONG
            if state.get('long'):
                self.last_long_entry = EntryRecord(**state['long'])
            
            # Restore SHORT
            if state.get('short'):
                self.last_short_entry = EntryRecord(**state['short'])
            
            logger.info(f"State loaded from {self.persist_path}")
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
    


# Global instance (singleton pattern)
_entry_cooldown_manager = None

def get_entry_cooldown_manager(scale_interval: float = 0.5, 
                                min_time_between: int = 60,
                                persist_path: Optional[str] = None) -> EntryCooldownManager:
    """Get or create global cooldown manager"""
    global _entry_cooldown_manager
    if _entry_cooldown_manager is None:
        _entry_cooldown_manager = EntryCooldownManager(
            scale_interval=scale_interval,
            min_time_between=min_time_between,
            persist_path=persist_path
        )
    return _entry_cooldown_manager

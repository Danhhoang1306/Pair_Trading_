"""
Position Persistence Manager
Saves and restores positions across system restarts

Flow:
1. Position opened → Save to disk
2. System crash/restart → Load from disk
3. Check if position still exists on MT5
4. If exists → Continue managing
5. If not exists → Delete from disk
6. Position closed → Delete from disk
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from core.mt5_manager import get_mt5

logger = logging.getLogger(__name__)


@dataclass
class PersistedPosition:
    """Position data to persist"""
    # Core identification
    position_id: str
    spread_id: str
    mt5_ticket: int
    
    # Position details
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    volume: float
    entry_price: float
    entry_time: str
    
    # Metadata
    entry_zscore: float
    hedge_ratio: float
    is_primary: bool  # True if primary, False if secondary
    
    # Timestamps
    created_at: str
    last_updated: str


class PositionPersistence:
    """
    Manages position persistence to disk
    
    File structure:
    positions/
        active_positions.json      # All active positions
        spread_XXXXX.json         # Individual spread backup
        history/
            closed_XXXXX.json     # Closed positions (for audit)
    """
    
    def __init__(self, data_dir: str = "positions"):
        """
        Initialize persistence manager
        
        Args:
            data_dir: Directory to store position files
        """
        self.data_dir = Path(data_dir)
        self.active_file = self.data_dir / "active_positions.json"
        self.history_dir = self.data_dir / "history"
        
        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"PositionPersistence initialized (dir={data_dir})")
    
    def save_position(self, position: PersistedPosition):
        """
        Save position to disk (atomic write)
        
        Args:
            position: Position to save
        """
        try:
            # Load current positions
            positions = self._load_active_positions()
            
            # Update or add position
            positions[position.position_id] = asdict(position)
            
            # Save atomically (write to temp, then rename)
            temp_file = self.active_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(positions, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.active_file)
            
            # Also save individual spread file as backup
            spread_file = self.data_dir / f"spread_{position.spread_id}.json"
            spread_positions = self._get_spread_positions(positions, position.spread_id)
            with open(spread_file, 'w') as f:
                json.dump(spread_positions, f, indent=2)
            
            logger.info(f"✓ Position saved: {position.position_id} (MT5 ticket: {position.mt5_ticket})")
            
        except Exception as e:
            logger.error(f"Failed to save position {position.position_id}: {e}")
    
    def load_active_positions(self) -> Dict[str, PersistedPosition]:
        """
        Load all active positions from disk
        
        Returns:
            Dict of position_id -> PersistedPosition
        """
        positions_dict = self._load_active_positions()
        
        # Convert to PersistedPosition objects
        positions = {}
        for pos_id, pos_data in positions_dict.items():
            try:
                positions[pos_id] = PersistedPosition(**pos_data)
            except Exception as e:
                logger.error(f"Failed to load position {pos_id}: {e}")
        
        logger.info(f"Loaded {len(positions)} active positions from disk")
        return positions
    
    def delete_position(self, position_id: str):
        """
        Delete position from active storage
        
        Args:
            position_id: Position to delete
        """
        try:
            positions = self._load_active_positions()
            
            if position_id not in positions:
                logger.warning(f"Position {position_id} not found in storage")
                return
            
            position_data = positions.pop(position_id)
            
            # Save updated active positions
            with open(self.active_file, 'w') as f:
                json.dump(positions, f, indent=2)
            
            logger.info(f"✓ Position deleted: {position_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete position {position_id}: {e}")
    
    def clear_all_positions(self):
        """
        Clear all active positions from disk
        Used for emergency close or system reset
        """
        try:
            # Simply overwrite with empty dict
            with open(self.active_file, 'w') as f:
                json.dump({}, f, indent=2)
            
            logger.info("✓ Cleared all active positions from disk")
        except Exception as e:
            logger.error(f"Failed to clear all positions: {e}")
    
    def delete_spread(self, spread_id: str):
        """
        Delete all positions for a spread
        
        Args:
            spread_id: Spread to delete
        """
        try:
            positions = self._load_active_positions()
            
            # Find positions for this spread
            to_delete = [
                pos_id for pos_id, pos_data in positions.items()
                if pos_data.get('spread_id') == spread_id
            ]
            
            # Delete them
            for pos_id in to_delete:
                positions.pop(pos_id)
            
            # Save updated positions
            with open(self.active_file, 'w') as f:
                json.dump(positions, f, indent=2)
            
            # Delete spread backup file
            spread_file = self.data_dir / f"spread_{spread_id}.json"
            if spread_file.exists():
                spread_file.unlink()
            
            logger.info(f"✓ Spread deleted: {spread_id} ({len(to_delete)} positions)")
            
        except Exception as e:
            logger.error(f"Failed to delete spread {spread_id}: {e}")
    
    def archive_spread(self, spread_id: str, reason: str = "closed"):
        """
        Move spread to history (for audit trail)
        
        Args:
            spread_id: Spread to archive
            reason: Reason for archiving
        """
        try:
            positions = self._load_active_positions()
            spread_positions = self._get_spread_positions(positions, spread_id)
            
            if not spread_positions:
                logger.warning(f"No positions found for spread {spread_id}")
                return
            
            # Add metadata
            archive_data = {
                'spread_id': spread_id,
                'closed_at': datetime.now().isoformat(),
                'reason': reason,
                'positions': spread_positions
            }
            
            # Save to history
            archive_file = self.history_dir / f"closed_{spread_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(archive_file, 'w') as f:
                json.dump(archive_data, f, indent=2)
            
            # Delete from active
            self.delete_spread(spread_id)
            
            logger.info(f"✓ Spread archived: {spread_id} → {archive_file.name}")
            
        except Exception as e:
            logger.error(f"Failed to archive spread {spread_id}: {e}")
    
    def get_spread_positions(self, spread_id: str) -> List[PersistedPosition]:
        """
        Get all positions for a spread
        
        Args:
            spread_id: Spread ID
            
        Returns:
            List of positions
        """
        positions_dict = self._load_active_positions()
        spread_dict = self._get_spread_positions(positions_dict, spread_id)
        
        positions = []
        for pos_data in spread_dict.values():
            try:
                positions.append(PersistedPosition(**pos_data))
            except Exception as e:
                logger.error(f"Failed to parse position: {e}")
        
        return positions
    
    def _load_active_positions(self) -> Dict:
        """Load active positions JSON"""
        if not self.active_file.exists():
            return {}
        
        try:
            with open(self.active_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load active positions: {e}")
            return {}
    
    def _get_spread_positions(self, positions: Dict, spread_id: str) -> Dict:
        """Filter positions by spread_id"""
        return {
            pos_id: pos_data
            for pos_id, pos_data in positions.items()
            if pos_data.get('spread_id') == spread_id
        }
    
    def verify_mt5_position(self, mt5_ticket: int) -> bool:
        """
        Verify if position still exists on MT5

        Args:
            mt5_ticket: MT5 ticket number

        Returns:
            True if position exists on MT5
        """
        try:
            mt5 = get_mt5()

            # Get position by ticket
            position = mt5.positions_get(ticket=mt5_ticket)
            
            if position is None or len(position) == 0:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify MT5 position {mt5_ticket}: {e}")
            return False
    
    def cleanup_orphaned_positions(self):
        """
        Remove positions from storage that don't exist on MT5
        Called on system startup
        """
        logger.info("Checking for orphaned positions...")
        
        positions = self._load_active_positions()
        orphaned = []
        
        for pos_id, pos_data in positions.items():
            mt5_ticket = pos_data.get('mt5_ticket')
            if mt5_ticket and not self.verify_mt5_position(mt5_ticket):
                orphaned.append(pos_id)
                logger.warning(f"Orphaned position found: {pos_id} (MT5 ticket {mt5_ticket} not found)")
        
        # Remove orphaned positions
        for pos_id in orphaned:
            positions.pop(pos_id)
        
        if orphaned:
            with open(self.active_file, 'w') as f:
                json.dump(positions, f, indent=2)
            logger.info(f"✓ Removed {len(orphaned)} orphaned positions")
        else:
            logger.info("✓ No orphaned positions found")
    
    def get_statistics(self) -> Dict:
        """Get persistence statistics"""
        positions = self._load_active_positions()
        
        # Count spreads
        spread_ids = set(pos_data.get('spread_id') for pos_data in positions.values())
        
        # Count history files
        history_files = list(self.history_dir.glob('closed_*.json'))
        
        return {
            'active_positions': len(positions),
            'active_spreads': len(spread_ids),
            'history_count': len(history_files),
            'storage_location': str(self.data_dir.absolute())
        }


# Example usage
if __name__ == '__main__':
    persistence = PositionPersistence()
    
    # Save position
    pos = PersistedPosition(
        position_id='pos_123',
        spread_id='spread_abc',
        mt5_ticket=12345,
        symbol='XAUUSD',
        side='SHORT',
        volume=0.02,
        entry_price=4300.00,
        entry_time=datetime.now().isoformat(),
        entry_zscore=1.75,
        hedge_ratio=0.8458,
        is_primary=True,
        created_at=datetime.now().isoformat(),
        last_updated=datetime.now().isoformat()
    )
    
    persistence.save_position(pos)
    
    # Load positions
    positions = persistence.load_active_positions()
    print(f"Loaded {len(positions)} positions")
    
    # Cleanup orphaned
    persistence.cleanup_orphaned_positions()
    
    # Stats
    stats = persistence.get_statistics()
    print(stats)

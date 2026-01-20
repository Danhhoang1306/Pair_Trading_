"""
Setup Flag Manager
Manages active setup state for startup recovery
"""
import json
from pathlib import Path
from datetime import datetime
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SetupFlagManager:
    """
    Manages setup flag to determine if recovery is needed
    
    Flag = True: Setup is ACTIVE (positions open) - need recovery check
    Flag = False: No active setup - start fresh
    """
    
    def __init__(self, data_dir: Path):
        """Initialize flag manager"""
        self.data_dir = Path(data_dir)
        self.flag_file = self.data_dir / 'active_setup_flag.json'
        
        # Ensure directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def is_setup_active(self) -> bool:
        """
        Check if there's an active setup
        
        Returns:
            True if setup is active (positions open)
            False if no setup or setup completed
        """
        if not self.flag_file.exists():
            return False
        
        try:
            with open(self.flag_file, 'r') as f:
                data = json.load(f)
                return data.get('active', False)
        except Exception as e:
            logger.error(f"Failed to read setup flag: {e}")
            return False
    
    def mark_setup_active(self, spread_id: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Mark setup as ACTIVE
        Called when first position of a setup is opened
        
        Args:
            spread_id: ID of the spread
            metadata: Optional metadata about the setup
        """
        data = {
            'active': True,
            'spread_id': spread_id,
            'activated_at': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        
        try:
            with open(self.flag_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"✅ Setup flag: ACTIVE (spread: {spread_id[:8]})")
        except Exception as e:
            logger.error(f"Failed to mark setup active: {e}")
    
    def mark_setup_inactive(self, reason: str = "Setup closed"):
        """
        Mark setup as INACTIVE
        Called when all positions are closed (setup complete)
        
        Args:
            reason: Reason for deactivation
        """
        data = {
            'active': False,
            'deactivated_at': datetime.now().isoformat(),
            'reason': reason
        }
        
        try:
            with open(self.flag_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"✅ Setup flag: INACTIVE ({reason})")
        except Exception as e:
            logger.error(f"Failed to mark setup inactive: {e}")
    
    def get_setup_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about active setup
        
        Returns:
            Setup info dict or None if no active setup
        """
        if not self.flag_file.exists():
            return None
        
        try:
            with open(self.flag_file, 'r') as f:
                data = json.load(f)
                if data.get('active', False):
                    return data
                return None
        except Exception as e:
            logger.error(f"Failed to read setup info: {e}")
            return None
    
    def clear_flag(self):
        """Remove flag file (reset state)"""
        try:
            if self.flag_file.exists():
                self.flag_file.unlink()
                logger.info("✅ Setup flag cleared")
        except Exception as e:
            logger.error(f"Failed to clear flag: {e}")

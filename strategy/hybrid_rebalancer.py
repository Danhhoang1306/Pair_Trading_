"""
Hybrid Rebalancing System - Volume Rebalancing (System 3)

⚠️  MIGRATION NOTE: Pyramiding functionality has been moved to SimpleUnifiedExecutor.
    This module now focuses on:
    - Volume rebalancing (maintain hedge ratio)
    - Position tracking
    - Configuration storage (scale_interval, initial_fraction used by SimpleUnifiedExecutor)

Features:
1. Volume Rebalancing: Maintain hedge ratio as it changes
2. Threshold-based: Only adjust when drift > threshold
3. Position tracking: Register and track active positions
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class VolumeAdjustment:
    """Volume adjustment action to maintain hedge ratio"""
    spread_id: str
    symbol: str
    action: str  # 'BUY' or 'SELL'
    quantity: float
    reason: str
    old_hedge: float
    new_hedge: float
    drift_pct: float


class HybridRebalancer:
    """
    Volume Rebalancing System (System 3)

    ⚠️  Pyramiding has been moved to SimpleUnifiedExecutor.

    This class now handles:
    1. Volume rebalancing (maintain hedge ratio)
    2. Position tracking and registration
    3. Configuration storage (scale_interval, initial_fraction) for SimpleUnifiedExecutor

    Configuration:
    - scale_interval: Used by SimpleUnifiedExecutor for pyramiding
    - initial_fraction: Used by SimpleUnifiedExecutor for position sizing
    - Hedge drift threshold: Minimum drift to trigger adjustment
    """

    def __init__(self,
                 # Config for SimpleUnifiedExecutor (stored here for backward compatibility)
                 scale_interval: float = 0.5,
                 max_zscore: float = 3.0,
                 initial_fraction: float = 0.33,

                 # Volume rebalancing config
                 hedge_drift_threshold: float = 0.05,  # 5% (DEPRECATED - not used)
                 min_absolute_drift: float = 0.01,  # 0.01 lots
                 min_adjustment_interval: int = 3600,  # DEPRECATED - cooldown removed
                 enable_hedge_adjustment: bool = True):
        """
        Initialize HybridRebalancer (now focuses on Volume Rebalancing)

        Args:
            scale_interval: Z-score interval (used by SimpleUnifiedExecutor for pyramiding)
            max_zscore: Maximum z-score (used by SimpleUnifiedExecutor for stop loss)
            initial_fraction: Position size fraction (used by SimpleUnifiedExecutor)
            hedge_drift_threshold: DEPRECATED - not used (natural protections handle throttling)
            min_absolute_drift: Minimum absolute drift in lots (e.g., 0.01)
            min_adjustment_interval: DEPRECATED - cooldown removed (relies on natural protections)
            enable_hedge_adjustment: Enable/disable volume rebalancing
        """
        # Config for SimpleUnifiedExecutor (stored here for backward compatibility)
        self.scale_interval = scale_interval
        self.max_zscore = max_zscore
        self.initial_fraction = initial_fraction

        # Volume rebalancing (System 3)
        self.hedge_drift_threshold = hedge_drift_threshold  # DEPRECATED: Not used anymore
        self.min_absolute_drift = min_absolute_drift
        self.min_adjustment_interval = min_adjustment_interval  # DEPRECATED: Not used anymore
        self.enable_volume_rebalancing = enable_hedge_adjustment  # New name
        self.enable_hedge_adjustment = enable_hedge_adjustment  # Backward compatibility

        # Tracking
        self.active_positions: Dict[str, Dict] = {}
        self.last_adjustment: Dict[str, float] = {}  # spread_id -> timestamp (tracking only)
        self.adjustment_history: List[VolumeAdjustment] = []

        logger.info(f"HybridRebalancer initialized:")
        logger.info(f"  Config Storage: scale_interval={scale_interval}, max_z={max_zscore}, fraction={initial_fraction:.1%}")
        logger.info(f"    → Used by SimpleUnifiedExecutor for pyramiding")
        logger.info(f"  Volume Rebalancing (System 3): min_drift={min_absolute_drift} lots, enabled={enable_hedge_adjustment}")
        logger.info(f"  ⚡ No cooldown - relies on natural protections (min volume, quality check)")

    def calculate_pyramiding_levels(self,
                                    initial_zscore: float,
                                    side: str) -> List:
        """
        DEPRECATED: Pyramiding is now handled by SimpleUnifiedExecutor.
        This method is kept for backward compatibility but should not be used.
        """
        logger.warning("[HYBRID] ⚠️  calculate_pyramiding_levels() is deprecated - use SimpleUnifiedExecutor instead")
        return []  # Return empty list

    def register_position(self,
                          spread_id: str,
                          side: str,
                          entry_zscore: float,
                          entry_hedge_ratio: float,
                          primary_lots: float,
                          secondary_lots: float,
                          total_position_size: float,
                          primary_symbol: str = 'XAUUSD',
                          secondary_symbol: str = 'XAGUSD') -> Dict:
        """
        Register position for volume rebalancing tracking

        ⚠️  Pyramiding is now handled by SimpleUnifiedExecutor.
            This method only tracks positions for volume rebalancing.

        Args:
            spread_id: Unique identifier
            side: 'LONG' or 'SHORT'
            entry_zscore: Entry z-score
            entry_hedge_ratio: Hedge ratio at entry
            primary_lots: Actual primary lots
            secondary_lots: Actual secondary lots
            total_position_size: Planned total size (100%)
            primary_symbol: Primary symbol (e.g., BTCUSD, XAUUSD)
            secondary_symbol: Secondary symbol (e.g., ETHUSD, XAGUSD)
        """
        position_data = {
            'spread_id': spread_id,
            'side': side,
            'entry_zscore': entry_zscore,
            'entry_hedge_ratio': entry_hedge_ratio,
            'current_hedge_ratio': entry_hedge_ratio,  # Will be updated
            'primary_lots': primary_lots,
            'secondary_lots': secondary_lots,
            'total_position_size': total_position_size,
            'entry_time': datetime.now(),
            'last_adjustment_time': None,
            'primary_symbol': primary_symbol,
            'secondary_symbol': secondary_symbol
        }

        self.active_positions[spread_id] = position_data
        self.last_adjustment[spread_id] = time.time()

        logger.info(f"[HYBRID] Position {spread_id[:8]} registered for volume rebalancing")
        logger.info(f"  Symbols: {primary_symbol}/{secondary_symbol}")
        logger.info(f"  Entry hedge ratio: {entry_hedge_ratio:.4f}")
        logger.info(f"  Primary: {primary_lots:.4f} lots, Secondary: {secondary_lots:.4f} lots")
        logger.info(f"  Note: Pyramiding is handled by SimpleUnifiedExecutor")

        return position_data



    def check_volume_imbalance(self,
                               spread_id: str,
                               current_hedge_ratio: float,
                               current_zscore: float,
                               mt5_primary_lots: float = None,
                               mt5_secondary_lots: float = None) -> Optional[VolumeAdjustment]:
        """
        [SYSTEM-3] Volume rebalance theo ĐÚNG flowchart

        Args:
            spread_id: Spread ID
            current_hedge_ratio: Current beta (hedge ratio)
            current_zscore: Current z-score
            mt5_primary_lots: REAL MT5 primary volume (NET: LONG - SHORT)
            mt5_secondary_lots: REAL MT5 secondary volume (NET: LONG - SHORT)

        Logic:
        1. Calculate imbalance = primary - (secondary / beta)
        2. If imbalance > 0 (Primary oversized):
           -> Adjust SECONDARY leg
        3. If imbalance < 0 (Secondary oversized):
           -> Adjust PRIMARY leg
        """
        if not self.enable_volume_rebalancing:
            return None

        if spread_id not in self.active_positions:
            return None

        position = self.active_positions[spread_id]

        # Get current volumes - PREFER MT5 REAL DATA
        if mt5_primary_lots is not None and mt5_secondary_lots is not None:
            # Use REAL MT5 volumes (absolute values)
            primary_lots = abs(mt5_primary_lots)
            secondary_lots = abs(mt5_secondary_lots)
            logger.info(f"[VOLUME-SOURCE] Using REAL MT5 volumes: Primary={primary_lots:.4f}, Secondary={secondary_lots:.4f}")
        else:
            # Fallback to internal tracking (may be inaccurate!)
            primary_lots = abs(position['primary_lots'])
            secondary_lots = abs(position['secondary_lots'])
            logger.warning(f"[VOLUME-SOURCE] Using internal tracking (may be inaccurate!): Primary={primary_lots:.4f}, Secondary={secondary_lots:.4f}")

        # ========== STEP 1: Calculate Imbalance ==========
        primary_lots_target = abs(secondary_lots) / current_hedge_ratio
        imbalance_primary = abs(primary_lots) - primary_lots_target

        secondary_lots_target = abs(primary_lots) * current_hedge_ratio
        imbalance_secondary = abs(secondary_lots) - secondary_lots_target

        max_imbalance = max(abs(imbalance_primary), abs(imbalance_secondary))
        if max_imbalance < 0.05:  # chênh lệch lên đến 0.05 lots thì  mới cho qua
            return None


        # ========== STEP 2: Determine Action Based on Flowchart ==========
        adjust_symbol = None
        adjust_action = None
        needed_volume = 0.0
        reason = ""
        if imbalance_primary < 0:
            # primary am co nghia la  thuc te dang nhieu hon target
            # Volume needed = imbalance × hedge_ratio
            needed_volume = abs(imbalance_primary)

            # Check minimum volume threshold

            # Decision based on z-score
            if current_zscore > 0:
                adjust_leg = 'PRIMARY'
                adjust_action = 'SELL'
                reason = f"Primary oversized, z>0 -> BUY secondary {needed_volume:.4f}"
            else:
                adjust_leg = 'PRIMARY'
                adjust_action = 'BUY'
                reason = f"Primary oversized, z<0 -> SELL secondary {needed_volume:.4f}"


        else:  # imbalance_primary > 0 (target nhiều hơn thực tế -> thiếu primary)
            # Imbalance_primary > 0 có nghĩa là: Primary target > Primary actual
            # => Thiếu primary
            # Imbalance_secondary < 0 có nghĩa là: Secondary actual > Secondary target
            # => Thừa secondary

            # Khi thiếu primary và thừa secondary -> điều chỉnh SECONDARY
            needed_volume = abs(imbalance_secondary)

            # Decision based on z-score
            if current_zscore > 0:
                # Z > 0: Spread đang cao (primary cao, secondary thấp)
                # Thiếu primary -> nên SELL secondary để cân bằng
                adjust_leg = 'SECONDARY'
                adjust_action = 'BUY'
                reason = f"Primary short by {imbalance_primary:.4f}, z>0 -> SELL secondary {needed_volume:.4f}"
            else:
                # Z < 0: Spread đang thấp (primary thấp, secondary cao)
                # Thiếu primary + thừa secondary -> nên BUY secondary để cân bằng
                adjust_leg = 'SECONDARY'
                adjust_action = 'SELL'
                reason = f"Primary short by {imbalance_primary:.4f}, z<0 -> BUY secondary {needed_volume:.4f}"
                logger.info(f"  -> Decision: BUY secondary (z<0)")


        # ========== STEP 3: Validate and Round Volume ==========
        import math

        if abs(needed_volume) < self.min_absolute_drift:
            logger.debug(f"  Skip: needed volume {abs(needed_volume):.4f} < min {self.min_absolute_drift}")
            return None

        # Round to exchange requirements
        if adjust_leg == 'PRIMARY':
            min_volume = 0.01
            rebalance_volume = max(min_volume, math.ceil(abs(needed_volume) / 0.01) * 0.01)
            adjust_symbol = position.get('primary_symbol', 'BTCUSD')
        else:
            min_volume = 0.01
            rebalance_volume = max(min_volume, math.ceil(abs(needed_volume) / 0.01) * 0.01)
            adjust_symbol = position.get('secondary_symbol', 'ETHUSD')

        # ========== STEP 4: Create Adjustment ==========
        logger.info(f"[SYSTEM-3-VOLUME-REBALANCE] ✅ Executing:")
        logger.info(f"  Action: {adjust_action} {rebalance_volume:.4f} {adjust_symbol}")
        logger.info(f"  Reason: {reason}")
        logger.info(f"  Imbalance (Primary): {imbalance_primary:+.4f} lots, Z-Score: {current_zscore:+.3f}")

        drift_pct = abs(imbalance_primary) / (primary_lots + secondary_lots * current_hedge_ratio) \
            if (primary_lots + secondary_lots * current_hedge_ratio) > 0 else 0

        adjustment = VolumeAdjustment(
            spread_id=spread_id,
            symbol=adjust_symbol,
            action=adjust_action,
            quantity=rebalance_volume,
            reason=reason,
            old_hedge=position['current_hedge_ratio'],
            new_hedge=current_hedge_ratio,
            drift_pct=drift_pct
        )

        return adjustment

    def check_all_rebalancing(self,
                              current_zscore: float,
                              current_hedge_ratio: float,
                              mt5_primary_lots: float = None,
                              mt5_secondary_lots: float = None) -> Tuple[List[Dict], List[VolumeAdjustment]]:
        """
        Check volume adjustments for all positions

        ⚠️  DEPRECATED: Pyramiding has been moved to SimpleUnifiedExecutor.
            This method now ONLY checks volume rebalancing.
            Returns empty list for pyramiding_actions for backward compatibility.

        Args:
            current_zscore: Current z-score
            current_hedge_ratio: Current hedge ratio (beta)
            mt5_primary_lots: REAL MT5 primary NET lots (LONG - SHORT)
            mt5_secondary_lots: REAL MT5 secondary NET lots (LONG - SHORT)

        Returns:
            (pyramiding_actions, volume_adjustments)
            - pyramiding_actions: Always empty (deprecated)
            - volume_adjustments: List of volume adjustment actions
        """
        pyramiding_actions = []  # Always empty - pyramiding handled by SimpleUnifiedExecutor
        volume_adjustments = []

        for spread_id in list(self.active_positions.keys()):
            # Check volume imbalance (with z-score) - PASS REAL MT5 VOLUMES
            volume_action = self.check_volume_imbalance(
                spread_id,
                current_hedge_ratio,
                current_zscore,
                mt5_primary_lots=mt5_primary_lots,
                mt5_secondary_lots=mt5_secondary_lots
            )
            if volume_action:
                volume_adjustments.append(volume_action)

        return pyramiding_actions, volume_adjustments



    def mark_volume_adjusted(self,
                            spread_id: str,
                            adjustment: VolumeAdjustment,
                            executed_quantity: float):
        """[SYSTEM-3] Mark volume adjustment as executed"""
        if spread_id not in self.active_positions:
            logger.warning(f"[SYSTEM-3-REBALANCE] Cannot mark - {spread_id} not active")
            return

        position = self.active_positions[spread_id]
        
        # Store old value for logging
        old_secondary = position['secondary_lots']

        # Update position
        if adjustment.action == 'BUY':
            position['secondary_lots'] += executed_quantity
        else:  # SELL
            position['secondary_lots'] -= executed_quantity

        new_secondary = position['secondary_lots']
        
        position['current_hedge_ratio'] = adjustment.new_hedge
        position['last_adjustment_time'] = datetime.now()

        # Update tracking
        self.last_adjustment[spread_id] = time.time()
        self.adjustment_history.append(adjustment)

        logger.info(f"[SYSTEM-3-REBALANCE] ✅ Position updated for {spread_id[:8]}:")
        logger.info(f"  Primary: {position['primary_lots']:.4f} lots (unchanged)")
        logger.info(f"  Secondary: {old_secondary:.4f} -> {new_secondary:.4f} lots ({adjustment.action} {executed_quantity:.4f})")
        logger.info(f"  Hedge ratio: {adjustment.old_hedge:.4f} -> {adjustment.new_hedge:.4f}")

    def remove_position(self, spread_id: str):
        """Remove position from tracking"""
        if spread_id in self.active_positions:
            del self.active_positions[spread_id]
        if spread_id in self.last_adjustment:
            del self.last_adjustment[spread_id]

        logger.info(f"[HYBRID] Position {spread_id[:8]} removed")

    def clear_all(self):
        """Clear all active positions and tracking"""
        self.active_positions.clear()
        self.last_adjustment.clear()
        logger.info("[HYBRID] Cleared all active positions and tracking")

    def get_statistics(self) -> Dict:
        """Get rebalancing statistics"""
        total_positions = len(self.active_positions)
        total_adjustments = len(self.adjustment_history)

        if total_adjustments > 0:
            avg_drift = sum(a.drift_pct for a in self.adjustment_history) / total_adjustments
        else:
            avg_drift = 0.0

        return {
            'active_positions': total_positions,
            'total_adjustments': total_adjustments,
            'avg_drift_pct': avg_drift,
            'adjustment_enabled': self.enable_hedge_adjustment,
            'drift_threshold': self.hedge_drift_threshold
        }
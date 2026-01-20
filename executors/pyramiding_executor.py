"""
Pyramiding Executor - Handles pyramiding/scaling logic
Extracted from main_cli.py

⚠️  DEPRECATED: This executor is deprecated and will be removed in a future version.
    Use UnifiedPositionExecutor instead, which merges entry + pyramiding logic.

    Migration path:
    - Old: EntryExecutor (entry at z=±2.0) + PyramidingExecutor (pyramid at z=±2.5, ±3.0)
    - New: UnifiedPositionExecutor (all z-score levels handled uniformly)

    Reason: Entry and pyramiding are fundamentally the same operation (opening
    2-leg spread orders at specific z-score levels). No need for two separate
    executors with duplicated logic.

    See: executors/unified_position_executor.py
"""
import logging
import warnings

logger = logging.getLogger(__name__)


class PyramidingExecutor:
    """
    Handles pyramiding (scaling in) execution

    ⚠️  DEPRECATED: Use UnifiedPositionExecutor instead.
    """

    def __init__(self, trade_executor, rebalancer, position_monitor,
                 mt5_tickets, primary_symbol, secondary_symbol,
                 entry_cooldown=None, enable_entry_cooldown=True):
        self.trade_executor = trade_executor
        self.rebalancer = rebalancer
        self.position_monitor = position_monitor
        self.mt5_tickets = mt5_tickets
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol
        self.entry_cooldown = entry_cooldown
        self.enable_entry_cooldown = enable_entry_cooldown
        logger.info("PyramidingExecutor initialized")
        if enable_entry_cooldown and entry_cooldown:
            logger.info("  Entry cooldown: ENABLED (will update last_z_entry on pyramiding)")
    
    def execute(self, action, snapshot) -> bool:
        """Execute pyramiding adjustment - scale into existing position
        
        Args:
            action: Dict with pyramiding info (spread_id, level, side, etc)
            snapshot: MarketSnapshot object (NOT a dict!)
        """
        spread_id = action.get('spread_id', 'unknown')
        logger.info(f"[PYRAMID] Executing scale-in for {spread_id[:8]}")
        
        # Extract info from action dict
        level = action.get('level')
        position_size = action.get('position_size', 0)
        side = action.get('side', 'UNKNOWN')
        current_zscore = action.get('current_zscore', 0)
        
        # snapshot is passed directly, not in a dict!
        if not snapshot:
            logger.error("[PYRAMID] No snapshot available - cannot execute")
            return False
        
        logger.info(f"  Level: z={level.zscore if level else 'N/A':.2f}")
        logger.info(f"  Current z: {current_zscore:.3f}")
        logger.info(f"  Size per level: {position_size:.4f} lots")
        logger.info(f"  Side: {side}")
        
        # Calculate volumes for this pyramid level
        # Use position_size which is already calculated per level
        primary_volume = position_size
        secondary_volume = position_size * snapshot.hedge_ratio
        
        logger.info(f"  Primary volume: {primary_volume:.4f} lots")
        logger.info(f"  Secondary volume: {secondary_volume:.4f} lots")
        
        # Determine order types based on spread side
        if side == 'LONG':
            # LONG spread: BUY primary, SELL secondary
            primary_type = 'BUY'
            secondary_type = 'SELL'
        elif side == 'SHORT':
            # SHORT spread: SELL primary, BUY secondary
            primary_type = 'SELL'
            secondary_type = 'BUY'
        else:
            logger.error(f"[PYRAMID] Unknown side: {side}")
            return False
        
        logger.info(f"  Orders: {primary_type} {self.primary_symbol}, {secondary_type} {self.secondary_symbol}")
        
        # Execute orders
        try:
            # Execute primary order
            primary_result = self.trade_executor.place_market_order(
                symbol=self.primary_symbol,
                order_type=primary_type,
                volume=primary_volume,
                comment=f"PYRAMID:{spread_id[:8]}"
            )
            
            if not primary_result.success:
                logger.error(f"[PYRAMID] Primary order failed: {primary_result.error_description}")
                return False
            
            primary_ticket = primary_result.order_ticket
            logger.info(f"  ✅ Primary: {primary_type} {primary_volume:.4f} lots @ ticket {primary_ticket}")
            
            # Execute secondary order
            secondary_result = self.trade_executor.place_market_order(
                symbol=self.secondary_symbol,
                order_type=secondary_type,
                volume=secondary_volume,
                comment=f"PYRAMID:{spread_id[:8]}"
            )
            
            if not secondary_result.success:
                logger.error(f"[PYRAMID] Secondary order failed: {secondary_result.error_description}")
                # TODO: Consider closing primary position if secondary fails
                logger.warning(f"[PYRAMID] Primary position opened but secondary failed - HEDGE INCOMPLETE!")
                return False
            
            secondary_ticket = secondary_result.order_ticket
            logger.info(f"  ✅ Secondary: {secondary_type} {secondary_volume:.4f} lots @ ticket {secondary_ticket}")
            
            # Register tickets for monitoring (mt5_tickets is a dict, not a set!)
            self.mt5_tickets[primary_ticket] = self.primary_symbol
            self.mt5_tickets[secondary_ticket] = self.secondary_symbol
            
            # Start monitoring the new positions (use register_position, not add_position!)
            self.position_monitor.register_position(primary_ticket, self.primary_symbol)
            self.position_monitor.register_position(secondary_ticket, self.secondary_symbol)
            
            # Mark level as executed in rebalancer
            if level:
                level.executed = True
                logger.info(f"  ✅ Level z={level.zscore:.2f} marked as executed")

            # ========== UPDATE ENTRY COOLDOWN ==========
            # CRITICAL: Update last_z_entry to prevent duplicate pyramiding
            # when z-score oscillates near the threshold
            if self.enable_entry_cooldown and self.entry_cooldown and level:
                self.entry_cooldown.mark_entry(side, level.zscore)
                logger.info(f"  📝 Entry cooldown updated: last_z_entry = {level.zscore:.3f}")

            # ⚠️ CRITICAL: Update rebalancer volumes after pyramiding
            # Without this, rebalancer uses stale volumes and calculates wrong imbalance!
            if spread_id in self.rebalancer.active_positions:
                old_primary = self.rebalancer.active_positions[spread_id]['primary_lots']
                old_secondary = self.rebalancer.active_positions[spread_id]['secondary_lots']
                
                # Pyramiding always ADDS to existing position (same direction)
                # Both volumes are stored as absolute values
                new_primary = old_primary + abs(primary_result.volume)
                new_secondary = old_secondary + abs(secondary_result.volume)
                
                self.rebalancer.active_positions[spread_id]['primary_lots'] = new_primary
                self.rebalancer.active_positions[spread_id]['secondary_lots'] = new_secondary
                
                logger.info(f"[PYRAMID] 📊 Updated rebalancer volumes:")
                logger.info(f"  Primary: {old_primary:.4f} → {new_primary:.4f} lots")
                logger.info(f"  Secondary: {old_secondary:.4f} → {new_secondary:.4f} lots")
            else:
                logger.warning(f"[PYRAMID] ⚠️ Spread {spread_id[:8]} not in rebalancer - cannot update volumes!")
            
            logger.info(f"[PYRAMID] ✅ Scale-in complete for {spread_id[:8]}")
            return True
            
        except Exception as e:
            logger.error(f"[PYRAMID] Execution error: {e}", exc_info=True)
            return False


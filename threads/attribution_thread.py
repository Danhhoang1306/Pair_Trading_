"""
AttributionThread - Extracted from main_cli.py
"""
import time
import queue
import logging
from datetime import datetime
from core.mt5_manager import get_mt5
from .base_thread import BaseThread

logger = logging.getLogger(__name__)


class AttributionThread(BaseThread):
    """Thread worker for attribution thread"""
    
    def __init__(self, system):
        super().__init__("AttributionThread", system)
    
    def run(self):
        """Main thread loop"""
        logger.info("Attribution thread started (immediate first run, then 60s interval)")

        from analytics.pnl_attribution import get_attribution_engine, PositionSnapshot
        from datetime import datetime

        mt5 = get_mt5()
        attribution_engine = get_attribution_engine()
        
        first_run = True
        
        while self.system.running:
            try:
                # Sleep AFTER calculation (except first run)
                if not first_run:
                    time.sleep(60)  # Update every 60 seconds
                else:
                    # First run - wait 5 seconds for data thread to initialize
                    time.sleep(5)
                    first_run = False
                
                # Get current market snapshot
                snapshot = self.system.current_snapshot
                if not snapshot:
                    continue
                
                # Get all MT5 positions
                mt5_positions = mt5.positions_get()
                if not mt5_positions:
                    continue
                
                # Group by spread_id using persistence data
                # Load active positions from disk to get spread_id mapping
                persisted_positions = self.system.persistence.load_active_positions()
                
                # Build ticket → spread_id mapping
                ticket_to_spread = {}
                for pos_id, pers_pos in persisted_positions.items():
                    ticket_to_spread[pers_pos.mt5_ticket] = pers_pos.spread_id
                
                # Group MT5 positions by spread_id
                spreads = {}
                for pos in mt5_positions:
                    ticket = pos.ticket
                    
                    # Get spread_id from persistence
                    spread_id = ticket_to_spread.get(ticket)
                    
                    if not spread_id:
                        # Position not in persistence (shouldn't happen for our system)
                        logger.debug(f"Position {ticket} not found in persistence, skipping attribution")
                        continue
                    
                    # Determine leg by symbol (use configured symbols)
                    if pos.symbol == self.system.primary_symbol:
                        leg = "PRIMARY"
                    elif pos.symbol == self.system.secondary_symbol:
                        leg = "SECONDARY"
                    else:
                        leg = "UNKNOWN"
                    
                    if spread_id not in spreads:
                        spreads[spread_id] = {}
                    
                    spreads[spread_id][leg] = pos
                
                # Calculate attribution for each spread
                for spread_id, legs in spreads.items():
                    #  Track if we calculate new attribution for this spread
                    attribution_calculated = False
                    
                    # Identify primary and secondary positions
                    primary_pos = legs.get("PRIMARY")
                    secondary_pos = legs.get("SECONDARY")
                    
                    if not primary_pos or not secondary_pos:
                        logger.debug(f"Incomplete spread {spread_id}: missing PRIMARY or SECONDARY leg - skipping attribution")
                        logger.debug(f"  Available legs: {list(legs.keys())}")
                        #  Don't check hedge quality for incomplete spreads
                        continue
                    
                    # Total P&L from MT5 (includes REAL swap!)
                    total_pnl_mt5 = primary_pos.profit + secondary_pos.profit
                    
                    # Current snapshot for attribution
                    current_snapshot = PositionSnapshot(
                        timestamp=datetime.now(),
                        xau_bid=snapshot.primary_bid,
                        xau_ask=snapshot.primary_ask,
                        xag_bid=snapshot.secondary_bid,
                        xag_ask=snapshot.secondary_ask,
                        spread=snapshot.spread,
                        mean=snapshot.spread_mean,
                        std=snapshot.spread_std,
                        zscore=snapshot.zscore,
                        hedge_ratio=snapshot.hedge_ratio,
                        xau_volume=primary_pos.volume,
                        xag_volume=secondary_pos.volume,
                        xau_side='LONG' if primary_pos.type == mt5.ORDER_TYPE_BUY else 'SHORT',
                        xag_side='LONG' if secondary_pos.type == mt5.ORDER_TYPE_BUY else 'SHORT',
                        xau_price=primary_pos.price_current,
                        xag_price=secondary_pos.price_current
                    )
                    
                    # Calculate attribution
                    components = attribution_engine.calculate_attribution(
                        spread_id,
                        current_snapshot,
                        total_pnl_mt5
                    )
                    
                    # Store for GUI (most recent only)
                    self.current_attribution = components
                    
                    logger.debug(f"Attribution {spread_id}: "
                               f"Spread=${components.spread_pnl:.2f} ({components.spread_pnl_pct:.1f}%), "
                               f"Directional=${components.directional_pnl:.2f} ({components.directional_pnl_pct:.1f}%), "
                               f"HedgeQ={components.hedge_quality:.1%}")
                    
                    #  Flag to track if we calculated new attribution
                    attribution_calculated = True
                    
                    # ========== KILL-SWITCH LOGIC ==========
                    #  DISABLED - Attribution engine has bugs causing false triggers
                    # Problem: Shows directional P&L as 273297%! Clearly wrong.
                    # TODO: Re-enable after fixing attribution
                    if False and abs(components.directional_pnl_pct) > 80:
                        # Check if zscore is diverging (moving away from mean)
                        if spread_id in attribution_engine.positions:
                            entry_zscore = attribution_engine.positions[spread_id]['entry'].zscore
                            current_zscore = snapshot.zscore

                            # Diverging if absolute zscore increased
                            is_diverging = abs(current_zscore) > abs(entry_zscore)

                            if is_diverging:
                                logger.critical(f" KILL-SWITCH TRIGGERED for {spread_id}!")
                                logger.critical(f"   Directional: {components.directional_pnl_pct:.1f}% (> 80%)")
                                logger.critical(f"   Z-score: {entry_zscore:.2f} → {current_zscore:.2f} (diverging)")
                                logger.critical(f"   Hedge Quality: {components.hedge_quality:.1%}")

                                # Close ALL positions using fast CloseManager
                                # NOTE: Cannot close individual tickets, closes ALL with this magic number
                                try:
                                    from utils.fast_close_all import CloseManager
                                    logger.critical(f"Closing ALL positions via CloseManager...")
                                    manager = CloseManager(magic_number=self.system.magic_number, max_workers=100)
                                    close_result = manager.close_all()

                                    # Report results
                                    if close_result['success']:
                                        logger.critical(f" Emergency closed ALL positions successfully!")
                                        logger.critical(f"   Total closed: {close_result['total_closed']}")

                                        # Unregister from attribution
                                        try:
                                            attribution_engine.unregister_position(spread_id)
                                            logger.info(f"Unregistered {spread_id} from attribution")
                                        except Exception as unregister_error:
                                            logger.warning(f"Could not unregister {spread_id}: {unregister_error}")
                                    else:
                                        logger.critical(f" EMERGENCY CLOSE FAILED!")
                                        logger.critical(f"   Closed: {close_result['total_closed']}")
                                        logger.critical(f"   Failed: {close_result['total_failed']}")

                                except Exception as e:
                                    logger.error(f"Exception during emergency close: {e}")
                                    import traceback
                                    logger.error(traceback.format_exc())
                    
                    # ========== REBALANCE ALERT ==========
                    #  Only show warnings if we just calculated attribution (not old data)
                    if attribution_calculated and components.hedge_quality < 0.7:
                        logger.warning(f" HEDGE QUALITY LOW for {spread_id}!")
                        logger.warning(f"   Quality: {components.hedge_quality:.1%} (< 70%)")
                        logger.warning(f"   Directional: {components.directional_pnl_pct:.1f}%")
                        logger.warning(f"   Consider rebalancing")
                    
                    # ========== CRITICAL ALERT ==========
                    if attribution_calculated and components.hedge_quality < 0.5:
                        logger.critical(f" CRITICAL HEDGE FAILURE for {spread_id}!")
                        logger.critical(f"   Quality: {components.hedge_quality:.1%} (< 50%)")
                        logger.critical(f"   Strategy not working properly!")
                
            except Exception as e:
                logger.error(f"Attribution thread error: {e}")
                import traceback
                traceback.print_exc()
    

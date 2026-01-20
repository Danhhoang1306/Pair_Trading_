"""
Hedge Executor - Handles hedge adjustment logic
Extracted from main_cli.py
"""
import logging
from core.mt5_manager import get_mt5

logger = logging.getLogger(__name__)


class HedgeExecutor:
    """Handles hedge ratio adjustment execution"""
    
    def __init__(self, trade_executor, rebalancer, position_monitor,
                 mt5_tickets, primary_symbol, secondary_symbol):
        self.trade_executor = trade_executor
        self.rebalancer = rebalancer
        self.position_monitor = position_monitor
        self.mt5_tickets = mt5_tickets
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol
        logger.info("HedgeExecutor initialized")
    
    def execute(self, adjustment, snapshot) -> bool:
        """
        Execute hedge adjustment (System 3)
        
        Opens ONLY ONE LEG to fix volume imbalance.
        May result in ODD number of MT5 positions.
        
        Args:
            adjustment: HedgeAdjustment dataclass from rebalancer
            snapshot: Market data snapshot
            
        Returns:
            bool: True if successful
        """
        try:
            spread_id = adjustment.spread_id
            
            logger.info("="*80)
            logger.info(f"[SYSTEM-3-REBALANCE] Volume Correction")
            logger.info("="*80)
            logger.info(f"  Spread: {spread_id[:8]}")
            logger.info(f"  Symbol: {adjustment.symbol}")
            logger.info(f"  Action: {adjustment.action} {adjustment.quantity:.4f} lots")
            logger.info(f"  Reason: {adjustment.reason}")
            logger.info(f"  Hedge: {adjustment.old_hedge:.4f} → {adjustment.new_hedge:.4f}")
            logger.info(f"  Legs: 1 (single correction)")
            logger.info(f"    This will create ODD position count!")
            
            # System 3 can adjust EITHER leg (PRIMARY or SECONDARY)
            # Rebalancer already chose the correct leg
            
            # Execute SINGLE order (not spread!)
            result = self.trade_executor.place_market_order(
                symbol=adjustment.symbol,
                order_type=adjustment.action,  # 'BUY' or 'SELL'
                volume=adjustment.quantity,
                comment=f"VOL_REBAL:{spread_id[:8]}"
            )
            
            if not result.success:
                logger.error(f"[SYSTEM-3-REBALANCE] ❌ Execution FAILED: {result.comment}")
                return False
            
            logger.info(f"[SYSTEM-3-REBALANCE] ✅ Order filled:")
            logger.info(f"  Ticket: {result.order_ticket}")
            logger.info(f"  Volume: {result.volume:.4f} lots")
            logger.info(f"  Price: ${result.price:.4f}")
            
            # Verify position count
            import time
            time.sleep(0.5)  # Wait for MT5

            mt5 = get_mt5()
            positions_after = mt5.positions_get()
            count_after = len(positions_after) if positions_after else 0
            is_odd = count_after % 2 == 1
            
            logger.info(f"  MT5 positions: {count_after} ({'ODD ✓' if is_odd else 'EVEN'})")
            
            # Update rebalancer
            self.rebalancer.mark_hedge_adjusted(
                spread_id=spread_id,
                adjustment=adjustment,
                executed_quantity=result.volume
            )
            
            # Register ticket in monitor
            self.position_monitor.register_position(result.order_ticket, adjustment.symbol)
            
            # Map ticket
            self.mt5_tickets[result.order_ticket] = result.order_ticket
            
            logger.info(f"[SYSTEM-3-REBALANCE] ✅ Correction complete for {spread_id[:8]}")
            logger.info("="*80)
            
            return True
            
        except Exception as e:
            logger.error(f"[SYSTEM-3-REBALANCE] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

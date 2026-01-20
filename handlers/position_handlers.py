"""
Position Handlers
"""
import logging


logger = logging.getLogger(__name__)


class PositionHandlers:
    """Handles position-related callbacks"""
    
    def __init__(self, system):
        self.system = system
    
    def handle_missing_positions(self, missing_tickets):
        """Handle missing positions"""
        logger.error(f" Position monitor detected {len(missing_tickets)} missing position(s)")

        # Check if ALL positions are missing
        if hasattr(self.system, 'position_monitor') and self.system.position_monitor:
            all_tickets = self.system.position_monitor.get_monitored_tickets()
            all_missing = (missing_tickets == all_tickets)

            if all_missing:
                logger.error("="*80)
                logger.error(" ALL POSITIONS CLOSED MANUALLY!")
                logger.error("="*80)
                logger.error("All tracked positions have been closed on MT5")
                logger.error("This likely means user closed everything manually")

                # Trigger full system reset
                self.handle_all_positions_closed()

            # Unregister from monitor
            for ticket in missing_tickets:
                self.system.position_monitor.unregister_position(ticket)

        # Note: User confirmation is handled by PositionMonitor
        # This callback is just for logging/tracking


    def handle_user_rebalance(self):
        """Handle user rebalance confirmation"""
        logger.info(" User confirmed: REBALANCE")
        logger.info(" Rebalancing not yet implemented - closing all instead")
        self.close_all_positions(reason="Emergency close")


    def handle_user_timeout(self):
        """Handle user timeout"""

    def handle_all_positions_closed(self):
        """Handle all positions closed event"""
        logger.warning("="*80)
        logger.warning(" RESETTING SYSTEM - All positions closed")
        logger.warning("="*80)

        try:
            # 1. Clear setup flag
            self.system.flag_manager.mark_setup_inactive("All positions closed")
            logger.info(" Setup flag cleared")

            # 2. Reset spread states (allow new entries)
            if hasattr(self.system, 'unified_executor') and self.system.unified_executor:
                self.system.unified_executor.spread_states.clear()
                self.system.unified_executor._save_states()
                logger.info(" Spread states reset (unified_executor)")

            # Legacy: Reset entry cooldown if exists
            if hasattr(self.system, 'entry_cooldown') and self.system.entry_cooldown:
                self.system.entry_cooldown.reset()
                logger.info(" Entry cooldown reset (legacy)")

            # 3. Clear rebalancer positions
            if hasattr(self, 'rebalancer') and self.system.rebalancer:
                self.system.rebalancer.active_positions.clear()
                self.system.rebalancer.last_adjustment.clear()
                logger.info(" Rebalancer positions cleared")

            # 4. Clear attribution engine
            from analytics.pnl_attribution import get_attribution_engine
            attribution_engine = get_attribution_engine()
            if attribution_engine:
                attribution_engine.positions.clear()
                logger.info(" Attribution engine cleared")

            # 5. Clear position tracker
            self.system.position_tracker.positions.clear()
            logger.info(" Position tracker cleared")

            # 6. Clear MT5 tickets mapping
            self.system.mt5_tickets.clear()
            logger.info(" MT5 tickets mapping cleared")

            # 7. Clear persistence
            self.system.persistence.clear_all_positions()
            logger.info(" Persistence cleared")

            logger.warning("="*80)
            logger.warning(" SYSTEM RESET COMPLETE")
            logger.warning("="*80)
            logger.warning("System is now ready to enter new positions")
            logger.warning("="*80)

        except Exception as e:
            logger.error(f"Error during system reset: {e}")
            import traceback
            logger.error(traceback.format_exc())

        logger.error(" Emergency close complete")


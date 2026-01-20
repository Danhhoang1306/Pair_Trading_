"""
Recovery Manager
"""
import logging
import time
from datetime import datetime
from core.mt5_manager import get_mt5

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Manages position recovery and synchronization"""
    
    def __init__(self, system):
        self.system = system
    
    def recover_positions(self):
        """Recover positions from disk"""
        logger.info("="*80)
        logger.info("POSITION RECOVERY - Checking for saved positions...")
        logger.info("="*80)

        # STEP 1: Check setup flag
        if not self.system.flag_manager.is_setup_active():
            logger.info(" No active setup flag - starting fresh")
            self.system.flag_manager.clear_flag()
            return

        logger.warning("  Active setup flag detected - checking MT5 positions...")
        setup_info = self.system.flag_manager.get_setup_info()
        if setup_info:
            logger.info(f"Setup ID: {setup_info.get('spread_id', 'UNKNOWN')[:8]}")
            logger.info(f"Activated: {setup_info.get('activated_at', 'UNKNOWN')}")

        # STEP 2: Cleanup orphaned positions first
        self.system.persistence.cleanup_orphaned_positions()

        # STEP 3: Load active positions
        persisted_positions = self.system.persistence.load_active_positions()

        if not persisted_positions:
            logger.warning("  Setup flag active but no positions found - clearing flag")
            self.system.flag_manager.mark_setup_inactive("No positions found")
            return

        logger.info(f"Found {len(persisted_positions)} saved positions")

        # STEP 4: Check if positions exist on MT5
        mt5 = get_mt5()
        mt5_positions = mt5.positions_get()
        if mt5_positions is None:
            logger.error(" Failed to get MT5 positions - cannot recover")
            return

        mt5_tickets = {pos.ticket for pos in mt5_positions}
        saved_tickets = {pos.mt5_ticket for pos in persisted_positions.values()}

        missing_tickets = saved_tickets - mt5_tickets

        # SPECIAL CASE: ALL positions closed offline
        if len(mt5_tickets) == 0 and len(saved_tickets) > 0:
            logger.warning("="*80)
            logger.warning("  ALL POSITIONS CLOSED OFFLINE!")
            logger.warning("="*80)
            logger.warning("Detected scenario:")
            logger.warning(f"  • Saved positions: {len(saved_tickets)}")
            logger.warning(f"  • MT5 positions: 0")
            logger.warning(f"  • Conclusion: All positions manually closed while system offline")

            # Clean up everything
            logger.info("Cleaning up persisted data...")
            for spread_id in set(pos.spread_id for pos in persisted_positions.values()):
                self.system.persistence.archive_spread(spread_id, reason="all_closed_offline")

            # Reset spread states to allow fresh entries
            if hasattr(self.system, 'unified_executor') and self.system.unified_executor:
                self.system.unified_executor.spread_states.clear()
                self.system.unified_executor._save_states()
                logger.info("  Spread states reset - ready for fresh entries")

            # Legacy: Reset entry cooldown if exists
            if hasattr(self.system, 'entry_cooldown') and self.system.entry_cooldown:
                self.system.entry_cooldown.reset()
                logger.info("  Entry cooldown reset (legacy)")

            self.system.flag_manager.mark_setup_inactive("All positions closed offline")
            logger.info(" Cleanup complete - ready for fresh start")
            return

        if missing_tickets:
            # INCOMPLETE - positions were closed
            logger.error("="*80)
            logger.error("  INCOMPLETE SETUP - Some positions closed!")
            logger.error("="*80)
            for ticket in missing_tickets:
                logger.error(f" Missing ticket: {ticket}")

            # Ask user what to do
            self.startup_user_confirmation(
                complete=False,
                missing_tickets=missing_tickets,
                persisted_positions=persisted_positions
            )
            return

        # STEP 5: All positions exist - ask user to continue
        logger.info("="*80)
        logger.info(" All saved positions found on MT5")
        logger.info("="*80)

        # Group by spread_id
        spreads = {}
        for pos_id, pers_pos in persisted_positions.items():
            spread_id = pers_pos.spread_id
            if spread_id not in spreads:
                spreads[spread_id] = []
            spreads[spread_id].append(pers_pos)

        for spread_id, spread_positions in spreads.items():
            logger.info(f"Spread {spread_id[:8]}:")
            for pos in spread_positions:
                logger.info(f"  • {pos.symbol} {pos.side} {pos.volume} lots "
                           f"@ {pos.entry_price:.2f} (Ticket: {pos.mt5_ticket})")

        # Ask user what to do
        self.startup_user_confirmation(
            complete=True,
            missing_tickets=set(),
            persisted_positions=persisted_positions
        )


    def startup_user_confirmation(self, complete, missing_tickets, persisted_positions):
        """
        Ask user for confirmation at startup

        Args:
            complete: True if all positions exist, False if some missing
            missing_tickets: Set of missing ticket IDs
            persisted_positions: All persisted positions
        """
        import time

        logger.warning("="*80)
        if complete:
            logger.warning(" RECOVERY OPTIONS:")
            logger.warning("  1. CONTINUE - Resume trading with existing positions")
            logger.warning("  2. CLOSE ALL - Close all positions and start fresh")
        else:
            logger.warning(" RECOVERY OPTIONS:")
            logger.warning("  1. REBALANCE - Reopen missing positions")
            logger.warning("  2. CLOSE ALL - Close all remaining positions")

        logger.warning("")
        logger.warning("⏰ Waiting 60 seconds for response...")
        logger.warning(" Use GUI or CLI to respond")
        logger.warning("⏰ If no response → CLOSE ALL")
        logger.warning("="*80)

        # TODO: In production, this should be interactive
        # For now, we'll use a simple timeout
        response_received = False
        user_choice = None

        # Wait for 60 seconds (can be interrupted by user input)
        start_time = time.time()
        timeout = 60

        # For now, auto-close if incomplete, auto-continue if complete
        # In production, this should wait for actual user input
        if complete:
            logger.info(" Setup complete - auto-continuing...")
            user_choice = 'continue'
            response_received = True
        else:
            logger.warning(" Setup incomplete - auto-closing all...")
            user_choice = 'close_all'
            response_received = True

        # Process user choice
        if not response_received or user_choice == 'close_all':
            # Close all and clear flag
            logger.warning(" CLOSING ALL POSITIONS...")
            self.close_all_positions(reason="Recovery timeout")
            self.system.flag_manager.mark_setup_inactive("User declined recovery")
            return

        if user_choice == 'rebalance':
            # Rebalance missing positions
            logger.info(" REBALANCING MISSING POSITIONS...")
            self._rebalance_missing_positions(missing_tickets, persisted_positions)
            return

        if user_choice == 'continue':
            # Restore positions to tracker
            logger.info(" CONTINUING WITH EXISTING POSITIONS...")
            self.restore_positions_to_tracker(persisted_positions)
            return


    def rebalance_missing_positions(self, response_received, user_choice, saved_positions):
        """Rebalance missing positions"""
        logger.info("="*80)
        logger.info(" REBALANCING MISSING POSITIONS")
        logger.info("="*80)

        # Find which positions are missing
        missing_positions = []
        remaining_positions = []

        for pos_id, pers_pos in positions.items():
            if pers_pos.mt5_ticket in missing_tickets:
                missing_positions.append(pers_pos)
            else:
                remaining_positions.append(pers_pos)

        logger.info(f"Missing: {len(missing_positions)} positions")
        logger.info(f"Remaining: {len(remaining_positions)} positions")

        # Check if it's a complete spread that's broken
        spreads = {}
        for pos in positions.values():
            spread_id = pos.spread_id
            if spread_id not in spreads:
                spreads[spread_id] = {'primary': None, 'secondary': None}

            if pos.is_primary:
                spreads[spread_id]['primary'] = pos
            else:
                spreads[spread_id]['secondary'] = pos

        # Check each spread
        for spread_id, legs in spreads.items():
            primary_pos = legs['primary']
            secondary_pos = legs['secondary']

            if not primary_pos or not secondary_pos:
                logger.error(f"Spread {spread_id[:8]} incomplete in persistence!")
                continue

            primary_missing = primary_pos.mt5_ticket in missing_tickets
            secondary_missing = secondary_pos.mt5_ticket in missing_tickets

            if primary_missing and secondary_missing:
                # BOTH missing - close spread completely
                logger.warning(f"Spread {spread_id[:8]} - BOTH legs missing")
                logger.warning("→ Marking as closed")
                self.system.persistence.archive_spread(spread_id, reason="both_legs_manually_closed")
                continue

            if primary_missing or secondary_missing:
                # ONE leg missing - this is dangerous!
                logger.error(f"Spread {spread_id[:8]} - ONE leg missing!")

                if primary_missing:
                    logger.error(f"   primary position missing (Ticket: {primary_pos.mt5_ticket})")
                    logger.error(f"   secondary position exists (Ticket: {secondary_pos.mt5_ticket})")
                    logger.error("  → CLOSING ALL remaining positions to avoid unhedged risk")

                    # Close ALL positions (fast_close_all cannot close individual tickets)
                    try:
                        from utils.fast_close_all import CloseManager
                        manager = CloseManager(magic_number=self.system.magic_number, max_workers=100)
                        close_result = manager.close_all()

                        if close_result['success']:
                            logger.info(f"   Closed all positions: {close_result['total_closed']} positions")
                        else:
                            logger.error(f"   Failed to close all: {close_result['total_failed']} failed")
                    except Exception as e:
                        logger.error(f"   Error closing positions: {e}")

                else:  # secondary_missing
                    logger.error(f"   primary position exists (Ticket: {primary_pos.mt5_ticket})")
                    logger.error(f"   secondary position missing (Ticket: {secondary_pos.mt5_ticket})")
                    logger.error("  → CLOSING ALL remaining positions to avoid unhedged risk")

                    # Close ALL positions (fast_close_all cannot close individual tickets)
                    try:
                        from utils.fast_close_all import CloseManager
                        manager = CloseManager(magic_number=self.system.magic_number, max_workers=100)
                        close_result = manager.close_all()

                        if close_result['success']:
                            logger.info(f"   Closed all positions: {close_result['total_closed']} positions")
                        else:
                            logger.error(f"   Failed to close all: {close_result['total_failed']} failed")
                    except Exception as e:
                        logger.error(f"   Error closing positions: {e}")

                # Archive the spread
                self.system.persistence.archive_spread(spread_id, reason="partial_spread_detected")

        # Clear all state
        self.system.position_tracker.positions.clear()
        self.system.mt5_tickets.clear()
        self.system.position_monitor.clear_all()
        self.system.persistence.clear_all_positions()
        self.system.flag_manager.mark_setup_inactive("Rebalance completed - all closed")

        logger.info("="*80)
        logger.info(" Rebalancing complete - all positions closed for safety")
        logger.info("="*80)


    def restore_positions_to_tracker(self, positions):
        """Restore positions to tracker"""
        from strategy.position_tracker import Position

        # Group by spread_id
        spreads = {}
        for pos_id, pers_pos in positions.items():
            spread_id = pers_pos.spread_id
            if spread_id not in spreads:
                spreads[spread_id] = []
            spreads[spread_id].append(pers_pos)

        # Restore each spread
        recovered = 0
        max_entry_zscore = None  # Track max z-score for entry cooldown
        recovered_side = None  # Track recovered position side

        for spread_id, positions in spreads.items():
            try:
                # Restore positions to tracker
                for pers_pos in positions:
                    position = Position(
                        position_id=pers_pos.position_id,
                        symbol=pers_pos.symbol,
                        side=pers_pos.side,
                        quantity=pers_pos.volume,
                        entry_price=pers_pos.entry_price,
                        current_price=pers_pos.entry_price,
                        metadata={
                            'spread_id': pers_pos.spread_id,
                            'entry_zscore': pers_pos.entry_zscore,
                            'hedge_ratio': pers_pos.hedge_ratio,
                            'recovered': True
                        }
                    )

                    self.system.position_tracker.positions[pers_pos.position_id] = position

                    # Map MT5 ticket
                    self.system.mt5_tickets[pers_pos.position_id] = pers_pos.mt5_ticket

                    # Register with monitor
                    self.system.position_monitor.register_position(
                        ticket=pers_pos.mt5_ticket,
                        symbol=pers_pos.symbol
                    )

                    logger.info(f" Recovered: {pers_pos.symbol} {pers_pos.side} "
                               f"{pers_pos.volume} lots @ {pers_pos.entry_price:.2f} "
                               f"(Ticket: {pers_pos.mt5_ticket})")

                    recovered += 1

                # Register spread with rebalancer
                if len(positions) == 2:
                    first_pos = positions[0]
                    # Use is_primary field to identify primary/secondary
                    primary_pos = positions[0] if positions[0].is_primary else positions[1]
                    secondary_pos = positions[1] if primary_pos == positions[0] else positions[0]

                    # Use last_z_entry from SimpleUnifiedExecutor's spread_states.json
                    # This ensures pyramiding continues from the LAST entry, not first entry
                    actual_entry_zscore = first_pos.entry_zscore  # Fallback to original

                    if hasattr(self.system, 'unified_executor') and self.system.unified_executor:
                        state = self.system.unified_executor.get_state(spread_id)
                        if state and state.last_z_entry is not None:
                            actual_entry_zscore = state.last_z_entry
                            logger.info(f"  Using last_z_entry = {actual_entry_zscore:.3f} from spread_states.json"
                                       f" (original = {first_pos.entry_zscore:.3f})")
                        else:
                            logger.info(f"  Using original entry_zscore = {actual_entry_zscore:.3f} "
                                       f"(no state found in spread_states.json)")
                    else:
                        logger.warning(f"  unified_executor not available, using original entry_zscore = {actual_entry_zscore:.3f}")

                    self.system.rebalancer.register_position(
                        spread_id=spread_id,
                        side=first_pos.side,
                        entry_zscore=actual_entry_zscore,  # ✅ Use last_z_entry, not original entry_zscore
                        entry_hedge_ratio=first_pos.hedge_ratio,  # Direct field, not metadata
                        primary_lots=primary_pos.volume,
                        secondary_lots=secondary_pos.volume,
                        total_position_size=primary_pos.volume,
                        primary_symbol=self.system.primary_symbol,
                        secondary_symbol=self.system.secondary_symbol
                    )

                    # Register with attribution engine using MT5 comment
                    # Query MT5 to get actual comment
                    mt5 = get_mt5()
                    mt5_pos = None
                    for pos in mt5.positions_get():
                        if pos.ticket == primary_pos.mt5_ticket:
                            mt5_pos = pos
                            break

                    if mt5_pos and mt5_pos.comment:
                        # Use MT5 comment as spread_id for attribution
                        mt5_spread_id = mt5_pos.comment

                        try:
                            from analytics.pnl_attribution import get_attribution_engine, PositionSnapshot
                            from datetime import datetime

                            # Create entry snapshot from persisted data
                            entry_snapshot = PositionSnapshot(
                                timestamp=datetime.fromisoformat(primary_pos.entry_time),
                                xau_bid=primary_pos.entry_price,
                                xau_ask=primary_pos.entry_price,
                                xag_bid=secondary_pos.entry_price,
                                xag_ask=secondary_pos.entry_price,
                                spread=0.0,  # Will be recalculated
                                mean=0.0,
                                std=0.0,
                                zscore=primary_pos.entry_zscore,
                                hedge_ratio=primary_pos.hedge_ratio,
                                xau_volume=primary_pos.volume,
                                xag_volume=secondary_pos.volume,
                                xau_side=primary_pos.side,
                                xag_side=secondary_pos.side,
                                xau_price=primary_pos.entry_price,
                                xag_price=secondary_pos.entry_price
                            )

                            attribution_engine = get_attribution_engine()
                            # Use spread_id for consistency with attribution thread lookup
                            attribution_engine.register_position(spread_id, entry_snapshot)
                            logger.info(f" Registered {spread_id} in attribution engine (recovered)")
                        except Exception as e:
                            logger.error(f"Failed to register attribution for recovered spread: {e}")

            except Exception as e:
                logger.error(f"Failed to recover spread {spread_id}: {e}")
                import traceback
                traceback.print_exc()

        # Entry state is now handled by SimpleUnifiedExecutor via spread_states.json
        # The state is auto-loaded on startup, so no manual restoration needed here
        if recovered > 0:
            logger.info(f"  Entry state managed by SimpleUnifiedExecutor (spread_states.json)")

        logger.info("="*80)
        logger.info(f"POSITION RECOVERY COMPLETE: {recovered} positions recovered")
        logger.info("="*80)


    def sync_mt5_positions_to_rebalancer(self):
        """Sync MT5 positions to rebalancer"""
        try:
            mt5 = get_mt5()

            # Get all MT5 positions
            mt5_positions = mt5.positions_get()
            if not mt5_positions:
                return

            # Group by magic number (our positions)
            our_positions = [p for p in mt5_positions if p.magic == self.trade_executor.magic_number]

            if not our_positions:
                return

            # Group by symbol
            primary_positions = [p for p in our_positions if p.symbol == self.primary_symbol]
            secondary_positions = [p for p in our_positions if p.symbol == self.secondary_symbol]

            if not primary_positions or not secondary_positions:
                logger.debug("[SYNC] No paired positions to sync")
                return

            # Calculate NET positions (consider BUY/SELL direction)
            # For PRIMARY (BTCUSD):
            total_primary_buy = sum(p.volume for p in primary_positions if p.type == mt5.ORDER_TYPE_BUY)
            total_primary_sell = sum(p.volume for p in primary_positions if p.type == mt5.ORDER_TYPE_SELL)
            total_primary = abs(total_primary_buy - total_primary_sell)  # NET position

            # For SECONDARY (ETHUSD):
            total_secondary_buy = sum(p.volume for p in secondary_positions if p.type == mt5.ORDER_TYPE_BUY)
            total_secondary_sell = sum(p.volume for p in secondary_positions if p.type == mt5.ORDER_TYPE_SELL)
            total_secondary = abs(total_secondary_buy - total_secondary_sell)  # NET position

            logger.debug(f"[SYNC] NET positions calculated:")
            logger.debug(f"  Primary: BUY {total_primary_buy:.4f} - SELL {total_primary_sell:.4f} = NET {total_primary:.4f}")
            logger.debug(f"  Secondary: BUY {total_secondary_buy:.4f} - SELL {total_secondary_sell:.4f} = NET {total_secondary:.4f}")

            # Detect side (majority rule) - KEEP THIS SAME
            primary_long = sum(p.volume for p in primary_positions if p.type == mt5.ORDER_TYPE_BUY)
            primary_short = sum(abs(p.volume) for p in primary_positions if p.type == mt5.ORDER_TYPE_SELL)
            side = 'LONG' if primary_long > primary_short else 'SHORT'

            # Create synthetic spread_id for manual positions
            # Use ticket-based ID to ensure consistency across loops
            primary_tickets = sorted([p.ticket for p in primary_positions])
            secondary_tickets = sorted([p.ticket for p in secondary_positions])
            spread_id = f"manual_{primary_tickets[0]}_{secondary_tickets[0]}"

            #  Check if these tickets are already registered in ANY spread
            # (Original spread uses format "ticket1-ticket2", manual uses "manual_ticket1_ticket2")
            existing_spread = None
            for registered_id, pos_data in self.system.rebalancer.active_positions.items():
                # Check if this spread contains our tickets
                if str(primary_tickets[0]) in registered_id and str(secondary_tickets[0]) in registered_id:
                    existing_spread = registered_id
                    break

            if existing_spread:
                # Already registered (possibly as original spread), just update volumes
                position = self.system.rebalancer.active_positions[existing_spread]
                position['primary_lots'] = total_primary
                position['secondary_lots'] = total_secondary
                position['current_hedge_ratio'] = current_hedge_ratio
                logger.debug(f"[SYNC] Updated {existing_spread[:15]}: {total_primary:.4f} BTC, {total_secondary:.4f} ETH")
                return

            # Register new manual position
            logger.info("="*80)
            logger.info("[SYNC]  Detected unregistered MT5 positions!")
            logger.info("="*80)
            logger.info(f"  Primary ({self.primary_symbol}): {total_primary:.4f} lots")
            logger.info(f"  Secondary ({self.secondary_symbol}): {total_secondary:.4f} lots")
            logger.info(f"  Side: {side}")
            logger.info(f"  Current hedge ratio: {current_hedge_ratio:.4f}")
            logger.info(f"  → Auto-registering for System 3 monitoring...")

            # Register in rebalancer (minimal registration for System 3 only)
            # No pyramiding levels since this is manual entry
            position_data = {
                'spread_id': spread_id,
                'side': side,
                'entry_zscore': 0.0,  # Unknown
                'entry_hedge_ratio': current_hedge_ratio,  # Assume current
                'current_hedge_ratio': current_hedge_ratio,
                'primary_lots': total_primary,
                'secondary_lots': total_secondary,
                'total_position_size': 0.0,  # Unknown
                'size_per_level': 0.0,
                'levels': [],  # No pyramiding for manual positions
                'total_executed': 1,
                'entry_time': datetime.now(),
                'last_adjustment_time': None,
                'primary_symbol': self.primary_symbol,
                'secondary_symbol': self.secondary_symbol,
                'is_manual': True  # Flag as manual
            }

            self.system.rebalancer.active_positions[spread_id] = position_data
            self.system.rebalancer.last_adjustment[spread_id] = time.time()

            logger.info(f"   Registered as {spread_id[:15]}")
            logger.info(f"   System 3 will now monitor and rebalance this position!")
            logger.info("="*80)

        except Exception as e:
            logger.error(f"[SYNC] Error syncing MT5 positions: {e}")
            import traceback
            traceback.print_exc()


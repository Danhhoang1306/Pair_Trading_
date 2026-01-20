"""
Exit Executor - Handles spread exit execution logic
Extracted from main_cli.py (_execute_exit method)
"""
import logging
from typing import Optional

from strategy.signal_generator import SignalType
from utils.fast_close_all import CloseManager

logger = logging.getLogger(__name__)


class ExitExecutor:
    """
    Handles execution of spread exit orders
    
    Responsibilities:
    - Exit validation
    - Close spread positions on MT5
    - Handle partial close failures
    - Cleanup all tracking systems
    - Reset flags and cooldowns
    """
    
    def __init__(self,
                 trade_executor,
                 position_tracker,
                 position_monitor,
                 persistence,
                 rebalancer,
                 flag_manager,
                 position_sizer,
                 drawdown_monitor,
                 risk_checker,
                 signal_generator,
                 mt5_tickets,
                 unified_executor=None,
                 primary_symbol='BTCUSD',
                 secondary_symbol='ETHUSD',
                 magic_number=234000,
                 risk_thread=None):
        """Initialize Exit Executor"""
        self.trade_executor = trade_executor
        self.position_tracker = position_tracker
        self.position_monitor = position_monitor
        self.persistence = persistence
        self.rebalancer = rebalancer
        self.flag_manager = flag_manager
        self.position_sizer = position_sizer
        self.drawdown_monitor = drawdown_monitor
        self.risk_checker = risk_checker
        self.signal_generator = signal_generator
        self.mt5_tickets = mt5_tickets
        self.unified_executor = unified_executor  # SimpleUnifiedExecutor for state reset
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol
        self.magic_number = magic_number
        self.risk_thread = risk_thread  # RiskManagementThread for unregistering

        # State
        self.account_balance = 0
        self.last_entry_zscore = None
        self.last_entry_mean = None

        logger.info("ExitExecutor initialized")

    def execute(self, signal, data):
        """
        Execute exit signal - unified entry point for exit operations

        Args:
            signal: Signal object with signal_type and zscore
            data: Market data snapshot
        """
        logger.info("="*80)
        logger.info(f"[EXIT EXECUTOR] Processing {signal.signal_type.value}")
        logger.info(f"  Z-score: {signal.zscore:.3f}")
        logger.info("="*80)

        # Get current positions
        positions = list(self.position_tracker.positions.values())

        # Validate exit
        if not self._validate_exit(positions):
            logger.warning("[EXIT] Validation failed - checking MT5 directly")
            # Even if tracker is empty, try to close MT5 positions
            mt5_count = self.trade_executor.get_position_count_by_magic(self.magic_number)
            if mt5_count > 0:
                logger.warning(f"[EXIT] Found {mt5_count} MT5 positions - forcing close")
                return self.fast_close_all_positions()
            return {'success': False, 'reason': 'No positions to close'}

        # Log spread info
        spread_ids = self._get_spread_ids(positions)
        self._log_exit_intent(signal, spread_ids)

        # Execute fast close all
        return self.fast_close_all_positions()

    def _validate_exit(self, positions) -> bool:
        """Validate if exit is possible"""
        if not positions:
            logger.warning("[SYSTEM-1-EXIT] No positions in tracker")
            
            # Safety check MT5
            mt5_count = self.trade_executor.get_position_count_by_magic(self.magic_number)
            if mt5_count > 0:
                logger.warning(f" Found {mt5_count} positions on MT5 but none in tracker!")
                logger.warning("Manual intervention required")
            return False
        
        return True
    
    def _get_spread_ids(self, positions):
        """Extract unique spread IDs from positions"""
        spread_ids = set()
        for pos in positions:
            if 'spread_id' in pos.metadata:
                spread_ids.add(pos.metadata['spread_id'])
        return spread_ids
    
    def _log_exit_intent(self, signal, spread_ids):
        """Log exit intent"""
        logger.info("="*80)
        logger.info(f"[SYSTEM-1-EXIT] Mean Reversion Exit")
        logger.info("="*80)
        logger.info(f"  Signal: {signal.signal_type.value}")
        logger.info(f"  Current Z: {signal.zscore:.2f}")
        logger.info(f"  Reason: Z-score returned to mean (±{self.signal_generator.exit_threshold:.1f} threshold)")
        logger.info(f"  Spreads to close: {len(spread_ids)}")
        logger.info(f"  Legs: 2 per spread (paired exit)")
    
    # REMOVED: All deprecated sequential close methods
    # Now using ONLY CloseManager.close_all() for unified exit path
    

    
    # REMOVED: _retry_remaining_leg()
    # CloseManager handles all retries automatically with multi-round verification
    
    def update_balance(self, new_balance: float):
        """Update account balance"""
        self.account_balance = new_balance
    
    def fast_close_all_positions(self) -> dict:
        """
        UNIFIED EXIT PATH - Close ALL positions using CloseManager

        Features:
        - Parallel execution (10 workers)
        - Automatic retry (multi-round)
        - Guaranteed verification
        - Auto cleanup internal tracking

        Returns:
            {
                'success': bool,
                'total_closed': int,
                'total_failed': int,
                'rounds': int,
                'remaining': list
            }
        """
        logger.warning("="*80)
        logger.warning("EXIT EXECUTOR: FAST CLOSE ALL")
        logger.warning("="*80)

        # Step 1: Close all positions on MT5 (parallel + retry)
        from utils.fast_close_all import CloseManager
        manager = CloseManager(magic_number=self.magic_number, max_workers=10)
        result = manager.close_all()

        # Step 2: Cleanup internal tracking (only if positions were closed)
        if result['success'] or result['total_closed'] > 0:
            logger.info("Cleaning up internal tracking...")

            try:
                # Clear all trackers
                self.position_tracker.clear_all()
                self.rebalancer.clear_all()
                self.position_monitor.clear_all()

                # Also clear from risk thread
                if self.risk_thread:
                    self.risk_thread.clear_monitored_tickets()

                # Reset unified executor state (allow new entries)
                if self.unified_executor:
                    # Reset all spread states
                    spread_ids = list(self.unified_executor.spread_states.keys())
                    for spread_id in spread_ids:
                        self.unified_executor.reset_state(spread_id)
                    logger.info(f"   Reset {len(spread_ids)} spread state(s)")

                # Update setup flag
                self.flag_manager.set_inactive()

                # Clear MT5 tickets mapping
                self.mt5_tickets.clear()

                logger.info("   Internal tracking cleared")
            except Exception as e:
                logger.warning(f"   Cleanup error: {e}")

        # Step 3: Log final summary
        logger.warning("="*80)
        logger.warning(f"FAST CLOSE COMPLETE:")
        logger.warning(f"  Closed: {result['total_closed']}")
        logger.warning(f"  Failed: {result['total_failed']}")
        logger.warning(f"  Rounds: {result['rounds']}")
        if result.get('remaining'):
            logger.error(f"  Still open: {len(result['remaining'])} positions")
        logger.warning("="*80)

        return result


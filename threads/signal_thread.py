"""
SignalThread - Unified Grid Version
Handles signal generation with integrated grid level checking
"""
import time
import queue
import logging
from typing import Optional
from datetime import datetime
from core.mt5_manager import get_mt5
from .base_thread import BaseThread
from strategy.signal_generator import SignalType

logger = logging.getLogger(__name__)


class SignalThread(BaseThread):
    """
    Signal generation thread with Unified Grid support

    Responsibilities:
    1. Receive market data from data_queue
    2. Generate trading signals (entry/exit)
    3. Check grid levels for entry/pyramiding
    4. Check volume rebalancing needs
    5. Queue actions for ExecutionThread
    """

    def __init__(self, system):
        super().__init__("SignalThread", system)

    def run(self):
        """Signal generation thread main loop"""
        logger.info("SignalThread started")

        iteration = 0
        while self.system.running:
            try:
                iteration += 1
                if iteration % 6 == 1:  # Log every 30s
                    logger.debug(f"SignalThread waiting for data (iteration {iteration})...")

                data = self.system.data_queue.get(timeout=5)
                logger.debug(f"SignalThread received data! Queue size: {self.system.data_queue.qsize()}")

                with self.system.lock:
                    snapshot = data['snapshot']

                    # Get current position state
                    open_positions = self.system.position_tracker.get_all_positions()
                    current_position = self._detect_current_position(open_positions)

                    # Generate signal using SignalGenerator
                    signal = self.system.signal_generator.generate_signal(
                        primary_price=snapshot.primary_bid,
                        secondary_price=snapshot.secondary_bid,
                        zscore=snapshot.zscore,
                        hedge_ratio=snapshot.hedge_ratio,
                        current_position=current_position
                    )

                    self.system.current_signal = signal

                    # Track z-score
                    self.system.zscore_monitor.add(signal.zscore)

                    # Log market status
                    zscore_status = self.system.zscore_monitor.format_status()
                    logger.info(f"[MARKET] {zscore_status}")
                    logger.info(f"         Primary: ${snapshot.primary_bid:.2f} | "
                               f"Secondary: ${snapshot.secondary_bid:.4f} | "
                               f"Signal: {signal.signal_type.value}")

                    # Alert on significant changes
                    if self.system.zscore_monitor.should_alert(threshold=0.3):
                        change = self.system.zscore_monitor.get_change()
                        logger.warning(f"[ALERT] Significant z-score change: {change:+.3f}")

                    # ==================== PRIORITY: EXIT SIGNALS ====================
                    is_exit_signal = signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]

                    if is_exit_signal:
                        self._handle_exit_signal(signal, data, open_positions)
                        continue  # Skip all other processing

                    # ==================== UNIFIED POSITION EXECUTOR (NEW) ====================
                    if self._is_unified_executor_enabled():
                        self._process_unified_executor(signal, data, snapshot, current_position, open_positions)
                    # ==================== UNIFIED GRID CHECK (DEPRECATED) ====================
                    elif self._is_unified_grid_enabled():
                        logger.warning("[SIGNAL] Using DEPRECATED UnifiedGrid - please migrate to SimpleUnifiedExecutor")
                        self._process_unified_grid(signal, data, snapshot, current_position, open_positions)
                    else:
                        # ==================== LEGACY MODE ====================
                        # Fallback to legacy rebalancer
                        logger.warning("[SIGNAL] Using LEGACY rebalancer/pyramiding - SimpleUnifiedExecutor is disabled!")
                        logger.warning("[SIGNAL] Set enable_unified_executor=True in main_cli.py to use new system")
                        self._process_legacy_rebalancer(signal, data, snapshot, open_positions)

                        # Entry signals (NO POSITION) - Legacy only
                        if not current_position and signal.signal_type in [SignalType.LONG_SPREAD, SignalType.SHORT_SPREAD]:
                            self._queue_entry_signal(signal, data)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Signal thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _detect_current_position(self, open_positions) -> str:
        """Detect current position direction"""
        if not open_positions:
            return None

        primary_positions = [p for p in open_positions if p.symbol == self.system.primary_symbol]

        if not primary_positions:
            return None

        long_positions = [p for p in primary_positions if p.side == 'LONG']
        short_positions = [p for p in primary_positions if p.side == 'SHORT']

        if long_positions and not short_positions:
            return 'LONG'
        elif short_positions and not long_positions:
            return 'SHORT'
        elif long_positions and short_positions:
            # Mixed - use dominant
            logger.warning(f"Mixed positions: {len(long_positions)} LONG, {len(short_positions)} SHORT")
            return 'LONG' if len(long_positions) > len(short_positions) else 'SHORT'

        return None

    def _is_unified_executor_enabled(self) -> bool:
        """Check if unified position executor is enabled"""
        return getattr(self.system, 'enable_unified_executor', False) and hasattr(self.system, 'unified_executor')

    def _is_unified_grid_enabled(self) -> bool:
        """Check if unified grid system is enabled (DEPRECATED - use unified_executor instead)"""
        return getattr(self.system, 'enable_unified_grid', False) and hasattr(self.system, 'unified_grid')

    def _handle_exit_signal(self, signal, data, open_positions):
        """Handle exit signal with priority"""
        logger.info("=" * 80)
        logger.info(f" EXIT SIGNAL DETECTED: {signal.signal_type.value}")
        logger.info(f"   Z-score: {signal.zscore:.3f}")
        logger.info(f"   Current positions: {len(open_positions)}")
        logger.info("=" * 80)

        # Queue exit signal with priority
        try:
            self.system.signal_queue.put({
                'signal': signal,
                'data': data,
                'action_type': 'EXIT',
                'grid_level': None,
                'volume_adjustment': None,
                'priority': 'EXIT'
            }, timeout=1.0)
            logger.info(" Exit signal queued successfully")

        except queue.Full:
            # Clear queue for exit priority
            logger.error(" CRITICAL: Signal queue full during exit!")
            self._force_clear_queue()

            self.system.signal_queue.put({
                'signal': signal,
                'data': data,
                'action_type': 'EXIT',
                'grid_level': None,
                'volume_adjustment': None,
                'priority': 'EXIT'
            })
            logger.info(" Exit signal queued after queue clear")

        # Reset grid on exit
        if self._is_unified_grid_enabled():
            self.system.unified_grid.reset()
            logger.info(" Unified grid reset on exit")

        # Cleanup unified executor on exit (reset 2-variable state)
        if self._is_unified_executor_enabled():
            # Get spread_ids to cleanup
            spread_ids_to_cleanup = list(self.system.unified_executor.spread_states.keys())
            for spread_id in spread_ids_to_cleanup:
                self.system.unified_executor.reset_state(spread_id)
            logger.info(f" Simple unified executor: Reset {len(spread_ids_to_cleanup)} spread states")

    def _process_unified_executor(self, signal, data, snapshot, current_position, open_positions):
        """
        Process using simple unified executor (2-variable algorithm)

        Uses check_and_execute() which handles both entry and pyramiding automatically.
        Executor checks last_z vs next_z internally - we just pass the data.
        """
        executor = self.system.unified_executor

        # Get spread_id if we have position
        spread_id = None
        if current_position and open_positions:
            spread_id = self._get_spread_id_from_positions(open_positions)

        # Simple: Let executor check and execute if needed
        # It handles both entry (spread_id=None) and pyramiding (spread_id exists)
        executed = executor.check_and_execute(
            signal=signal,
            snapshot=snapshot,
            current_position=current_position,
            spread_id=spread_id
        )

        if executed:
            logger.info(f"[SIMPLE-UNIFIED] ✓ Position executed")

        # Log state periodically
        if spread_id and spread_id in executor.spread_states:
            if not hasattr(self, '_last_state_log'):
                self._last_state_log = {}

            if spread_id not in self._last_state_log or time.time() - self._last_state_log[spread_id] > 60:
                self._last_state_log[spread_id] = time.time()
                state = executor.get_state(spread_id)
                if state:
                    logger.info(f"[SIMPLE-UNIFIED] {state}")

    def _get_spread_id_from_positions(self, open_positions) -> Optional[str]:
        """Extract spread_id from open positions"""
        for pos in open_positions:
            if 'spread_id' in pos.metadata:
                return pos.metadata['spread_id']
        return None

    def _process_unified_grid(self, signal, data, snapshot, current_position, open_positions):
        """Process using unified grid system"""
        grid = self.system.unified_grid

        # ========== CASE 1: NO POSITION - CHECK FOR ENTRY ===========
        if not current_position:
            # Check if z-score crosses entry threshold
            if signal.signal_type == SignalType.LONG_SPREAD:
                # Activate grid for LONG
                if not grid.side:
                    import uuid
                    spread_id = str(uuid.uuid4())
                    grid.activate(side='LONG', spread_id=spread_id)
                    logger.info(f"[GRID] Activated for LONG spread: {spread_id[:8]}")

            elif signal.signal_type == SignalType.SHORT_SPREAD:
                # Activate grid for SHORT
                if not grid.side:
                    import uuid
                    spread_id = str(uuid.uuid4())
                    grid.activate(side='SHORT', spread_id=spread_id)
                    logger.info(f"[GRID] Activated for SHORT spread: {spread_id[:8]}")

        # ========== CASE 2: HAS POSITION - CHECK GRID LEVELS ===========
        if grid.side:
            # Check which level to trigger
            result = grid.check_levels(snapshot.zscore)

            if result.has_skipped:
                logger.info(f"[GRID] Skipping {len(result.skipped_levels)} levels (z-score jumped)")
                # Skipped levels will be marked when executing

            if result.has_trigger:
                level = result.triggered_level
                logger.info(f"[GRID] Level triggered: {level.name} at z={level.zscore:.2f}")
                logger.info(f"  Current z: {snapshot.zscore:.3f}")
                logger.info(f"  Reason: {result.reason}")

                # Queue grid level execution
                try:
                    self.system.signal_queue.put({
                        'signal': signal,
                        'data': data,
                        'action_type': 'GRID_LEVEL',
                        'grid_result': result,  # Contains triggered_level and skipped_levels
                        'volume_adjustment': None,
                        'priority': 'NORMAL'
                    }, block=False)
                    logger.info(f"[GRID] Level {level.name} queued for execution")
                except queue.Full:
                    logger.warning("[GRID] Signal queue full - level execution delayed")

            # Log grid status periodically
            if hasattr(self, '_last_grid_log') and time.time() - self._last_grid_log < 60:
                pass  # Skip logging
            else:
                self._last_grid_log = time.time()
                stats = grid.get_statistics()
                logger.info(f"[GRID STATUS] Executed: {stats['executed_fraction']:.0%} | "
                           f"Blocked: {stats['blocked_fraction']:.0%} | "
                           f"Remaining: {stats['remaining_fraction']:.0%}")

        # ========== VOLUME REBALANCING (System 3) ===========
        if open_positions and getattr(self.system, 'enable_volume_rebalancing', True):
            self._check_volume_rebalancing(signal, data, snapshot)

    def _process_legacy_rebalancer(self, signal, data, snapshot, open_positions):
        """Fallback to legacy pyramiding/rebalancing system"""
        if not open_positions:
            return

        # Auto-sync MT5 positions
        if self.system.enable_manual_position_sync:
            if hasattr(self.system, '_sync_mt5_positions_to_rebalancer'):
                self.system._sync_mt5_positions_to_rebalancer(snapshot.hedge_ratio)

        # Get MT5 volumes
        mt5_primary_lots, mt5_secondary_lots = self._get_mt5_volumes()

        # Check rebalancing
        try:
            pyramid_actions, volume_adjustments = self.system.rebalancer.check_all_rebalancing(
                current_zscore=snapshot.zscore,
                current_hedge_ratio=snapshot.hedge_ratio,
                mt5_primary_lots=mt5_primary_lots,
                mt5_secondary_lots=mt5_secondary_lots
            )

            # Limit actions
            pyramid_actions = pyramid_actions[:2]
            volume_adjustments = volume_adjustments[:1]

        except Exception as e:
            logger.error(f"Rebalancing check error: {e}")
            pyramid_actions = []
            volume_adjustments = []

        # Queue pyramiding actions
        for action in pyramid_actions:
            logger.info(f"[PYRAMIDING] {action['reason']}")
            try:
                self.system.signal_queue.put({
                    'signal': signal,
                    'data': data,
                    'action_type': 'PYRAMIDING',
                    'pyramiding': action,
                    'volume_adjustment': None
                }, block=False)
            except queue.Full:
                logger.warning("Signal queue full - skipping pyramid action")
                break

        # Queue volume adjustments
        for adjustment in volume_adjustments:
            logger.info(f"[VOLUME REBALANCE] {adjustment.reason}")
            try:
                self.system.signal_queue.put({
                    'signal': signal,
                    'data': data,
                    'action_type': 'VOLUME_REBALANCE',
                    'pyramiding': None,
                    'volume_adjustment': adjustment
                }, block=False)
            except queue.Full:
                logger.warning("Signal queue full - skipping volume adjustment")
                break

    def _check_volume_rebalancing(self, signal, data, snapshot):
        """Check and queue volume rebalancing (System 3)"""
        # Volume rebalancing uses HybridRebalancer's check_volume_imbalance method
        if not hasattr(self.system, 'rebalancer'):
            return

        # Need active positions in rebalancer
        if not self.system.rebalancer.active_positions:
            return

        mt5_primary_lots, mt5_secondary_lots = self._get_mt5_volumes()

        try:
            # Check for each active spread
            for spread_id in list(self.system.rebalancer.active_positions.keys()):
                adjustment = self.system.rebalancer.check_volume_imbalance(
                    spread_id=spread_id,
                    current_hedge_ratio=snapshot.hedge_ratio,
                    current_zscore=snapshot.zscore,
                    mt5_primary_lots=mt5_primary_lots,
                    mt5_secondary_lots=mt5_secondary_lots
                )

                if adjustment:
                    logger.info(f"[VOLUME REBALANCE] {adjustment.reason}")
                    try:
                        self.system.signal_queue.put({
                            'signal': signal,
                            'data': data,
                            'action_type': 'VOLUME_REBALANCE',
                            'grid_result': None,
                            'volume_adjustment': adjustment,
                            'priority': 'NORMAL'
                        }, block=False)
                    except queue.Full:
                        logger.warning("Signal queue full - skipping volume adjustment")
                    break  # Only one adjustment per cycle

        except Exception as e:
            logger.error(f"Volume rebalancing check error: {e}")

    def _queue_entry_signal(self, signal, data):
        """
        DEPRECATED: Queue entry signal (legacy mode only)
        Should NOT be called when SimpleUnifiedExecutor is enabled
        """
        logger.error(f"[SIGNAL] ❌ _queue_entry_signal() called - this should not happen!")
        logger.error(f"[SIGNAL] SimpleUnifiedExecutor should handle entries directly")
        logger.error(f"[SIGNAL] Check if enable_unified_executor=True")
        return

    def _get_mt5_volumes(self):
        """Get real MT5 position volumes"""
        mt5_primary_lots = None
        mt5_secondary_lots = None

        try:
            mt5 = get_mt5()
            positions = mt5.positions_get()

            if positions:
                primary_positions = [p for p in positions if p.symbol == self.system.primary_symbol]
                secondary_positions = [p for p in positions if p.symbol == self.system.secondary_symbol]

                # Calculate NET lots
                primary_long = sum(p.volume for p in primary_positions if p.type == mt5.ORDER_TYPE_BUY)
                primary_short = sum(p.volume for p in primary_positions if p.type == mt5.ORDER_TYPE_SELL)
                mt5_primary_lots = primary_long - primary_short

                secondary_long = sum(p.volume for p in secondary_positions if p.type == mt5.ORDER_TYPE_BUY)
                secondary_short = sum(p.volume for p in secondary_positions if p.type == mt5.ORDER_TYPE_SELL)
                mt5_secondary_lots = secondary_long - secondary_short

                logger.debug(f"[MT5-VOLUMES] Primary: {mt5_primary_lots:+.4f}, Secondary: {mt5_secondary_lots:+.4f}")

        except Exception as e:
            logger.warning(f"Failed to get MT5 volumes: {e}")

        return mt5_primary_lots, mt5_secondary_lots

    def _force_clear_queue(self):
        """Force clear signal queue"""
        cleared = 0
        while not self.system.signal_queue.empty():
            try:
                self.system.signal_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        logger.warning(f"Cleared {cleared} queued signals for exit priority")

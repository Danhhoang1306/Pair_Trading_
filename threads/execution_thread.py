"""
ExecutionThread - Unified Grid Version
Handles order execution for grid levels and volume rebalancing
"""
import time
import queue
import logging
from datetime import datetime
from .base_thread import BaseThread
from strategy.signal_generator import SignalType

logger = logging.getLogger(__name__)


class ExecutionThread(BaseThread):
    """
    Execution thread with Unified Grid support

    Handles:
    1. Grid level execution (entry + pyramiding)
    2. Volume rebalancing (System 3)
    3. Exit signals
    4. Legacy entry/pyramiding (fallback)
    """

    def __init__(self, system):
        super().__init__("ExecutionThread", system)

    def run(self):
        """Execution thread main loop"""
        logger.info("ExecutionThread started")

        while self.system.running:
            try:
                signal_data = self.system.signal_queue.get(timeout=5)

                with self.system.lock:
                    self._process_signal_data(signal_data)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Execution thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _process_signal_data(self, signal_data: dict):
        """Process signal data from queue"""
        signal = signal_data['signal']
        data = signal_data['data']
        action_type = signal_data.get('action_type', 'UNKNOWN')
        priority = signal_data.get('priority', 'NORMAL')

        logger.debug(f"Processing action: {action_type} (priority: {priority})")

        # ==================== EXIT SIGNALS (HIGHEST PRIORITY) ====================
        if action_type == 'EXIT' or signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
            self._handle_exit(signal, data)
            return

        # ==================== UNIFIED POSITION EXECUTOR ====================
        # NOTE: SimpleUnifiedExecutor executes directly in SignalThread
        # No need to queue - this action type is unused now
        if action_type == 'UNIFIED_POSITION':
            logger.warning("[EXEC] UNIFIED_POSITION action received but SimpleUnifiedExecutor "
                          "executes directly in SignalThread - this should not happen!")
            return

        # ==================== GRID LEVEL EXECUTION (DEPRECATED) ====================
        if action_type == 'GRID_LEVEL':
            grid_result = signal_data.get('grid_result')
            if grid_result:
                self._handle_grid_level(grid_result, data)
            return

        # ==================== VOLUME REBALANCING (System 3) ====================
        if action_type == 'VOLUME_REBALANCE':
            volume_adjustment = signal_data.get('volume_adjustment')
            if volume_adjustment:
                self._handle_volume_rebalance(volume_adjustment, data)
            return

        # ==================== DEPRECATED ACTIONS ====================
        # These should NOT be received - SimpleUnifiedExecutor handles entry/pyramiding directly in SignalThread
        if action_type == 'PYRAMIDING':
            logger.error(f"[EXEC] ❌ Received PYRAMIDING action - this should not happen!")
            logger.error(f"[EXEC] SimpleUnifiedExecutor should handle pyramiding directly in SignalThread")
            logger.error(f"[EXEC] Check if enable_unified_executor=True and legacy rebalancer is disabled")
            return

        if action_type == 'ENTRY' or signal.signal_type in [SignalType.LONG_SPREAD, SignalType.SHORT_SPREAD]:
            logger.error(f"[EXEC] ❌ Received ENTRY action - this should not happen!")
            logger.error(f"[EXEC] SimpleUnifiedExecutor should handle entry directly in SignalThread")
            logger.error(f"[EXEC] Check if enable_unified_executor=True and legacy entry executor is disabled")
            return

        logger.warning(f"[EXEC] Unknown action type: {action_type}")

    def _handle_exit(self, signal, data):
        """Handle exit signal"""
        logger.info(f"[EXEC] Processing EXIT: {signal.signal_type.value}")
        self.system.exit_executor.execute(signal, data)
        logger.info(f"[EXEC] Exit complete - positions: {len(self.system.position_tracker.positions)}")

        # Note: Grid reset is handled by exit_executor.fast_close_all_positions()

    # REMOVED: _handle_unified_position() - SimpleUnifiedExecutor executes directly in SignalThread
    # No need for ExecutionThread handler anymore

    def _handle_grid_level(self, grid_result, data):
        """Handle grid level execution"""
        snapshot = data['snapshot']

        # Mark skipped levels as BLOCKED
        if grid_result.has_skipped:
            self.system.unified_grid.mark_skipped(grid_result.skipped_levels)
            for level in grid_result.skipped_levels:
                logger.info(f"[GRID] Level {level.name} BLOCKED (skipped)")

        # Execute triggered level
        if not grid_result.has_trigger:
            return

        level = grid_result.triggered_level
        logger.info(f"[EXEC] ====== GRID LEVEL: {level.name} ======")

        # Risk checks before execution
        if not self._check_risk_for_grid():
            logger.warning(f"[EXEC] Risk check failed - level {level.name} blocked")
            return

        # Daily risk check
        if not self.system.daily_risk_manager.can_trade():
            logger.critical(f"[EXEC] TRADING LOCKED: {self.system.daily_risk_manager.lock_reason}")
            return

        # Execute using GridExecutor
        if hasattr(self.system, 'grid_executor'):
            success = self.system.grid_executor.process_grid_check(
                result=grid_result,
                snapshot=snapshot,
                account_balance=self.system.account_balance
            )

            if success:
                logger.info(f"[EXEC] Level {level.name} executed successfully")
                self._log_grid_status()
            else:
                logger.error(f"[EXEC] Level {level.name} execution failed")
        else:
            # Fallback: use legacy entry executor for entry level
            if level.index == 0:  # Entry level
                self._handle_entry_via_legacy(snapshot, level)
            else:
                logger.warning("[EXEC] GridExecutor not available, cannot execute pyramid level")

    def _handle_entry_via_legacy(self, snapshot, level):
        """Fallback: execute entry via legacy entry executor"""
        logger.info(f"[EXEC] Using legacy entry for level {level.name}")

        # Calculate position size
        primary_vol, _ = self.system.market_data.get_volatility()

        pos_size_result = self.system.position_sizer.calculate_optimal(
            win_rate=0.55,
            avg_win=150,
            avg_loss=100,
            volatility=primary_vol
        )

        # Create a mock signal for entry executor
        from strategy.signal_generator import TradingSignal, SignalStrength
        from datetime import datetime

        side = self.system.unified_grid.side
        signal_type = SignalType.LONG_SPREAD if side == 'LONG' else SignalType.SHORT_SPREAD

        mock_signal = TradingSignal(
            signal_type=signal_type,
            strength=SignalStrength.MEDIUM,
            zscore=snapshot.zscore,
            spread=0,
            hedge_ratio=snapshot.hedge_ratio,
            confidence=0.7,
            timestamp=datetime.now()
        )

        # Execute
        self.system.entry_executor.execute(mock_signal, snapshot, pos_size_result)

        # Mark level as executed in grid
        # Note: We don't have actual lots here, entry_executor handles it
        self.system.unified_grid.mark_executed(
            level=level,
            primary_lots=pos_size_result.position_size,  # Approximate
            secondary_lots=pos_size_result.position_size * snapshot.hedge_ratio,
            order_tickets=[]  # Entry executor handles tickets
        )

    def _handle_volume_rebalance(self, adjustment, data):
        """Handle volume rebalancing (System 3)"""
        logger.info(f"[EXEC] Processing VOLUME REBALANCE: {adjustment.reason}")

        if hasattr(self.system, 'volume_rebalancer'):
            self.system.volume_rebalancer.execute(adjustment, data['snapshot'])
        else:
            logger.warning("[EXEC] VolumeRebalancer not available")

    def _handle_entry(self, signal, data):
        """
        DEPRECATED: Legacy entry handler - should NOT be called!
        SimpleUnifiedExecutor handles entry directly in SignalThread.
        """
        logger.error(f"[EXEC] ❌ _handle_entry() called - this is deprecated!")
        logger.error(f"[EXEC] SimpleUnifiedExecutor should handle all entries")
        return

    def _check_risk_for_grid(self) -> bool:
        """Check risk before grid level execution"""
        # Max position check based on grid fraction
        stats = self.system.unified_grid.get_statistics()

        # Check if we've exceeded max allowed fraction
        max_fraction = getattr(self.system, 'max_position_pct', 100) / 100
        if stats['executed_fraction'] >= max_fraction:
            logger.warning(f"Max position fraction reached: {stats['executed_fraction']:.0%}")
            return False

        # Check drawdown
        dd_metrics = self.system.drawdown_monitor.get_metrics()
        max_dd = getattr(self.system, 'max_drawdown_pct', 20) / 100

        if dd_metrics.current_drawdown_pct >= max_dd:
            logger.warning(f"Max drawdown reached: {dd_metrics.current_drawdown_pct:.1%}")
            return False

        return True

    def _is_unified_grid_enabled(self) -> bool:
        """Check if unified grid is enabled"""
        return getattr(self.system, 'enable_unified_grid', False) and hasattr(self.system, 'unified_grid')

    def _log_grid_status(self):
        """Log current grid status"""
        if not self._is_unified_grid_enabled():
            return

        stats = self.system.unified_grid.get_statistics()
        logger.info(f"[GRID STATUS] Executed: {stats['executed_fraction']:.0%} | "
                   f"Levels: {stats['executed_count']}/{stats['total_levels']} | "
                   f"Lots: {stats['total_primary_lots']:.4f}/{stats['total_secondary_lots']:.4f}")

"""
Simple Unified Position Executor - Simplified 2-variable approach
Merges EntryExecutor + PyramidingExecutor with minimal state management

Design Philosophy:
- Only 2 variables: last_z_entry, next_z_entry
- No complex level lists or state machines
- Simple comparison: current_z >= next_z_entry → Execute
- Reset on exit

Author: Claude Code
Created: 2026-01-16
"""

import logging
import json
import os
from datetime import datetime
from typing import Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

from strategy.signal_generator import SignalType
from strategy.order_manager import OrderStatus
from core.position_persistence import PersistedPosition
from analytics.pnl_attribution import get_attribution_engine, PositionSnapshot

logger = logging.getLogger(__name__)


@dataclass
class SpreadEntryState:
    """Simple state tracking for a spread position"""
    spread_id: str
    side: str  # 'LONG' or 'SHORT'
    last_z_entry: float  # Z-score of last entry
    next_z_entry: float  # Z-score for next entry
    entry_count: int = 0  # Number of entries made
    total_primary_lots: float = 0.0
    total_secondary_lots: float = 0.0
    first_entry_spread_mean: float = 0.0  # Spread mean at first entry (for mean drift calculation)

    def __str__(self):
        return f"Spread {self.spread_id[:8]}: {self.side} | Last z={self.last_z_entry:.2f} | Next z={self.next_z_entry:.2f} | Entries={self.entry_count}"


class SimpleUnifiedExecutor:
    """
    Simplified unified executor using 2-variable tracking

    Algorithm:
    1. First entry: Save last_z_entry, calculate next_z_entry = last_z + scale_interval
    2. Check: if current_z crosses next_z_entry → Execute
    3. After execute: Update last_z_entry, calculate new next_z_entry
    4. On exit: Reset all variables

    No complex state, no level lists, just simple comparisons.
    """

    def __init__(self,
                 trade_executor,
                 order_manager,
                 position_tracker,
                 market_data,
                 persistence,
                 flag_manager,
                 position_monitor,
                 signal_generator,
                 trading_lock_manager,
                 account_balance=0,
                 mt5_tickets=None,
                 primary_symbol='XAUUSD',
                 secondary_symbol='XAGUSD',
                 risk_thread=None,
                 # Config
                 entry_threshold=2.0,
                 scale_interval=0.5,
                 max_zscore=3.5,
                 initial_fraction=0.33,
                 max_entries=10):
        """
        Initialize Simple Unified Executor

        Args:
            scale_interval: Z-score interval between entries (e.g., 0.5)
            max_zscore: Maximum z-score limit (stop adding positions)
            initial_fraction: Position size fraction per entry
            max_entries: Maximum number of entries allowed

        Note: No entry_cooldown needed - last_z/next_z automatically prevents duplicates!
        """
        # Core dependencies
        self.trade_executor = trade_executor
        self.order_manager = order_manager
        self.position_tracker = position_tracker
        self.market_data = market_data
        self.persistence = persistence
        self.flag_manager = flag_manager
        self.position_monitor = position_monitor
        self.signal_generator = signal_generator
        self.trading_lock_manager = trading_lock_manager
        self.account_balance = account_balance
        self.mt5_tickets = mt5_tickets if mt5_tickets is not None else {}
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol
        self.risk_thread = risk_thread

        # Config
        self.entry_threshold = entry_threshold
        self.scale_interval = scale_interval
        self.max_zscore = max_zscore
        self.initial_fraction = initial_fraction
        self.max_entries = max_entries

        # Simple state tracking - ONE state per spread
        self.spread_states: dict[str, SpreadEntryState] = {}

        # State persistence - use absolute path from project root
        self.state_file = Path(__file__).parent.parent / "asset" / "state" / "spread_states.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_states()

        logger.info("SimpleUnifiedExecutor initialized")
        logger.info(f"  Entry threshold: ±{entry_threshold}")
        logger.info(f"  Scale interval: {scale_interval}")
        logger.info(f"  Max z-score: ±{max_zscore}")
        logger.info(f"  Fraction per entry: {initial_fraction:.1%}")
        logger.info(f"  Algorithm: 2-variable tracking (last_z, next_z)")
        logger.info(f"  State persistence: {self.state_file}")
        logger.info(f"  ✓ No cooldown needed - automatic duplicate prevention!")

    def check_and_execute(self, signal, snapshot, current_position, spread_id: Optional[str] = None) -> bool:
        """
        Check if we should execute and execute if needed

        This is the MAIN method - handles both entry and pyramiding

        Args:
            signal: Trading signal
            snapshot: MarketSnapshot
            current_position: Current position side ('LONG', 'SHORT', or None)
            spread_id: Existing spread ID (None for new entry)

        Returns:
            True if executed
        """
        current_z = snapshot.zscore

        # ========== CASE 1: NO POSITION - CHECK ENTRY ==========
        if not current_position and signal.signal_type in [SignalType.LONG_SPREAD, SignalType.SHORT_SPREAD]:
            # IMPORTANT: Only execute if we don't have ANY active spreads
            # (Prevents duplicate entries when signal oscillates)
            if len(self.spread_states) == 0:
                return self._execute_entry(signal, snapshot)
            else:
                # Already have a spread - don't create duplicate
                return False

        # ========== CASE 2: HAS POSITION - CHECK PYRAMIDING ==========
        if current_position and spread_id and spread_id in self.spread_states:
            return self._check_and_execute_pyramid(spread_id, current_z, snapshot)

        return False

    def _execute_entry(self, signal, snapshot) -> bool:
        """Execute initial entry"""
        side = 'LONG' if signal.signal_type == SignalType.LONG_SPREAD else 'SHORT'
        current_z = snapshot.zscore

        # Validate
        if not self._validate_execution(side, current_z):
            return False

        logger.info("="*80)
        logger.info(f"[SIMPLE-UNIFIED] INITIAL ENTRY")
        logger.info(f"  Side: {side}")
        logger.info(f"  Z-score: {current_z:.3f}")
        logger.info(f"  Threshold: ±{self.entry_threshold}")
        logger.info("="*80)

        # ========== CREATE TEMPORARY STATE FIRST ==========
        # This prevents duplicate attempts if orders fail
        import uuid
        temp_spread_id = str(uuid.uuid4())

        if side == 'LONG':
            temp_next_z = current_z - self.scale_interval
        else:
            temp_next_z = current_z + self.scale_interval

        temp_state = SpreadEntryState(
            spread_id=temp_spread_id,
            side=side,
            last_z_entry=current_z,
            next_z_entry=temp_next_z,
            entry_count=0  # Not executed yet
        )

        # Store temp state to prevent re-entry
        self.spread_states[temp_spread_id] = temp_state
        logger.debug(f"[SIMPLE-UNIFIED] Temp state created to prevent duplicates")

        # Calculate position size
        primary_lots, secondary_lots = self._calculate_position_size(snapshot)

        # Execute orders
        primary_result, secondary_result, spread_id, entry_zscore = self._execute_orders(
            side, primary_lots, secondary_lots, snapshot, is_first_entry=True
        )

        if not primary_result or not secondary_result:
            # Orders failed - remove temp state
            del self.spread_states[temp_spread_id]
            logger.error(f"[SIMPLE-UNIFIED] Orders failed - temp state removed")
            return False

        # Orders succeeded - remove temp state and create real one
        del self.spread_states[temp_spread_id]

        # Register in all systems (full registration for first entry)
        self._register_execution(
            spread_id, side, snapshot, entry_zscore,
            primary_result, secondary_result, is_first_entry=True
        )

        # ========== CREATE STATE (2 variables) ==========
        # Calculate next_z_entry based on direction
        if side == 'LONG':
            # LONG: z goes MORE negative, so next = current - interval
            next_z = current_z - self.scale_interval
        else:
            # SHORT: z goes MORE positive, so next = current + interval
            next_z = current_z + self.scale_interval

        # Create state
        state = SpreadEntryState(
            spread_id=spread_id,
            side=side,
            last_z_entry=current_z,
            next_z_entry=next_z,
            entry_count=1,
            total_primary_lots=primary_lots,
            total_secondary_lots=secondary_lots,
            first_entry_spread_mean=snapshot.spread_mean if snapshot else 0.0
        )
        self.spread_states[spread_id] = state

        logger.info(f"[SIMPLE-UNIFIED] State created:")
        logger.info(f"  last_z_entry = {state.last_z_entry:.3f}")
        logger.info(f"  next_z_entry = {state.next_z_entry:.3f}")
        logger.info(f"  entry_count = {state.entry_count}")
        logger.info(f"  first_entry_spread_mean = {state.first_entry_spread_mean:.2f}")

        # Save state to disk
        self._save_states()

        # No cooldown needed - next_z_entry provides automatic protection!

        return True

    def _check_and_execute_pyramid(self, spread_id: str, current_z: float, snapshot) -> bool:
        """
        Check if pyramiding should execute using simple 2-variable comparison

        Algorithm:
        - LONG: if current_z <= next_z_entry → Execute (z going more negative)
        - SHORT: if current_z >= next_z_entry → Execute (z going more positive)
        """
        state = self.spread_states[spread_id]

        # Check if we've hit max entries
        if state.entry_count >= self.max_entries:
            logger.debug(f"[SIMPLE-UNIFIED] Max entries ({self.max_entries}) reached for {spread_id[:8]}")
            return False

        # Check if we've hit max z-score
        if abs(current_z) >= abs(self.max_zscore):
            logger.warning(f"[SIMPLE-UNIFIED] Max z-score ({self.max_zscore}) reached at z={current_z:.3f}")
            return False

        # ========== SIMPLE COMPARISON ==========
        should_execute = False

        if state.side == 'LONG':
            # LONG: Execute when z-score goes MORE negative (crosses next_z_entry downward)
            if current_z <= state.next_z_entry:
                should_execute = True
                logger.debug(f"[SIMPLE-UNIFIED] LONG trigger: {current_z:.3f} <= {state.next_z_entry:.3f}")
            else:
                logger.debug(f"[SIMPLE-UNIFIED] LONG waiting: {current_z:.3f} > {state.next_z_entry:.3f}")
        else:
            # SHORT: Execute when z-score goes MORE positive (crosses next_z_entry upward)
            if current_z >= state.next_z_entry:
                should_execute = True
                logger.debug(f"[SIMPLE-UNIFIED] SHORT trigger: {current_z:.3f} >= {state.next_z_entry:.3f}")
            else:
                logger.debug(f"[SIMPLE-UNIFIED] SHORT waiting: {current_z:.3f} < {state.next_z_entry:.3f}")

        if not should_execute:
            return False

        # ========== EXECUTE PYRAMIDING ==========
        logger.info("="*80)
        logger.info(f"[SIMPLE-UNIFIED] PYRAMIDING TRIGGERED")
        logger.info(f"  Spread: {spread_id[:8]}")
        logger.info(f"  Side: {state.side}")
        logger.info(f"  Current z: {current_z:.3f}")
        logger.info(f"  Crossed: {state.next_z_entry:.3f}")
        logger.info(f"  Entry #{state.entry_count + 1}")
        logger.info("="*80)

        # Validate
        if not self._validate_execution(state.side, current_z):
            return False

        # ========== UPDATE STATE TEMPORARILY ==========
        # Save old values in case we need to rollback
        old_last_z = state.last_z_entry
        old_next_z = state.next_z_entry

        # Update state BEFORE executing to prevent duplicate attempts
        state.last_z_entry = current_z
        if state.side == 'LONG':
            state.next_z_entry = current_z - self.scale_interval
        else:
            state.next_z_entry = current_z + self.scale_interval

        logger.debug(f"[SIMPLE-UNIFIED] Temp state update: next_z {old_next_z:.3f} -> {state.next_z_entry:.3f}")

        # Calculate position size
        primary_lots, secondary_lots = self._calculate_position_size(snapshot)

        # Execute orders
        primary_result, secondary_result, _, _ = self._execute_orders(
            state.side, primary_lots, secondary_lots, snapshot,
            is_first_entry=False, spread_id=spread_id
        )

        if not primary_result or not secondary_result:
            # Orders failed - rollback state
            state.last_z_entry = old_last_z
            state.next_z_entry = old_next_z
            logger.error(f"[SIMPLE-UNIFIED] Orders failed - state rolled back")
            return False

        # Register monitors only (not full registration)
        self._register_monitor(primary_result, secondary_result)

        # ========== FINALIZE STATE UPDATE ==========
        # (last_z_entry and next_z_entry already updated before execution)
        state.entry_count += 1
        state.total_primary_lots += primary_lots
        state.total_secondary_lots += secondary_lots

        logger.info(f"[SIMPLE-UNIFIED] State updated:")
        logger.info(f"  last_z_entry = {state.last_z_entry:.3f} (was {old_last_z:.3f})")
        logger.info(f"  next_z_entry = {state.next_z_entry:.3f}")
        logger.info(f"  entry_count = {state.entry_count}")
        logger.info(f"  total_lots = {state.total_primary_lots:.4f} XAU + {state.total_secondary_lots:.4f} XAG")

        # Save state to disk
        self._save_states()

        # No cooldown needed - next_z_entry provides automatic protection!

        return True

    def reset_state(self, spread_id: str):
        """
        Reset state for a spread (called on exit)

        This is the reset function you mentioned
        """
        if spread_id in self.spread_states:
            state = self.spread_states[spread_id]
            logger.info(f"[SIMPLE-UNIFIED] Resetting state for {spread_id[:8]}")
            logger.info(f"  Final entries: {state.entry_count}")
            logger.info(f"  Last z: {state.last_z_entry:.3f}")
            del self.spread_states[spread_id]
            # Save state to disk after reset
            self._save_states()
        else:
            logger.debug(f"[SIMPLE-UNIFIED] No state to reset for {spread_id[:8]}")

    def get_state(self, spread_id: str) -> Optional[SpreadEntryState]:
        """Get current state for a spread"""
        return self.spread_states.get(spread_id)

    def _validate_execution(self, side: str, zscore: float) -> bool:
        """
        Validate if execution is allowed

        Note: No cooldown check needed - last_z/next_z provides natural protection!
        """
        # Check trading lock
        if self.trading_lock_manager.is_locked():
            logger.warning(f"[SIMPLE-UNIFIED] BLOCKED - System is LOCKED")
            return False

        return True

    def _calculate_position_size(self, snapshot) -> Tuple[float, float]:
        """Calculate position sizes based on fraction"""
        primary_value = self.account_balance * self.initial_fraction
        primary_quantity = primary_value / snapshot.primary_bid / 100

        # Use real-time hedge calculation
        primary_lots, secondary_lots = self.market_data.calculate_hedge_quantities(primary_quantity)

        return primary_lots, secondary_lots

    def _execute_orders(self, side, primary_lots, secondary_lots, snapshot,
                       is_first_entry: bool, spread_id: Optional[str] = None):
        """Execute spread orders on MT5"""
        if is_first_entry:
            # Use place_spread_orders for first entry
            (primary_result, secondary_result), spread_id, entry_zscore = self.trade_executor.place_spread_orders(
                primary_volume=primary_lots,
                secondary_volume=secondary_lots,
                side=side,
                entry_zscore=snapshot.zscore
            )
        else:
            # Use individual orders for pyramiding
            primary_type = 'BUY' if side == 'LONG' else 'SELL'
            secondary_type = 'SELL' if side == 'LONG' else 'BUY'

            primary_result = self.trade_executor.place_market_order(
                symbol=self.primary_symbol,
                order_type=primary_type,
                volume=primary_lots,
                comment=f"PYRAMID:{spread_id[:8]}"
            )

            if not primary_result.success:
                return None, None, None, None

            secondary_result = self.trade_executor.place_market_order(
                symbol=self.secondary_symbol,
                order_type=secondary_type,
                volume=secondary_lots,
                comment=f"PYRAMID:{spread_id[:8]}"
            )

            entry_zscore = snapshot.zscore

        # Check success
        if not primary_result.success or not secondary_result.success:
            logger.error(f"[SIMPLE-UNIFIED] Trade execution FAILED!")
            return None, None, None, None

        logger.info(f"[SIMPLE-UNIFIED] Orders filled:")
        logger.info(f"  Primary: {primary_result.order_ticket} - {primary_result.volume} @ ${primary_result.price:.2f}")
        logger.info(f"  Secondary: {secondary_result.order_ticket} - {secondary_result.volume} @ ${secondary_result.price:.4f}")

        return primary_result, secondary_result, spread_id, entry_zscore

    def _register_execution(self, spread_id, side, snapshot, entry_zscore,
                          primary_result, secondary_result, is_first_entry: bool):
        """Register execution in tracking systems"""
        # Full registration for first entry
        if is_first_entry:
            # Attribution
            try:
                entry_snapshot = PositionSnapshot(
                    timestamp=datetime.now(),
                    xau_bid=snapshot.primary_bid,
                    xau_ask=snapshot.primary_ask,
                    xag_bid=snapshot.secondary_bid,
                    xag_ask=snapshot.secondary_ask,
                    spread=snapshot.spread,
                    mean=snapshot.spread_mean,
                    std=snapshot.spread_std,
                    zscore=entry_zscore,
                    hedge_ratio=snapshot.hedge_ratio,
                    xau_volume=primary_result.volume,
                    xag_volume=secondary_result.volume,
                    xau_side='LONG' if side == 'LONG' else 'SHORT',
                    xag_side='SHORT' if side == 'LONG' else 'LONG',
                    xau_price=primary_result.price,
                    xag_price=secondary_result.price
                )
                attribution_engine = get_attribution_engine()
                attribution_engine.register_position(spread_id, entry_snapshot)
            except Exception as e:
                logger.error(f"Failed to register attribution: {e}")

            # Order manager
            primary_order, secondary_order = self.order_manager.create_spread_orders(
                primary_result.volume, secondary_result.volume, side
            )
            self.order_manager.update_order_status(
                primary_order.order_id, OrderStatus.FILLED,
                primary_result.volume, primary_result.price
            )
            self.order_manager.update_order_status(
                secondary_order.order_id, OrderStatus.FILLED,
                secondary_result.volume, secondary_result.price
            )

            # Position tracker
            primary_pos, secondary_pos = self.position_tracker.open_spread_position(
                primary_result.volume, secondary_result.volume,
                primary_result.price, secondary_result.price,
                side, snapshot.hedge_ratio
            )
            primary_pos.metadata['spread_id'] = spread_id
            secondary_pos.metadata['spread_id'] = spread_id
            self.mt5_tickets[primary_pos.position_id] = primary_result.order_ticket
            self.mt5_tickets[secondary_pos.position_id] = secondary_result.order_ticket

            # Persistence
            primary_persisted = PersistedPosition(
                position_id=primary_pos.position_id,
                spread_id=spread_id,
                mt5_ticket=primary_result.order_ticket,
                symbol=self.primary_symbol,
                side=primary_pos.side,
                volume=primary_pos.quantity,
                entry_price=primary_pos.entry_price,
                entry_time=str(primary_pos.opened_at),
                entry_zscore=entry_zscore,
                hedge_ratio=snapshot.hedge_ratio,
                is_primary=True,
                created_at=datetime.now().isoformat(),
                last_updated=datetime.now().isoformat()
            )
            self.persistence.save_position(primary_persisted)

            secondary_persisted = PersistedPosition(
                position_id=secondary_pos.position_id,
                spread_id=spread_id,
                mt5_ticket=secondary_result.order_ticket,
                symbol=self.secondary_symbol,
                side=secondary_pos.side,
                volume=secondary_pos.quantity,
                entry_price=secondary_pos.entry_price,
                entry_time=str(secondary_pos.opened_at),
                entry_zscore=entry_zscore,
                hedge_ratio=snapshot.hedge_ratio,
                is_primary=False,
                created_at=datetime.now().isoformat(),
                last_updated=datetime.now().isoformat()
            )
            self.persistence.save_position(secondary_persisted)

            # Setup flag
            if not self.flag_manager.is_setup_active():
                self.flag_manager.mark_setup_active(
                    spread_id=spread_id,
                    metadata={'side': side, 'entry_zscore': entry_zscore}
                )

        # Always register monitors
        self._register_monitor(primary_result, secondary_result)

    def _register_monitor(self, primary_result, secondary_result):
        """Register positions with monitors"""
        self.position_monitor.register_position(
            ticket=primary_result.order_ticket,
            symbol=self.primary_symbol
        )
        self.position_monitor.register_position(
            ticket=secondary_result.order_ticket,
            symbol=self.secondary_symbol
        )

        if self.risk_thread:
            self.risk_thread.register_mt5_ticket(primary_result.order_ticket)
            self.risk_thread.register_mt5_ticket(secondary_result.order_ticket)

    def update_balance(self, new_balance: float):
        """Update account balance"""
        self.account_balance = new_balance

    def update_scale_interval(self, new_scale_interval: float):
        """
        Update scale_interval and recalculate next_z_entry for all active spreads

        This method should be called when user changes scale_interval in GUI settings.
        It recalculates next_z_entry based on the NEW scale_interval while preserving last_z_entry.

        Args:
            new_scale_interval: New scale interval value from GUI
        """
        old_interval = self.scale_interval
        self.scale_interval = new_scale_interval

        if not self.spread_states:
            logger.info(f"[SIMPLE-UNIFIED] Scale interval updated: {old_interval} → {new_scale_interval}")
            return

        logger.info("="*70)
        logger.info(f"[SIMPLE-UNIFIED] RECALCULATING next_z_entry")
        logger.info(f"  Scale interval: {old_interval} → {new_scale_interval}")
        logger.info("="*70)

        for spread_id, state in self.spread_states.items():
            old_next_z = state.next_z_entry

            # Recalculate next_z_entry based on last_z_entry and NEW scale_interval
            if state.side == 'LONG':
                # LONG: z goes MORE negative, so next = last - interval
                state.next_z_entry = state.last_z_entry - new_scale_interval
            else:
                # SHORT: z goes MORE positive, so next = last + interval
                state.next_z_entry = state.last_z_entry + new_scale_interval

            logger.info(f"  {spread_id[:8]} ({state.side}):")
            logger.info(f"    last_z_entry = {state.last_z_entry:.3f} (unchanged)")
            logger.info(f"    next_z_entry = {old_next_z:.3f} → {state.next_z_entry:.3f}")

        # Save updated states to disk
        self._save_states()
        logger.info(f"[SIMPLE-UNIFIED] States saved with recalculated next_z_entry")

    def _save_states(self):
        """
        Save spread states to disk for persistence across restarts

        Saves last_z_entry, next_z_entry, entry_count, and first_entry_spread_mean for all active spreads
        """
        try:
            data = {
                'spreads': {
                    spread_id: {
                        'spread_id': state.spread_id,
                        'side': state.side,
                        'last_z_entry': state.last_z_entry,
                        'next_z_entry': state.next_z_entry,
                        'entry_count': state.entry_count,
                        'total_primary_lots': state.total_primary_lots,
                        'total_secondary_lots': state.total_secondary_lots,
                        'first_entry_spread_mean': state.first_entry_spread_mean
                    }
                    for spread_id, state in self.spread_states.items()
                },
                'last_updated': datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"[SIMPLE-UNIFIED] States saved to {self.state_file} ({len(self.spread_states)} spreads)")
        except Exception as e:
            logger.error(f"[SIMPLE-UNIFIED] Failed to save states: {e}")

    def _load_states(self):
        """
        Load spread states from disk on initialization

        Restores last_z_entry, next_z_entry, entry_count, and first_entry_spread_mean from previous session
        """
        try:
            if not self.state_file.exists():
                logger.info(f"[SIMPLE-UNIFIED] No previous state found - starting fresh")
                # Try auto-migration from legacy system
                self._migrate_legacy_positions()
                return

            with open(self.state_file, 'r') as f:
                data = json.load(f)

            # Restore all spread states
            spreads_data = data.get('spreads', {})
            for spread_id, state_dict in spreads_data.items():
                self.spread_states[spread_id] = SpreadEntryState(
                    spread_id=state_dict['spread_id'],
                    side=state_dict['side'],
                    last_z_entry=state_dict['last_z_entry'],
                    next_z_entry=state_dict['next_z_entry'],
                    entry_count=state_dict['entry_count'],
                    total_primary_lots=state_dict['total_primary_lots'],
                    total_secondary_lots=state_dict['total_secondary_lots'],
                    first_entry_spread_mean=state_dict.get('first_entry_spread_mean', 0.0)
                )

            if self.spread_states:
                logger.info(f"[SIMPLE-UNIFIED] Loaded {len(self.spread_states)} spread states from disk:")
                for spread_id, state in self.spread_states.items():
                    logger.info(f"  {spread_id[:8]}: {state.side} | last_z={state.last_z_entry:.3f} | next_z={state.next_z_entry:.3f} | entries={state.entry_count} | first_mean={state.first_entry_spread_mean:.2f}")
            else:
                logger.info(f"[SIMPLE-UNIFIED] State file exists but no active spreads")
                # Try auto-migration if state file is empty but legacy has data
                self._migrate_legacy_positions()

        except Exception as e:
            logger.warning(f"[SIMPLE-UNIFIED] Failed to load states: {e}")
            # Try auto-migration as fallback
            self._migrate_legacy_positions()

    def _migrate_legacy_positions(self):
        """
        Auto-migrate positions from legacy systems:
        1. First try: active_positions.json (current system)
        2. Fallback: last_z_entry.json (old system)

        This allows seamless transition without losing track of existing positions.
        """
        try:
            # ========== PRIORITY 1: Migrate from active_positions.json ==========
            active_positions_file = Path(__file__).parent.parent / "positions" / "active_positions.json"
            if active_positions_file.exists():
                if self._migrate_from_active_positions(active_positions_file):
                    return  # Successfully migrated

            # ========== PRIORITY 2: Migrate from legacy last_z_entry.json ==========
            legacy_file = Path(__file__).parent.parent / "asset" / "state" / "last_z_entry.json"
            if not legacy_file.exists():
                return

            with open(legacy_file, 'r') as f:
                legacy_data = json.load(f)

            migrated_count = 0
            import uuid

            # Migrate LONG position
            if legacy_data.get('long') and isinstance(legacy_data['long'], dict):
                spread_id = str(uuid.uuid4())
                last_z = legacy_data['long']['zscore']
                next_z = last_z - self.scale_interval

                self.spread_states[spread_id] = SpreadEntryState(
                    spread_id=spread_id,
                    side='LONG',
                    last_z_entry=last_z,
                    next_z_entry=next_z,
                    entry_count=1,  # Assume first entry
                    total_primary_lots=0.0,  # Will be updated on next execution
                    total_secondary_lots=0.0
                )

                logger.warning(f"[SIMPLE-UNIFIED] AUTO-MIGRATION: Migrated LONG position from legacy system")
                logger.info(f"  {spread_id[:8]}: LONG | last_z={last_z:.3f} | next_z={next_z:.3f} | entries=1")
                logger.info(f"  Next pyramid will execute when z-score <= {next_z:.3f}")
                migrated_count += 1

            # Migrate SHORT position
            if legacy_data.get('short') and isinstance(legacy_data['short'], dict):
                spread_id = str(uuid.uuid4())
                last_z = legacy_data['short']['zscore']
                next_z = last_z + self.scale_interval

                self.spread_states[spread_id] = SpreadEntryState(
                    spread_id=spread_id,
                    side='SHORT',
                    last_z_entry=last_z,
                    next_z_entry=next_z,
                    entry_count=1,  # Assume first entry
                    total_primary_lots=0.0,  # Will be updated on next execution
                    total_secondary_lots=0.0
                )

                logger.warning(f"[SIMPLE-UNIFIED] AUTO-MIGRATION: Migrated SHORT position from legacy system")
                logger.info(f"  {spread_id[:8]}: SHORT | last_z={last_z:.3f} | next_z={next_z:.3f} | entries=1")
                logger.info(f"  Next pyramid will execute when z-score >= {next_z:.3f}")
                migrated_count += 1

            # Save migrated states
            if migrated_count > 0:
                self._save_states()
                logger.info(f"[SIMPLE-UNIFIED] Auto-migration complete - {migrated_count} position(s) migrated")
                logger.info(f"[SIMPLE-UNIFIED] Pyramiding will now work for legacy positions")

        except Exception as e:
            logger.error(f"[SIMPLE-UNIFIED] Auto-migration failed: {e}")

    def _migrate_from_active_positions(self, active_positions_file: Path) -> bool:
        """
        Migrate spread states from active_positions.json

        Args:
            active_positions_file: Path to active_positions.json

        Returns:
            True if migration successful, False otherwise
        """
        try:
            with open(active_positions_file, 'r') as f:
                positions_data = json.load(f)

            if not positions_data:
                return False

            # Group positions by spread_id
            spreads = {}
            for pos_id, pos in positions_data.items():
                spread_id = pos.get('spread_id')
                if spread_id:
                    if spread_id not in spreads:
                        spreads[spread_id] = []
                    spreads[spread_id].append(pos)

            if not spreads:
                return False

            migrated_count = 0
            for spread_id, positions in spreads.items():
                if spread_id in self.spread_states:
                    continue  # Already exists

                # Get data from first position
                first_pos = positions[0]
                side = first_pos.get('side', 'LONG')
                entry_zscore = first_pos.get('entry_zscore', 0.0)

                # Calculate next_z based on side
                if side == 'LONG':
                    next_z = entry_zscore - self.scale_interval
                else:
                    next_z = entry_zscore + self.scale_interval

                # Calculate total lots
                total_primary = sum(p.get('volume', 0.0) for p in positions if p.get('is_primary', False))
                total_secondary = sum(p.get('volume', 0.0) for p in positions if not p.get('is_primary', False))

                self.spread_states[spread_id] = SpreadEntryState(
                    spread_id=spread_id,
                    side=side,
                    last_z_entry=entry_zscore,
                    next_z_entry=next_z,
                    entry_count=1,  # Assume first entry
                    total_primary_lots=total_primary,
                    total_secondary_lots=total_secondary
                )

                logger.warning(f"[SIMPLE-UNIFIED] AUTO-MIGRATION from active_positions.json:")
                logger.info(f"  {spread_id[:16]}: {side} | last_z={entry_zscore:.3f} | "
                           f"next_z={next_z:.3f} | entries=1")
                migrated_count += 1

            if migrated_count > 0:
                self._save_states()
                logger.info(f"[SIMPLE-UNIFIED] Migrated {migrated_count} spread(s) from active_positions.json")
                return True

            return False

        except Exception as e:
            logger.error(f"[SIMPLE-UNIFIED] Migration from active_positions.json failed: {e}")
            return False

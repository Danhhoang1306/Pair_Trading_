"""
Entry Executor - Handles spread entry execution logic
Extracted from main_cli.py to reduce complexity

⚠️  DEPRECATED: This executor is deprecated and will be removed in a future version.
    Use UnifiedPositionExecutor instead, which merges entry + pyramiding logic.

    Migration path:
    - Old: EntryExecutor (entry at z=±2.0) + PyramidingExecutor (pyramid at z=±2.5, ±3.0)
    - New: UnifiedPositionExecutor (all z-score levels handled uniformly)

    See: executors/unified_position_executor.py
"""
import logging
import warnings
from datetime import datetime
from typing import Optional, Tuple

from strategy.signal_generator import SignalType
from strategy.order_manager import OrderStatus
from core.position_persistence import PersistedPosition
from analytics.pnl_attribution import get_attribution_engine, PositionSnapshot

logger = logging.getLogger(__name__)


class EntryExecutor:
    """
    Handles execution of spread entry orders

    ⚠️  DEPRECATED: Use UnifiedPositionExecutor instead.

    Responsibilities:
    - Pre-entry validation (lock check, cooldown check)
    - Position sizing calculation
    - Order execution via trade executor
    - Post-entry registration (tracker, persistence, monitor, rebalancer)
    - Attribution tracking
    """

    def __init__(self,
                 trade_executor,
                 order_manager,
                 position_tracker,
                 market_data,
                 persistence,
                 flag_manager,
                 position_monitor,
                 rebalancer,
                 signal_generator,
                 trading_lock_manager,
                 entry_cooldown=None,
                 enable_entry_cooldown=True,
                 account_balance=0,
                 mt5_tickets=None,
                 primary_symbol='BTCUSD',
                 secondary_symbol='ETHUSD',
                 risk_thread=None):
        """
        Initialize Entry Executor

        Args:
            trade_executor: MT5 trade executor
            order_manager: Order management system
            position_tracker: Position tracking system
            market_data: Real-time market data manager
            persistence: Position persistence manager
            flag_manager: Setup flag manager
            position_monitor: Position monitoring system
            rebalancer: Hybrid rebalancer
            signal_generator: Signal generator (for entry threshold)
            trading_lock_manager: Trading lock manager
            entry_cooldown: Entry cooldown manager (optional)
            enable_entry_cooldown: Whether to use entry cooldown
            account_balance: Current account balance
            mt5_tickets: MT5 ticket mapping dictionary
            primary_symbol: Primary symbol
            secondary_symbol: Secondary symbol
            risk_thread: RiskManagementThread instance (optional)
        """
        self.trade_executor = trade_executor
        self.order_manager = order_manager
        self.position_tracker = position_tracker
        self.market_data = market_data
        self.persistence = persistence
        self.flag_manager = flag_manager
        self.position_monitor = position_monitor
        self.rebalancer = rebalancer
        self.signal_generator = signal_generator
        self.trading_lock_manager = trading_lock_manager
        self.entry_cooldown = entry_cooldown
        self.enable_entry_cooldown = enable_entry_cooldown
        self.account_balance = account_balance
        self.mt5_tickets = mt5_tickets if mt5_tickets is not None else {}
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol
        self.risk_thread = risk_thread  # RiskManagementThread for independent monitoring

        # State tracking
        self.last_entry_zscore = None
        self.last_entry_mean = None

        logger.info("EntryExecutor initialized")
    
    def execute(self, signal, snapshot, pos_size_result) -> bool:
        """
        Execute spread entry with REAL-TIME hedge calculation
        
        Args:
            signal: Trading signal
            snapshot: MarketSnapshot object
            pos_size_result: Position sizing result
            
        Returns:
            True if entry successful, False otherwise
        """
        try:
            # Determine side
            side = 'LONG' if signal.signal_type == SignalType.LONG_SPREAD else 'SHORT'
            
            # ========== PRE-ENTRY VALIDATION ==========
            if not self._validate_entry(side, signal.zscore):
                return False
            
            # ========== POSITION SIZING ==========
            primary_lots, secondary_lots = self._calculate_position_size(
                snapshot, pos_size_result
            )
            
            # ========== LOG ENTRY INTENT ==========
            self._log_entry_intent(side, snapshot, primary_lots, secondary_lots, pos_size_result)
            
            # ========== EXECUTE ORDERS ==========
            primary_result, secondary_result, spread_id, entry_zscore = self._execute_orders(
                side, primary_lots, secondary_lots, snapshot
            )
            
            if not primary_result or not secondary_result:
                return False
            
            # ========== POST-ENTRY REGISTRATION ==========
            self._register_entry(
                spread_id, side, snapshot, entry_zscore,
                primary_result, secondary_result, pos_size_result
            )
            
            # ========== MARK COOLDOWN ==========
            if self.enable_entry_cooldown and self.entry_cooldown:
                self.entry_cooldown.mark_entry(side, entry_zscore)
            
            logger.info(f"[SYSTEM-1-ENTRY]  Entry complete - Spread {spread_id[:8]} opened")
            logger.info("="*80)
            
            return True
            
        except Exception as e:
            logger.error(f"Entry error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _validate_entry(self, side: str, zscore: float) -> bool:
        """
        Validate if entry is allowed
        
        Returns:
            True if entry allowed, False if blocked
        """
        # Check trading lock
        if self.trading_lock_manager.is_locked():
            logger.warning(f" Entry BLOCKED - System is LOCKED")
            logger.warning(f"   Reason: {self.trading_lock_manager.lock_state.lock_reason}")
            logger.warning(f"   Locked until: {self.trading_lock_manager.lock_state.locked_until}")
            return False
        
        # Check entry cooldown
        if self.enable_entry_cooldown and self.entry_cooldown:
            if not self.entry_cooldown.can_enter(side, zscore):
                status = self.entry_cooldown.get_status(side)
                logger.warning(f" Entry BLOCKED by cooldown - {side} at z={zscore:.3f}")
                if status.get('last_zscore'):
                    logger.warning(f"   Last entry: z={status['last_zscore']:.3f}")
                if status.get('last_timestamp'):
                    logger.warning(f"   Time: {status['last_timestamp']}")
                return False
        
        return True
    
    def _calculate_position_size(self, snapshot, pos_size_result) -> Tuple[float, float]:
        """
        Calculate position sizes using real-time hedge ratio
        
        Args:
            snapshot: MarketSnapshot object
            pos_size_result: Position sizing result
            
        Returns:
            (primary_lots, secondary_lots)
        """
        primary_value = self.account_balance * pos_size_result.position_size
        primary_quantity = primary_value / snapshot.primary_bid / 100
        
        # Use real-time hedge calculation
        primary_lots, secondary_lots = self.market_data.calculate_hedge_quantities(primary_quantity)
        
        return primary_lots, secondary_lots
    
    def _log_entry_intent(self, side, snapshot, primary_lots, secondary_lots, pos_size_result):
        """Log entry intent with details"""
        logger.info("="*80)
        logger.info(f"[SYSTEM-1-ENTRY] Z-Score Trigger Entry")
        logger.info("="*80)
        logger.info(f"  Signal: {side} SPREAD")
        logger.info(f"  Reason: Z-score {snapshot.zscore:.2f} crossed threshold ±{self.signal_generator.entry_threshold:.1f}")
        logger.info(f"  Market: Primary ${snapshot.primary_bid:.2f}, Secondary ${snapshot.secondary_bid:.4f}")
        logger.info(f"  Hedge ratio: {snapshot.hedge_ratio:.4f}")
        logger.info(f"  Position: {primary_lots:.4f} XAU + {secondary_lots:.4f} XAG")
        logger.info(f"  Legs: 2 (paired entry)")
        logger.info(f"  Risk: {pos_size_result.position_size:.1%} of account")
    
    def _execute_orders(self, side, primary_lots, secondary_lots, snapshot):
        """
        Execute spread orders on MT5
        
        Returns:
            (primary_result, secondary_result, spread_id, entry_zscore)
        """
        # Execute real orders
        (primary_result, secondary_result), spread_id, returned_zscore = self.trade_executor.place_spread_orders(
            primary_volume=primary_lots,
            secondary_volume=secondary_lots,
            side=side,
            entry_zscore=snapshot.zscore
        )
        
        # Use returned zscore (should match snapshot.zscore)
        entry_zscore = returned_zscore if returned_zscore is not None else snapshot.zscore
        
        # Check execution success
        if not primary_result.success or not secondary_result.success:
            logger.error(f"[SYSTEM-1-ENTRY]  Trade execution FAILED!")
            if not primary_result.success:
                logger.error(f"  Primary: {primary_result.comment}")
            if not secondary_result.success:
                logger.error(f"  Secondary: {secondary_result.comment}")
            return None, None, None, None
        
        logger.info(f"[SYSTEM-1-ENTRY]  Spread {spread_id[:8]} filled:")
        logger.info(f"  Primary: Ticket {primary_result.order_ticket} - {primary_result.volume} lots @ ${primary_result.price:.2f}")
        logger.info(f"  Secondary: Ticket {secondary_result.order_ticket} - {secondary_result.volume} lots @ ${secondary_result.price:.4f}")
        
        return primary_result, secondary_result, spread_id, entry_zscore
    
    def _register_entry(self, spread_id, side, snapshot, entry_zscore,
                       primary_result, secondary_result, pos_size_result):
        """
        Register entry in all tracking systems
        """
        # 1. Register in attribution engine
        self._register_attribution(spread_id, side, snapshot, entry_zscore,
                                  primary_result, secondary_result)
        
        # 2. Update order manager
        self._update_order_manager(side, primary_result, secondary_result)
        
        # 3. Register in position tracker
        primary_pos, secondary_pos = self._register_tracker(
            spread_id, side, snapshot, primary_result, secondary_result
        )
        
        # 4. Save to disk (persistence)
        self._save_persistence(spread_id, snapshot, entry_zscore,
                              primary_pos, secondary_pos, primary_result, secondary_result)
        
        # 5. Set setup flag
        self._set_setup_flag(spread_id, side, entry_zscore, snapshot, primary_result, secondary_result)
        
        # 6. Register with position monitor
        self._register_monitor(primary_result, secondary_result)
        
        # 7. Register with rebalancer
        self._register_rebalancer(spread_id, side, snapshot, primary_result, secondary_result, pos_size_result)
        
        # 8. Store for GUI
        self.last_entry_zscore = entry_zscore
        self.last_entry_mean = snapshot.spread_mean
    
    def _register_attribution(self, spread_id, side, snapshot, entry_zscore,
                             primary_result, secondary_result):
        """Register position in attribution engine"""
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
            logger.info(f" Registered {spread_id} in attribution engine")
        except Exception as e:
            logger.error(f"Failed to register attribution: {e}")
    
    def _update_order_manager(self, side, primary_result, secondary_result):
        """Update order manager with filled orders"""
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
    
    def _register_tracker(self, spread_id, side, snapshot, primary_result, secondary_result):
        """Register positions in position tracker"""
        primary_pos, secondary_pos = self.position_tracker.open_spread_position(
            primary_result.volume, secondary_result.volume,
            primary_result.price, secondary_result.price,
            side, snapshot.hedge_ratio
        )
        
        # Override tracker's UUID spread_id with ticket-based spread_id
        primary_pos.metadata['spread_id'] = spread_id
        secondary_pos.metadata['spread_id'] = spread_id
        
        # Map to MT5 tickets
        self.mt5_tickets[primary_pos.position_id] = primary_result.order_ticket
        self.mt5_tickets[secondary_pos.position_id] = secondary_result.order_ticket
        
        return primary_pos, secondary_pos
    
    def _save_persistence(self, spread_id, snapshot, entry_zscore,
                         primary_pos, secondary_pos, primary_result, secondary_result):
        """Save positions to disk for crash recovery"""
        # Save primary position
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
        
        # Save secondary position
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
        
        logger.info(f"[PERSISTENCE] Spread {spread_id[:8]} saved to disk")
    
    def _set_setup_flag(self, spread_id, side, entry_zscore, snapshot,
                       primary_result, secondary_result):
        """Set active setup flag if first position"""
        if not self.flag_manager.is_setup_active():
            self.flag_manager.mark_setup_active(
                spread_id=spread_id,
                metadata={
                    'side': side,
                    'entry_zscore': entry_zscore,
                    'hedge_ratio': snapshot.hedge_ratio,
                    'primary_lots': primary_result.volume,
                    'secondary_lots': secondary_result.volume
                }
            )
            logger.info(f" Setup flag: ACTIVE")
    
    def _register_monitor(self, primary_result, secondary_result):
        """
        Register positions with position monitor AND risk thread

        DUAL REGISTRATION for safety:
        1. PositionMonitor - Primary manual closure detection
        2. RiskManagementThread - Independent backup monitoring
        """
        # Register with PositionMonitor
        self.position_monitor.register_position(
            ticket=primary_result.order_ticket,
            symbol=self.primary_symbol
        )
        self.position_monitor.register_position(
            ticket=secondary_result.order_ticket,
            symbol=self.secondary_symbol
        )

        # ALSO register with RiskManagementThread for independent monitoring
        if self.risk_thread:
            self.risk_thread.register_mt5_ticket(primary_result.order_ticket)
            self.risk_thread.register_mt5_ticket(secondary_result.order_ticket)
            logger.debug(f"Registered tickets {primary_result.order_ticket}, {secondary_result.order_ticket} "
                        f"with RiskManagementThread")
    
    def _register_rebalancer(self, spread_id, side, snapshot,
                            primary_result, secondary_result, pos_size_result):
        """Register position with hybrid rebalancer"""
        if spread_id:
            self.rebalancer.register_position(
                spread_id=spread_id,
                side=side,
                entry_zscore=snapshot.zscore,
                entry_hedge_ratio=snapshot.hedge_ratio,
                primary_lots=primary_result.volume,
                secondary_lots=secondary_result.volume,
                total_position_size=pos_size_result.position_size,
                primary_symbol=self.primary_symbol,
                secondary_symbol=self.secondary_symbol
            )
            logger.info(f"[SYSTEM-1-ENTRY] Position registered with rebalancer")
            logger.info(f"  Pyramiding: Enabled")
            logger.info(f"  Volume rebalance: {'Enabled' if self.rebalancer.enable_hedge_adjustment else 'Disabled'}")
    
    def update_balance(self, new_balance: float):
        """Update account balance"""
        self.account_balance = new_balance

"""
Main Application - XAU/XAG Pair Trading System
Multi-threaded real-time trading system
"""

import sys
from pathlib import Path

# Ensure project root is in path (works even when imported from subdirectories)
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ============================================================
# LICENSE CHECK - REQUIRED BEFORE RUNNING
# ============================================================
from licensing.license_validator import require_license

import threading
import queue
import time
import signal
from datetime import datetime
from typing import Dict, Any, Optional
import logging

from core.data_manager import DataManager
from core.mt5_trade_executor import MT5TradeExecutor
from core.realtime_market_data import RealTimeMarketData
from core.position_monitor import PositionMonitor
from core.setup_flag_manager import SetupFlagManager
from core.position_persistence import PositionPersistence

# ========== EXECUTORS (REFACTORED) ==========
# Refactored modules (v5.0 - MODULARIZED)
from threads import (
    DataThread, SignalThread, ExecutionThread,
    MonitorThread, AttributionThread, RiskManagementThread
)
from handlers import PositionHandlers, SignalHandlers
from recovery import RecoveryManager


from utils.data_preprocessor import DataPreprocessor
from utils.zscore_monitor import ZScoreMonitor
from models import HedgeRatioCalculator
from risk import PositionSizer, DrawdownMonitor, RiskChecker, DailyRiskManager
from risk.trading_lock_manager import TradingLockManager
from strategy import (SignalGenerator, OrderManager, PositionTracker, 
                      SignalType, OrderStatus)
from strategy.hybrid_rebalancer import HybridRebalancer
# EntryCooldownManager removed - SimpleUnifiedExecutor handles state via spread_states.json
from utils.logger import setup_logging

from executors.volume_rebalancer import VolumeRebalancer
from executors.exit_executor import ExitExecutor

from core.mt5_manager import get_mt5
from core.position_persistence import PositionPersistence

logger = logging.getLogger(__name__)


class TradingSystem:
    """Multi-threaded pair trading system"""
    
    def __init__(self, 
                 account_balance: float = 100000,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize trading system
        
        Args:
            account_balance: Account balance (from MT5)
            config: Complete trading configuration (dict or PairConfig)
                   If provided, ALL settings come from config!
                   If None, uses defaults
        
        Config can contain:
            - update_interval
            - max_positions
            - volume_multiplier
            - entry_threshold
            - exit_threshold
            - stop_loss_zscore
            - rolling_window_size
            - hedge_drift_threshold
            - max_position_pct
            - max_risk_pct
            - daily_loss_limit
            - enable_pyramiding
            - enable_hedge_adjustment
            - primary_symbol
            - secondary_symbol
            - ... and more!
        """
        self.account_balance = account_balance
        
        # Convert config to dict if it's a dataclass
        if config is not None and hasattr(config, 'to_dict'):
            config = config.to_dict()
        
        # Store config
        self.config = config or {}

        # ========== RISK CONFIG (NEW) ==========
        # Create RiskConfig with backward compatibility
        from config.settings import RiskConfig
        self.risk_config = RiskConfig.from_dict(self.config)

        # Log risk limits
        logger.info("="*80)
        logger.info("RISK LIMITS CONFIGURED:")
        logger.info(f"  Per-Setup Loss Limit: {self.risk_config.max_loss_per_setup_pct}%")
        logger.info(f"  Total Portfolio Loss Limit: {self.risk_config.max_total_unrealized_loss_pct}%")
        logger.info(f"  Daily Loss Limit: {self.risk_config.daily_loss_limit_pct}%")
        logger.info("="*80)

        # DEBUG: Log received config values
        logger.info("="*80)
        logger.info("CONFIG DEBUG - Values Received:")
        logger.info(f"  entry_threshold: {self.config.get('entry_threshold', 'NOT SET')}")
        logger.info(f"  exit_threshold: {self.config.get('exit_threshold', 'NOT SET')}")
        logger.info(f"  stop_loss_zscore: {self.config.get('stop_loss_zscore', 'NOT SET')}")
        logger.info(f"  volume_multiplier: {self.config.get('volume_multiplier', 'NOT SET')}")
        logger.info("="*80)
        
        # ========== STEP 1: CHECK TRADING LOCK (FIRST THING!) ==========
        logger.info("=" * 80)
        logger.info("SYSTEM STARTUP - CHECKING LOCK STATUS")
        logger.info("=" * 80)
        
        self.trading_lock_manager = TradingLockManager(
            session_start_time=self.config.get('session_start_time', '00:00'),
            persist_path=None  # Uses default: asset/trading_lock.json
        )
        
        # If locked, warn user
        if self.trading_lock_manager.is_locked():
            lock_info = self.trading_lock_manager.get_lock_info()
            logger.critical("=" * 80)
            logger.critical("  WARNING: SYSTEM IS LOCKED - TRADING DISABLED")
            logger.critical("=" * 80)
            logger.critical(f"Reason: {lock_info['reason']}")
            logger.critical(f"Locked at: {lock_info['locked_at']}")
            logger.critical(f"Locked until: {lock_info['locked_until']}")
            logger.critical(f"Daily P&L at lock: ${lock_info['daily_pnl_at_lock']:,.2f}")
            logger.critical(f"Daily Limit at lock: ${lock_info['daily_limit_at_lock']:,.2f}")
            logger.critical("=" * 80)
            logger.critical("System will continue running but NOT open new positions")
            logger.critical("Will auto-unlock at next session start time")
            logger.critical("=" * 80)
        
        logger.info("=" * 80)
        logger.info("CONTINUING WITH SYSTEM INITIALIZATION")
        logger.info("=" * 80)
        
        # Extract settings from config (with defaults)
        self.update_interval = self.config.get('update_interval', 60)
        self.max_positions = self.config.get('max_positions', 5)
        self.volume_multiplier = self.config.get('volume_multiplier', 1.0)
        
        # Risk alert callback (for GUI)
        self.risk_alert_callback = None
        
        # Threading
        self.running = False
        self.threads = []
        self.lock = threading.RLock()
        
        # Queues
        self.data_queue = queue.Queue(maxsize=10)
        self.signal_queue = queue.Queue(maxsize=10)
        
        # Components
        logger.info("Initializing components...")
        logger.info(f"Using config: update_interval={self.update_interval}, "
                   f"max_positions={self.max_positions}, "
                   f"volume_multiplier={self.volume_multiplier}")
        
        self.data_manager = DataManager()
        
        # MT5 TradeExecutor - use magic number and symbols from config!
        self.magic_number = self.config.get('magic_number', 234000)
        self.primary_symbol = self.config.get('primary_symbol', 'BTCUSD')
        self.secondary_symbol = self.config.get('secondary_symbol', 'ETHUSD')
        
        # Log configured symbols
        logger.info(f"Configured symbols: {self.primary_symbol} / {self.secondary_symbol}")
        
        self.trade_executor = MT5TradeExecutor(
            magic_number=self.magic_number,
            volume_multiplier=self.volume_multiplier,
            primary_symbol=self.primary_symbol,
            secondary_symbol=self.secondary_symbol
        )
        self.preprocessor = DataPreprocessor()
        self.hedge_calculator = HedgeRatioCalculator()
        
        # Apply rolling window from config FIRST
        rolling_window = self.config.get('rolling_window', 1000)
        logger.info(f"Rolling window: {rolling_window} bars (responsive mode)")
        
        # Real-time market data manager with correct window size
        self.market_data = RealTimeMarketData(
            data_manager=self.data_manager,
            preprocessor=self.preprocessor,
            hedge_calculator=self.hedge_calculator,
            rolling_window_size=rolling_window,  # Pass window size at initialization!
            historical_update_interval=3600  # Update historical every hour
        )
        
        # Position sizer - now accepts config directly!
        self.position_sizer = PositionSizer(
            account_balance=account_balance,
            config=self.config  # ← Pass config!
        )
        
        # Drawdown monitor - now accepts config directly!
        self.drawdown_monitor = DrawdownMonitor(
            account_balance=account_balance,
            config=self.config  # ← Pass config!
        )
        
        # Daily Risk Manager - Pass percentage, not dollar amount!
        daily_limit_pct = self.config.get('daily_loss_limit_pct', 10.0)  # Default 10%

        logger.info(f"=" * 60)
        logger.info(f"DAILY RISK CONFIGURATION:")
        logger.info(f"  Current Balance: ${account_balance:,.2f}")
        logger.info(f"  Daily Limit %: {daily_limit_pct:.1f}%")


        self.daily_risk_manager = DailyRiskManager(
            account_balance=account_balance,
            max_risk_pct=self.config.get('max_risk_pct', 2.0),
            daily_loss_limit_pct=daily_limit_pct,  # Pass percentage, not dollars!
            session_start_time=self.config.get('session_start_time', '00:00'),
            session_end_time=self.config.get('session_end_time', '23:59'),
            magic_number=self.config.get('magic_number', 234000),
            trading_lock_manager=self.trading_lock_manager  # CRITICAL: Pass lock manager
        )
        
        # ========== LOAD TODAY'S HISTORY - NEW FORMULA ==========
        # Get current equity from MT5

        mt5 = get_mt5()
        account_info = mt5.account_info()
        current_equity = account_info.equity if account_info else account_balance

        # Load history with new formula (ALL trades, no magic filter)
        history_result = self.daily_risk_manager.load_daily_history(current_equity)

        if history_result['trade_count'] > 0:
            logger.warning("=" * 70)
            logger.warning("CONTINUING FROM EARLIER SESSION")
            logger.warning("=" * 70)
            logger.warning(f"  Starting Balance: ${history_result['starting_balance']:,.2f}")
            logger.warning(f"  Net Realized P&L: ${history_result['net_realized_pnl']:,.2f}")
            logger.warning(f"  Total Commission: ${history_result['total_commission']:,.2f}")
            logger.warning(f"  Current Equity: ${current_equity:,.2f}")
            logger.warning(f"  Closed Trades: {history_result['trade_count']}")
            logger.warning("=" * 70)
        else:
            logger.info("No previous trades today - fresh session")
            logger.info(f"Starting Balance = Current Equity = ${current_equity:,.2f}")
        
        logger.info("=" * 60)
        
        # Store max drawdown limit for easy access
        self.max_drawdown_limit = self.config.get('max_drawdown_pct', 20.0) / 100.0  # Convert % to fraction
        
        # Risk checker - now accepts config directly!
        self.risk_checker = RiskChecker(config=self.config)
        
        # Signal generator - now accepts config directly!
        self.signal_generator = SignalGenerator(config=self.config)
        
        self.order_manager = OrderManager()
        self.position_tracker = PositionTracker()
        
        # Rebalancer with config
        stop_loss_zscore = self.config.get('stop_loss_zscore', 3.5)
        hedge_drift_threshold = self.config.get('hedge_drift_threshold', 0.05)
        enable_hedge_adjustment = self.config.get('enable_hedge_adjustment', True)
        enable_pyramiding = self.config.get('enable_pyramiding', True)
        
        self.rebalancer = HybridRebalancer(
            scale_interval=self.config.get('scale_interval', 0.1),
            max_zscore=stop_loss_zscore,
            initial_fraction=self.config.get('initial_fraction', 0.33),
            hedge_drift_threshold=hedge_drift_threshold,
            min_absolute_drift=self.config.get('min_absolute_drift', 0.01),
            min_adjustment_interval=self.config.get('min_adjustment_interval', 3600),
            enable_hedge_adjustment=enable_hedge_adjustment
        )
        logger.info(f"Rebalancer: pyramiding={enable_pyramiding}, "
                   f"hedge_adjustment={enable_hedge_adjustment}, "
                   f"drift_threshold={hedge_drift_threshold}, "
                   f"min_absolute_drift={self.config.get('min_absolute_drift', 0.01)}, "
                   f"scale_interval={self.config.get('scale_interval', 0.1)}, "
                   f"initial_fraction={self.config.get('initial_fraction', 0.33)}")
        
        # ZScore monitor from config
        zscore_history = self.config.get('zscore_history_size', 200)
        self.zscore_monitor = ZScoreMonitor(max_history=zscore_history)
        
        # Entry cooldown now handled by SimpleUnifiedExecutor via spread_states.json
        # No need for separate EntryCooldownManager

        # Position Persistence from config

        position_dir = self.config.get('position_data_dir', 'positions')
        self.persistence = PositionPersistence(data_dir=position_dir)
        
        # Setup Flag Manager - tracks if setup is active
        self.flag_manager = SetupFlagManager(data_dir=position_dir)
        
        # Position Monitor - monitors MT5 positions in real-time
        self.position_monitor = PositionMonitor(
            check_interval=5,  # Check every 5 seconds
            user_response_timeout=60  # Wait 60 seconds for user response
        )
        
        # Manual position sync flag
        self.enable_manual_position_sync = self.config.get('enable_manual_position_sync', True)
        logger.info(f"Manual position sync: {'ENABLED' if self.enable_manual_position_sync else 'DISABLED'}")
        
        # MT5 ticket mapping (MUST be before executors!)
        self.mt5_tickets = {}
        
        # ========== REFACTORED MODULES (v5.0) ==========
        logger.info("="*80)
        logger.info("INITIALIZING REFACTORED MODULES (v5.0)")
        logger.info("="*80)
        
        # Create all threads
        self.threads = {}
        self.threads['data'] = DataThread(self)
        self.threads['signal'] = SignalThread(self)
        self.threads['execution'] = ExecutionThread(self)
        self.threads['monitor'] = MonitorThread(self)
        self.threads['attribution'] = AttributionThread(self)
        self.threads['risk'] = RiskManagementThread(self)
        logger.info("✅ Created 6 thread workers (modularized)")
        
        # Create handlers
        self.position_handlers = PositionHandlers(self)
        self.signal_handlers = SignalHandlers(self)
        logger.info("✅ Created event handlers (modularized)")
        
        # Register position monitor callbacks
        self.position_monitor.on_position_missing = self.position_handlers.handle_missing_positions
        self.position_monitor.on_user_confirmed = self.position_handlers.handle_user_rebalance
        self.position_monitor.on_user_timeout = self.position_handlers.handle_user_timeout
        self.position_monitor.on_all_positions_closed = self.position_handlers.handle_all_positions_closed
        logger.info("✅ Registered position monitor callbacks")
        
        # Create recovery manager
        self.recovery_manager = RecoveryManager(self)
        logger.info("✅ Created recovery manager (modularized)")
        
        logger.info("="*80)
        logger.info("MODULARIZATION v5.0 INITIALIZED SUCCESSFULLY!")
        logger.info("="*80)


        # ========== SIMPLE UNIFIED EXECUTOR (ACTIVE) ==========
        # Replaces EntryExecutor + PyramidingExecutor with ultra-simple 2-variable logic
        # Algorithm: last_z_entry + next_z_entry = no complex level tracking needed!
        # State persistence: asset/state/spread_states.json (replaces last_z_entry.json)
        from executors.simple_unified_executor import SimpleUnifiedExecutor

        self.unified_executor = SimpleUnifiedExecutor(
            trade_executor=self.trade_executor,
            order_manager=self.order_manager,
            position_tracker=self.position_tracker,
            market_data=self.market_data,
            persistence=self.persistence,
            flag_manager=self.flag_manager,
            position_monitor=self.position_monitor,
            signal_generator=self.signal_generator,
            trading_lock_manager=self.trading_lock_manager,
            account_balance=self.account_balance,
            mt5_tickets=self.mt5_tickets,
            primary_symbol=self.primary_symbol,
            secondary_symbol=self.secondary_symbol,
            risk_thread=None,  # Will be set after RiskManagementThread is created
            entry_threshold=self.signal_generator.entry_threshold,
            scale_interval=self.rebalancer.scale_interval,
            max_zscore=self.signal_generator.stop_loss_zscore,
            initial_fraction=self.rebalancer.initial_fraction,
            max_entries=10
        )
        logger.info("SimpleUnifiedExecutor initialized (2-variable algorithm)")
        logger.info("   State file: asset/state/spread_states.json")
        logger.info("   Algorithm: last_z -> next_z -> execute -> update")

        # Enable/disable unified executor (set to False to use legacy executors)
        self.enable_unified_executor = True  # Set to True to use the new unified system

        # ========== EXIT EXECUTOR ==========
        # Handles spread exit logic, uses unified_executor for state reset
        self.exit_executor = ExitExecutor(
            trade_executor=self.trade_executor,
            position_tracker=self.position_tracker,
            position_monitor=self.position_monitor,
            persistence=self.persistence,
            rebalancer=self.rebalancer,
            flag_manager=self.flag_manager,
            position_sizer=self.position_sizer,
            drawdown_monitor=self.drawdown_monitor,
            risk_checker=self.risk_checker,
            signal_generator=self.signal_generator,
            mt5_tickets=self.mt5_tickets,
            unified_executor=self.unified_executor,  # For state reset on exit
            primary_symbol=self.primary_symbol,
            secondary_symbol=self.secondary_symbol,
            magic_number=self.magic_number
        )
        self.exit_executor.account_balance = self.account_balance
        logger.info("ExitExecutor initialized (uses unified_executor for state reset)")
        if self.enable_unified_executor:
            logger.info("🔹 Simple Unified Executor: ENABLED (entry + pyramiding merged)")
        else:
            logger.info("🔹 Simple Unified Executor: DISABLED (using legacy Entry + Pyramiding executors)")

        # Volume Rebalancer (System 3) - Single leg volume correction

        self.volume_rebalancer = VolumeRebalancer(
            trade_executor=self.trade_executor,
            rebalancer=self.rebalancer,
            position_monitor=self.position_monitor,
            mt5_tickets=self.mt5_tickets,
            primary_symbol=self.primary_symbol,
            secondary_symbol=self.secondary_symbol
        )

        # Backward compatibility alias
        self.hedge_executor = self.volume_rebalancer
        
        # State
        self.current_snapshot = None
        self.current_signal = None
        self.last_update_time = None
        
        # Entry tracking (for GUI display)
        self.last_entry_zscore = None  # Z-score của lệnh cuối
        self.last_entry_mean = None    # Mean của lệnh cuối
        
        # Attribution state (for GUI display)
        self.current_attribution = None
        
        logger.info(f"System initialized (balance=${account_balance:,.0f})")
    
    def start(self):
        """Start the trading system"""
        logger.info("="*80)
        logger.info("STARTING MODULARIZED TRADING SYSTEM v5.0")
        logger.info("="*80)
        
        # CRITICAL: Set running flag BEFORE starting threads!
        self.running = True
        logger.info("✅ System running flag set to True")
        
        # Position recovery (modularized)
        logger.info("Position Recovery...")
        self.recovery_manager.recover_positions()
        
        # Start position monitor
        self.position_monitor.start()
        logger.info("✅ Position Monitor started")
        
        # Start all threads (modularized)
        for name, thread in self.threads.items():
            thread.start()
            logger.info(f"✅ {name.capitalize()} Thread started")
        
        logger.info("="*80)
        logger.info("ALL SYSTEMS OPERATIONAL!")
        logger.info("="*80)

    def stop(self):
        """Stop the trading system"""
        logger.info("="*80)
        logger.info("STOPPING TRADING SYSTEM...")
        logger.info("="*80)
        
        self.running = False
        
        # Stop all threads (modularized)
        for name, thread in self.threads.items():
            thread.stop()
            logger.info(f"✅ Stopped {name.capitalize()} Thread")
        
        # Stop position monitor
        if hasattr(self, 'position_monitor'):
            self.position_monitor.stop()
            logger.info("✅ Stopped Position Monitor")
        
        # Cleanup
        if hasattr(self, 'trade_executor'):
            self.trade_executor.shutdown()
        
        logger.info("="*80)
        logger.info("SYSTEM STOPPED CLEANLY")
        logger.info("="*80)

    def emit_risk_alert(self, severity: str, title: str, message: str):
        """
        Emit risk alert to GUI

        Args:
            severity: 'WARNING' or 'CRITICAL'
            title: Alert title
            message: Alert message
        """
        logger.warning(f"[RISK ALERT] {severity}: {title}")
        logger.warning(f"  {message}")

        # Call GUI callback if set
        if self.risk_alert_callback:
            try:
                self.risk_alert_callback(severity, title, message)
            except Exception as e:
                logger.error(f"Failed to call risk alert callback: {e}")

    def _get_lock_until_time(self) -> str:
        """Get lock until time from TradingLockManager for GUI display"""
        try:
            if hasattr(self, 'trading_lock_manager') and self.trading_lock_manager:
                lock_info = self.trading_lock_manager.get_lock_info()
                if lock_info.get('locked') and lock_info.get('locked_until'):
                    from datetime import datetime
                    locked_until = datetime.fromisoformat(lock_info['locked_until'])
                    return locked_until.strftime("%Y-%m-%d %H:%M")
        except Exception as e:
            logger.debug(f"Could not get lock until time: {e}")
        return ""

    def get_status(self):
        """Get system status including attribution and risk"""
        with self.lock:
            pnl_data = self.position_tracker.get_total_pnl()
            dd_metrics = self.drawdown_monitor.get_metrics()
            
            # Get risk status from daily risk manager
            from core.mt5_manager import get_mt5
            mt5 = get_mt5()
            mt5_info = mt5.account_info()
            unrealized_pnl = mt5_info.profit if mt5_info else pnl_data['unrealized_pnl']
            risk_status = self.daily_risk_manager.check_risk(unrealized_pnl)
            
            # Attribution data (if available)
            attr = self.current_attribution
            
            # Entry tracking (for GUI position monitoring)
            entry_zscore = self.last_entry_zscore
            entry_mean = self.last_entry_mean
            current_zscore = self.current_snapshot.zscore if self.current_snapshot else None
            current_mean = self.current_snapshot.mean if self.current_snapshot else None
            
            status = {
                'running': self.running,
                'balance': self.account_balance,
                'account_balance': self.account_balance,  # For GUI compatibility
                'positions': pnl_data['open_positions'],
                'unrealized_pnl': pnl_data['unrealized_pnl'],
                'total_pnl': pnl_data['total_pnl'],
                'drawdown': dd_metrics.current_drawdown_pct,
                'signal': self.current_signal.signal_type.value if self.current_signal else None,
                
                # Risk status (NEW FORMULA!)
                'risk_max_risk_limit': risk_status.max_risk_limit,
                'risk_max_risk_breached': risk_status.max_risk_breached,
                'risk_starting_balance': risk_status.starting_balance,          # NEW
                'risk_net_realized_pnl': risk_status.net_realized_pnl,          # NEW
                'risk_total_commission': risk_status.total_commission,          # NEW
                'risk_unrealized_pnl': risk_status.session_unrealized_pnl,      # NEW
                'risk_daily_loss_limit': risk_status.daily_loss_limit,
                'risk_daily_total_pnl': risk_status.daily_total_pnl,
                'risk_daily_limit_breached': risk_status.daily_limit_breached,
                'risk_remaining_until_limit': risk_status.remaining_until_daily_limit,
                'risk_trading_locked': risk_status.trading_locked,
                'risk_lock_reason': risk_status.lock_reason,
                'daily_limit_pct': self.config.get('daily_loss_limit_pct', 10.0),  # For GUI default calculation
                'max_risk_pct': self.config.get('max_risk_pct', 2.0),  # For GUI max risk display
                'setup_risk_pct': self.config.get('max_risk_pct', 2.0),  # For GUI setup risk display
                'risk_lock_until': self._get_lock_until_time(),  # For GUI lock until display
                
                # Entry tracking (NEW!)
                'entry_zscore': entry_zscore,
                'entry_mean': entry_mean,
                'current_zscore': current_zscore,
                
                # Attribution components
                'attr_spread_pnl': attr.spread_pnl if attr else 0.0,
                'attr_spread_pct': attr.spread_pnl_pct if attr else 0.0,
                'attr_mean_pnl': attr.mean_drift_pnl if attr else 0.0,
                'attr_mean_pct': attr.mean_drift_pnl_pct if attr else 0.0,
                'attr_directional_pnl': attr.directional_pnl if attr else 0.0,
                'attr_directional_pct': attr.directional_pnl_pct if attr else 0.0,
                'attr_hedge_pnl': attr.hedge_imbalance_pnl if attr else 0.0,
                'attr_hedge_pct': attr.hedge_imbalance_pnl_pct if attr else 0.0,
                'attr_costs': attr.transaction_costs if attr else 0.0,
                'attr_costs_pct': attr.transaction_costs_pct if attr else 0.0,
                'attr_slippage': attr.slippage if attr else 0.0,
                'attr_slippage_pct': attr.slippage_pct if attr else 0.0,
                'attr_rebalance': attr.rebalance_alpha if attr else 0.0,
                'attr_rebalance_pct': attr.rebalance_alpha_pct if attr else 0.0,
                'attr_hedge_quality': attr.hedge_quality if attr else 0.0,
                'attr_purity': attr.strategy_purity if attr else 0.0,
                'attr_classification': attr.classification if attr else 'NO DATA'
            }
            
            return status

    def get_spreads_with_pnl(self) -> Dict[str, Dict]:
        """
        Get all active spreads with their PnL calculated from MT5

        Returns:
            {
                'spread_abc123': {
                    'positions': [mt5_pos1, mt5_pos2],
                    'total_pnl': -1500.00,
                    'primary_ticket': 12345,
                    'secondary_ticket': 12346
                },
                ...
            }
        """
        from core.mt5_manager import get_mt5
        mt5 = get_mt5()

        spreads = {}

        # Load all persisted positions
        all_positions = self.persistence.load_active_positions()

        # Group positions by spread_id (pos_data is PersistedPosition dataclass)
        spread_groups = {}
        for pos_id, pos_obj in all_positions.items():
            spread_id = pos_obj.spread_id  # Access attribute, not dict key
            if spread_id:
                if spread_id not in spread_groups:
                    spread_groups[spread_id] = []
                spread_groups[spread_id].append(pos_obj)

        # Calculate PnL for each spread from MT5
        for spread_id, positions in spread_groups.items():
            mt5_positions = []
            total_pnl = 0.0
            primary_ticket = None
            secondary_ticket = None

            for pos_obj in positions:
                ticket = pos_obj.mt5_ticket  # Access attribute
                if not ticket:
                    continue

                # Get current position from MT5
                mt5_pos_list = mt5.positions_get(ticket=ticket)

                if mt5_pos_list and len(mt5_pos_list) > 0:
                    mt5_pos = mt5_pos_list[0]
                    mt5_positions.append(mt5_pos)
                    total_pnl += mt5_pos.profit

                    # Track tickets
                    if pos_obj.is_primary:  # Access attribute
                        primary_ticket = ticket
                    else:
                        secondary_ticket = ticket

            # Only include spreads that still have open positions on MT5
            if mt5_positions:
                spreads[spread_id] = {
                    'positions': mt5_positions,
                    'total_pnl': total_pnl,
                    'primary_ticket': primary_ticket,
                    'secondary_ticket': secondary_ticket
                }

        return spreads


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global system
    logger.info("Shutdown signal received")
    if system:
        system.stop()
    sys.exit(0)


@require_license
def main():
    """Main entry point"""

    print("""

       XAU/XAG PAIR TRADING SYSTEM - Multi-Threaded v1.0

""")

    setup_logging()

    # ========== STEP 0: INITIALIZE MT5 CONNECTION (FIRST!) ==========
    logger.info("=" * 80)
    logger.info("INITIALIZING MT5 CONNECTION")
    logger.info("=" * 80)

    from core.mt5_manager import get_mt5_manager

    mt5_manager = get_mt5_manager()
    if not mt5_manager.initialize():
        logger.critical("=" * 80)
        logger.critical("FATAL ERROR: Failed to initialize MT5 connection")
        logger.critical("=" * 80)
        logger.critical("Please check:")
        logger.critical("  1. MT5 terminal is running")
        logger.critical("  2. Login credentials in config are correct")
        logger.critical("  3. Internet connection is stable")
        logger.critical("=" * 80)
        sys.exit(1)

    logger.info("=" * 80)
    logger.info("MT5 CONNECTION READY - Proceeding with system initialization")
    logger.info("=" * 80)
    
    # Create complete config for CLI mode - ALL parameters from config!
    from config.settings import PairConfig
    
    cli_config = PairConfig(
        name="XAU_XAG_CLI",
        primary_symbol="BTCUSD",
        secondary_symbol="ETHUSD",
        
        # Trading parameters
        entry_threshold=2.0,
        exit_threshold=0.5,
        stop_loss_zscore=3.5,
        max_positions=3,
        volume_multiplier=1.0,
        
        # Model parameters
        rolling_window_size=1000,
        update_interval=60,
        hedge_drift_threshold=0.05,

        # Risk parameters
        max_position_pct=20.0,
        max_risk_pct=2.0,
        max_drawdown_pct=20.0,
        daily_loss_limit=5000.0,

        # Rebalancer parameters - NO MORE HARDCODED!
        scale_interval=0.1,
        initial_fraction=0.33,
        min_adjustment_interval=3600,

        # Feature flags
        enable_pyramiding=True,
        enable_hedge_adjustment=True,
        enable_regime_filter=False,

        # System parameters - NO MORE HARDCODED!
        magic_number=234000,
        zscore_history_size=200,
        position_data_dir="positions"
    )
    
    logger.info("Using CLI config:")
    logger.info(f"  Pair: {cli_config.primary_symbol}/{cli_config.secondary_symbol}")
    logger.info(f"  Entry: {cli_config.entry_threshold}, Max Positions: {cli_config.max_positions}")
    logger.info(f"  Scale Interval: {cli_config.scale_interval}, Initial Fraction: {cli_config.initial_fraction}")
    logger.info(f"  Magic Number: {cli_config.magic_number}")
    
    global system
    system = TradingSystem(
        account_balance=100000,
        config=cli_config  # Pass config instead of individual params!
    )
    
    signal.signal(signal.SIGINT, lambda s, f: system.signal_handlers.signal_handler(s, f))
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set symbols for CLI mode
    system.market_data.primary_symbol = cli_config.primary_symbol
    system.market_data.secondary_symbol = cli_config.secondary_symbol
    
    system.start()
    
    logger.info("="*70)
    logger.info("SYSTEM RUNNING - Press Ctrl+C to stop")
    logger.info("="*70)
    
    try:
        while True:
            time.sleep(60)
            
            status = system.get_status()
            
            print("\n" + "="*70)
            print(f"STATUS - {datetime.now().strftime('%H:%M:%S')}")
            print("="*70)
            print(f"Balance: ${status['balance']:,.2f}")
            print(f"Positions: {status['positions']}")
            print(f"P&L: ${status['total_pnl']:,.2f}")
            print(f"Drawdown: {status['drawdown']:.2%}")
            print(f"Signal: {status['signal']}")
            print("="*70)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt")
        system.stop()



if __name__ == "__main__":
    main()

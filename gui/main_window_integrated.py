"""
Professional Pair Trading GUI - Fully Integrated
Connects GUI to existing trading system without changing logic
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QGroupBox, QGridLayout, QLineEdit,
    QTextEdit, QSplitter, QFrame, QSpinBox, QDoubleSpinBox,
    QCheckBox, QProgressBar, QStatusBar, QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QPalette
from datetime import datetime
import json
import logging
import threading

# Import theme (styles only)
from asset.theme import DARCULA_THEME_QSS, apply_theme
from asset.theme.styles import *

# Import configuration system
from config.settings import get_config, ConfigManager, PairConfig

# Import chart widget
from gui.chart_widget import ChartWidget

# Import pair discovery tab
from gui.pair_discovery_tab import PairDiscoveryTab

# Import risk alert handler
from gui.risk_alert_handler import RiskAlertHandler

# Import GUI data presenter (NEW: Presentation layer)
from gui.gui_data_presenter import GUIDataPresenter

# Import config sync manager and indicator (NEW: Hot-reload & sync)
from core.config_sync_manager import ConfigSyncManager, SymbolValidator, get_config_sync_manager
from gui.config_sync_indicator import ConfigSyncIndicator, ConfigSyncStatusBar

# Import trading system (EXISTING CODE - NO CHANGES)
# CRITICAL: Use lazy import to avoid triggering main_cli module-level code!
# This prevents TradingSystem from auto-starting when GUI loads
from core.trading_system import TradingSystem

logger = logging.getLogger(__name__)


class StopThread(QThread):
    """Thread to stop trading system without blocking GUI"""

    finished_signal = pyqtSignal(bool)  # True if stopped gracefully, False if forced
    log_message = pyqtSignal(str)

    def __init__(self, trading_thread):
        super().__init__()
        self.trading_thread = trading_thread

    def run(self):
        """Stop trading system in background"""
        try:
            self.log_message.emit("   Stop signal sent to thread...")

            # Tell thread to stop
            self.trading_thread.stop()

            # Wait for graceful stop (max 10 seconds)
            stopped = self.trading_thread.wait(10000)

            if not stopped:
                self.log_message.emit("⚠️  Thread did not stop in 10 seconds, force terminating...")
                self.trading_thread.terminate()
                self.trading_thread.wait(2000)  # Wait for terminate
                self.log_message.emit("   Thread terminated forcefully")
                self.finished_signal.emit(False)  # Forced stop
            else:
                self.log_message.emit("   Thread stopped gracefully")
                self.finished_signal.emit(True)  # Graceful stop

        except Exception as e:
            self.log_message.emit(f"❌ Error stopping: {e}")
            self.finished_signal.emit(False)


class TradingSystemThread(QThread):
    """Thread to run trading system without blocking GUI"""

    # Signals for GUI updates
    status_update = pyqtSignal(dict)
    position_update = pyqtSignal(list)
    log_message = pyqtSignal(str)
    snapshot_update = pyqtSignal(object)  # ← NEW: For chart updates
    error_occurred = pyqtSignal(str)  # ← NEW: For error handling

    def __init__(self, trading_config: dict, risk_alert_handler=None):
        super().__init__()
        self.trading_config = trading_config
        self.trading_system = None
        self.running = False
        self.risk_alert_handler = risk_alert_handler  # Store risk alert handler

        # Track statistics
        self.max_zscore = 0.0
        self.min_zscore = 0.0  # NEW: Track minimum Z-score
        self.min_mean = float('inf')
        self.max_mean = float('-inf')

    def run(self):
        """Run trading system in background thread"""
        try:
            # Extract from trading_config FIRST
            symbols = self.trading_config['symbols']
            settings = self.trading_config['settings']
            primary_symbol = self.trading_config['primary_symbol']
            secondary_symbol = self.trading_config['secondary_symbol']

            # DEBUG: Log what we received
            self.log_message.emit("")
            self.log_message.emit("🔍 DEBUG - Trading Config Received:")
            self.log_message.emit(f"   Primary Symbol: {primary_symbol}")
            self.log_message.emit(f"   Secondary Symbol: {secondary_symbol}")
            self.log_message.emit(f"   Primary Contract: {symbols['primary']['contract_size']}")
            self.log_message.emit(f"   Secondary Contract: {symbols['secondary']['contract_size']}")
            self.log_message.emit("")

            # ========== INITIALIZE MT5 CONNECTION (FIRST!) ==========
            self.log_message.emit("🔌 Initializing MT5 connection...")
            self.log_message.emit("   This may take up to 60 seconds...")

            try:
                from core.mt5_manager import get_mt5_manager

                mt5_manager = get_mt5_manager()

                self.log_message.emit("   Connecting to MT5 terminal...")
                init_success = mt5_manager.initialize()

                if not init_success:
                    self.log_message.emit("❌ FATAL ERROR: Failed to initialize MT5 connection")
                    self.log_message.emit("")
                    self.log_message.emit("Common issues:")
                    self.log_message.emit("  1. MT5 terminal is NOT running")
                    self.log_message.emit("     → Please start MetaTrader 5 terminal first")
                    self.log_message.emit("")
                    self.log_message.emit("  2. Wrong credentials in .env file")
                    self.log_message.emit("     → Check MT5_LOGIN, MT5_PASSWORD, MT5_SERVER")
                    self.log_message.emit("")
                    self.log_message.emit("  3. No internet connection")
                    self.log_message.emit("     → Check your network")
                    self.log_message.emit("")
                    self.error_occurred.emit("Failed to initialize MT5 connection")
                    return

                self.log_message.emit("✅ MT5 Connection established")

            except Exception as e:
                self.log_message.emit(f"❌ Exception during MT5 initialization: {e}")
                import traceback
                error_details = traceback.format_exc()
                self.log_message.emit(f"   Details: {error_details}")
                self.error_occurred.emit(f"MT5 initialization error: {e}")
                return

            # Get real MT5 balance
            mt5 = mt5_manager.mt5
            account_info = mt5.account_info()
            if account_info is None:
                real_balance = 100000.0  # Fallback
                self.log_message.emit("⚠️  Could not get MT5 balance, using default $100,000")
            else:
                real_balance = account_info.balance
                self.log_message.emit(f"✅ MT5 Account Balance: ${real_balance:,.2f}")
                self.log_message.emit(f"   Account: {account_info.login}")
                self.log_message.emit(f"   Leverage: 1:{account_info.leverage}")

            # Create trading system with symbols + settings!
            self.log_message.emit("")
            self.log_message.emit("🔧 Creating TradingSystem...")

            # Add symbols to config dict
            config_with_symbols = settings.copy()
            config_with_symbols['primary_symbol'] = primary_symbol
            config_with_symbols['secondary_symbol'] = secondary_symbol
            
            # Get daily loss limit percentage from config
            # IMPORTANT: Don't convert to dollar amount - TradingSystem now accepts percentage!
            daily_loss_pct = config_with_symbols.get('daily_loss_limit_pct', 5.0)  # Default 5%

            self.log_message.emit(f"💰 Risk Settings:")
            self.log_message.emit(f"   Risk Per Setup: {config_with_symbols.get('max_risk_pct', 2.0):.1f}%")
            self.log_message.emit(f"   Daily Risk Limit: {daily_loss_pct:.1f}% (calculated from starting balance)")

            self.trading_system = TradingSystem(
                account_balance=real_balance,
                config=config_with_symbols  # ← Settings WITH symbols AND converted daily limit!
            )

            # CRITICAL: Set risk alert callback (for GUI notifications)
            if self.risk_alert_handler:
                self.trading_system.risk_alert_callback = lambda severity, title, msg: self.risk_alert_handler.emit_alert(severity, title, msg)
                self.log_message.emit("✅ Risk alert handler connected")
            else:
                self.log_message.emit("⚠️  Risk alert handler not found (GUI won't show alerts)")

            # Set symbol info (runtime data)
            self.log_message.emit(f"📝 Setting symbols in market_data:")
            self.log_message.emit(f"   primary_symbol = {primary_symbol}")
            self.log_message.emit(f"   secondary_symbol = {secondary_symbol}")
            self.trading_system.market_data.primary_symbol = primary_symbol
            self.trading_system.market_data.secondary_symbol = secondary_symbol
            self.trading_system.market_data.primary_contract_size = symbols['primary']['contract_size']
            self.trading_system.market_data.secondary_contract_size = symbols['secondary']['contract_size']

            # CRITICAL: Also update trade executor symbols!
            self.log_message.emit(f"📝 Setting symbols in trade_executor:")
            self.trading_system.trade_executor.primary_symbol = primary_symbol
            self.trading_system.trade_executor.secondary_symbol = secondary_symbol
            self.log_message.emit(f"   ✅ Executor updated: {primary_symbol}/{secondary_symbol}")

            # VERIFY what was actually set
            self.log_message.emit("")
            self.log_message.emit("✅ Verification - Symbols in TradingSystem:")
            self.log_message.emit(f"   market_data.primary_symbol = {self.trading_system.market_data.primary_symbol}")
            self.log_message.emit(
                f"   market_data.secondary_symbol = {self.trading_system.market_data.secondary_symbol}")
            self.log_message.emit(
                f"   market_data.primary_contract_size = {self.trading_system.market_data.primary_contract_size}")
            self.log_message.emit(
                f"   market_data.secondary_contract_size = {self.trading_system.market_data.secondary_contract_size}")
            self.log_message.emit(
                f"   trade_executor.primary_symbol = {self.trading_system.trade_executor.primary_symbol}")
            self.log_message.emit(
                f"   trade_executor.secondary_symbol = {self.trading_system.trade_executor.secondary_symbol}")
            self.log_message.emit("")

            self.log_message.emit(f"✅ Trading system initialized and ready!")
            self.log_message.emit(f"   Trading Pair: {primary_symbol}/{secondary_symbol}")
            self.log_message.emit(f"   Global config applied")

            # Start trading system in separate thread (non-blocking)
            self.running = True

            # Start the trading system (this starts its own threads)
            self.trading_system.start()

            # Monitor loop - keep thread alive and check running flag
            import time
            while self.running:
                time.sleep(0.5)  # Check every 500ms

                # Emit current snapshot for chart updates
                try:
                    if self.trading_system and hasattr(self.trading_system, 'market_data'):
                        snapshot = self.trading_system.market_data.get_realtime_snapshot()
                        if snapshot:
                            self.snapshot_update.emit(snapshot)
                except Exception as e:
                    # Don't crash on snapshot errors
                    pass

                # If trading_system stopped itself, exit
                if hasattr(self.trading_system, '_stop_event'):
                    if self.trading_system._stop_event.is_set():
                        self.log_message.emit("⚠️  Trading system stopped itself")
                        break

            # Clean exit
            self.log_message.emit("🛑 Trading thread exiting...")

        except Exception as e:
            self.log_message.emit(f"❌ Error starting trading system: {str(e)}")
            logger.error(f"Trading system error: {e}", exc_info=True)
        finally:
            # Ensure system is stopped
            if self.trading_system:
                try:
                    self.trading_system.stop()
                except:
                    pass
            self.running = False

    def stop(self):
        """Stop trading system"""
        self.running = False
        if self.trading_system:
            # CRITICAL: Must call stop() on TradingSystem to stop its threads!
            self.trading_system.stop()
            self.log_message.emit("⏸️ Trading system stop signal sent")

    def get_status(self) -> dict:
        """
        Get current system status - Returns raw values for GUI presentation layer.
        All fields use *_value suffix to clearly indicate they're data values, not labels.
        """

        # Default values (shown when not running)
        default_status = {
            'is_running': False,
            # Core market data
            'zscore_value': 0.0,
            'correlation_value': 0.0,
            'hedge_ratio_value': 0.0,
            'spread_value': 0.0,
            'spread_mean_value': 0.0,
            'spread_std_value': 0.0,
            'signal_value': 'HOLD',
            # P&L data
            'total_pnl_value': 0.0,
            'unrealized_pnl_value': 0.0,
            'realized_pnl_value': 0.0,
            # Position counts
            'open_positions_value': 0,
            'closed_positions_value': 0,
            # Account data (MT5)
            'balance_value': 0.0,
            'equity_value': 0.0,
            'used_margin_value': 0.0,
            'free_margin_value': 0.0,
            'margin_level_value': 0.0,
            # Hedge metrics
            'primary_lots_value': 0.0,
            'secondary_lots_value': 0.0,
            'hedge_imbalance_value': 0.0,
            'hedge_imbalance_pct_value': 0.0,
            # Model parameters
            'entry_threshold_value': 2.0,
            'exit_threshold_value': 0.5,
            'window_size_value': 200,
            'scale_interval_value': 0.5,
            'volume_multiplier_value': 1.0,
            # Statistics tracking
            'max_zscore_value': 0.0,
            'min_zscore_value': 0.0,
            'min_mean_value': 0.0,
            'max_mean_value': 0.0,
            # Entry tracking (for pyramiding display)
            'last_entry_zscore_value': None,
            'next_entry_zscore_value': None,
            # Note: entry_mean_value removed - gui_data_presenter reads first_entry_spread_mean directly from spread_states.json
            # Risk management
            'setup_risk_pct_value': 0.0,
            'daily_limit_pct_value': 0.0,
            'daily_total_pnl_value': 0.0,
            'trading_locked_value': False,
            'lock_time_value': None,
            'unlock_time_value': None,
        }

        # If not running, return defaults
        if not self.trading_system or not self.running:
            return default_status

        try:
            # Get real data
            snapshot = self.trading_system.market_data.get_realtime_snapshot()
            pnl_data = self.trading_system.position_tracker.get_total_pnl()


            # Get MT5 risk metrics
            from risk.mt5_risk_monitor import MT5RiskMonitor
            mt5_monitor = MT5RiskMonitor()
            max_risk = self.trading_config['settings'].get('max_risk_pct', 2.0) / 100.0  # Convert to fraction

            try:
                mt5_metrics = mt5_monitor.get_metrics(
                    primary_symbol=self.trading_config.get('primary_symbol', 'XAUUSD'),
                    secondary_symbol=self.trading_config.get('secondary_symbol', 'XAGUSD'),
                    target_hedge_ratio=snapshot.hedge_ratio if snapshot else None,
                    max_risk_pct=max_risk
                )
                if not mt5_metrics:
                    logger.warning("MT5RiskMonitor returned None - using defaults")
                else:
                    logger.debug(f"MT5 Metrics obtained: Balance=${mt5_metrics.balance:,.2f}, "
                               f"Equity=${mt5_metrics.equity:,.2f}, Profit=${mt5_metrics.profit:,.2f}")
            except Exception as e:
                logger.error(f"Error getting MT5 metrics: {e}", exc_info=True)
                mt5_metrics = None

            # Determine signal
            zscore = snapshot.zscore if snapshot else 0.0
            entry = self.trading_config['settings'].get('entry_threshold', 2.0)
            if abs(zscore) >= entry:
                signal = "SHORT SPREAD" if zscore > 0 else "LONG SPREAD"
            else:
                signal = "HOLD"

            # Track statistics
            if snapshot and snapshot.spread_mean > 0:  # Ensure valid snapshot
                # Track max/min z-score (only if zscore is meaningful)
                if abs(zscore) > 0.01:  # Ignore very small values
                    if abs(zscore) > abs(self.max_zscore):
                        self.max_zscore = zscore
                    
                    # Track minimum z-score (most negative or least positive)
                    if self.min_zscore == 0.0:  # First time
                        self.min_zscore = zscore
                    elif abs(zscore) < abs(self.min_zscore):
                        self.min_zscore = zscore

                # Track min/max rolling mean (ensure valid values)
                current_mean = snapshot.spread_mean
                if current_mean > 0:  # Valid mean
                    if self.min_mean == float('inf'):  # First time
                        self.min_mean = current_mean
                    elif current_mean < self.min_mean:
                        self.min_mean = current_mean
                    
                    if self.max_mean == float('-inf'):  # First time
                        self.max_mean = current_mean
                    elif current_mean > self.max_mean:
                        self.max_mean = current_mean
                
                # Debug log periodically
                if hasattr(self, '_debug_counter'):
                    self._debug_counter += 1
                    if self._debug_counter % 10 == 0:  # Every 10 updates
                        logger.debug(f"Tracking: max_z={self.max_zscore:.3f}, min_z={self.min_zscore:.3f}, "
                                   f"min_mean={self.min_mean:.2f}, max_mean={self.max_mean:.2f}")
                else:
                    self._debug_counter = 1

            # Get config values
            config = self.trading_system.config if hasattr(self.trading_system, 'config') else {}

            # Get trading lock status
            is_locked = False
            lock_time = None
            unlock_time = None
            daily_pnl = 0.0
            daily_limit_pct = config.get('daily_loss_limit_pct', 5.0)
            setup_risk_pct = config.get('max_risk_pct', 2.0)

            if hasattr(self.trading_system, 'daily_risk_manager'):
                risk_status = self.trading_system.daily_risk_manager.check_risk(mt5_metrics.profit if mt5_metrics else 0.0)
                is_locked = risk_status.trading_locked
                daily_pnl = risk_status.daily_total_pnl
                if is_locked and hasattr(risk_status, 'locked_at'):
                    lock_time = risk_status.locked_at
                    unlock_time = risk_status.locked_until

            # Return ONLY fields needed by GUI (cleaned up, no unused data)
            return {
                'is_running': True,
                # Core market data
                'zscore_value': zscore,
                'correlation_value': snapshot.correlation if snapshot else 0.0,
                'hedge_ratio_value': snapshot.hedge_ratio if snapshot else 0.0,
                'spread_value': snapshot.spread if snapshot else 0.0,
                'spread_mean_value': snapshot.spread_mean if snapshot else 0.0,
                'spread_std_value': snapshot.spread_std if snapshot else 0.0,
                'signal_value': signal,
                # P&L data
                'total_pnl_value': pnl_data.get('total_pnl', 0.0),
                # IMPORTANT: Use MT5 real profit from ALL positions (not just tracked ones)
                # This ensures manual positions on ANY symbol are displayed
                'unrealized_pnl_value': mt5_metrics.profit if mt5_metrics else pnl_data.get('unrealized_pnl', 0.0),
                'realized_pnl_value': pnl_data.get('realized_pnl', 0.0),
                # Position counts
                # IMPORTANT: Use MT5 real position count (includes manual positions)
                'open_positions_value': mt5_metrics.total_positions if mt5_metrics else pnl_data.get('open_positions', 0),
                'closed_positions_value': pnl_data.get('closed_positions', 0),
                # Account data (from MT5)
                'balance_value': mt5_metrics.balance if mt5_metrics else 0.0,
                'equity_value': mt5_metrics.equity if mt5_metrics else 0.0,
                'used_margin_value': mt5_metrics.margin if mt5_metrics else 0.0,
                'free_margin_value': mt5_metrics.margin_free if mt5_metrics else 0.0,
                'margin_level_value': mt5_metrics.margin_level if mt5_metrics else 0.0,
                # Hedge metrics (from MT5)
                'primary_lots_value': mt5_metrics.primary_lots if mt5_metrics else 0.0,
                'secondary_lots_value': mt5_metrics.secondary_lots if mt5_metrics else 0.0,
                'hedge_imbalance_value': mt5_metrics.hedge_imbalance if mt5_metrics else 0.0,
                'hedge_imbalance_pct_value': mt5_metrics.hedge_imbalance_pct if mt5_metrics else 0.0,
                # Model parameters (from config - synced by apply_settings)
                'entry_threshold_value': config.get('entry_threshold', 2.0),
                'exit_threshold_value': config.get('exit_threshold', 0.5),
                'window_size_value': config.get('rolling_window_size', 200),
                'scale_interval_value': config.get('scale_interval', 0.5),
                'volume_multiplier_value': config.get('volume_multiplier', 1.0),
                # Statistics tracking
                'max_zscore_value': self.max_zscore,
                'min_zscore_value': self.min_zscore,
                'min_mean_value': self.min_mean if self.min_mean != float('inf') else 0.0,
                'max_mean_value': self.max_mean if self.max_mean != float('-inf') else 0.0,
                # Note: entry_mean_value removed - gui_data_presenter reads first_entry_spread_mean directly from spread_states.json
                # Risk management
                'setup_risk_pct_value': setup_risk_pct,
                'daily_limit_pct_value': daily_limit_pct,
                'daily_total_pnl_value': daily_pnl,
                'trading_locked_value': is_locked,
                'lock_time_value': lock_time,
                'unlock_time_value': unlock_time,
            }

        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            return default_status  # Return defaults on error

    def get_positions(self) -> list:
        """Get current positions"""
        if not self.trading_system:
            return []

        try:
            positions = []
            for pos in self.trading_system.position_tracker.get_all_positions():
                # Use spread_id from metadata (ticket-based) instead of position_id (UUID)
                spread_id = pos.metadata.get('spread_id', pos.position_id)

                # Format spread_id for display
                if '-' in spread_id:
                    # Ticket-based format: "1538873231-1538873233"
                    # Show as: "8231-3233" (last 4 digits of each ticket)
                    parts = spread_id.split('-')
                    if len(parts) == 2:
                        display_id = f"{parts[0][-4:]}-{parts[1][-4:]}"
                    else:
                        display_id = spread_id[:8]
                else:
                    # UUID format or other
                    display_id = spread_id[:8]

                positions.append({
                    'id': display_id,  # Display shortened spread_id
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'opened_at': pos.opened_at.strftime("%H:%M:%S"),
                    'metadata': pos.metadata
                })
            return positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []


class PairTradingGUI(QMainWindow):
    """Main GUI Window - Integrated with Trading System"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pair Trading System - Professional Edition")
        self.setGeometry(100, 100, 100, 600)

        # Apply dark title bar on Windows
        self._apply_dark_title_bar()

        # Apply PyCharm Darcula theme from assets
        self.setStyleSheet(DARCULA_THEME_QSS)

        # Initialize state
        self.trading_thread = None

        # NEW: Use simplified settings manager (one global config!)
        from config.trading_settings import TradingSettingsManager, SymbolLoader
        self.settings_manager = TradingSettingsManager()
        self.symbol_loader = SymbolLoader()

        # Risk alert handler (for receiving risk alerts from trading system)
        self.risk_alert_handler = RiskAlertHandler(self)

        # GUI Data Presenter (NEW: Handles all data formatting and calculations)
        self.presenter = GUIDataPresenter()

        # Config Sync Manager (NEW: Hot-reload & change detection)
        self.config_sync_manager = get_config_sync_manager()
        self.config_sync_manager.config_out_of_sync.connect(self._on_config_sync_changed)
        self.config_sync_manager.config_applied.connect(self._on_config_applied)

        self.current_pair = None

        # Create UI
        self.init_ui()

        # Setup update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # Update every second

        # Load settings into GUI
        self.load_settings_into_gui()

        # Load current state from MT5 (account info, risk values from config)
        self.load_current_state_from_mt5()

        # Initial startup message
        self.add_log("=" * 70)
        self.add_log("PAIR TRADING SYSTEM - PROFESSIONAL EDITION")
        self.add_log("=" * 70)
        self.add_log("")
        self.add_log("✅ GUI initialized successfully")
        self.add_log(f"📂 Settings loaded from: config/trading_settings.yaml")
        self.add_log(f"⚙️  Global settings apply to ALL pairs")
        self.add_log("")
        self.add_log("📋 READY TO START:")
        self.add_log("   1. Enter symbols (or use defaults)")
        self.add_log("   2. Adjust settings if needed")
        self.add_log("   3. Click 'Start Trading'")
        self.add_log("   4. System will auto-save config on start")
        self.add_log("")
        self.add_log("💡 System will NOT auto-start - waiting for your command!")
        self.add_log("=" * 70)

    def _apply_dark_title_bar(self):
        """Apply dark title bar on Windows 10/11"""
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20

            # Try Windows 11 first, then Windows 10
            dwmapi = ctypes.windll.dwmapi
            value = ctypes.c_int(1)
            result = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )

            if result != 0:
                # Try older attribute for Windows 10 build < 19041
                DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
                dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                    ctypes.byref(value),
                    ctypes.sizeof(value)
                )
        except Exception as e:
            logger.debug(f"Could not apply dark title bar: {e}")

    def init_ui(self):
        """Initialize the user interface"""
        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 10))

        # Add tabs
        self.dashboard_tab = self.create_dashboard_tab()
        self.chart_tab = self.create_chart_tab()  # ← NEW: Chart tab
        self.discovery_tab = PairDiscoveryTab()  # ← NEW: Pair Discovery tab
        self.settings_tab = self.create_settings_tab()
        self.logs_tab = self.create_logs_tab()

        self.tabs.addTab(self.dashboard_tab, "📊 Dashboard")
        self.tabs.addTab(self.chart_tab, "📈 Charts")  # ← NEW: Charts tab
        self.tabs.addTab(self.discovery_tab, "🔬 Pair Discovery")  # ← NEW: Discovery tab
        self.tabs.addTab(self.settings_tab, "⚙️ Settings")
        self.tabs.addTab(self.logs_tab, "📝 Logs")

        main_layout.addWidget(self.tabs)

        # Status bar with config sync indicator
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready - Select pair and start trading")

        # Config sync indicator in status bar (shows when GUI config differs from running system)
        self.config_sync_indicator = ConfigSyncIndicator()
        self.config_sync_indicator.apply_clicked.connect(self._on_sync_apply_clicked)
        self.config_sync_indicator.details_clicked.connect(self._on_sync_details_clicked)
        self.statusBar.addPermanentWidget(self.config_sync_indicator)

    def load_settings_into_gui(self):
        """
        Load global settings into GUI controls
        ONE set of settings applies to ALL pairs!
        """
        settings = self.settings_manager.get()

        # Trading parameters
        self.entry_zscore_spin.setValue(settings.entry_threshold)
        self.exit_zscore_spin.setValue(settings.exit_threshold)
        self.stop_zscore_spin.setValue(settings.stop_loss_zscore)
        self.max_positions_spin.setValue(settings.max_positions)
        self.volume_mult_spin.setValue(settings.volume_multiplier)

        # Model parameters
        self.window_spin.setValue(settings.rolling_window_size)
        self.interval_spin.setValue(settings.update_interval)
        self.hedge_drift_spin.setValue(settings.hedge_drift_threshold)

        # Risk parameters
        self.max_pos_pct_spin.setValue(settings.max_position_pct)
        self.max_risk_pct_spin.setValue(settings.max_risk_pct)
        self.daily_loss_spin.setValue(settings.daily_loss_limit_pct)
        
        # Session times (NEW v5.5)
        self.session_start_input.setText(getattr(settings, 'session_start_time', '00:00'))
        self.session_end_input.setText(getattr(settings, 'session_end_time', '23:59'))

        # Feature flags
        self.pyramiding_check.setChecked(settings.enable_pyramiding)
        self.hedge_adjust_check.setChecked(settings.enable_hedge_adjustment)
        self.entry_cooldown_check.setChecked(settings.enable_entry_cooldown)
        self.manual_sync_check.setChecked(settings.enable_manual_position_sync)

        # Advanced settings
        self.scale_interval_spin.setValue(settings.scale_interval)
        self.initial_fraction_spin.setValue(settings.initial_fraction)
        self.min_adjust_interval_spin.setValue(settings.min_adjustment_interval)
        self.magic_number_spin.setValue(settings.magic_number)
        self.zscore_history_spin.setValue(settings.zscore_history_size)

        # Update displays
        self.entry_threshold_label.setText(f"{settings.entry_threshold:.1f}")
        self.exit_threshold_label.setText(f"{settings.exit_threshold:.1f}")
        self.window_size_label.setText(f"{settings.rolling_window_size}")

        # Update new labels
        self.scalp_interval_label.setText(f"{settings.scale_interval:.1f}")
        self.volume_multiplier_label.setText(f"{settings.volume_multiplier:.2f}")

        # risk manager
        self.daily_risk_pct_label.setText(f"{settings.daily_loss_limit_pct:.2f}%")

        # Set default symbols
        self.primary_input.setText("BTCUSD")
        self.secondary_input.setText("ETHUSD")

        # Connect settings controls to change detector (for config sync indicator)
        self._connect_settings_change_signals()

    def _connect_settings_change_signals(self):
        """Connect all settings controls to change detector for config sync indicator"""
        # Trading parameters
        self.entry_zscore_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.exit_zscore_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.stop_zscore_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.max_positions_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.volume_mult_spin.valueChanged.connect(self._on_gui_setting_changed)

        # Model parameters
        self.window_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.interval_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.hedge_drift_spin.valueChanged.connect(self._on_gui_setting_changed)

        # Feature flags
        self.pyramiding_check.stateChanged.connect(self._on_gui_setting_changed)
        self.hedge_adjust_check.stateChanged.connect(self._on_gui_setting_changed)
        self.entry_cooldown_check.stateChanged.connect(self._on_gui_setting_changed)
        self.manual_sync_check.stateChanged.connect(self._on_gui_setting_changed)

        # Risk parameters
        self.max_pos_pct_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.max_risk_pct_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.daily_loss_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.session_start_input.textChanged.connect(self._on_gui_setting_changed)
        self.session_end_input.textChanged.connect(self._on_gui_setting_changed)

        # Advanced settings
        self.scale_interval_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.initial_fraction_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.min_adjust_interval_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.magic_number_spin.valueChanged.connect(self._on_gui_setting_changed)
        self.zscore_history_spin.valueChanged.connect(self._on_gui_setting_changed)

    def load_current_state_from_mt5(self):
        """
        Load current state from MT5 when GUI starts.
        This updates the RISK MANAGER panel and other displays
        with real values instead of defaults.
        Uses mt5_manager to ensure single MT5 connection.
        """
        try:
            from core.mt5_manager import get_mt5
            mt5 = get_mt5()

            # Get account info
            account_info = mt5.account_info()
            if account_info is None:
                logger.warning("Could not get MT5 account info for initial state load")
                return

            balance = account_info.balance
            equity = account_info.equity
            profit = account_info.profit

            # Update MT5 Account panel
            self.balance_label.setText(f"${balance:,.2f}")
            self.equity_label.setText(f"${equity:,.2f}")
            self.unrealized_pnl_label.setText(f"${profit:,.2f}")

            # Color code profit
            if profit > 0:
                self.unrealized_pnl_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            elif profit < 0:
                self.unrealized_pnl_label.setStyleSheet("color: #e74c3c; font-weight: bold;")

            # Update margin info
            margin = account_info.margin
            free_margin = account_info.margin_free
            margin_level = account_info.margin_level if account_info.margin_level else 0

            self.used_margin_label.setText(f"${margin:,.2f}")
            self.free_margin_label.setText(f"${free_margin:,.2f}")
            self.margin_level_label.setText(f"{margin_level:.1f}%")

            # ========== RISK MANAGER - Load from settings and MT5 ==========
            try:
                settings = self.settings_manager.get()

                # Get unrealized P&L (open positions)
                unrealized_pnl = equity - balance

                # Risk Per Setup - from config
                setup_risk_pct = settings.max_risk_pct
                setup_risk_amount = balance * (setup_risk_pct / 100.0)
                self.setup_risk_pct_label.setText(f"{setup_risk_pct:.2f}%")
                self.setup_risk_amount_label.setText(f"${setup_risk_amount:,.0f}")
                self.risk_unrealized_label.setText(f"${unrealized_pnl:,.2f}")
                if unrealized_pnl < 0:
                    self.risk_unrealized_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
                else:
                    self.risk_unrealized_label.setStyleSheet("color: #27ae60; font-weight: bold;")

                # Daily Risk - from config
                daily_risk_pct = settings.daily_loss_limit_pct
                daily_risk_amount = balance * (daily_risk_pct / 100.0)
                self.daily_risk_limit_label.setText(f"${daily_risk_amount:,.0f}")

                # Get session P&L from history
                from risk.daily_risk_manager import DailyRiskManager
                daily_risk = DailyRiskManager(
                    account_balance=balance,
                    max_risk_pct=settings.max_risk_pct,
                    daily_loss_limit_pct=settings.daily_loss_limit_pct
                )
                history = daily_risk.load_daily_history(current_equity=equity)
                session_pnl = history['net_realized_pnl'] + unrealized_pnl
                self.daily_total_pnl_label.setText(f"${session_pnl:,.0f}")
                if session_pnl < 0:
                    self.daily_total_pnl_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
                else:
                    self.daily_total_pnl_label.setStyleSheet("color: #27ae60; font-weight: bold;")

                logger.info(f"[GUI] Risk Manager: Setup={setup_risk_pct}%/${setup_risk_amount:.0f}, "
                           f"Daily={daily_risk_pct}%/${daily_risk_amount:.0f}, PnL=${session_pnl:.0f}")

            except Exception as e:
                logger.warning(f"Could not load Risk Manager state: {e}")

            # ========== Load Trading Lock Status ==========
            try:
                from risk.trading_lock_manager import TradingLockManager
                lock_manager = TradingLockManager()

                if lock_manager.is_locked():
                    self.trading_status_label.setText("LOCK")
                    self.trading_status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
                    # Show block/unlock time
                    lock_info = lock_manager.get_lock_info()
                    if lock_info.get('locked_at'):
                        from datetime import datetime
                        locked_at = datetime.fromisoformat(lock_info['locked_at'])
                        self.block_time_label.setText(locked_at.strftime("%H:%M"))
                    if lock_info.get('locked_until'):
                        locked_until = datetime.fromisoformat(lock_info['locked_until'])
                        self.unlock_time_label.setText(locked_until.strftime("%H:%M"))
                else:
                    self.trading_status_label.setText("UNLOCK")
                    self.trading_status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
                    self.block_time_label.setText("--")
                    self.unlock_time_label.setText("--")
            except Exception as e:
                logger.warning(f"Could not load TradingLockManager state: {e}")

            # ========== Load Active Positions Count ==========
            positions = mt5.positions_get()
            if positions:
                position_count = len(positions)
                # Count spreads (pairs of positions)
                spread_count = position_count // 2
                self.open_close_label.setText(f"{spread_count} / --")

            logger.info("[GUI] Initial MT5 state loaded successfully")

        except Exception as e:
            logger.warning(f"Could not load initial MT5 state: {e}")

    def populate_symbols(self):
        """
        DEPRECATED - Kept for compatibility
        Old method that loaded from pairs config
        Now we use load_settings_into_gui() instead
        """
        pass

    def update_dashboard_from_config(self, pair: PairConfig):
        """Update dashboard display labels from config"""
        # Update Model Metrics display on Dashboard
        self.entry_threshold_label.setText(f"{pair.entry_threshold:.1f}")
        self.exit_threshold_label.setText(f"{pair.exit_threshold:.1f}")
        self.window_size_label.setText(f"{pair.rolling_window_size}")

        # Update new labels
        self.scalp_interval_label.setText(f"{getattr(pair, 'scale_interval', 0.5):.1f}")
        self.volume_multiplier_label.setText(f"{pair.volume_multiplier:.2f}")

        # Update status
        self.statusBar.showMessage(f"Configuration loaded: {pair.primary_symbol}/{pair.secondary_symbol}")

    def create_dashboard_tab(self):
        """Create main dashboard tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ========== Top Control Panel ==========
        control_panel = QGroupBox("Control Panel")
        control_layout = QHBoxLayout()

        # Symbol selection
        symbol_group = QGroupBox("Symbol Selection")
        symbol_layout = QGridLayout()

        # Primary symbol input (text field instead of dropdown!)
        symbol_layout.addWidget(QLabel("Primary Symbol:"), 0, 0)
        self.primary_input = QLineEdit()
        self.primary_input.setPlaceholderText("e.g., XAUUSD, GOLD, XAU/USD...")
        self.primary_input.setMinimumWidth(150)
        self.primary_input.setText("XAUUSD")  # Default
        self.primary_input.textChanged.connect(self.on_symbol_changed)
        symbol_layout.addWidget(self.primary_input, 0, 1)

        # Secondary symbol input (text field instead of dropdown!)
        symbol_layout.addWidget(QLabel("Secondary Symbol:"), 1, 0)
        self.secondary_input = QLineEdit()
        self.secondary_input.setPlaceholderText("e.g., XAGUSD, SILVER, XAG/USD...")
        self.secondary_input.setMinimumWidth(150)
        self.secondary_input.setText("XAGUSD")  # Default
        self.secondary_input.textChanged.connect(self.on_symbol_changed)
        symbol_layout.addWidget(self.secondary_input, 1, 1)

        # Analyze button removed - not needed yet
        # self.analyze_btn = QPushButton("🔍 Analyze Pair")
        # self.analyze_btn.clicked.connect(self.analyze_pair)
        # symbol_layout.addWidget(self.analyze_btn, 0, 2)

        self.start_stop_btn = QPushButton("▶️ Start Trading")
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.start_stop_btn.clicked.connect(self.toggle_trading)
        symbol_layout.addWidget(self.start_stop_btn, 1, 2)

        symbol_group.setLayout(symbol_layout)
        control_layout.addWidget(symbol_group)

        # Live statistics (Core metrics only - no duplicates)
        stats_group = QGroupBox("Live Statistics")
        stats_layout = QGridLayout()

        # Row 0: Z-Score (most important - large font)
        self.z_score_label = QLabel("--")
        self.z_score_label.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        stats_layout.addWidget(QLabel("Z-Score:"), 0, 0)
        stats_layout.addWidget(self.z_score_label, 0, 1)

        # Row 0 col 2: Signal (important for quick decision)
        self.signal_label = QLabel("HOLD")
        self.signal_label.setStyleSheet(
            "background-color: #7f8c8d; color: white; padding: 5px; border-radius: 3px; font-weight: bold;")
        stats_layout.addWidget(QLabel("Signal:"), 0, 2)
        stats_layout.addWidget(self.signal_label, 0, 3)

        # Row 1: Correlation
        self.correlation_label = QLabel("--")
        stats_layout.addWidget(QLabel("Correlation:"), 1, 0)
        stats_layout.addWidget(self.correlation_label, 1, 1)

        # Row 1 col 2: Hedge Ratio
        self.hedge_ratio_label = QLabel("--")
        stats_layout.addWidget(QLabel("Hedge Ratio:"), 1, 2)
        stats_layout.addWidget(self.hedge_ratio_label, 1, 3)

        stats_group.setLayout(stats_layout)
        control_layout.addWidget(stats_group)

        control_panel.setLayout(control_layout)
        layout.addWidget(control_panel)

        # ========== Model Metrics Panel ==========
        metrics_panel = QGroupBox("Model Metrics")
        metrics_layout = QGridLayout()

        # ========== Row 0: Entry Threshold, Spread Mean, Mean Drift ==========
        metrics_layout.addWidget(QLabel("Entry Threshold:"), 0, 0)
        self.entry_threshold_label = QLabel("2.0")
        self.entry_threshold_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.entry_threshold_label, 0, 1)

        metrics_layout.addWidget(QLabel("Spread Mean:"), 0, 2)
        self.spread_mean_label = QLabel("--")
        self.spread_mean_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.spread_mean_label, 0, 3)

        metrics_layout.addWidget(QLabel("Mean Drift:"), 0, 4)
        self.mean_drift_label = QLabel("--")
        mean_drift_font = QFont("Courier New", 10)
        mean_drift_font.setBold(True)
        self.mean_drift_label.setFont(mean_drift_font)
        self.mean_drift_label.setToolTip("Thay đổi Mean từ lúc entry")
        metrics_layout.addWidget(self.mean_drift_label, 0, 5)

        # ========== Row 1: Exit Threshold, Spread Std, Window Size ==========
        metrics_layout.addWidget(QLabel("Exit Threshold:"), 1, 0)
        self.exit_threshold_label = QLabel("0.5")
        self.exit_threshold_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.exit_threshold_label, 1, 1)

        metrics_layout.addWidget(QLabel("Spread Std:"), 1, 2)
        self.spread_std_label = QLabel("--")
        self.spread_std_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.spread_std_label, 1, 3)

        metrics_layout.addWidget(QLabel("Window Size:"), 1, 4)
        self.window_size_label = QLabel("200")
        self.window_size_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.window_size_label, 1, 5)

        # ========== Row 2: Max Z-Score, Max Mean, Last Update ==========
        metrics_layout.addWidget(QLabel("Max Z-Score:"), 2, 0)
        self.max_z_score_label = QLabel("--")
        self.max_z_score_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.max_z_score_label, 2, 1)

        metrics_layout.addWidget(QLabel("Max Mean:"), 2, 2)
        self.max_mean_label = QLabel("--")
        self.max_mean_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.max_mean_label, 2, 3)

        metrics_layout.addWidget(QLabel("Last Update:"), 2, 4)
        self.last_update_label = QLabel("--")
        self.last_update_label.setFont(QFont("Courier New", 9))
        metrics_layout.addWidget(self.last_update_label, 2, 5)

        # ========== Row 3: Min Z-Score, Min Mean, Status ==========
        metrics_layout.addWidget(QLabel("Min Z-Score:"), 3, 0)
        self.min_z_score_label = QLabel("--")
        min_z_font = QFont("Courier New", 10)
        min_z_font.setBold(True)
        self.min_z_score_label.setFont(min_z_font)
        self.min_z_score_label.setToolTip("Z-score thấp nhất trong session")
        metrics_layout.addWidget(self.min_z_score_label, 3, 1)

        metrics_layout.addWidget(QLabel("Min Mean:"), 3, 2)
        self.min_mean_label = QLabel("--")
        self.min_mean_label.setFont(QFont("Courier New", 10))
        metrics_layout.addWidget(self.min_mean_label, 3, 3)

        metrics_layout.addWidget(QLabel("Status:"), 3, 4)
        self.status_label = QLabel("⚫ Stopped")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")
        metrics_layout.addWidget(self.status_label, 3, 5)

        # ========== Row 4: Last Z Score Entries, Scalp Interval ==========
        metrics_layout.addWidget(QLabel("Last Z Score Entries:"), 4, 0)
        self.last_z_score_entries_label = QLabel("--")
        self.last_z_score_entries_label.setFont(QFont("Courier New", 10))
        self.last_z_score_entries_label.setToolTip("Z-score của lần entry cuối cùng")
        metrics_layout.addWidget(self.last_z_score_entries_label, 4, 1)

        metrics_layout.addWidget(QLabel("Scalp Interval:"), 4, 2)
        self.scalp_interval_label = QLabel("0.5")
        self.scalp_interval_label.setFont(QFont("Courier New", 10))
        self.scalp_interval_label.setToolTip("Khoảng cách z-score giữa các lần pyramiding")
        metrics_layout.addWidget(self.scalp_interval_label, 4, 3)

        # ========== Row 5: Next Z Score Entries, Volume Multiplier ==========
        metrics_layout.addWidget(QLabel("Next Z Score Entries:"), 5, 0)
        self.next_z_score_entries_label = QLabel("--")
        self.next_z_score_entries_label.setFont(QFont("Courier New", 10))
        self.next_z_score_entries_label.setToolTip("Z-score dự kiến cho lần entry tiếp theo")
        metrics_layout.addWidget(self.next_z_score_entries_label, 5, 1)

        metrics_layout.addWidget(QLabel("Volume Multiplier:"), 5, 2)
        self.volume_multiplier_label = QLabel("1.0")
        self.volume_multiplier_label.setFont(QFont("Courier New", 10))
        self.volume_multiplier_label.setToolTip("Hệ số nhân khối lượng giao dịch")
        metrics_layout.addWidget(self.volume_multiplier_label, 5, 3)

        metrics_panel.setLayout(metrics_layout)
        layout.addWidget(metrics_panel)

        # ========== UNIFIED ACCOUNT & RISK MANAGEMENT PANEL ==========
        account_risk_panel = QGroupBox("💰 ACCOUNT & RISK MANAGEMENT")
        account_risk_layout = QGridLayout()
        
        # ===== SECTION 1: ACCOUNT STATUS =====
        section1_label = QLabel("ACCOUNT STATUS")
        section1_label.setStyleSheet("font-weight: bold; color: #3498db; font-size: 11px; padding: 3px; border-bottom: 1px solid #34495e;")
        account_risk_layout.addWidget(section1_label, 0, 0, 1, 6)
        
        account_risk_layout.addWidget(QLabel("Balance:"), 1, 0)
        self.balance_label = QLabel("$0.00")
        self.balance_label.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self.balance_label.setStyleSheet("color: #2980b9;")
        account_risk_layout.addWidget(self.balance_label, 1, 1)

        account_risk_layout.addWidget(QLabel("Equity:"), 1, 2)
        self.equity_label = QLabel("$0.00")
        self.equity_label.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self.equity_label.setStyleSheet("color: #27ae60;")
        account_risk_layout.addWidget(self.equity_label, 1, 3)

        account_risk_layout.addWidget(QLabel("Unrealized P&L:"), 1, 4)
        self.unrealized_pnl_label = QLabel("$0.00")
        self.unrealized_pnl_label.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        account_risk_layout.addWidget(self.unrealized_pnl_label, 1, 5)

        # Margin Info (Row 2)
        account_risk_layout.addWidget(QLabel("Used Margin:"), 2, 0)
        self.used_margin_label = QLabel("$0.00")
        account_risk_layout.addWidget(self.used_margin_label, 2, 1)
        
        account_risk_layout.addWidget(QLabel("Free Margin:"), 2, 2)
        self.free_margin_label = QLabel("$0.00")
        account_risk_layout.addWidget(self.free_margin_label, 2, 3)

        account_risk_layout.addWidget(QLabel("Margin Level:"), 2, 4)
        self.margin_level_label = QLabel("0.0%")
        self.margin_level_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        account_risk_layout.addWidget(self.margin_level_label, 2, 5)
        
        # ===== SECTION 2: POSITION OVERVIEW =====
        section2_label = QLabel("POSITION OVERVIEW")
        section2_label.setStyleSheet("font-weight: bold; color: #3498db; font-size: 11px; padding: 3px; margin-top: 5px; border-bottom: 1px solid #34495e;")
        account_risk_layout.addWidget(section2_label, 3, 0, 1, 6)

        # Row 4: Open Spread | Open/Close | Total Lots
        account_risk_layout.addWidget(QLabel("Open Spread:"), 4, 0)
        self.open_spread_label = QLabel("0")
        self.open_spread_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        account_risk_layout.addWidget(self.open_spread_label, 4, 1)

        account_risk_layout.addWidget(QLabel("Open/Close:"), 4, 2)
        self.open_close_label = QLabel("0 / 0")
        self.open_close_label.setFont(QFont("Courier New", 9))
        account_risk_layout.addWidget(self.open_close_label, 4, 3)

        account_risk_layout.addWidget(QLabel("Total Lots:"), 4, 4)
        self.total_lots_label = QLabel("0.00 / 0.00")
        self.total_lots_label.setFont(QFont("Courier New", 9))
        account_risk_layout.addWidget(self.total_lots_label, 4, 5)

        # Row 5: Hedge Quality | Imbalance | Value
        account_risk_layout.addWidget(QLabel("Hedge Quality:"), 5, 0)
        self.hedge_quality_label = QLabel("--")
        self.hedge_quality_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        account_risk_layout.addWidget(self.hedge_quality_label, 5, 1)

        account_risk_layout.addWidget(QLabel("Imbalance:"), 5, 2)
        self.imbalance_label = QLabel("Balanced")
        self.imbalance_label.setFont(QFont("Courier New", 9))
        account_risk_layout.addWidget(self.imbalance_label, 5, 3)

        account_risk_layout.addWidget(QLabel("Value:"), 5, 4)
        self.value_label = QLabel("$0.00")
        self.value_label.setFont(QFont("Courier New", 9))
        account_risk_layout.addWidget(self.value_label, 5, 5)
        
        # ===== SECTION 3: RISK MANAGER =====
        section3_label = QLabel("RISK MANAGER")
        section3_label.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 11px; padding: 3px; margin-top: 5px; border-bottom: 1px solid #34495e;")
        account_risk_layout.addWidget(section3_label, 6, 0, 1, 6)

        # Row 7: Risk Per Setup header | Daily Risk header
        setup_header = QLabel("Risk per Setup")
        setup_header.setStyleSheet("color: #3498db; font-weight: bold; font-size: 10px;")
        account_risk_layout.addWidget(setup_header, 7, 0, 1, 2)

        daily_header = QLabel("Daily Risk")
        daily_header.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 10px;")
        account_risk_layout.addWidget(daily_header, 7, 2, 1, 2)

        # Row 8: risk % | Risk % | trading status
        account_risk_layout.addWidget(QLabel("Risk %:"), 8, 0)
        self.setup_risk_pct_label = QLabel("--%")
        self.setup_risk_pct_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.setup_risk_pct_label.setStyleSheet("color: #3498db;")
        account_risk_layout.addWidget(self.setup_risk_pct_label, 8, 1)

        account_risk_layout.addWidget(QLabel("Risk %:"), 8, 2)
        self.daily_risk_pct_label = QLabel("--%")
        self.daily_risk_pct_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.daily_risk_pct_label.setStyleSheet("color: #e74c3c;")
        account_risk_layout.addWidget(self.daily_risk_pct_label, 8, 3)

        account_risk_layout.addWidget(QLabel("Trading Status:"), 8, 4)
        self.trading_status_label = QLabel("--")
        self.trading_status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.trading_status_label.setStyleSheet("color: #95a5a6;")
        account_risk_layout.addWidget(self.trading_status_label, 8, 5)

        # Row 9: risk $ | Risk $ | block time
        account_risk_layout.addWidget(QLabel("Risk $:"), 9, 0)
        self.setup_risk_amount_label = QLabel("$--")
        self.setup_risk_amount_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.setup_risk_amount_label.setStyleSheet("color: #3498db;")
        account_risk_layout.addWidget(self.setup_risk_amount_label, 9, 1)

        account_risk_layout.addWidget(QLabel("Risk $:"), 9, 2)
        self.daily_risk_limit_label = QLabel("$--")
        self.daily_risk_limit_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.daily_risk_limit_label.setStyleSheet("color: #e74c3c;")
        account_risk_layout.addWidget(self.daily_risk_limit_label, 9, 3)

        account_risk_layout.addWidget(QLabel("Block Time:"), 9, 4)
        self.block_time_label = QLabel("--")
        self.block_time_label.setFont(QFont("Courier New", 9))
        account_risk_layout.addWidget(self.block_time_label, 9, 5)

        # Row 10: unrealized pnl | Total PnL | unlock time
        account_risk_layout.addWidget(QLabel("Unrealized:"), 10, 0)
        self.risk_unrealized_label = QLabel("$--")
        self.risk_unrealized_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        account_risk_layout.addWidget(self.risk_unrealized_label, 10, 1)

        account_risk_layout.addWidget(QLabel("Total PnL:"), 10, 2)
        self.daily_total_pnl_label = QLabel("$--")
        self.daily_total_pnl_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        account_risk_layout.addWidget(self.daily_total_pnl_label, 10, 3)

        account_risk_layout.addWidget(QLabel("Unlock Time:"), 10, 4)
        self.unlock_time_label = QLabel("--")
        self.unlock_time_label.setFont(QFont("Courier New", 9))
        account_risk_layout.addWidget(self.unlock_time_label, 10, 5)

        # Hidden labels for backwards compatibility (internal use)
        self._starting_balance_label = QLabel("$0.00")
        self._remaining_label = QLabel("$0.00")
        self._max_open_limit_label = QLabel("$0.00")
        self._current_open_loss_label = QLabel("$0.00")
        self._max_open_status_label = QLabel("SAFE")
        self._setup_id_label = QLabel("--")
        self._setup_entry_pnl_label = QLabel("$0.00")
        self._total_setups_label = QLabel("0")

        # Hidden labels for backwards compatibility (used by update logic)
        self._primary_lots_label = QLabel("0.00")  # Hidden - data stored in total_lots_label
        self._secondary_lots_label = QLabel("0.00")  # Hidden - data stored in total_lots_label
        self._hedge_imbalance_pct_label = QLabel("0.00%")  # Hidden - shown in hedge quality
        self._hedge_quality_pct = 0.0  # Store hedge quality percentage
        self._stop_loss_label = QLabel("$0.00")  # Hidden - not needed in unified view
        self._max_risk_label = QLabel("0.0%")  # Hidden - not needed in unified view
        self._risk_amount_label = QLabel("$0.00")  # Hidden - now shown per-setup
        self._distance_to_sl_label = QLabel("0.0%")  # Hidden - not needed
        self._open_pnl_label = QLabel("$0.00 / $0.00")  # Hidden - shown in unrealized P&L
        self._open_status_label = QLabel("SAFE")  # Hidden - shown in hedge quality
        
        account_risk_panel.setLayout(account_risk_layout)
        layout.addWidget(account_risk_panel)
        # ========== END UNIFIED ACCOUNT & RISK MANAGEMENT ==========

        # ========== P&L Attribution Panel ==========
        attribution_panel = QGroupBox("📊 P&L Attribution (Real-Time)")
        attribution_layout = QGridLayout()

        # Row 0: Spread P&L
        attribution_layout.addWidget(QLabel("Spread P&L:"), 0, 0)
        self.spread_pnl_label = QLabel("$0.00")
        self.spread_pnl_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.spread_pnl_label.setStyleSheet("color: #3498db;")
        attribution_layout.addWidget(self.spread_pnl_label, 0, 1)

        self.spread_pnl_pct_label = QLabel("0.0%")
        self.spread_pnl_pct_label.setFont(QFont("Courier New", 9))
        attribution_layout.addWidget(self.spread_pnl_pct_label, 0, 2)

        # Row 1: Mean Drift P&L
        attribution_layout.addWidget(QLabel("Mean Drift P&L:"), 1, 0)
        self.mean_drift_pnl_label = QLabel("$0.00")
        self.mean_drift_pnl_label.setFont(QFont("Courier New", 10))
        self.mean_drift_pnl_label.setStyleSheet("color: #9b59b6;")
        attribution_layout.addWidget(self.mean_drift_pnl_label, 1, 1)

        self.mean_drift_pnl_pct_label = QLabel("0.0%")
        self.mean_drift_pnl_pct_label.setFont(QFont("Courier New", 9))
        attribution_layout.addWidget(self.mean_drift_pnl_pct_label, 1, 2)

        # Row 2: Directional P&L
        attribution_layout.addWidget(QLabel("Directional P&L:"), 2, 0)
        self.directional_pnl_label = QLabel("$0.00")
        self.directional_pnl_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.directional_pnl_label.setStyleSheet("color: #95a5a6;")
        attribution_layout.addWidget(self.directional_pnl_label, 2, 1)

        self.directional_pnl_pct_label = QLabel("0.0%")
        self.directional_pnl_pct_label.setFont(QFont("Courier New", 9))
        attribution_layout.addWidget(self.directional_pnl_pct_label, 2, 2)

        # Row 3: Hedge Imbalance P&L
        attribution_layout.addWidget(QLabel("Hedge Imbalance:"), 3, 0)
        self.hedge_imbalance_pnl_label = QLabel("$0.00")
        self.hedge_imbalance_pnl_label.setFont(QFont("Courier New", 10))
        attribution_layout.addWidget(self.hedge_imbalance_pnl_label, 3, 1)

        self.hedge_imbalance_pnl_pct_label = QLabel("0.0%")
        self.hedge_imbalance_pnl_pct_label.setFont(QFont("Courier New", 9))
        attribution_layout.addWidget(self.hedge_imbalance_pnl_pct_label, 3, 2)

        # Spacer column
        attribution_layout.setColumnMinimumWidth(3, 30)

        # Row 0 (right side): Transaction Costs
        attribution_layout.addWidget(QLabel("Transaction Costs:"), 0, 4)
        self.transaction_costs_label = QLabel("$0.00")
        self.transaction_costs_label.setFont(QFont("Courier New", 10))
        self.transaction_costs_label.setStyleSheet("color: #e74c3c;")
        attribution_layout.addWidget(self.transaction_costs_label, 0, 5)

        self.transaction_costs_pct_label = QLabel("0.0%")
        self.transaction_costs_pct_label.setFont(QFont("Courier New", 9))
        attribution_layout.addWidget(self.transaction_costs_pct_label, 0, 6)

        # Row 1 (right side): Slippage
        attribution_layout.addWidget(QLabel("Slippage:"), 1, 4)
        self.slippage_label = QLabel("$0.00")
        self.slippage_label.setFont(QFont("Courier New", 10))
        attribution_layout.addWidget(self.slippage_label, 1, 5)

        self.slippage_pct_label = QLabel("0.0%")
        self.slippage_pct_label.setFont(QFont("Courier New", 9))
        attribution_layout.addWidget(self.slippage_pct_label, 1, 6)

        # Row 2 (right side): Rebalance Alpha
        attribution_layout.addWidget(QLabel("Rebalance Alpha:"), 2, 4)
        self.rebalance_alpha_label = QLabel("$0.00")
        self.rebalance_alpha_label.setFont(QFont("Courier New", 10))
        self.rebalance_alpha_label.setStyleSheet("color: #27ae60;")
        attribution_layout.addWidget(self.rebalance_alpha_label, 2, 5)

        self.rebalance_alpha_pct_label = QLabel("0.0%")
        self.rebalance_alpha_pct_label.setFont(QFont("Courier New", 9))
        attribution_layout.addWidget(self.rebalance_alpha_pct_label, 2, 6)

        # Separator line
        separator = QLabel("─" * 80)
        separator.setStyleSheet("color: #34495e;")
        attribution_layout.addWidget(separator, 4, 0, 1, 7)

        # Row 5: Quality Metrics
        attribution_layout.addWidget(QLabel("Hedge Quality:"), 5, 0)
        self.pnl_hedge_quality_label = QLabel("--")
        self.pnl_hedge_quality_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.pnl_hedge_quality_label.setStyleSheet("color: #95a5a6;")
        attribution_layout.addWidget(self.pnl_hedge_quality_label, 5, 1)

        attribution_layout.addWidget(QLabel("Strategy Purity:"), 5, 2)
        self.strategy_purity_label = QLabel("--")
        self.strategy_purity_label.setFont(QFont("Courier New", 10))
        attribution_layout.addWidget(self.strategy_purity_label, 5, 3)

        attribution_layout.addWidget(QLabel("Classification:"), 5, 4)
        self.classification_label = QLabel("NO DATA")
        self.classification_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.classification_label.setStyleSheet("color: #95a5a6;")
        attribution_layout.addWidget(self.classification_label, 5, 5, 1, 2)

        attribution_panel.setLayout(attribution_layout)
        layout.addWidget(attribution_panel)

        # ========== Positions Table REMOVED ==========
        # Users can check positions directly on MT5 Terminal
        # Important info already shown in "Per-Setup Risk" section above
        # Keeping table would be redundant and add clutter
        
        return tab

    def create_chart_tab(self):
        """Create real-time chart tab"""
        self.chart_widget = ChartWidget()
        return self.chart_widget

    def create_settings_tab(self):
        """Create settings configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Create scroll area for all settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background-color: #3C3F41; border: none; }")

        # Container widget for all settings
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: #3C3F41; }")
        container_layout = QVBoxLayout(container)

        # ========== Row 1: Trading + Model Parameters ==========
        row1_layout = QHBoxLayout()

        # ========== Trading Parameters ==========
        trading_group = QGroupBox("Trading Parameters")
        trading_layout = QGridLayout()

        row = 0
        trading_layout.addWidget(QLabel("Entry Z-Score:"), row, 0)
        self.entry_zscore_spin = QDoubleSpinBox()
        self.entry_zscore_spin.setRange(0.1, 5.0)
        self.entry_zscore_spin.setValue(2.0)
        self.entry_zscore_spin.setSingleStep(0.1)
        self.entry_zscore_spin.setFixedWidth(100)
        trading_layout.addWidget(self.entry_zscore_spin, row, 1)

        row += 1
        trading_layout.addWidget(QLabel("Exit Z-Score:"), row, 0)
        self.exit_zscore_spin = QDoubleSpinBox()
        self.exit_zscore_spin.setRange(0.0, 2.0)
        self.exit_zscore_spin.setValue(0.5)
        self.exit_zscore_spin.setSingleStep(0.1)
        self.exit_zscore_spin.setFixedWidth(100)
        trading_layout.addWidget(self.exit_zscore_spin, row, 1)

        row += 1
        trading_layout.addWidget(QLabel("Stop Loss Z-Score:"), row, 0)
        self.stop_zscore_spin = QDoubleSpinBox()
        self.stop_zscore_spin.setRange(2.0, 10.0)
        self.stop_zscore_spin.setValue(3.5)
        self.stop_zscore_spin.setSingleStep(0.5)
        self.stop_zscore_spin.setFixedWidth(100)
        trading_layout.addWidget(self.stop_zscore_spin, row, 1)

        row += 1
        trading_layout.addWidget(QLabel("Max Positions:"), row, 0)
        self.max_positions_spin = QSpinBox()
        self.max_positions_spin.setRange(1, 20)
        self.max_positions_spin.setValue(10)
        self.max_positions_spin.setFixedWidth(100)
        trading_layout.addWidget(self.max_positions_spin, row, 1)

        row += 1
        trading_layout.addWidget(QLabel("Volume Multiplier:"), row, 0)
        self.volume_mult_spin = QDoubleSpinBox()
        self.volume_mult_spin.setRange(0.01, 10000.0)
        self.volume_mult_spin.setValue(1.0)
        self.volume_mult_spin.setSingleStep(0.1)
        self.volume_mult_spin.setFixedWidth(100)
        trading_layout.addWidget(self.volume_mult_spin, row, 1)

        trading_group.setLayout(trading_layout)
        row1_layout.addWidget(trading_group)

        # ========== Model Parameters ==========
        model_group = QGroupBox("Model Parameters")
        model_layout = QGridLayout()

        row = 0
        model_layout.addWidget(QLabel("Rolling Window:"), row, 0)
        self.window_spin = QSpinBox()
        self.window_spin.setRange(50, 2000)
        self.window_spin.setValue(1000)
        self.window_spin.setSingleStep(10)
        self.window_spin.setFixedWidth(100)
        model_layout.addWidget(self.window_spin, row, 1)

        row += 1
        model_layout.addWidget(QLabel("Update Interval (s):"), row, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 300)
        self.interval_spin.setValue(5)
        self.interval_spin.setFixedWidth(100)
        model_layout.addWidget(self.interval_spin, row, 1)

        row += 1
        model_layout.addWidget(QLabel("Hedge Drift Threshold:"), row, 0)
        self.hedge_drift_spin = QDoubleSpinBox()
        self.hedge_drift_spin.setRange(0.01, 0.5)
        self.hedge_drift_spin.setValue(0.05)
        self.hedge_drift_spin.setSingleStep(0.01)
        self.hedge_drift_spin.setFixedWidth(100)
        model_layout.addWidget(self.hedge_drift_spin, row, 1)

        row += 1
        self.pyramiding_check = QCheckBox("Enable Pyramiding")
        self.pyramiding_check.setChecked(True)
        model_layout.addWidget(self.pyramiding_check, row, 0, 1, 2)

        row += 1
        self.hedge_adjust_check = QCheckBox("Enable Hedge Adjustment")
        self.hedge_adjust_check.setChecked(True)
        model_layout.addWidget(self.hedge_adjust_check, row, 0, 1, 2)
        
        row += 1
        self.entry_cooldown_check = QCheckBox("Enable Entry Cooldown (Z-Delta)")
        self.entry_cooldown_check.setChecked(True)
        self.entry_cooldown_check.setToolTip("Prevent duplicate entries when z-score oscillates")
        model_layout.addWidget(self.entry_cooldown_check, row, 0, 1, 2)
        
        row += 1
        self.manual_sync_check = QCheckBox("Enable Manual Position Sync")
        self.manual_sync_check.setChecked(True)
        self.manual_sync_check.setToolTip("Auto-detect and rebalance manual MT5 positions")
        model_layout.addWidget(self.manual_sync_check, row, 0, 1, 2)

        model_group.setLayout(model_layout)
        row1_layout.addWidget(model_group)

        # Add row1 to container
        container_layout.addLayout(row1_layout)

        # ========== Row 2: Risk + Advanced Settings ==========
        row2_layout = QHBoxLayout()

        # ========== Risk Management ==========
        risk_group = QGroupBox("Risk Management")
        risk_layout = QGridLayout()

        row = 0
        risk_layout.addWidget(QLabel("Max Position %:"), row, 0)
        self.max_pos_pct_spin = QDoubleSpinBox()
        self.max_pos_pct_spin.setRange(1.0, 50.0)
        self.max_pos_pct_spin.setValue(20.0)
        self.max_pos_pct_spin.setSuffix("%")
        self.max_pos_pct_spin.setFixedWidth(100)
        risk_layout.addWidget(self.max_pos_pct_spin, row, 1)

        row += 1
        risk_layout.addWidget(QLabel("Risk Per Setup:"), row, 0)
        self.max_risk_pct_spin = QDoubleSpinBox()
        self.max_risk_pct_spin.setRange(0.1, 10.0)
        self.max_risk_pct_spin.setValue(2.0)
        self.max_risk_pct_spin.setSuffix("%")
        self.max_risk_pct_spin.setFixedWidth(100)
        self.max_risk_pct_spin.setToolTip(
            "Maximum risk per trade/setup as % of balance\n"
            "Example: 2% means each trade risks max $2,000 on $100k account\n"
            "This is the risk PER INDIVIDUAL TRADE, not daily total"
        )
        risk_layout.addWidget(self.max_risk_pct_spin, row, 1)

        row += 1
        risk_layout.addWidget(QLabel("Daily Risk Limit:"), row, 0)
        self.daily_loss_spin = QDoubleSpinBox()
        self.daily_loss_spin.setRange(1.0, 20.0)
        self.daily_loss_spin.setValue(5.0)
        self.daily_loss_spin.setSuffix("%")
        self.daily_loss_spin.setDecimals(1)
        self.daily_loss_spin.setFixedWidth(100)
        self.daily_loss_spin.setToolTip(
            "Maximum total loss allowed per day as % of balance\n"
            "Example: 5% means if total daily loss reaches 5% of balance, trading stops\n"
            "On $100k account: 5% = $5,000 daily limit\n"
            "This is the TOTAL DAILY LOSS LIMIT across all trades\n"
            "Resets at session start time (default 00:00)"
        )
        risk_layout.addWidget(self.daily_loss_spin, row, 1)

        # Session Time Settings
        row += 1
        risk_layout.addWidget(QLabel("Session Start Time:"), row, 0)
        self.session_start_input = QLineEdit()
        self.session_start_input.setText("00:00")
        self.session_start_input.setPlaceholderText("HH:MM")
        self.session_start_input.setMaxLength(5)
        self.session_start_input.setFixedWidth(100)
        self.session_start_input.setToolTip("Daily P&L resets at this time (HH:MM format)")
        risk_layout.addWidget(self.session_start_input, row, 1)

        row += 1
        risk_layout.addWidget(QLabel("Session End Time:"), row, 0)
        self.session_end_input = QLineEdit()
        self.session_end_input.setText("23:59")
        self.session_end_input.setPlaceholderText("HH:MM")
        self.session_end_input.setMaxLength(5)
        self.session_end_input.setFixedWidth(100)
        self.session_end_input.setToolTip("Session end time (HH:MM format)")
        risk_layout.addWidget(self.session_end_input, row, 1)

        risk_group.setLayout(risk_layout)
        row2_layout.addWidget(risk_group)

        # Advanced Settings (Rebalancer & System Parameters)
        advanced_group = QGroupBox("⚙️ Advanced Settings")
        advanced_layout = QGridLayout()
        row = 0

        # Pyramiding settings
        advanced_layout.addWidget(QLabel("Scale Interval (Z-score):"), row, 0)
        self.scale_interval_spin = QDoubleSpinBox()
        self.scale_interval_spin.setRange(0.1, 2.0)
        self.scale_interval_spin.setSingleStep(0.1)
        self.scale_interval_spin.setValue(0.1)
        self.scale_interval_spin.setDecimals(1)
        self.scale_interval_spin.setFixedWidth(100)
        self.scale_interval_spin.setToolTip("Pyramiding every N z-score units")
        advanced_layout.addWidget(self.scale_interval_spin, row, 1)
        row += 1

        advanced_layout.addWidget(QLabel("Initial Position Fraction:"), row, 0)
        self.initial_fraction_spin = QDoubleSpinBox()
        self.initial_fraction_spin.setRange(0.1, 1.0)
        self.initial_fraction_spin.setSingleStep(0.05)
        self.initial_fraction_spin.setValue(0.33)
        self.initial_fraction_spin.setDecimals(2)
        self.initial_fraction_spin.setFixedWidth(100)
        self.initial_fraction_spin.setToolTip("First entry uses this fraction of total position (0.33 = 33%)")
        advanced_layout.addWidget(self.initial_fraction_spin, row, 1)
        row += 1

        advanced_layout.addWidget(QLabel("Min Adjustment Interval (sec):"), row, 0)
        self.min_adjust_interval_spin = QSpinBox()
        self.min_adjust_interval_spin.setRange(300, 14400)  # 5 min to 4 hours
        self.min_adjust_interval_spin.setSingleStep(300)
        self.min_adjust_interval_spin.setValue(3600)  # 1 hour
        self.min_adjust_interval_spin.setFixedWidth(100)
        self.min_adjust_interval_spin.setToolTip("Minimum time between hedge adjustments")
        advanced_layout.addWidget(self.min_adjust_interval_spin, row, 1)
        row += 1

        # System settings
        advanced_layout.addWidget(QLabel("Magic Number:"), row, 0)
        self.magic_number_spin = QSpinBox()
        self.magic_number_spin.setRange(100000, 999999)
        self.magic_number_spin.setSingleStep(1)
        self.magic_number_spin.setValue(234000)
        self.magic_number_spin.setFixedWidth(100)
        self.magic_number_spin.setToolTip("MT5 Magic Number for trade identification")
        advanced_layout.addWidget(self.magic_number_spin, row, 1)
        row += 1

        advanced_layout.addWidget(QLabel("Z-Score History Size:"), row, 0)
        self.zscore_history_spin = QSpinBox()
        self.zscore_history_spin.setRange(50, 1000)
        self.zscore_history_spin.setSingleStep(50)
        self.zscore_history_spin.setValue(200)
        self.zscore_history_spin.setFixedWidth(100)
        self.zscore_history_spin.setToolTip("Number of z-score values to keep in history")
        advanced_layout.addWidget(self.zscore_history_spin, row, 1)
        row += 1

        advanced_group.setLayout(advanced_layout)
        row2_layout.addWidget(advanced_group)

        # Add row2 to container
        container_layout.addLayout(row2_layout)

        # Add stretch to push everything to top
        container_layout.addStretch()

        # Set container to scroll area
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Buttons
        button_layout = QHBoxLayout()

        save_btn = QPushButton("💾 Save Settings")
        save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(save_btn)

        apply_btn = QPushButton("✅ Apply to Current Pair")
        apply_btn.clicked.connect(self.apply_settings)
        button_layout.addWidget(apply_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        return tab

    def create_logs_tab(self):
        """Create logs viewing tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Log controls
        controls = QHBoxLayout()

        clear_btn = QPushButton("🗑️ Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        controls.addWidget(clear_btn)

        controls.addStretch()

        layout.addLayout(controls)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier New", 9))
        layout.addWidget(self.log_display)

        return tab

    def _on_gui_setting_changed(self):
        """Called when any GUI setting changes - update sync indicator"""
        if self.trading_thread and self.trading_thread.isRunning():
            gui_config = self._get_current_gui_config()
            self.config_sync_manager.update_gui_config(gui_config)

    def on_symbol_changed(self):
        """
        Handle symbol input change
        With simplified config, we just show what symbols are entered
        Settings are global, not per-pair!
        """
        primary = self.primary_input.text().strip()
        secondary = self.secondary_input.text().strip()

        if primary and secondary and primary != secondary:
            self.statusBar.showMessage(f"Ready to trade: {primary}/{secondary}")
            self.add_log(f"📊 Symbols: {primary} / {secondary}")
            self.add_log(f"   Global settings will be applied")
        elif primary == secondary:
            self.statusBar.showMessage("Error: Primary and secondary must be different")
        else:
            self.statusBar.showMessage("Enter both symbols to begin")

    def load_pair_settings(self, pair: PairConfig):
        """Load pair configuration into GUI"""
        self.current_pair = pair

        # Update displays
        self.entry_threshold_label.setText(f"{pair.entry_threshold:.1f}")
        self.exit_threshold_label.setText(f"{pair.exit_threshold:.1f}")
        self.window_size_label.setText(f"{pair.rolling_window_size}")

        # Update new labels
        self.scalp_interval_label.setText(f"{getattr(pair, 'scale_interval', 0.5):.1f}")
        self.volume_multiplier_label.setText(f"{pair.volume_multiplier:.2f}")

        # Update spinboxes
        self.entry_zscore_spin.setValue(pair.entry_threshold)
        self.exit_zscore_spin.setValue(pair.exit_threshold)
        self.stop_zscore_spin.setValue(pair.stop_loss_zscore)
        self.max_positions_spin.setValue(pair.max_positions)
        self.volume_mult_spin.setValue(pair.volume_multiplier)

        self.window_spin.setValue(pair.rolling_window_size)
        self.interval_spin.setValue(pair.update_interval)
        self.hedge_drift_spin.setValue(pair.hedge_drift_threshold)

        self.pyramiding_check.setChecked(pair.enable_pyramiding)
        self.hedge_adjust_check.setChecked(pair.enable_hedge_adjustment)
        self.entry_cooldown_check.setChecked(getattr(pair, 'enable_entry_cooldown', True))
        self.manual_sync_check.setChecked(getattr(pair, 'enable_manual_position_sync', True))

        self.max_pos_pct_spin.setValue(pair.max_position_pct)
        self.max_risk_pct_spin.setValue(pair.max_risk_pct)
        self.daily_loss_spin.setValue(getattr(pair, 'daily_loss_limit_pct', pair.daily_loss_limit))

        # Load advanced settings (with defaults if not present)
        self.scale_interval_spin.setValue(getattr(pair, 'scale_interval', 0.5))
        self.initial_fraction_spin.setValue(getattr(pair, 'initial_fraction', 0.33))
        self.min_adjust_interval_spin.setValue(getattr(pair, 'min_adjustment_interval', 3600))
        self.magic_number_spin.setValue(getattr(pair, 'magic_number', 234000))
        self.zscore_history_spin.setValue(getattr(pair, 'zscore_history_size', 200))

    def analyze_pair(self):
        """Analyze selected pair for cointegration"""
        primary = self.primary_input.text().strip()
        secondary = self.secondary_input.text().strip()

        if not primary or not secondary:
            QMessageBox.warning(self, "Invalid Selection", "Please enter both symbols!")
            return

        if primary == secondary:
            QMessageBox.warning(self, "Invalid Selection", "Please enter different symbols!")
            return

        # Log analysis
        self.add_log("=" * 70)
        self.add_log(f"🔍 ANALYZING PAIR: {primary} / {secondary}")
        self.add_log("=" * 70)

        # Load symbols from MT5 using SymbolLoader
        try:
            symbols = self.symbol_loader.load_pair(primary, secondary)

            self.add_log(f"📊 {primary}:")
            self.add_log(f"   Contract Size: {symbols['primary']['contract_size']}")
            self.add_log(f"   Min Lot: {symbols['primary']['min_lot']}")
            self.add_log(f"   Lot Step: {symbols['primary']['lot_step']}")
            self.add_log("")
            self.add_log(f"📊 {secondary}:")
            self.add_log(f"   Contract Size: {symbols['secondary']['contract_size']}")
            self.add_log(f"   Min Lot: {symbols['secondary']['min_lot']}")
            self.add_log(f"   Lot Step: {symbols['secondary']['lot_step']}")
            self.add_log("")

        except Exception as e:
            self.add_log(f"❌ Error loading symbols: {e}")
            self.add_log(f"   Check:")
            self.add_log(f"   1. MT5 is running and logged in")
            self.add_log(f"   2. Symbol names are correct")
            self.add_log(f"   3. Symbols are in Market Watch")
            self.add_log("")
            QMessageBox.critical(self, "Symbol Error",
                                 f"Could not load symbols:\n\n{e}")
            return

        # Show global settings info
        settings = self.settings_manager.get()
        self.add_log(f"⚙️  Global Settings (apply to ALL pairs):")
        self.add_log(f"   Entry: {settings.entry_threshold}, Exit: {settings.exit_threshold}")
        self.add_log(f"   Volume: {settings.volume_multiplier}x, Window: {settings.rolling_window_size}")
        self.add_log(f"   Max Positions: {settings.max_positions}, Risk: {settings.max_risk_pct}%")

        self.add_log("=" * 70)
        self.add_log(f"✅ Pair {primary}/{secondary} is ready for trading!")
        self.add_log(f"   Adjust settings in Settings tab if needed")
        self.add_log(f"   Then click 'Start Trading' to begin")
        self.add_log("=" * 70)

        self.statusBar.showMessage(f"Analysis complete: {primary}/{secondary}")

        # Show summary in message box
        msg = f"Pair Analysis: {primary} / {secondary}\n\n"
        msg += f"{primary}: Contract={symbols['primary']['contract_size']}\n"
        msg += f"{secondary}: Contract={symbols['secondary']['contract_size']}\n\n"
        msg += "Ready to trade!\n"
        msg += "Click 'Start Trading' when ready."

        QMessageBox.information(self, "Pair Analysis", msg)

    def toggle_trading(self):
        """Start or stop trading"""

        # CRITICAL: Check if thread exists and is running
        if self.trading_thread is not None and self.trading_thread.isRunning():
            # ========== STOP TRADING (NON-BLOCKING) ==========
            self.add_log("=" * 70)
            self.add_log("⏸️ STOPPING TRADING SYSTEM")
            self.add_log("=" * 70)

            # Disable stop button while stopping
            self.start_stop_btn.setEnabled(False)
            self.start_stop_btn.setText("⏸️ Stopping...")
            self.statusBar.showMessage("Stopping trading system...")

            # Create and start stop thread (non-blocking!)
            self.stop_thread = StopThread(self.trading_thread)
            self.stop_thread.log_message.connect(self.add_log)
            self.stop_thread.finished_signal.connect(self._on_stop_finished)
            self.stop_thread.start()



            return  # Done - stop happens in background!

        # ========== START TRADING ==========
        # Clean up any dead threads first
        if self.trading_thread is not None:
            self.trading_thread = None

        primary = self.primary_input.text().strip()
        secondary = self.secondary_input.text().strip()

        if not primary or not secondary or primary == secondary:
            QMessageBox.warning(self, "Invalid Selection",
                                "Please enter valid, different symbols!")
            return

        # CRITICAL: Safety check - if symbols different from last run
        # This can happen if user somehow changes inputs while running (shouldn't be possible)
        # or if there's a UI bug
        if hasattr(self, '_last_symbols') and self._last_symbols:
            last_primary, last_secondary = self._last_symbols
            if (primary != last_primary or secondary != last_secondary):
                self.add_log("=" * 70)
                self.add_log(f"⚠️  SYMBOL CHANGE DETECTED!")
                self.add_log(f"   Previous: {last_primary}/{last_secondary}")
                self.add_log(f"   New: {primary}/{secondary}")
                self.add_log(f"   Starting with NEW symbols...")
                self.add_log("=" * 70)

        # Store current symbols for next time
        self._last_symbols = (primary, secondary)

        # ========== SYMBOL VALIDATION (NEW) ==========
        self.add_log("=" * 70)
        self.add_log("🚀 STARTING TRADING SYSTEM")
        self.add_log("=" * 70)
        self.add_log(f"📊 Selected Pair: {primary} / {secondary}")
        self.add_log("🔍 Validating symbols in MT5...")

        # Validate symbols before proceeding
        is_valid, error_msg, pair_info = SymbolValidator.validate_pair(primary, secondary)

        if not is_valid:
            self.add_log(f"❌ Symbol validation failed!")
            self.add_log(f"   {error_msg}")
            QMessageBox.critical(self, "Symbol Validation Failed",
                                 f"Could not validate trading pair:\n\n{error_msg}\n\n"
                                 "Please check:\n"
                                 "1. MT5 is running and logged in\n"
                                 "2. Symbol names are correct (case-sensitive)\n"
                                 "3. Symbols are added to Market Watch\n"
                                 "4. Market is open")
            return

        # Show validation success with details
        self.add_log(f"✅ Symbol validation passed!")
        self.add_log(f"   {primary}: bid={pair_info['primary']['bid']:.5f}, spread={pair_info['primary']['spread']}")
        self.add_log(f"   {secondary}: bid={pair_info['secondary']['bid']:.5f}, spread={pair_info['secondary']['spread']}")

        # Load full symbol info
        self.add_log("🔄 Loading symbol specifications...")
        try:
            symbols = self.symbol_loader.load_pair(primary, secondary)
            self.add_log(
                f"✅ {primary}: contract_size={symbols['primary']['contract_size']}, min_lot={symbols['primary']['min_lot']}")
            self.add_log(
                f"✅ {secondary}: contract_size={symbols['secondary']['contract_size']}, min_lot={symbols['secondary']['min_lot']}")
        except Exception as e:
            self.add_log(f"❌ Failed to load symbols: {e}")
            QMessageBox.critical(self, "Symbol Error",
                                 f"Could not load symbols from MT5:\n\n{e}\n\n"
                                 "Please check:\n"
                                 "1. MT5 is running and logged in\n"
                                 "2. Symbol names are correct\n"
                                 "3. Symbols are in Market Watch")
            return

        # Get global settings
        settings = self.settings_manager.get()
        self.add_log(f"⚙️  Global Settings:")
        self.add_log(f"   Entry: {settings.entry_threshold}, Exit: {settings.exit_threshold}")
        self.add_log(f"   Volume: {settings.volume_multiplier}x, Window: {settings.rolling_window_size}")
        self.add_log(f"   Max Positions: {settings.max_positions}, Risk: {settings.max_risk_pct}%")
        self.add_log("=" * 70)

        # Update dashboard displays with NEW symbols
        self.add_log(f"🔄 Updating dashboard for {primary}/{secondary}...")
        # You can add dashboard update here if needed

        # Create trading config (combine symbols + settings)
        trading_config = {
            'symbols': symbols,
            'settings': settings.to_dict(),
            'primary_symbol': primary,
            'secondary_symbol': secondary
        }

        # Create and start trading thread (with risk alert handler!)
        self.trading_thread = TradingSystemThread(trading_config, self.risk_alert_handler)
        self.trading_thread.log_message.connect(self.add_log)
        self.trading_thread.snapshot_update.connect(self.on_snapshot_update)  # ← NEW: Chart updates
        self.trading_thread.finished.connect(self._on_thread_finished)  # Handle cleanup
        self.trading_thread.start()

        # Auto-save config after successful start (không cần hỏi!)
        self.add_log("")
        self.add_log("💾 Auto-saving configuration...")
        try:
            # Update settings from current GUI values
            self.settings_manager.update(
                entry_threshold=self.entry_zscore_spin.value(),
                exit_threshold=self.exit_zscore_spin.value(),
                stop_loss_zscore=self.stop_zscore_spin.value(),
                max_positions=self.max_positions_spin.value(),
                volume_multiplier=self.volume_mult_spin.value(),
                rolling_window_size=self.window_spin.value(),
                update_interval=self.interval_spin.value(),
                hedge_drift_threshold=self.hedge_drift_spin.value(),
                max_position_pct=self.max_pos_pct_spin.value(),
                max_risk_pct=self.max_risk_pct_spin.value(),
                daily_loss_limit_pct=self.daily_loss_spin.value(),
                session_start_time=self.session_start_input.text(),
                session_end_time=self.session_end_input.text(),
                scale_interval=self.scale_interval_spin.value(),
                initial_fraction=self.initial_fraction_spin.value(),
                min_adjustment_interval=self.min_adjust_interval_spin.value(),
                magic_number=self.magic_number_spin.value(),
                zscore_history_size=self.zscore_history_spin.value(),
                enable_pyramiding=self.pyramiding_check.isChecked(),
                enable_hedge_adjustment=self.hedge_adjust_check.isChecked(),
                enable_entry_cooldown=self.entry_cooldown_check.isChecked(),
                enable_manual_position_sync=self.manual_sync_check.isChecked()
            )
            self.settings_manager.save()
            self.add_log("✅ Configuration auto-saved for next time")
        except Exception as e:
            self.add_log(f"⚠️  Failed to auto-save config: {e}")

        self.add_log("=" * 70)

        # Update UI to RUNNING state
        self.start_stop_btn.setText("⏸️ Stop Trading")
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.status_label.setText("🟢 Running")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        self.statusBar.showMessage(f"Trading {primary}/{secondary}...")

        # Disable symbol selection while running
        self.primary_input.setEnabled(False)
        self.secondary_input.setEnabled(False)
        # self.analyze_btn.setEnabled(False)  # Button removed

        # Load historical data into chart (after 3 seconds to let system bootstrap)
        self.load_chart_historical_data()

        # Connect ConfigSyncManager to trading system (after 2 seconds to ensure system is ready)
        QTimer.singleShot(2000, self._connect_config_sync_manager)

    def _connect_config_sync_manager(self):
        """Connect config sync manager to running trading system"""
        if self.trading_thread and self.trading_thread.trading_system:
            self.config_sync_manager.set_trading_system(self.trading_thread.trading_system)
            self.config_sync_indicator.set_running(True)
            self.add_log("🔄 Config sync manager connected to trading system")

    def _on_config_sync_changed(self, out_of_sync: bool):
        """Handle config sync status change"""
        if out_of_sync:
            diff = self.config_sync_manager.get_current_diff()
            if diff:
                self.config_sync_indicator.set_synced(False, diff.change_count, diff.get_summary())
        else:
            self.config_sync_indicator.set_synced(True)

    def _on_config_applied(self):
        """Handle config applied event"""
        self.config_sync_indicator.set_synced(True)
        self.add_log("✅ Config changes applied successfully")

    def _on_sync_apply_clicked(self):
        """Handle click on Apply button in sync indicator - Hot-reload config"""
        if not self.trading_thread or not self.trading_thread.isRunning():
            QMessageBox.warning(self, "Not Running",
                                "Trading system is not running. Start trading first!")
            return

        # Get current GUI config
        gui_config = self._get_current_gui_config()

        # Check for restart-required changes
        diff = self.config_sync_manager.get_current_diff()
        if diff and diff.has_restart_required_changes:
            restart_params = [c.key for c in diff.changes
                              if c.change_type.value == 'requires_restart']
            reply = QMessageBox.question(
                self, "Restart Required",
                f"The following changes require a restart:\n\n"
                f"{', '.join(restart_params)}\n\n"
                "Restart trading system now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.add_log("🔄 Restarting for config changes requiring restart...")
                self.toggle_trading()  # Stop
                QTimer.singleShot(1500, self.toggle_trading)  # Start after delay
            return

        # Apply hot-reload changes
        self.add_log("=" * 70)
        self.add_log("🔄 HOT-RELOAD: Applying config changes...")

        success, applied = self.config_sync_manager.apply_hot_reload(gui_config)

        if success:
            self.add_log(f"   Applied {len(applied)} changes:")
            for change in applied[:10]:  # Show first 10
                self.add_log(f"      • {change}")
            if len(applied) > 10:
                self.add_log(f"      ... and {len(applied) - 10} more")
            self.add_log("=" * 70)
            QMessageBox.information(self, "Config Applied",
                                    f"Successfully applied {len(applied)} changes!\n\n"
                                    "New settings are now active.")
        else:
            self.add_log(f"❌ Failed to apply changes: {applied}")
            self.add_log("=" * 70)
            QMessageBox.warning(self, "Apply Failed",
                                f"Failed to apply changes:\n\n{applied[0] if applied else 'Unknown error'}")

    def _on_sync_details_clicked(self):
        """Show details of config differences"""
        diff = self.config_sync_manager.get_current_diff()

        if not diff or not diff.has_changes:
            QMessageBox.information(self, "Config Sync",
                                    "GUI settings match running system.\n\n"
                                    "No changes to apply.")
            return

        # Build details message
        msg = f"📝 {diff.change_count} difference(s) detected:\n\n"

        for change in diff.changes:
            icon = "🔄" if change.change_type.value == 'hot_reload' else "⚠️"
            msg += f"{icon} {change.key}:\n"
            msg += f"    Running: {change.old_value}\n"
            msg += f"    GUI: {change.new_value}\n\n"

        if diff.has_restart_required_changes:
            msg += "⚠️ Some changes require a restart.\n"

        msg += "\nClick 'Apply' to sync changes to running system."

        QMessageBox.information(self, "Config Differences", msg)

    def _get_current_gui_config(self) -> dict:
        """Get current config values from GUI controls"""
        return {
            'entry_threshold': self.entry_zscore_spin.value(),
            'exit_threshold': self.exit_zscore_spin.value(),
            'stop_loss_zscore': self.stop_zscore_spin.value(),
            'max_positions': self.max_positions_spin.value(),
            'volume_multiplier': self.volume_mult_spin.value(),
            'rolling_window_size': self.window_spin.value(),
            'update_interval': self.interval_spin.value(),
            'hedge_drift_threshold': self.hedge_drift_spin.value(),
            'max_position_pct': self.max_pos_pct_spin.value(),
            'max_risk_pct': self.max_risk_pct_spin.value(),
            'daily_loss_limit_pct': self.daily_loss_spin.value(),
            'session_start_time': self.session_start_input.text(),
            'session_end_time': self.session_end_input.text(),
            'scale_interval': self.scale_interval_spin.value(),
            'initial_fraction': self.initial_fraction_spin.value(),
            'min_adjustment_interval': self.min_adjust_interval_spin.value(),
            'magic_number': self.magic_number_spin.value(),
            'zscore_history_size': self.zscore_history_spin.value(),
            'enable_pyramiding': self.pyramiding_check.isChecked(),
            'enable_hedge_adjustment': self.hedge_adjust_check.isChecked(),
            'enable_entry_cooldown': self.entry_cooldown_check.isChecked(),
            'enable_manual_position_sync': self.manual_sync_check.isChecked(),
            'primary_symbol': self.primary_input.text().strip(),
            'secondary_symbol': self.secondary_input.text().strip()
        }

    def _on_thread_finished(self):
        """Handle thread finished signal"""
        self.add_log("📍 Trading thread has finished")

        # If button still shows "Stop", update it
        if self.start_stop_btn.text() == "⏸️ Stop Trading":
            self.start_stop_btn.setText("▶️ Start Trading")
            self.start_stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    font-weight: bold;
                    padding: 10px;
                    border-radius: 4px;
                    min-width: 150px;
                }
                QPushButton:hover {
                    background-color: #2ecc71;
                }
            """)
            self.status_label.setText("⚫ Stopped")
            self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")

            # Re-enable controls
            self.primary_input.setEnabled(True)
            self.secondary_input.setEnabled(True)
            # self.analyze_btn.setEnabled(True)  # Button removed

    def _on_stop_finished(self, graceful: bool):
        """Called when stop thread finishes (non-blocking!)"""
        # Log result
        if graceful:
            self.add_log("✅ Trading system stopped gracefully")
        else:
            self.add_log("⚠️  Trading system force stopped")
        self.add_log("=" * 70)

        # Disconnect config sync manager
        self.config_sync_manager.clear_trading_system()
        self.config_sync_indicator.set_running(False)

        # Clear thread reference
        self.trading_thread = None

        # Update UI to STOPPED state
        self.start_stop_btn.setEnabled(True)
        self.start_stop_btn.setText("▶️ Start Trading")
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.status_label.setText("⚫ Stopped")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")
        self.statusBar.showMessage("Trading system stopped")

        # Re-enable symbol selection
        self.primary_input.setEnabled(True)
        self.secondary_input.setEnabled(True)

        # Stop chart updates
        if hasattr(self, 'chart_widget'):
            self.chart_widget.stop_auto_update()

    def on_snapshot_update(self, snapshot):
        """Handle new market snapshot for chart updates"""
        if hasattr(self, 'chart_widget') and snapshot:
            self.chart_widget.add_realtime_data(snapshot)

    def load_chart_historical_data(self):
        """Load historical data into chart when trading starts"""
        if hasattr(self, 'chart_widget') and hasattr(self, 'trading_thread'):
            if self.trading_thread and self.trading_thread.trading_system:
                # Wait a bit for trading system to bootstrap
                QTimer.singleShot(3000, lambda: self._do_load_chart_data())

    def _do_load_chart_data(self):
        """Actually load the chart data"""
        if hasattr(self, 'trading_thread') and self.trading_thread and self.trading_thread.trading_system:
            self.chart_widget.load_historical_data(self.trading_thread.trading_system)
            self.chart_widget.start_auto_update()



    def update_display(self):
        """Update all displays with current data using presentation layer"""
        if not self.trading_thread or not self.trading_thread.isRunning():
            return

        try:
            # Get raw status from trading system
            raw_status = self.trading_thread.get_status()

            if raw_status:
                # Transform raw data into presentation format using presenter
                data = self.presenter.present_status(raw_status)

                # ========== LIVE STATISTICS ==========
                self.z_score_label.setText(data['z_score_value'])
                self.z_score_label.setStyleSheet(data['z_score_style'])

                self.correlation_label.setText(data['correlation_value'])
                self.hedge_ratio_label.setText(data['hedge_ratio_value'])

                self.signal_label.setText(data['signal_value'])
                self.signal_label.setStyleSheet(data['signal_style'])

                # ========== MODEL METRICS ==========
                self.entry_threshold_label.setText(data['entry_threshold_value'])
                self.exit_threshold_label.setText(data['exit_threshold_value'])
                self.window_size_label.setText(data['window_size_value'])

                self.spread_mean_label.setText(data['spread_mean_value'])
                self.spread_std_label.setText(data['spread_std_value'])

                self.mean_drift_label.setText(data['mean_drift_value'])
                self.mean_drift_label.setStyleSheet(data['mean_drift_style'])

                self.max_z_score_label.setText(data['max_z_score_value'])
                self.min_z_score_label.setText(data['min_z_score_value'])

                self.max_mean_label.setText(data['max_mean_value'])
                self.min_mean_label.setText(data['min_mean_value'])

                self.last_update_label.setText(data['last_update_value'])

                self.status_label.setText(data['status_value'])
                self.status_label.setStyleSheet(data['status_style'])

                self.last_z_score_entries_label.setText(data['last_z_score_entries_value'])
                self.next_z_score_entries_label.setText(data['next_z_score_entries_value'])

                self.scalp_interval_label.setText(data['scalp_interval_value'])
                self.volume_multiplier_label.setText(data['volume_multiplier_value'])

                # ========== ACCOUNT STATUS ==========
                self.balance_label.setText(data['balance_value'])
                self.equity_label.setText(data['equity_value'])

                self.unrealized_pnl_label.setText(data['unrealized_pnl_value'])
                self.unrealized_pnl_label.setStyleSheet(data['unrealized_pnl_style'])

                self.used_margin_label.setText(data['used_margin_value'])
                self.free_margin_label.setText(data['free_margin_value'])
                self.margin_level_label.setText(data['margin_level_value'])

                # ========== POSITION OVERVIEW ==========
                self.open_spread_label.setText(data['open_spread_value'])
                self.open_close_label.setText(data['open_close_value'])

                # Total lots (primary / secondary)
                primary_lots = data.get('primary_lots_value', '+0.0000')
                secondary_lots = data.get('secondary_lots_value', '+0.0000')
                self.total_lots_label.setText(f"{primary_lots} / {secondary_lots}")

                # Hedge metrics
                self.hedge_quality_label.setText(data['hedge_quality_value'])
                self.hedge_quality_label.setStyleSheet(data['hedge_quality_style'])
                self.imbalance_label.setText(data['imbalance_value'])
                self.imbalance_label.setStyleSheet(data['imbalance_style'])

                # ========== RISK MONITORING ==========
                self.setup_risk_pct_label.setText(data['setup_risk_pct_value'])
                self.setup_risk_amount_label.setText(data['setup_risk_amount_value'])

                self.risk_unrealized_label.setText(data['risk_unrealized_value'])
                self.risk_unrealized_label.setStyleSheet(data['risk_unrealized_style'])

                # Daily risk
                self.daily_risk_pct_label.setText(data['daily_risk_pct_value'])
                self.daily_risk_limit_label.setText(data['daily_risk_limit_value'])

                self.daily_total_pnl_label.setText(data['daily_total_pnl_value'])
                self.daily_total_pnl_label.setStyleSheet(data['daily_total_pnl_style'])

                # ========== TRADING LOCK STATUS ==========
                self.trading_status_label.setText(data['trading_status_value'])
                self.trading_status_label.setStyleSheet(data['trading_status_style'])

                self.block_time_label.setText(data['block_time_value'])
                self.unlock_time_label.setText(data['unlock_time_value'])

        except Exception as e:
            logger.error(f"Error updating display: {e}")

    def save_settings(self):
        """
        Save current settings to configuration
        These settings apply to ALL pairs!
        """
        # Update settings from GUI
        self.settings_manager.update(
            # Trading
            entry_threshold=self.entry_zscore_spin.value(),
            exit_threshold=self.exit_zscore_spin.value(),
            stop_loss_zscore=self.stop_zscore_spin.value(),
            max_positions=self.max_positions_spin.value(),
            volume_multiplier=self.volume_mult_spin.value(),

            # Model
            rolling_window_size=self.window_spin.value(),
            update_interval=self.interval_spin.value(),
            hedge_drift_threshold=self.hedge_drift_spin.value(),

            # Risk
            max_position_pct=self.max_pos_pct_spin.value(),
            max_risk_pct=self.max_risk_pct_spin.value(),
            daily_loss_limit_pct=self.daily_loss_spin.value(),
            session_start_time=self.session_start_input.text(),
            session_end_time=self.session_end_input.text(),

            # Advanced
            scale_interval=self.scale_interval_spin.value(),

            # Features
            enable_pyramiding=self.pyramiding_check.isChecked(),
            enable_hedge_adjustment=self.hedge_adjust_check.isChecked(),
            enable_entry_cooldown=self.entry_cooldown_check.isChecked(),
            enable_manual_position_sync=self.manual_sync_check.isChecked()
        )

        # Save to file
        self.settings_manager.save()

        # Update displays
        settings = self.settings_manager.get()
        self.entry_threshold_label.setText(f"{settings.entry_threshold:.1f}")
        self.exit_threshold_label.setText(f"{settings.exit_threshold:.1f}")
        self.window_size_label.setText(f"{settings.rolling_window_size}")

        # Update new labels
        self.scalp_interval_label.setText(f"{settings.scale_interval:.1f}")
        self.volume_multiplier_label.setText(f"{settings.volume_multiplier:.2f}")

        # Log details
        self.add_log(f"💾 Global settings saved!")
        self.add_log(f"   Entry: {settings.entry_threshold}, Exit: {settings.exit_threshold}")
        self.add_log(f"   Volume: {settings.volume_multiplier}x, Window: {settings.rolling_window_size}")
        self.add_log(f"   Max Positions: {settings.max_positions}, Risk: {settings.max_risk_pct}%")
        self.add_log(f"   ✅ These settings apply to ALL symbol pairs!")
        self.add_log(f"   Saved to: config/trading_settings.yaml")

        QMessageBox.information(self, "Settings Saved",
                                "Global settings saved successfully!\n\n"
                                "These settings will apply to ALL symbol pairs.\n\n"
                                "File: config/trading_settings.yaml")

    def apply_settings(self):
        """Apply current settings to running system"""
        if not self.trading_thread or not self.trading_thread.isRunning():
            QMessageBox.warning(self, "Not Running",
                                "Trading system is not running. Start trading first!")
            return

        # Get new settings from GUI
        settings = self.settings_manager.get()

        if self.trading_thread.trading_system:
            sys = self.trading_thread.trading_system

            # Check if rolling window changed (requires recalculation)
            old_window = sys.market_data.rolling_window_size
            new_window = self.window_spin.value()
            window_changed = (old_window != new_window)

            if window_changed:
                # Window size changed - need to restart and recalculate!
                reply = QMessageBox.question(
                    self,
                    "Restart Required",
                    f"Rolling window changed ({old_window} → {new_window}).\n\n"
                    "This requires stopping and restarting the system to recalculate from scratch.\n\n"
                    "Restart now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self.add_log("=" * 70)
                    self.add_log("🔄 RESTARTING SYSTEM (Rolling Window Changed)")
                    self.add_log(f"   Old Window: {old_window} → New Window: {new_window}")
                    self.add_log("=" * 70)

                    # Stop current system
                    self.toggle_trading()  # Stop

                    # Wait a bit for clean shutdown
                    import time
                    time.sleep(1)

                    # Start with new settings
                    self.toggle_trading()  # Start with new config

                    self.add_log("✅ System restarted with new rolling window")
                else:
                    self.add_log("⚠️  Rolling window change cancelled")
                return

            # Apply settings to running system (hot-reload)
            self.add_log("=" * 70)
            self.add_log("🔄 APPLYING SETTINGS (Hot-Reload)")
            self.add_log("=" * 70)

            # Signal generator
            entry = self.entry_zscore_spin.value()
            exit_val = self.exit_zscore_spin.value()
            stop = self.stop_zscore_spin.value()
            sys.signal_generator.entry_threshold = entry
            sys.signal_generator.exit_threshold = exit_val
            sys.signal_generator.stop_loss_zscore = stop
            self.add_log(f"   Entry: {entry}, Exit: {exit_val}, Stop: {stop}")

            # Rebalancer
            hedge_drift = self.hedge_drift_spin.value()
            enable_hedge = self.hedge_adjust_check.isChecked()
            sys.rebalancer.hedge_drift_threshold = hedge_drift
            sys.rebalancer.enable_hedge_adjustment = enable_hedge
            self.add_log(f"   Hedge Drift: {hedge_drift}, Adjustment: {enable_hedge}")

            # Risk settings
            if hasattr(sys, 'position_sizer'):
                max_pos = self.max_pos_pct_spin.value()
                max_risk = self.max_risk_pct_spin.value()
                sys.position_sizer.max_position_pct = max_pos
                sys.position_sizer.max_risk_pct = max_risk
                self.add_log(f"   Position: {max_pos}%, Risk: {max_risk}%")

            # Volume multiplier (affects future trades)
            vol_mult = self.volume_mult_spin.value()
            sys.volume_multiplier = vol_mult
            self.add_log(f"   Volume Multiplier: {vol_mult}x")

            # Scale interval - update rebalancer, executor, and recalculate next_z_entry
            scale_interval = self.scale_interval_spin.value()

            # Update rebalancer first (source of truth for many components)
            if hasattr(sys, 'rebalancer'):
                sys.rebalancer.scale_interval = scale_interval

            # Update unified executor and recalculate next_z_entry for active spreads
            if hasattr(sys, 'unified_executor') and hasattr(sys.unified_executor, 'update_scale_interval'):
                sys.unified_executor.update_scale_interval(scale_interval)
                self.add_log(f"   Scale Interval: {scale_interval} (rebalancer + executor updated, next_z recalculated)")
            else:
                self.add_log(f"   Scale Interval: {scale_interval}")

            # Update ALL settings in config (for backend/presenter sync)
            if hasattr(sys, 'config'):
                # Trading thresholds
                sys.config['entry_threshold'] = entry
                sys.config['exit_threshold'] = exit_val
                sys.config['stop_loss_zscore'] = stop

                # Risk settings
                sys.config['max_position_pct'] = max_pos
                sys.config['max_risk_pct'] = max_risk
                sys.config['daily_loss_limit_pct'] = self.daily_loss_spin.value()

                # Model settings
                sys.config['rolling_window_size'] = new_window
                sys.config['hedge_drift_threshold'] = hedge_drift

                # Volume and scaling
                sys.config['volume_multiplier'] = vol_mult
                sys.config['scale_interval'] = scale_interval

                # Max positions
                sys.config['max_positions'] = self.max_positions_spin.value()

                self.add_log(f"   ✓ All settings synced to backend config")
                self.add_log(f"      Entry/Exit: {entry}/{exit_val}, Stop: {stop}")
                self.add_log(f"      Max Pos: {max_pos}%, Risk: {max_risk}%")
                self.add_log(f"      Daily Limit: {sys.config['daily_loss_limit_pct']}%")
                self.add_log(f"      Volume: {vol_mult}x, Scale: {scale_interval}")

            # Update display labels
            self.entry_threshold_label.setText(f"{entry:.1f}")
            self.exit_threshold_label.setText(f"{exit_val:.1f}")
            self.window_size_label.setText(f"{new_window}")
            self.scalp_interval_label.setText(f"{scale_interval:.1f}")
            self.volume_multiplier_label.setText(f"{vol_mult:.2f}")

            self.add_log("=" * 70)
            self.add_log("✅ Settings applied to running system")
            self.add_log("=" * 70)

            QMessageBox.information(self, "Settings Applied",
                                    "Settings have been applied!\n\n"
                                    "New trades will use updated parameters.")

    def add_log(self, message: str):
        """Add message to log display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")

        # Auto-scroll to bottom
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_logs(self):
        """Clear all logs"""
        self.log_display.clear()
        self.add_log("Logs cleared")

    def closeEvent(self, event):
        """Handle window close event - ALWAYS stop trading thread"""
        if self.trading_thread and self.trading_thread.isRunning():
            reply = QMessageBox.question(self, "Confirm Exit",
                                         "Trading system is running. Stop and exit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                self.add_log("🛑 Stopping trading system before exit...")
                self.trading_thread.stop()

                # Wait up to 10 seconds for graceful stop
                if not self.trading_thread.wait(10000):
                    self.add_log("⚠️  Force terminating thread...")
                    self.trading_thread.terminate()
                    self.trading_thread.wait(2000)

                self.add_log("✅ Trading system stopped - safe to exit")
                event.accept()
            else:
                # User chose not to exit
                event.ignore()
        else:
            # No trading thread running - safe to exit
            event.accept()


def main():
    """Main entry point"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = QApplication(sys.argv)

    # Set application info
    app.setApplicationName("Pair Trading System - Professional")
    app.setOrganizationName("Professional Trading")

    # Create and show window
    window = PairTradingGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
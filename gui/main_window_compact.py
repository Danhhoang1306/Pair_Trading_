"""
Professional Pair Trading GUI - Compact Version
Refactored to use separate display and settings panels
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QMessageBox, QStatusBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont
from datetime import datetime
import logging

# Import theme
from asset.theme import DARCULA_THEME_QSS

# Import configuration
from config.trading_settings import TradingSettingsManager, SymbolLoader

# Import new modular panels
from gui.settings_panel import SettingsPanel
from gui.display_panel import DisplayPanel

# Import pair discovery tab
from gui.pair_discovery_tab import PairDiscoveryTab

# Import risk alert handler
from gui.risk_alert_handler import RiskAlertHandler

# Import trading system
from core.trading_system import TradingSystem

logger = logging.getLogger(__name__)


class StopThread(QThread):
    """Thread to stop trading system without blocking GUI"""

    finished_signal = pyqtSignal(bool)
    log_message = pyqtSignal(str)

    def __init__(self, trading_thread):
        super().__init__()
        self.trading_thread = trading_thread

    def run(self):
        """Stop trading system in background"""
        try:
            self.log_message.emit("   Stop signal sent to thread...")
            self.trading_thread.stop()

            stopped = self.trading_thread.wait(10000)

            if not stopped:
                self.log_message.emit("⚠️  Thread did not stop in 10 seconds, force terminating...")
                self.trading_thread.terminate()
                self.trading_thread.wait(2000)
                self.log_message.emit("   Thread terminated forcefully")
                self.finished_signal.emit(False)
            else:
                self.log_message.emit("   Thread stopped gracefully")
                self.finished_signal.emit(True)

        except Exception as e:
            self.log_message.emit(f"❌ Error stopping: {e}")
            self.finished_signal.emit(False)


class TradingSystemThread(QThread):
    """Thread to run trading system without blocking GUI"""

    status_update = pyqtSignal(dict)
    position_update = pyqtSignal(list)
    log_message = pyqtSignal(str)
    snapshot_update = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, trading_config: dict, risk_alert_handler=None):
        super().__init__()
        self.trading_config = trading_config
        self.trading_system = None
        self.running = False
        self.risk_alert_handler = risk_alert_handler

    def run(self):
        """Run the trading system"""
        self.running = True

        try:
            self.log_message.emit("🔧 Initializing Trading System...")

            # Create trading system instance
            self.trading_system = TradingSystem(
                symbol_primary=self.trading_config['primary_symbol'],
                symbol_secondary=self.trading_config['secondary_symbol'],
                **self.trading_config['settings']
            )

            # Connect risk alert handler if provided
            if self.risk_alert_handler:
                self.trading_system.risk_manager.alert_callback = self.risk_alert_handler.handle_alert

            self.log_message.emit("✅ Trading System initialized")
            self.log_message.emit("🔄 Starting main trading loop...")
            self.log_message.emit("")

            # Run trading system
            self.trading_system.run()

        except Exception as e:
            logger.exception("Trading system error")
            self.error_occurred.emit(str(e))
            self.log_message.emit(f"❌ Trading system error: {e}")

        finally:
            self.running = False
            self.log_message.emit("")
            self.log_message.emit("=" * 70)
            self.log_message.emit("✅ Trading system stopped")
            self.log_message.emit("=" * 70)

    def stop(self):
        """Stop the trading system gracefully"""
        self.running = False
        if self.trading_system:
            self.trading_system.stop()


class PairTradingGUI(QMainWindow):
    """Main GUI Window - Compact Version with Modular Panels"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pair Trading System - Professional Edition")
        self.setGeometry(100, 100, 1000, 800)

        # Apply theme
        self.setStyleSheet(DARCULA_THEME_QSS)

        # Initialize state
        self.trading_thread = None
        self.stop_thread = None

        # Settings and symbol loader
        self.settings_manager = TradingSettingsManager()
        self.symbol_loader = SymbolLoader()

        # Risk alert handler
        self.risk_alert_handler = RiskAlertHandler(self)

        # Create UI
        self.init_ui()

        # Setup update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)

        # Load initial state
        self.load_initial_state()

        # Startup message
        self.show_startup_message()

    def init_ui(self):
        """Initialize the user interface"""
        # Create panels first (before tabs)
        self.settings_panel = SettingsPanel(self.settings_manager)
        self.display_panel = DisplayPanel()

        # Connect signals
        self.settings_panel.settings_saved.connect(self.on_settings_saved)
        self.settings_panel.settings_applied.connect(self.on_settings_applied)
        self.settings_panel.symbol_changed.connect(self.on_symbol_changed)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 10))

        # ========== DASHBOARD TAB (ALL-IN-ONE) ==========
        # Combine symbol selection + display in one tab
        dashboard_tab = self.create_dashboard_tab()
        self.tabs.addTab(dashboard_tab, "📊 Dashboard")

        # ========== CHARTS TAB ==========
        self.chart_widget = self.display_panel.chart_widget
        self.tabs.addTab(self.chart_widget, "📈 Charts")

        # ========== PAIR DISCOVERY TAB ==========
        self.discovery_tab = PairDiscoveryTab()
        self.tabs.addTab(self.discovery_tab, "🔬 Pair Discovery")

        # ========== SETTINGS TAB ==========
        self.tabs.addTab(self.settings_panel, "⚙️ Settings")

        # ========== LOGS TAB ==========
        self.logs_widget = self.display_panel.logs_widget
        self.tabs.addTab(self.logs_widget, "📝 Logs")

        main_layout.addWidget(self.tabs)

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready - Select pair and start trading")

    def create_dashboard_tab(self):
        """Create dashboard tab - combines symbol selection + display panels"""
        from PyQt6.QtWidgets import QGroupBox, QLineEdit, QPushButton

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ========== Top Control Panel ==========
        control_panel = QGroupBox("Control Panel")
        control_layout = QHBoxLayout()

        # Symbol selection
        symbol_group = QGroupBox("Symbol Selection")
        symbol_layout = QGridLayout()

        symbol_layout.addWidget(QLabel("Primary Symbol:"), 0, 0)
        self.primary_input = QLineEdit()
        self.primary_input.setPlaceholderText("e.g., BTCUSD, XAUUSD")
        self.primary_input.setMinimumWidth(150)
        self.primary_input.setText("BTCUSD")
        self.primary_input.textChanged.connect(self._on_symbol_input_changed)
        symbol_layout.addWidget(self.primary_input, 0, 1)

        symbol_layout.addWidget(QLabel("Secondary Symbol:"), 1, 0)
        self.secondary_input = QLineEdit()
        self.secondary_input.setPlaceholderText("e.g., ETHUSD, XAGUSD")
        self.secondary_input.setMinimumWidth(150)
        self.secondary_input.setText("ETHUSD")
        self.secondary_input.textChanged.connect(self._on_symbol_input_changed)
        symbol_layout.addWidget(self.secondary_input, 1, 1)

        # Start/Stop button
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

        # Add live statistics from display panel
        control_layout.addWidget(self.display_panel.dashboard_widget._create_control_panel().findChildren(QGroupBox)[1])  # Get Live Statistics group

        control_panel.setLayout(control_layout)
        layout.addWidget(control_panel)

        # Add all display panels from DisplayPanel's dashboard
        dashboard_widget = self.display_panel.dashboard_widget
        layout.addWidget(dashboard_widget._create_metrics_panel())
        layout.addWidget(dashboard_widget._create_account_risk_panel())
        layout.addWidget(dashboard_widget._create_attribution_panel())

        return tab

    def _on_symbol_input_changed(self):
        """Handle symbol input change in dashboard"""
        primary = self.primary_input.text().strip().upper()
        secondary = self.secondary_input.text().strip().upper()

        # Update settings panel too
        self.settings_panel.set_symbols(primary, secondary)

        if primary and secondary and primary != secondary:
            self.statusBar.showMessage(f"Ready to trade: {primary}/{secondary}")
            self.add_log(f"📊 Symbols: {primary} / {secondary}")

    def load_initial_state(self):
        """Load initial state from settings and MT5"""
        # Load settings into settings panel
        self.settings_panel.load_settings()

        # Load current MT5 state
        self.load_current_state_from_mt5()

    def load_current_state_from_mt5(self):
        """Load current state from MT5"""
        try:
            from core.mt5_manager import get_mt5
            mt5 = get_mt5()

            account_info = mt5.account_info()
            if account_info is None:
                logger.warning("Could not get MT5 account info")
                return

            balance = account_info.balance
            equity = account_info.equity
            profit = account_info.profit

            margin_info = {
                'used': account_info.margin,
                'free': account_info.margin_free,
                'level': account_info.margin_level if account_info.margin_level else 0
            }

            # Update display panel
            self.display_panel.update_account_info(balance, equity, profit, margin_info)

            # Update risk manager
            settings = self.settings_manager.get()
            unrealized_pnl = equity - balance

            risk_data = {
                'setup_risk_pct': settings.max_risk_pct,
                'setup_risk_amount': balance * (settings.max_risk_pct / 100.0),
                'daily_risk_pct': settings.daily_loss_limit_pct,
                'daily_risk_limit': balance * (settings.daily_loss_limit_pct / 100.0),
                'trading_status': 'READY',
                'block_time': '--',
                'unrealized': unrealized_pnl,
                'total_pnl': 0,
                'unlock_time': '--'
            }

            self.display_panel.update_risk_manager(risk_data)

        except Exception as e:
            logger.error(f"Failed to load MT5 state: {e}")

    def show_startup_message(self):
        """Show startup message in logs"""
        self.add_log("=" * 70)
        self.add_log("PAIR TRADING SYSTEM - PROFESSIONAL EDITION")
        self.add_log("=" * 70)
        self.add_log("")
        self.add_log("✅ GUI initialized successfully")
        self.add_log(f"📂 Settings loaded from: config/trading_settings.yaml")
        self.add_log(f"⚙️  Global settings apply to ALL pairs")
        self.add_log("")
        self.add_log("📋 READY TO START:")
        self.add_log("   1. Configure symbols in Settings tab")
        self.add_log("   2. Adjust parameters if needed")
        self.add_log("   3. Click 'Start Trading' in Dashboard")
        self.add_log("")
        self.add_log("=" * 70)

    def toggle_trading(self):
        """Start or stop trading"""
        if self.trading_thread is not None and self.trading_thread.isRunning():
            # ========== STOP TRADING ==========
            self.add_log("=" * 70)
            self.add_log("⏸️ STOPPING TRADING SYSTEM")
            self.add_log("=" * 70)

            btn = self.display_panel.get_start_stop_button()
            btn.setEnabled(False)
            btn.setText("⏸️ Stopping...")
            self.statusBar.showMessage("Stopping trading system...")

            self.stop_thread = StopThread(self.trading_thread)
            self.stop_thread.log_message.connect(self.add_log)
            self.stop_thread.finished_signal.connect(self._on_stop_finished)
            self.stop_thread.start()
            return

        # ========== START TRADING ==========
        if self.trading_thread is not None:
            self.trading_thread = None

        primary, secondary = self.settings_panel.get_symbols()

        if not primary or not secondary or primary == secondary:
            QMessageBox.warning(self, "Invalid Selection",
                                "Please enter valid, different symbols in Settings tab!")
            return

        self.add_log("=" * 70)
        self.add_log("🚀 STARTING TRADING SYSTEM")
        self.add_log("=" * 70)
        self.add_log(f"📊 Selected Pair: {primary} / {secondary}")
        self.add_log("🔄 Loading symbol info from MT5...")

        try:
            symbols = self.symbol_loader.load_pair(primary, secondary)
            self.add_log(
                f"✅ {primary}: contract_size={symbols['primary']['contract_size']}, "
                f"min_lot={symbols['primary']['min_lot']}")
            self.add_log(
                f"✅ {secondary}: contract_size={symbols['secondary']['contract_size']}, "
                f"min_lot={symbols['secondary']['min_lot']}")
        except Exception as e:
            self.add_log(f"❌ Failed to load symbols: {e}")
            QMessageBox.critical(self, "Symbol Error",
                                 f"Could not load symbols from MT5:\n\n{e}\n\n"
                                 "Please check:\n"
                                 "1. MT5 is running and logged in\n"
                                 "2. Symbol names are correct\n"
                                 "3. Symbols are in Market Watch")
            return

        # Get settings
        settings = self.settings_manager.get()
        self.add_log(f"⚙️  Global Settings:")
        self.add_log(f"   Entry: {settings.entry_threshold}, Exit: {settings.exit_threshold}")
        self.add_log(f"   Volume: {settings.volume_multiplier}x, Window: {settings.rolling_window_size}")
        self.add_log(f"   Max Positions: {settings.max_positions}, Risk: {settings.max_risk_pct}%")
        self.add_log("=" * 70)

        # Create trading config
        trading_config = {
            'symbols': symbols,
            'settings': settings.to_dict(),
            'primary_symbol': primary,
            'secondary_symbol': secondary
        }

        # Create and start trading thread
        self.trading_thread = TradingSystemThread(trading_config, self.risk_alert_handler)
        self.trading_thread.log_message.connect(self.add_log)
        self.trading_thread.snapshot_update.connect(self.on_snapshot_update)
        self.trading_thread.finished.connect(self._on_thread_finished)
        self.trading_thread.start()

        # Auto-save config
        self.add_log("")
        self.add_log("💾 Auto-saving configuration...")
        try:
            self.settings_panel.save_settings()
            self.add_log("✅ Configuration auto-saved")
        except Exception as e:
            self.add_log(f"⚠️  Failed to auto-save: {e}")

        self.add_log("=" * 70)

        # Update UI to running state
        btn = self.display_panel.get_start_stop_button()
        btn.setText("⏸️ Stop Trading")
        btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
                min-width: 180px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)

        self.statusBar.showMessage(f"Trading {primary}/{secondary}")
        self.display_panel.update_status("🟢 Running", "#27ae60")

    def _on_stop_finished(self, graceful: bool):
        """Handle stop thread completion"""
        self.add_log("")
        if graceful:
            self.add_log("✅ Trading system stopped gracefully")
        else:
            self.add_log("⚠️  Trading system force-stopped")
        self.add_log("=" * 70)

        # Clean up threads
        if self.stop_thread:
            self.stop_thread.deleteLater()
            self.stop_thread = None

        if self.trading_thread:
            self.trading_thread.deleteLater()
            self.trading_thread = None

        # Reset UI
        btn = self.display_panel.get_start_stop_button()
        btn.setEnabled(True)
        btn.setText("▶️ Start Trading")
        btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
                min-width: 180px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)

        self.statusBar.showMessage("Ready")
        self.display_panel.update_status("⚫ Stopped", "#7f8c8d")

    def _on_thread_finished(self):
        """Handle trading thread natural finish"""
        if self.trading_thread and not self.trading_thread.running:
            self.add_log("🔔 Trading thread finished")

    @pyqtSlot(object)
    def on_snapshot_update(self, snapshot):
        """Handle snapshot update from trading system"""
        if snapshot:
            self.display_panel.update_chart(snapshot)

    def update_display(self):
        """Periodic display update"""
        if not self.trading_thread or not self.trading_thread.isRunning():
            return

        try:
            if not self.trading_thread.trading_system:
                return

            system = self.trading_thread.trading_system

            # Get latest snapshot
            if hasattr(system, 'snapshots') and system.snapshots:
                snapshot = system.snapshots[-1]

                # Update live stats
                self.display_panel.update_live_stats(
                    z_score=snapshot.get('z_score'),
                    correlation=snapshot.get('correlation'),
                    hedge_ratio=snapshot.get('hedge_ratio'),
                    spread=snapshot.get('spread'),
                    signal=snapshot.get('signal', 'HOLD')
                )

                # Update model metrics
                metrics = {
                    'entry_threshold': snapshot.get('entry_threshold', 2.0),
                    'exit_threshold': snapshot.get('exit_threshold', 0.5),
                    'window_size': snapshot.get('window_size', 200),
                    'spread_mean': snapshot.get('spread_mean'),
                    'spread_std': snapshot.get('spread_std'),
                    'mean_drift': snapshot.get('mean_drift'),
                    'max_z_score': snapshot.get('max_z_score'),
                    'min_z_score': snapshot.get('min_z_score'),
                    'max_mean': snapshot.get('max_mean'),
                    'min_mean': snapshot.get('min_mean'),
                    'last_update': datetime.now().strftime("%H:%M:%S")
                }
                self.display_panel.update_model_metrics(metrics)

                # Update total P&L
                total_pnl = snapshot.get('total_pnl', 0)
                self.display_panel.update_total_pnl(total_pnl)

        except Exception as e:
            logger.error(f"Display update error: {e}")

    def add_log(self, message):
        """Add log message"""
        self.display_panel.add_log(message)

    def on_settings_saved(self):
        """Handle settings saved"""
        self.add_log("💾 Settings saved successfully")
        self.statusBar.showMessage("Settings saved", 3000)

    def on_settings_applied(self):
        """Handle settings applied"""
        self.add_log("✅ Settings applied to current session")
        self.statusBar.showMessage("Settings applied", 3000)

        # TODO: Apply settings to running trading system if active

    def on_symbol_changed(self, primary, secondary):
        """Handle symbol change"""
        if primary and secondary and primary != secondary:
            self.statusBar.showMessage(f"Ready to trade: {primary}/{secondary}")
            self.add_log(f"📊 Symbols: {primary} / {secondary}")


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = PairTradingGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""
Professional Pair Trading GUI - Refactored with Modular Code
Same UI as original, but with cleaner code organization
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QMessageBox, QStatusBar, QGroupBox, QGridLayout,
    QLabel, QLineEdit, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont
from datetime import datetime
import logging

# Import theme
from asset.theme import DARCULA_THEME_QSS

# Import configuration
from config.trading_settings import TradingSettingsManager, SymbolLoader

# Import modular components (for cleaner code organization)
from gui.settings_panel import SettingsPanel
from gui.display_panel import DisplayPanel, DashboardWidget

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

            # Merge config with symbols
            config = self.trading_config['settings'].copy()
            config['primary_symbol'] = self.trading_config['primary_symbol']
            config['secondary_symbol'] = self.trading_config['secondary_symbol']

            # Create trading system instance
            self.trading_system = TradingSystem(config=config)

            # Connect risk alert handler if provided (check if risk_manager exists)
            if self.risk_alert_handler and hasattr(self.trading_system, 'risk_manager'):
                self.trading_system.risk_manager.alert_callback = self.risk_alert_handler.emit_alert

            self.log_message.emit("✅ Trading System initialized")
            self.log_message.emit("🔄 Starting main trading loop...")
            self.log_message.emit("")

            # Start trading system
            self.trading_system.start()

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
    """Main GUI Window - Same UI as original, cleaner code"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pair Trading System - Professional Edition")
        self.setGeometry(100, 100, 1400, 800)

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

        # Create modular components (hidden, used internally)
        self._dashboard_widget = DashboardWidget()
        self._settings_panel = SettingsPanel(self.settings_manager)

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
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 10))

        # ========== DASHBOARD TAB ==========
        dashboard_tab = self.create_dashboard_tab()
        self.tabs.addTab(dashboard_tab, "📊 Dashboard")

        # ========== CHARTS TAB ==========
        from gui.chart_widget import ChartWidget
        self.chart_widget = ChartWidget()
        self.tabs.addTab(self.chart_widget, "📈 Charts")

        # ========== PAIR DISCOVERY TAB ==========
        self.discovery_tab = PairDiscoveryTab()
        self.tabs.addTab(self.discovery_tab, "🔬 Pair Discovery")

        # ========== SETTINGS TAB ==========
        self.tabs.addTab(self._settings_panel, "⚙️ Settings")

        # ========== LOGS TAB ==========
        from PyQt6.QtWidgets import QTextEdit
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)

        # Log controls
        controls = QHBoxLayout()
        clear_btn = QPushButton("🗑️ Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        controls.addWidget(clear_btn)
        controls.addStretch()
        logs_layout.addLayout(controls)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier New", 9))
        logs_layout.addWidget(self.log_display)

        self.tabs.addTab(logs_tab, "📝 Logs")

        main_layout.addWidget(self.tabs)

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready - Select pair and start trading")

    def create_dashboard_tab(self):
        """Create main dashboard tab - all-in-one like original"""
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
        self.primary_input.setPlaceholderText("e.g., XAUUSD, BTCUSD")
        self.primary_input.setMinimumWidth(150)
        self.primary_input.setText("BTCUSD")
        self.primary_input.textChanged.connect(self.on_symbol_changed)
        symbol_layout.addWidget(self.primary_input, 0, 1)

        symbol_layout.addWidget(QLabel("Secondary Symbol:"), 1, 0)
        self.secondary_input = QLineEdit()
        self.secondary_input.setPlaceholderText("e.g., XAGUSD, ETHUSD")
        self.secondary_input.setMinimumWidth(150)
        self.secondary_input.setText("ETHUSD")
        self.secondary_input.textChanged.connect(self.on_symbol_changed)
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

        # Live statistics (reuse from DashboardWidget)
        stats_group = QGroupBox("Live Statistics")
        stats_layout = QGridLayout()

        self.z_score_label = self._dashboard_widget.z_score_label
        stats_layout.addWidget(QLabel("Z-Score:"), 0, 0)
        stats_layout.addWidget(self.z_score_label, 0, 1)

        self.correlation_label = self._dashboard_widget.correlation_label
        stats_layout.addWidget(QLabel("Correlation:"), 1, 0)
        stats_layout.addWidget(self.correlation_label, 1, 1)

        self.hedge_ratio_label = self._dashboard_widget.hedge_ratio_label
        stats_layout.addWidget(QLabel("Hedge Ratio:"), 2, 0)
        stats_layout.addWidget(self.hedge_ratio_label, 2, 1)

        self.spread_label = self._dashboard_widget.spread_label
        stats_layout.addWidget(QLabel("Spread:"), 0, 2)
        stats_layout.addWidget(self.spread_label, 0, 3)

        self.total_pnl_label = self._dashboard_widget.total_pnl_label
        stats_layout.addWidget(QLabel("Total P&L:"), 1, 2)
        stats_layout.addWidget(self.total_pnl_label, 1, 3)

        self.signal_label = self._dashboard_widget.signal_label
        stats_layout.addWidget(QLabel("Signal:"), 2, 2)
        stats_layout.addWidget(self.signal_label, 2, 3)

        stats_group.setLayout(stats_layout)
        control_layout.addWidget(stats_group)

        control_panel.setLayout(control_layout)
        layout.addWidget(control_panel)

        # Add rest of dashboard panels (create once and store references)
        if not hasattr(self, '_metrics_panel'):
            self._metrics_panel = self._dashboard_widget._create_metrics_panel()
        if not hasattr(self, '_account_risk_panel'):
            self._account_risk_panel = self._dashboard_widget._create_account_risk_panel()
        if not hasattr(self, '_attribution_panel'):
            self._attribution_panel = self._dashboard_widget._create_attribution_panel()

        layout.addWidget(self._metrics_panel)
        layout.addWidget(self._account_risk_panel)
        layout.addWidget(self._attribution_panel)

        return tab

    def load_initial_state(self):
        """Load initial state from settings and MT5"""
        # Load settings
        self._settings_panel.load_settings()

        # Sync symbols to dashboard
        primary, secondary = self._settings_panel.get_symbols()
        self.primary_input.setText(primary)
        self.secondary_input.setText(secondary)

        # Load MT5 state
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

            # Update display
            self._dashboard_widget.update_account_info(balance, equity, profit, margin_info)

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

            self._dashboard_widget.update_risk_manager(risk_data)

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
        self.add_log("")
        self.add_log("📋 READY TO START:")
        self.add_log("   1. Enter symbols (or use defaults)")
        self.add_log("   2. Adjust settings if needed (Settings tab)")
        self.add_log("   3. Click 'Start Trading'")
        self.add_log("")
        self.add_log("=" * 70)

    def on_symbol_changed(self):
        """Handle symbol change"""
        primary = self.primary_input.text().strip().upper()
        secondary = self.secondary_input.text().strip().upper()

        # Sync to settings panel
        self._settings_panel.set_symbols(primary, secondary)

        if primary and secondary and primary != secondary:
            self.statusBar.showMessage(f"Ready to trade: {primary}/{secondary}")
            self.add_log(f"📊 Symbols: {primary} / {secondary}")

    def toggle_trading(self):
        """Start or stop trading"""
        if self.trading_thread is not None and self.trading_thread.isRunning():
            # STOP
            self.add_log("=" * 70)
            self.add_log("⏸️ STOPPING TRADING SYSTEM")
            self.add_log("=" * 70)

            self.start_stop_btn.setEnabled(False)
            self.start_stop_btn.setText("⏸️ Stopping...")

            self.stop_thread = StopThread(self.trading_thread)
            self.stop_thread.log_message.connect(self.add_log)
            self.stop_thread.finished_signal.connect(self._on_stop_finished)
            self.stop_thread.start()
            return

        # START
        if self.trading_thread is not None:
            self.trading_thread = None

        primary = self.primary_input.text().strip()
        secondary = self.secondary_input.text().strip()

        if not primary or not secondary or primary == secondary:
            QMessageBox.warning(self, "Invalid Selection", "Please enter valid, different symbols!")
            return

        self.add_log("=" * 70)
        self.add_log("🚀 STARTING TRADING SYSTEM")
        self.add_log("=" * 70)
        self.add_log(f"📊 Selected Pair: {primary} / {secondary}")
        self.add_log("🔄 Loading symbol info from MT5...")

        try:
            symbols = self.symbol_loader.load_pair(primary, secondary)
            self.add_log(f"✅ {primary}: contract_size={symbols['primary']['contract_size']}, min_lot={symbols['primary']['min_lot']}")
            self.add_log(f"✅ {secondary}: contract_size={symbols['secondary']['contract_size']}, min_lot={symbols['secondary']['min_lot']}")
        except Exception as e:
            self.add_log(f"❌ Failed to load symbols: {e}")
            QMessageBox.critical(self, "Symbol Error", f"Could not load symbols from MT5:\n\n{e}")
            return

        # Get settings
        settings = self.settings_manager.get()
        self.add_log(f"⚙️  Settings: Entry={settings.entry_threshold}, Exit={settings.exit_threshold}, Window={settings.rolling_window_size}")

        # Create config
        trading_config = {
            'symbols': symbols,
            'settings': settings.to_dict(),
            'primary_symbol': primary,
            'secondary_symbol': secondary
        }

        # Start thread
        self.trading_thread = TradingSystemThread(trading_config, self.risk_alert_handler)
        self.trading_thread.log_message.connect(self.add_log)
        self.trading_thread.snapshot_update.connect(self.on_snapshot_update)
        self.trading_thread.finished.connect(self._on_thread_finished)
        self.trading_thread.start()

        # Auto-save
        self.add_log("💾 Auto-saving configuration...")
        try:
            self._settings_panel.save_settings()
            self.add_log("✅ Configuration saved")
        except:
            pass

        # Update UI
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
            QPushButton:hover { background-color: #c0392b; }
        """)

        self._dashboard_widget.update_status("🟢 Running", "#27ae60")

    def _on_stop_finished(self, graceful):
        """Handle stop completion"""
        self.add_log("✅ Trading system stopped")

        if self.stop_thread:
            self.stop_thread.deleteLater()
            self.stop_thread = None

        if self.trading_thread:
            self.trading_thread.deleteLater()
            self.trading_thread = None

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
            QPushButton:hover { background-color: #2ecc71; }
        """)

        self._dashboard_widget.update_status("⚫ Stopped", "#7f8c8d")

    def _on_thread_finished(self):
        """Handle thread finish"""
        pass

    @pyqtSlot(object)
    def on_snapshot_update(self, snapshot):
        """Handle snapshot update"""
        if snapshot:
            self.chart_widget.update_chart(snapshot)

    def update_display(self):
        """Periodic display update"""
        if not self.trading_thread or not self.trading_thread.isRunning():
            return

        try:
            if not self.trading_thread.trading_system:
                return

            system = self.trading_thread.trading_system

            if hasattr(system, 'snapshots') and system.snapshots:
                snapshot = system.snapshots[-1]

                # Update live stats
                self._dashboard_widget.update_live_stats(
                    z_score=snapshot.get('z_score'),
                    correlation=snapshot.get('correlation'),
                    hedge_ratio=snapshot.get('hedge_ratio'),
                    spread=snapshot.get('spread'),
                    signal=snapshot.get('signal', 'HOLD')
                )

                # Update metrics
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
                self._dashboard_widget.update_model_metrics(metrics)

                # Update P&L
                total_pnl = snapshot.get('total_pnl', 0)
                self._dashboard_widget.update_total_pnl(total_pnl)

                # Update account info from MT5
                try:
                    from core.mt5_manager import get_mt5
                    mt5 = get_mt5()
                    account_info = mt5.account_info()
                    if account_info:
                        margin_info = {
                            'used': account_info.margin,
                            'free': account_info.margin_free,
                            'level': account_info.margin_level if account_info.margin_level else 0
                        }
                        self._dashboard_widget.update_account_info(
                            account_info.balance,
                            account_info.equity,
                            account_info.profit,
                            margin_info
                        )
                except Exception as mt5_err:
                    pass  # Silent fail for MT5 updates

                # Update position overview if available
                if hasattr(system, 'position_tracker') and system.position_tracker:
                    positions = system.position_tracker.get_all_positions()
                    overview = {
                        'open_spread': len([p for p in positions if p.get('status') == 'OPEN']),
                        'open_positions': len([p for p in positions if p.get('status') == 'OPEN']),
                        'closed_positions': len([p for p in positions if p.get('status') == 'CLOSED']),
                        'primary_lots': sum(p.get('primary_volume', 0) for p in positions if p.get('status') == 'OPEN'),
                        'secondary_lots': sum(p.get('secondary_volume', 0) for p in positions if p.get('status') == 'OPEN'),
                        'hedge_quality': '--',
                        'imbalance': 'Balanced',
                        'value': 0
                    }
                    self._dashboard_widget.update_position_overview(overview)

                # Update Risk Manager data
                if hasattr(system, 'risk_config'):
                    try:
                        # Get account info for risk calculation
                        balance = account_info.balance if 'account_info' in locals() and account_info else 100000

                        # Calculate risk percentages and amounts
                        setup_risk_pct = system.risk_config.max_loss_per_setup_pct
                        daily_risk_pct = system.risk_config.daily_loss_limit_pct

                        setup_risk_amount = balance * (setup_risk_pct / 100)
                        daily_risk_limit = balance * (daily_risk_pct / 100)

                        # Get current PnL for daily tracking
                        pnl_data = system.position_tracker.get_total_pnl() if hasattr(system, 'position_tracker') else {}
                        daily_pnl = pnl_data.get('total_pnl', 0)
                        unrealized = pnl_data.get('unrealized_pnl', 0)

                        # Determine trading status
                        if daily_pnl < -daily_risk_limit:
                            trading_status = "🔴 BLOCKED"
                        elif abs(daily_pnl) > daily_risk_limit * 0.8:
                            trading_status = "🟡 WARNING"
                        else:
                            trading_status = "🟢 ACTIVE"

                        risk_data = {
                            'setup_risk_pct': setup_risk_pct,
                            'setup_risk_amount': setup_risk_amount,
                            'daily_risk_pct': daily_risk_pct,
                            'daily_risk_limit': daily_risk_limit,
                            'trading_status': trading_status,
                            'block_time': '--',
                            'unrealized': unrealized,
                            'daily_total_pnl': daily_pnl,
                            'unlock_time': '--'
                        }
                        self._dashboard_widget.update_risk_manager(risk_data)
                    except Exception as risk_err:
                        logger.debug(f"Risk manager update skipped: {risk_err}")

                # Update P&L Attribution
                try:
                    from analytics.pnl_attribution import get_attribution_engine
                    attribution_engine = get_attribution_engine()

                    # Get current open positions
                    if hasattr(system, 'position_tracker') and system.position_tracker:
                        positions = system.position_tracker.positions

                        # If we have open positions, calculate attribution
                        if positions:
                            # Use first position for attribution (or sum all later)
                            spread_id = list(positions.keys())[0] if positions else None

                            if spread_id and hasattr(system, 'market_data'):
                                # Build current snapshot
                                from analytics.pnl_attribution import PositionSnapshot

                                current_prices = system.market_data.get_current_prices()
                                if current_prices:
                                    current_snapshot = PositionSnapshot(
                                        timestamp=datetime.now(),
                                        xau_bid=current_prices.get('primary_bid', 0),
                                        xau_ask=current_prices.get('primary_ask', 0),
                                        xag_bid=current_prices.get('secondary_bid', 0),
                                        xag_ask=current_prices.get('secondary_ask', 0),
                                        spread=snapshot.get('spread', 0),
                                        mean=snapshot.get('spread_mean', 0),
                                        std=snapshot.get('spread_std', 1),
                                        zscore=snapshot.get('z_score', 0),
                                        hedge_ratio=snapshot.get('hedge_ratio', 1),
                                        xau_volume=0.01,
                                        xag_volume=0.01,
                                        xau_side='BUY',
                                        xag_side='SELL',
                                        xau_price=current_prices.get('primary_bid', 0),
                                        xag_price=current_prices.get('secondary_ask', 0)
                                    )

                                    # Calculate attribution
                                    current_pnl = pnl_data.get('total_pnl', 0)
                                    attribution = attribution_engine.calculate_attribution(
                                        spread_id, current_snapshot, current_pnl
                                    )

                                    # Convert to dict for update
                                    attribution_dict = {
                                        'spread_pnl': attribution.spread_pnl,
                                        'spread_pnl_pct': attribution.spread_pnl_pct,
                                        'mean_drift_pnl': attribution.mean_drift_pnl,
                                        'mean_drift_pnl_pct': attribution.mean_drift_pnl_pct,
                                        'directional_pnl': attribution.directional_pnl,
                                        'directional_pnl_pct': attribution.directional_pnl_pct,
                                        'hedge_imbalance_pnl': attribution.hedge_imbalance_pnl,
                                        'hedge_imbalance_pnl_pct': attribution.hedge_imbalance_pnl_pct,
                                        'transaction_costs': attribution.transaction_costs,
                                        'transaction_costs_pct': attribution.transaction_costs_pct,
                                        'slippage': attribution.slippage,
                                        'slippage_pct': attribution.slippage_pct,
                                        'rebalance_alpha': attribution.rebalance_alpha,
                                        'rebalance_alpha_pct': attribution.rebalance_alpha_pct,
                                        'hedge_quality': f"{attribution.hedge_quality:.1%}" if attribution.hedge_quality else "--",
                                        'strategy_purity': f"{attribution.strategy_purity:.1%}" if attribution.strategy_purity else "--",
                                        'classification': attribution.classification
                                    }
                                    self._dashboard_widget.update_pnl_attribution(attribution_dict)
                except Exception as attr_err:
                    logger.debug(f"PnL attribution update skipped: {attr_err}")

        except Exception as e:
            logger.error(f"Display update error: {e}")

    def add_log(self, message):
        """Add log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")

    def clear_logs(self):
        """Clear logs"""
        self.log_display.clear()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = PairTradingGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

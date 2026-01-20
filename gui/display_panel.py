"""
Display Panel - Information Display and Visualization
Handles all display widgets: dashboard, charts, logs, and real-time updates
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QTabWidget, QTextEdit, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor
from datetime import datetime
import logging

from gui.chart_widget import ChartWidget

logger = logging.getLogger(__name__)


class DisplayPanel(QWidget):
    """
    Display Panel Widget
    Contains dashboard, charts, and logs
    """

    # Signals
    start_stop_clicked = pyqtSignal()  # Emitted when start/stop button clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        """Initialize display panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tabs for different displays
        self.tabs = QTabWidget()

        # Dashboard tab
        self.dashboard_widget = DashboardWidget()
        self.tabs.addTab(self.dashboard_widget, "📊 Dashboard")

        # Chart tab
        self.chart_widget = ChartWidget()
        self.tabs.addTab(self.chart_widget, "📈 Charts")

        # Logs tab
        self.logs_widget = LogsWidget()
        self.tabs.addTab(self.logs_widget, "📝 Logs")

        layout.addWidget(self.tabs)

        # Connect signals
        self.dashboard_widget.start_stop_clicked.connect(self.start_stop_clicked.emit)

    def add_log(self, message):
        """Add log message"""
        self.logs_widget.add_log(message)

    def get_start_stop_button(self):
        """Get reference to start/stop button"""
        return self.dashboard_widget.start_stop_btn

    @pyqtSlot(object)
    def update_chart(self, snapshot):
        """Update chart with new snapshot"""
        self.chart_widget.update_chart(snapshot)

    # Dashboard update methods - delegate to dashboard widget
    def update_live_stats(self, z_score, correlation, hedge_ratio, spread, signal):
        """Update live statistics panel"""
        self.dashboard_widget.update_live_stats(z_score, correlation, hedge_ratio, spread, signal)

    def update_model_metrics(self, metrics):
        """Update model metrics panel"""
        self.dashboard_widget.update_model_metrics(metrics)

    def update_account_info(self, balance, equity, unrealized_pnl, margin_info):
        """Update account information"""
        self.dashboard_widget.update_account_info(balance, equity, unrealized_pnl, margin_info)

    def update_position_overview(self, overview):
        """Update position overview"""
        self.dashboard_widget.update_position_overview(overview)

    def update_risk_manager(self, risk_data):
        """Update risk manager panel"""
        self.dashboard_widget.update_risk_manager(risk_data)

    def update_pnl_attribution(self, attribution):
        """Update P&L attribution panel"""
        self.dashboard_widget.update_pnl_attribution(attribution)

    def update_total_pnl(self, pnl):
        """Update total P&L"""
        self.dashboard_widget.update_total_pnl(pnl)

    def update_status(self, status, color):
        """Update status label"""
        self.dashboard_widget.update_status(status, color)


class DashboardWidget(QWidget):
    """Dashboard widget with live statistics and controls"""

    start_stop_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        """Initialize dashboard UI"""
        layout = QVBoxLayout(self)

        # ========== Control Panel ==========
        control_panel = self._create_control_panel()
        layout.addWidget(control_panel)

        # ========== Model Metrics Panel ==========
        metrics_panel = self._create_metrics_panel()
        layout.addWidget(metrics_panel)

        # ========== Account & Risk Management ==========
        account_risk_panel = self._create_account_risk_panel()
        layout.addWidget(account_risk_panel)

        # ========== P&L Attribution Panel ==========
        attribution_panel = self._create_attribution_panel()
        layout.addWidget(attribution_panel)

        layout.addStretch()

    def _create_control_panel(self):
        """Create control panel with button and live stats"""
        panel = QGroupBox("Control Panel")
        layout = QHBoxLayout()

        # Start/Stop button
        button_group = QGroupBox("Trading Control")
        button_layout = QVBoxLayout()
        self.start_stop_btn = QPushButton("▶️ Start Trading")
        self.start_stop_btn.setStyleSheet("""
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
        self.start_stop_btn.clicked.connect(self.start_stop_clicked.emit)
        button_layout.addWidget(self.start_stop_btn)
        button_group.setLayout(button_layout)
        layout.addWidget(button_group)

        # Live statistics
        stats_group = QGroupBox("Live Statistics")
        stats_layout = QGridLayout()

        self.z_score_label = QLabel("--")
        self.z_score_label.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        stats_layout.addWidget(QLabel("Z-Score:"), 0, 0)
        stats_layout.addWidget(self.z_score_label, 0, 1)

        self.correlation_label = QLabel("--")
        stats_layout.addWidget(QLabel("Correlation:"), 1, 0)
        stats_layout.addWidget(self.correlation_label, 1, 1)

        self.hedge_ratio_label = QLabel("--")
        stats_layout.addWidget(QLabel("Hedge Ratio:"), 2, 0)
        stats_layout.addWidget(self.hedge_ratio_label, 2, 1)

        self.spread_label = QLabel("--")
        stats_layout.addWidget(QLabel("Spread:"), 0, 2)
        stats_layout.addWidget(self.spread_label, 0, 3)

        self.total_pnl_label = QLabel("$0.00")
        self.total_pnl_label.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        stats_layout.addWidget(QLabel("Total P&L:"), 1, 2)
        stats_layout.addWidget(self.total_pnl_label, 1, 3)

        self.signal_label = QLabel("HOLD")
        self.signal_label.setStyleSheet(
            "background-color: #7f8c8d; color: white; padding: 5px; border-radius: 3px; font-weight: bold;")
        stats_layout.addWidget(QLabel("Signal:"), 2, 2)
        stats_layout.addWidget(self.signal_label, 2, 3)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        panel.setLayout(layout)
        return panel

    def _create_metrics_panel(self):
        """Create model metrics panel"""
        panel = QGroupBox("Model Metrics")
        layout = QGridLayout()

        # Row 0
        layout.addWidget(QLabel("Entry Threshold:"), 0, 0)
        self.entry_threshold_label = QLabel("2.0")
        self.entry_threshold_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.entry_threshold_label, 0, 1)

        layout.addWidget(QLabel("Spread Mean:"), 0, 2)
        self.spread_mean_label = QLabel("--")
        self.spread_mean_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.spread_mean_label, 0, 3)

        layout.addWidget(QLabel("Mean Drift:"), 0, 4)
        self.mean_drift_label = QLabel("--")
        self.mean_drift_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        layout.addWidget(self.mean_drift_label, 0, 5)

        # Row 1
        layout.addWidget(QLabel("Exit Threshold:"), 1, 0)
        self.exit_threshold_label = QLabel("0.5")
        self.exit_threshold_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.exit_threshold_label, 1, 1)

        layout.addWidget(QLabel("Spread Std:"), 1, 2)
        self.spread_std_label = QLabel("--")
        self.spread_std_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.spread_std_label, 1, 3)

        layout.addWidget(QLabel("Window Size:"), 1, 4)
        self.window_size_label = QLabel("200")
        self.window_size_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.window_size_label, 1, 5)

        # Row 2
        layout.addWidget(QLabel("Max Z-Score:"), 2, 0)
        self.max_z_score_label = QLabel("--")
        self.max_z_score_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.max_z_score_label, 2, 1)

        layout.addWidget(QLabel("Max Mean:"), 2, 2)
        self.max_mean_label = QLabel("--")
        self.max_mean_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.max_mean_label, 2, 3)

        layout.addWidget(QLabel("Last Update:"), 2, 4)
        self.last_update_label = QLabel("--")
        self.last_update_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.last_update_label, 2, 5)

        # Row 3
        layout.addWidget(QLabel("Min Z-Score:"), 3, 0)
        self.min_z_score_label = QLabel("--")
        self.min_z_score_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        layout.addWidget(self.min_z_score_label, 3, 1)

        layout.addWidget(QLabel("Min Mean:"), 3, 2)
        self.min_mean_label = QLabel("--")
        self.min_mean_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.min_mean_label, 3, 3)

        layout.addWidget(QLabel("Status:"), 3, 4)
        self.status_label = QLabel("⚫ Stopped")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")
        layout.addWidget(self.status_label, 3, 5)

        panel.setLayout(layout)
        return panel

    def _create_account_risk_panel(self):
        """Create unified account & risk management panel"""
        panel = QGroupBox("💰 ACCOUNT & RISK MANAGEMENT")
        layout = QGridLayout()

        # === ACCOUNT STATUS ===
        section1 = QLabel("ACCOUNT STATUS")
        section1.setStyleSheet("font-weight: bold; color: #3498db; font-size: 11px; border-bottom: 1px solid #34495e;")
        layout.addWidget(section1, 0, 0, 1, 6)

        layout.addWidget(QLabel("Balance:"), 1, 0)
        self.balance_label = QLabel("$0.00")
        self.balance_label.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self.balance_label.setStyleSheet("color: #2980b9;")
        layout.addWidget(self.balance_label, 1, 1)

        layout.addWidget(QLabel("Equity:"), 1, 2)
        self.equity_label = QLabel("$0.00")
        self.equity_label.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self.equity_label.setStyleSheet("color: #27ae60;")
        layout.addWidget(self.equity_label, 1, 3)

        layout.addWidget(QLabel("Unrealized P&L:"), 1, 4)
        self.unrealized_pnl_label = QLabel("$0.00")
        self.unrealized_pnl_label.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        layout.addWidget(self.unrealized_pnl_label, 1, 5)

        # Margin Info
        layout.addWidget(QLabel("Used Margin:"), 2, 0)
        self.used_margin_label = QLabel("$0.00")
        layout.addWidget(self.used_margin_label, 2, 1)

        layout.addWidget(QLabel("Free Margin:"), 2, 2)
        self.free_margin_label = QLabel("$0.00")
        layout.addWidget(self.free_margin_label, 2, 3)

        layout.addWidget(QLabel("Margin Level:"), 2, 4)
        self.margin_level_label = QLabel("0.0%")
        self.margin_level_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        layout.addWidget(self.margin_level_label, 2, 5)

        # === POSITION OVERVIEW ===
        section2 = QLabel("POSITION OVERVIEW")
        section2.setStyleSheet("font-weight: bold; color: #3498db; font-size: 11px; margin-top: 5px; border-bottom: 1px solid #34495e;")
        layout.addWidget(section2, 3, 0, 1, 6)

        layout.addWidget(QLabel("Open Spread:"), 4, 0)
        self.open_spread_label = QLabel("0")
        self.open_spread_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        layout.addWidget(self.open_spread_label, 4, 1)

        layout.addWidget(QLabel("Open/Close:"), 4, 2)
        self.open_close_label = QLabel("0 / 0")
        self.open_close_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.open_close_label, 4, 3)

        layout.addWidget(QLabel("Total Lots:"), 4, 4)
        self.total_lots_label = QLabel("0.00 / 0.00")
        self.total_lots_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.total_lots_label, 4, 5)

        layout.addWidget(QLabel("Hedge Quality:"), 5, 0)
        self.hedge_quality_label = QLabel("--")
        self.hedge_quality_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        layout.addWidget(self.hedge_quality_label, 5, 1)

        layout.addWidget(QLabel("Imbalance:"), 5, 2)
        self.imbalance_label = QLabel("Balanced")
        self.imbalance_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.imbalance_label, 5, 3)

        layout.addWidget(QLabel("Value:"), 5, 4)
        self.value_label = QLabel("$0.00")
        self.value_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.value_label, 5, 5)

        # === RISK MANAGER ===
        section3 = QLabel("RISK MANAGER")
        section3.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 11px; margin-top: 5px; border-bottom: 1px solid #34495e;")
        layout.addWidget(section3, 6, 0, 1, 6)

        # Headers
        setup_header = QLabel("Risk per Setup")
        setup_header.setStyleSheet("color: #3498db; font-weight: bold; font-size: 10px;")
        layout.addWidget(setup_header, 7, 0, 1, 2)

        daily_header = QLabel("Daily Risk")
        daily_header.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 10px;")
        layout.addWidget(daily_header, 7, 2, 1, 2)

        # Risk percentages
        layout.addWidget(QLabel("Risk %:"), 8, 0)
        self.setup_risk_pct_label = QLabel("--%")
        self.setup_risk_pct_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.setup_risk_pct_label.setStyleSheet("color: #3498db;")
        layout.addWidget(self.setup_risk_pct_label, 8, 1)

        layout.addWidget(QLabel("Risk %:"), 8, 2)
        self.daily_risk_pct_label = QLabel("--%")
        self.daily_risk_pct_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.daily_risk_pct_label.setStyleSheet("color: #e74c3c;")
        layout.addWidget(self.daily_risk_pct_label, 8, 3)

        layout.addWidget(QLabel("Trading Status:"), 8, 4)
        self.trading_status_label = QLabel("--")
        self.trading_status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.trading_status_label, 8, 5)

        # Risk amounts
        layout.addWidget(QLabel("Risk $:"), 9, 0)
        self.setup_risk_amount_label = QLabel("$--")
        self.setup_risk_amount_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.setup_risk_amount_label.setStyleSheet("color: #3498db;")
        layout.addWidget(self.setup_risk_amount_label, 9, 1)

        layout.addWidget(QLabel("Risk $:"), 9, 2)
        self.daily_risk_limit_label = QLabel("$--")
        self.daily_risk_limit_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.daily_risk_limit_label.setStyleSheet("color: #e74c3c;")
        layout.addWidget(self.daily_risk_limit_label, 9, 3)

        layout.addWidget(QLabel("Block Time:"), 9, 4)
        self.block_time_label = QLabel("--")
        self.block_time_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.block_time_label, 9, 5)

        # Unrealized & Total
        layout.addWidget(QLabel("Unrealized:"), 10, 0)
        self.risk_unrealized_label = QLabel("$--")
        self.risk_unrealized_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        layout.addWidget(self.risk_unrealized_label, 10, 1)

        layout.addWidget(QLabel("Total PnL:"), 10, 2)
        self.daily_total_pnl_label = QLabel("$--")
        self.daily_total_pnl_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        layout.addWidget(self.daily_total_pnl_label, 10, 3)

        layout.addWidget(QLabel("Unlock Time:"), 10, 4)
        self.unlock_time_label = QLabel("--")
        self.unlock_time_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.unlock_time_label, 10, 5)

        panel.setLayout(layout)
        return panel

    def _create_attribution_panel(self):
        """Create P&L attribution panel"""
        panel = QGroupBox("📊 P&L Attribution (Real-Time)")
        layout = QGridLayout()

        # Left side - P&L components
        layout.addWidget(QLabel("Spread P&L:"), 0, 0)
        self.spread_pnl_label = QLabel("$0.00")
        self.spread_pnl_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.spread_pnl_label.setStyleSheet("color: #3498db;")
        layout.addWidget(self.spread_pnl_label, 0, 1)
        self.spread_pnl_pct_label = QLabel("0.0%")
        self.spread_pnl_pct_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.spread_pnl_pct_label, 0, 2)

        layout.addWidget(QLabel("Mean Drift P&L:"), 1, 0)
        self.mean_drift_pnl_label = QLabel("$0.00")
        self.mean_drift_pnl_label.setFont(QFont("Courier New", 10))
        self.mean_drift_pnl_label.setStyleSheet("color: #9b59b6;")
        layout.addWidget(self.mean_drift_pnl_label, 1, 1)
        self.mean_drift_pnl_pct_label = QLabel("0.0%")
        self.mean_drift_pnl_pct_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.mean_drift_pnl_pct_label, 1, 2)

        layout.addWidget(QLabel("Directional P&L:"), 2, 0)
        self.directional_pnl_label = QLabel("$0.00")
        self.directional_pnl_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.directional_pnl_label.setStyleSheet("color: #95a5a6;")
        layout.addWidget(self.directional_pnl_label, 2, 1)
        self.directional_pnl_pct_label = QLabel("0.0%")
        self.directional_pnl_pct_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.directional_pnl_pct_label, 2, 2)

        layout.addWidget(QLabel("Hedge Imbalance:"), 3, 0)
        self.hedge_imbalance_pnl_label = QLabel("$0.00")
        self.hedge_imbalance_pnl_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.hedge_imbalance_pnl_label, 3, 1)
        self.hedge_imbalance_pnl_pct_label = QLabel("0.0%")
        self.hedge_imbalance_pnl_pct_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.hedge_imbalance_pnl_pct_label, 3, 2)

        # Spacer
        layout.setColumnMinimumWidth(3, 30)

        # Right side - Costs and alpha
        layout.addWidget(QLabel("Transaction Costs:"), 0, 4)
        self.transaction_costs_label = QLabel("$0.00")
        self.transaction_costs_label.setFont(QFont("Courier New", 10))
        self.transaction_costs_label.setStyleSheet("color: #e74c3c;")
        layout.addWidget(self.transaction_costs_label, 0, 5)
        self.transaction_costs_pct_label = QLabel("0.0%")
        self.transaction_costs_pct_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.transaction_costs_pct_label, 0, 6)

        layout.addWidget(QLabel("Slippage:"), 1, 4)
        self.slippage_label = QLabel("$0.00")
        self.slippage_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.slippage_label, 1, 5)
        self.slippage_pct_label = QLabel("0.0%")
        self.slippage_pct_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.slippage_pct_label, 1, 6)

        layout.addWidget(QLabel("Rebalance Alpha:"), 2, 4)
        self.rebalance_alpha_label = QLabel("$0.00")
        self.rebalance_alpha_label.setFont(QFont("Courier New", 10))
        self.rebalance_alpha_label.setStyleSheet("color: #27ae60;")
        layout.addWidget(self.rebalance_alpha_label, 2, 5)
        self.rebalance_alpha_pct_label = QLabel("0.0%")
        self.rebalance_alpha_pct_label.setFont(QFont("Courier New", 9))
        layout.addWidget(self.rebalance_alpha_pct_label, 2, 6)

        # Separator
        separator = QLabel("─" * 80)
        separator.setStyleSheet("color: #34495e;")
        layout.addWidget(separator, 4, 0, 1, 7)

        # Quality metrics
        layout.addWidget(QLabel("Hedge Quality:"), 5, 0)
        self.pnl_hedge_quality_label = QLabel("--")
        self.pnl_hedge_quality_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.pnl_hedge_quality_label.setStyleSheet("color: #95a5a6;")
        layout.addWidget(self.pnl_hedge_quality_label, 5, 1)

        layout.addWidget(QLabel("Strategy Purity:"), 5, 2)
        self.strategy_purity_label = QLabel("--")
        self.strategy_purity_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.strategy_purity_label, 5, 3)

        layout.addWidget(QLabel("Classification:"), 5, 4)
        self.classification_label = QLabel("NO DATA")
        self.classification_label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.classification_label.setStyleSheet("color: #95a5a6;")
        layout.addWidget(self.classification_label, 5, 5, 1, 2)

        panel.setLayout(layout)
        return panel

    def update_live_stats(self, z_score, correlation, hedge_ratio, spread, signal):
        """Update live statistics"""
        self.z_score_label.setText(f"{z_score:.2f}" if z_score is not None else "--")
        self.correlation_label.setText(f"{correlation:.3f}" if correlation is not None else "--")
        self.hedge_ratio_label.setText(f"{hedge_ratio:.3f}" if hedge_ratio is not None else "--")
        self.spread_label.setText(f"{spread:.4f}" if spread is not None else "--")

        if signal:
            self.signal_label.setText(signal)
            if "LONG" in signal:
                self.signal_label.setStyleSheet("background-color: #27ae60; color: white; padding: 5px; border-radius: 3px; font-weight: bold;")
            elif "SHORT" in signal:
                self.signal_label.setStyleSheet("background-color: #e74c3c; color: white; padding: 5px; border-radius: 3px; font-weight: bold;")
            else:
                self.signal_label.setStyleSheet("background-color: #7f8c8d; color: white; padding: 5px; border-radius: 3px; font-weight: bold;")

    def update_model_metrics(self, metrics):
        """Update model metrics panel"""
        if not metrics:
            return

        self.entry_threshold_label.setText(f"{metrics.get('entry_threshold', 2.0):.1f}")
        self.exit_threshold_label.setText(f"{metrics.get('exit_threshold', 0.5):.1f}")
        self.window_size_label.setText(str(metrics.get('window_size', 200)))

        self.spread_mean_label.setText(f"{metrics.get('spread_mean', 0):.4f}" if metrics.get('spread_mean') is not None else "--")
        self.spread_std_label.setText(f"{metrics.get('spread_std', 0):.4f}" if metrics.get('spread_std') is not None else "--")

        self.mean_drift_label.setText(f"{metrics.get('mean_drift', 0):.4f}" if metrics.get('mean_drift') is not None else "--")
        self.max_z_score_label.setText(f"{metrics.get('max_z_score', 0):.2f}" if metrics.get('max_z_score') is not None else "--")
        self.min_z_score_label.setText(f"{metrics.get('min_z_score', 0):.2f}" if metrics.get('min_z_score') is not None else "--")
        self.max_mean_label.setText(f"{metrics.get('max_mean', 0):.4f}" if metrics.get('max_mean') is not None else "--")
        self.min_mean_label.setText(f"{metrics.get('min_mean', 0):.4f}" if metrics.get('min_mean') is not None else "--")

        if 'last_update' in metrics:
            self.last_update_label.setText(metrics['last_update'])

    def update_account_info(self, balance, equity, unrealized_pnl, margin_info):
        """Update account information"""
        self.balance_label.setText(f"${balance:,.2f}" if balance is not None else "$0.00")
        self.equity_label.setText(f"${equity:,.2f}" if equity is not None else "$0.00")
        self.unrealized_pnl_label.setText(f"${unrealized_pnl:,.2f}" if unrealized_pnl is not None else "$0.00")

        # Color code unrealized P&L
        if unrealized_pnl and unrealized_pnl > 0:
            self.unrealized_pnl_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        elif unrealized_pnl and unrealized_pnl < 0:
            self.unrealized_pnl_label.setStyleSheet("color: #e74c3c; font-weight: bold;")

        if margin_info:
            self.used_margin_label.setText(f"${margin_info.get('used', 0):,.2f}")
            self.free_margin_label.setText(f"${margin_info.get('free', 0):,.2f}")
            self.margin_level_label.setText(f"{margin_info.get('level', 0):.1f}%")

    def update_position_overview(self, overview):
        """Update position overview"""
        if not overview:
            return

        self.open_spread_label.setText(str(overview.get('open_spread', 0)))
        self.open_close_label.setText(f"{overview.get('open_positions', 0)} / {overview.get('closed_positions', 0)}")
        self.total_lots_label.setText(f"{overview.get('primary_lots', 0):.2f} / {overview.get('secondary_lots', 0):.2f}")

        hedge_quality = overview.get('hedge_quality', '--')
        self.hedge_quality_label.setText(str(hedge_quality))

        self.imbalance_label.setText(overview.get('imbalance', 'Balanced'))
        self.value_label.setText(f"${overview.get('value', 0):,.2f}")

    def update_risk_manager(self, risk_data):
        """Update risk manager panel"""
        if not risk_data:
            return

        self.setup_risk_pct_label.setText(f"{risk_data.get('setup_risk_pct', 0):.0f}%")
        self.setup_risk_amount_label.setText(f"${risk_data.get('setup_risk_amount', 0):,.0f}")

        self.daily_risk_pct_label.setText(f"{risk_data.get('daily_risk_pct', 0):.0f}%")
        self.daily_risk_limit_label.setText(f"${risk_data.get('daily_risk_limit', 0):,.0f}")

        self.trading_status_label.setText(risk_data.get('trading_status', '--'))
        self.block_time_label.setText(risk_data.get('block_time', '--'))

        self.risk_unrealized_label.setText(f"${risk_data.get('unrealized', 0):,.2f}")
        unrealized = risk_data.get('unrealized', 0)
        if unrealized < 0:
            self.risk_unrealized_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        else:
            self.risk_unrealized_label.setStyleSheet("color: #27ae60; font-weight: bold;")

        self.daily_total_pnl_label.setText(f"${risk_data.get('total_pnl', 0):,.2f}")
        self.unlock_time_label.setText(risk_data.get('unlock_time', '--'))

    def update_pnl_attribution(self, attribution):
        """Update P&L attribution panel"""
        if not attribution:
            return

        self.spread_pnl_label.setText(f"${attribution.get('spread_pnl', 0):,.2f}")
        self.spread_pnl_pct_label.setText(f"{attribution.get('spread_pnl_pct', 0):.1f}%")

        self.mean_drift_pnl_label.setText(f"${attribution.get('mean_drift_pnl', 0):,.2f}")
        self.mean_drift_pnl_pct_label.setText(f"{attribution.get('mean_drift_pnl_pct', 0):.1f}%")

        self.directional_pnl_label.setText(f"${attribution.get('directional_pnl', 0):,.2f}")
        self.directional_pnl_pct_label.setText(f"{attribution.get('directional_pnl_pct', 0):.1f}%")

        self.hedge_imbalance_pnl_label.setText(f"${attribution.get('hedge_imbalance_pnl', 0):,.2f}")
        self.hedge_imbalance_pnl_pct_label.setText(f"{attribution.get('hedge_imbalance_pnl_pct', 0):.1f}%")

        self.transaction_costs_label.setText(f"${attribution.get('transaction_costs', 0):,.2f}")
        self.transaction_costs_pct_label.setText(f"{attribution.get('transaction_costs_pct', 0):.1f}%")

        self.slippage_label.setText(f"${attribution.get('slippage', 0):,.2f}")
        self.slippage_pct_label.setText(f"{attribution.get('slippage_pct', 0):.1f}%")

        self.rebalance_alpha_label.setText(f"${attribution.get('rebalance_alpha', 0):,.2f}")
        self.rebalance_alpha_pct_label.setText(f"{attribution.get('rebalance_alpha_pct', 0):.1f}%")

        self.pnl_hedge_quality_label.setText(attribution.get('hedge_quality', '--'))
        self.strategy_purity_label.setText(attribution.get('strategy_purity', '--'))
        self.classification_label.setText(attribution.get('classification', 'NO DATA'))

    def update_total_pnl(self, pnl):
        """Update total P&L"""
        self.total_pnl_label.setText(f"${pnl:,.2f}" if pnl is not None else "$0.00")

        if pnl and pnl > 0:
            self.total_pnl_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 16px;")
        elif pnl and pnl < 0:
            self.total_pnl_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 16px;")
        else:
            self.total_pnl_label.setStyleSheet("color: #ecf0f1; font-weight: bold; font-size: 16px;")

    def update_status(self, status, color):
        """Update status label"""
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")


class LogsWidget(QWidget):
    """Logs display widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        """Initialize logs UI"""
        layout = QVBoxLayout(self)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier New", 9))
        layout.addWidget(self.log_display)

        # Clear button
        button_layout = QHBoxLayout()
        clear_btn = QPushButton("🗑️ Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        button_layout.addWidget(clear_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

    def add_log(self, message):
        """Add log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")

    def clear_logs(self):
        """Clear all logs"""
        self.log_display.clear()

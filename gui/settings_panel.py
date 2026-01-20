"""
Settings Panel - Configuration and Backend Connection
Handles all settings controls, symbol inputs, and backend connections
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
    QCheckBox, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import logging

logger = logging.getLogger(__name__)


class SettingsPanel(QWidget):
    """
    Settings Panel Widget
    Contains all configuration controls for the trading system
    """

    # Signals to notify main window
    settings_saved = pyqtSignal()  # Emitted when settings are saved
    settings_applied = pyqtSignal()  # Emitted when settings are applied
    symbol_changed = pyqtSignal(str, str)  # Emitted when symbols change (primary, secondary)

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.init_ui()

    def init_ui(self):
        """Initialize the settings panel UI"""
        layout = QVBoxLayout(self)

        # Note: Symbol selection is in Dashboard tab, not here
        # Create hidden inputs for internal use (get_symbols, set_symbols methods)
        self.primary_input = QLineEdit()
        self.primary_input.setText("BTCUSD")
        self.primary_input.hide()

        self.secondary_input = QLineEdit()
        self.secondary_input.setText("ETHUSD")
        self.secondary_input.hide()

        # ========== Parameter Sections in Splitter ==========
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Trading Parameters
        trading_group = self._create_trading_params()
        splitter.addWidget(trading_group)

        # Model Parameters
        model_group = self._create_model_params()
        splitter.addWidget(model_group)

        # Risk Management
        risk_group = self._create_risk_params()
        splitter.addWidget(risk_group)

        # Advanced Settings
        advanced_group = self._create_advanced_params()
        splitter.addWidget(advanced_group)

        layout.addWidget(splitter)

        # ========== Action Buttons ==========
        button_layout = QHBoxLayout()

        save_btn = QPushButton("💾 Save Settings")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setToolTip("Save settings to config file")
        button_layout.addWidget(save_btn)

        apply_btn = QPushButton("✅ Apply to Current Pair")
        apply_btn.clicked.connect(self.apply_settings)
        apply_btn.setToolTip("Apply settings to running system")
        button_layout.addWidget(apply_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

    def _create_trading_params(self):
        """Create trading parameters group"""
        group = QGroupBox("Trading Parameters")
        layout = QGridLayout()

        row = 0
        layout.addWidget(QLabel("Entry Z-Score:"), row, 0)
        self.entry_zscore_spin = QDoubleSpinBox()
        self.entry_zscore_spin.setRange(0.1, 5.0)
        self.entry_zscore_spin.setValue(2.0)
        self.entry_zscore_spin.setSingleStep(0.1)
        layout.addWidget(self.entry_zscore_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Exit Z-Score:"), row, 0)
        self.exit_zscore_spin = QDoubleSpinBox()
        self.exit_zscore_spin.setRange(0.0, 2.0)
        self.exit_zscore_spin.setValue(0.5)
        self.exit_zscore_spin.setSingleStep(0.1)
        layout.addWidget(self.exit_zscore_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Stop Loss Z-Score:"), row, 0)
        self.stop_zscore_spin = QDoubleSpinBox()
        self.stop_zscore_spin.setRange(2.0, 10.0)
        self.stop_zscore_spin.setValue(3.5)
        self.stop_zscore_spin.setSingleStep(0.5)
        layout.addWidget(self.stop_zscore_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Max Positions:"), row, 0)
        self.max_positions_spin = QSpinBox()
        self.max_positions_spin.setRange(1, 20)
        self.max_positions_spin.setValue(10)
        layout.addWidget(self.max_positions_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Volume Multiplier:"), row, 0)
        self.volume_mult_spin = QDoubleSpinBox()
        self.volume_mult_spin.setRange(0.01, 10000.0)
        self.volume_mult_spin.setValue(1.0)
        self.volume_mult_spin.setSingleStep(0.1)
        layout.addWidget(self.volume_mult_spin, row, 1)

        group.setLayout(layout)
        return group

    def _create_model_params(self):
        """Create model parameters group"""
        group = QGroupBox("Model Parameters")
        layout = QGridLayout()

        row = 0
        layout.addWidget(QLabel("Rolling Window:"), row, 0)
        self.window_spin = QSpinBox()
        self.window_spin.setRange(50, 2000)
        self.window_spin.setValue(1000)
        self.window_spin.setSingleStep(10)
        layout.addWidget(self.window_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Update Interval (s):"), row, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 300)
        self.interval_spin.setValue(5)
        layout.addWidget(self.interval_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Hedge Drift Threshold:"), row, 0)
        self.hedge_drift_spin = QDoubleSpinBox()
        self.hedge_drift_spin.setRange(0.01, 0.5)
        self.hedge_drift_spin.setValue(0.05)
        self.hedge_drift_spin.setSingleStep(0.01)
        layout.addWidget(self.hedge_drift_spin, row, 1)

        row += 1
        self.pyramiding_check = QCheckBox("Enable Pyramiding")
        self.pyramiding_check.setChecked(True)
        layout.addWidget(self.pyramiding_check, row, 0, 1, 2)

        row += 1
        self.hedge_adjust_check = QCheckBox("Enable Hedge Adjustment")
        self.hedge_adjust_check.setChecked(True)
        layout.addWidget(self.hedge_adjust_check, row, 0, 1, 2)

        row += 1
        self.entry_cooldown_check = QCheckBox("Enable Entry Cooldown")
        self.entry_cooldown_check.setChecked(True)
        self.entry_cooldown_check.setToolTip("Prevent duplicate entries when z-score oscillates")
        layout.addWidget(self.entry_cooldown_check, row, 0, 1, 2)

        row += 1
        self.manual_sync_check = QCheckBox("Enable Manual Position Sync")
        self.manual_sync_check.setChecked(True)
        self.manual_sync_check.setToolTip("Auto-detect and rebalance manual MT5 positions")
        layout.addWidget(self.manual_sync_check, row, 0, 1, 2)

        group.setLayout(layout)
        return group

    def _create_risk_params(self):
        """Create risk management parameters group"""
        group = QGroupBox("Risk Management")
        layout = QGridLayout()

        # Explanation
        explanation = QLabel(
            "📌 TWO TYPES OF RISK LIMITS:\n"
            "• Risk Per Setup: Max % loss per trade\n"
            "• Daily Risk: Max % loss per day"
        )
        explanation.setStyleSheet(
            "background-color: #34495e; "
            "padding: 8px; "
            "border-radius: 4px; "
            "color: #ecf0f1; "
            "font-size: 10px;"
        )
        layout.addWidget(explanation, 0, 0, 1, 2)

        row = 1
        layout.addWidget(QLabel("Max Position %:"), row, 0)
        self.max_pos_pct_spin = QDoubleSpinBox()
        self.max_pos_pct_spin.setRange(1.0, 50.0)
        self.max_pos_pct_spin.setValue(20.0)
        self.max_pos_pct_spin.setSuffix("%")
        layout.addWidget(self.max_pos_pct_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Risk Per Setup:"), row, 0)
        self.max_risk_pct_spin = QDoubleSpinBox()
        self.max_risk_pct_spin.setRange(0.5, 10.0)
        self.max_risk_pct_spin.setValue(2.0)
        self.max_risk_pct_spin.setSuffix("%")
        self.max_risk_pct_spin.setToolTip("Max risk per individual trade as % of balance")
        layout.addWidget(self.max_risk_pct_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Daily Risk Limit:"), row, 0)
        self.daily_loss_spin = QDoubleSpinBox()
        self.daily_loss_spin.setRange(1.0, 20.0)
        self.daily_loss_spin.setValue(5.0)
        self.daily_loss_spin.setSuffix("%")
        self.daily_loss_spin.setDecimals(1)
        self.daily_loss_spin.setToolTip("Max total daily loss as % of balance")
        layout.addWidget(self.daily_loss_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Session Start:"), row, 0)
        self.session_start_input = QLineEdit()
        self.session_start_input.setText("00:00")
        self.session_start_input.setPlaceholderText("HH:MM")
        self.session_start_input.setMaxLength(5)
        self.session_start_input.setToolTip("Daily P&L resets at this time")
        layout.addWidget(self.session_start_input, row, 1)

        row += 1
        layout.addWidget(QLabel("Session End:"), row, 0)
        self.session_end_input = QLineEdit()
        self.session_end_input.setText("23:59")
        self.session_end_input.setPlaceholderText("HH:MM")
        self.session_end_input.setMaxLength(5)
        layout.addWidget(self.session_end_input, row, 1)

        group.setLayout(layout)
        return group

    def _create_advanced_params(self):
        """Create advanced settings group"""
        group = QGroupBox("⚙️ Advanced Settings")
        layout = QGridLayout()

        row = 0
        layout.addWidget(QLabel("Scale Interval:"), row, 0)
        self.scale_interval_spin = QDoubleSpinBox()
        self.scale_interval_spin.setRange(0.1, 2.0)
        self.scale_interval_spin.setSingleStep(0.1)
        self.scale_interval_spin.setValue(0.1)
        self.scale_interval_spin.setToolTip("Pyramiding interval in z-score units")
        layout.addWidget(self.scale_interval_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Initial Fraction:"), row, 0)
        self.initial_fraction_spin = QDoubleSpinBox()
        self.initial_fraction_spin.setRange(0.1, 1.0)
        self.initial_fraction_spin.setSingleStep(0.05)
        self.initial_fraction_spin.setValue(0.33)
        self.initial_fraction_spin.setDecimals(2)
        self.initial_fraction_spin.setToolTip("First entry fraction (0.33 = 33%)")
        layout.addWidget(self.initial_fraction_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Min Adjust Interval (s):"), row, 0)
        self.min_adjust_interval_spin = QSpinBox()
        self.min_adjust_interval_spin.setRange(300, 14400)
        self.min_adjust_interval_spin.setSingleStep(300)
        self.min_adjust_interval_spin.setValue(3600)
        self.min_adjust_interval_spin.setToolTip("Min time between hedge adjustments")
        layout.addWidget(self.min_adjust_interval_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Magic Number:"), row, 0)
        self.magic_number_spin = QSpinBox()
        self.magic_number_spin.setRange(100000, 999999)
        self.magic_number_spin.setValue(234000)
        self.magic_number_spin.setToolTip("MT5 Magic Number for identification")
        layout.addWidget(self.magic_number_spin, row, 1)

        row += 1
        layout.addWidget(QLabel("Z-Score History Size:"), row, 0)
        self.zscore_history_spin = QSpinBox()
        self.zscore_history_spin.setRange(50, 1000)
        self.zscore_history_spin.setSingleStep(50)
        self.zscore_history_spin.setValue(200)
        layout.addWidget(self.zscore_history_spin, row, 1)

        group.setLayout(layout)
        return group

    def _on_symbol_changed(self):
        """Internal handler when symbols change"""
        primary = self.primary_input.text().strip().upper()
        secondary = self.secondary_input.text().strip().upper()
        if primary and secondary:
            self.symbol_changed.emit(primary, secondary)

    def get_symbols(self):
        """Get current symbol pair"""
        return (
            self.primary_input.text().strip().upper(),
            self.secondary_input.text().strip().upper()
        )

    def set_symbols(self, primary, secondary):
        """Set symbol pair"""
        self.primary_input.setText(primary)
        self.secondary_input.setText(secondary)

    def save_settings(self):
        """Save settings to config file"""
        try:
            settings = self.settings_manager.get()

            # Update settings from GUI controls
            settings.entry_threshold = self.entry_zscore_spin.value()
            settings.exit_threshold = self.exit_zscore_spin.value()
            settings.stop_loss_zscore = self.stop_zscore_spin.value()
            settings.max_positions = self.max_positions_spin.value()
            settings.volume_multiplier = self.volume_mult_spin.value()

            settings.rolling_window_size = self.window_spin.value()
            settings.update_interval = self.interval_spin.value()
            settings.hedge_drift_threshold = self.hedge_drift_spin.value()

            settings.max_position_pct = self.max_pos_pct_spin.value()
            settings.max_risk_pct = self.max_risk_pct_spin.value()
            settings.daily_loss_limit_pct = self.daily_loss_spin.value()
            settings.session_start_time = self.session_start_input.text()
            settings.session_end_time = self.session_end_input.text()

            settings.enable_pyramiding = self.pyramiding_check.isChecked()
            settings.enable_hedge_adjustment = self.hedge_adjust_check.isChecked()
            settings.enable_entry_cooldown = self.entry_cooldown_check.isChecked()
            settings.enable_manual_position_sync = self.manual_sync_check.isChecked()

            settings.scale_interval = self.scale_interval_spin.value()
            settings.initial_fraction = self.initial_fraction_spin.value()
            settings.min_adjustment_interval = self.min_adjust_interval_spin.value()
            settings.magic_number = self.magic_number_spin.value()
            settings.zscore_history_size = self.zscore_history_spin.value()

            # Save to file
            self.settings_manager.save()

            QMessageBox.information(self, "Success", "Settings saved successfully!")
            self.settings_saved.emit()
            logger.info("Settings saved successfully")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
            logger.error(f"Failed to save settings: {e}")

    def apply_settings(self):
        """Apply settings to running system"""
        # This will be handled by the main window
        self.settings_applied.emit()
        logger.info("Settings apply requested")

    def load_settings(self):
        """Load settings from config into GUI controls"""
        try:
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

            logger.info("Settings loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            QMessageBox.warning(self, "Warning", f"Failed to load some settings: {e}")

"""
Config Sync Indicator Widget
Shows visual indicator when GUI config differs from running system
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QToolTip, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QCursor
import logging

logger = logging.getLogger(__name__)


class ConfigSyncIndicator(QWidget):
    """
    Visual indicator showing config sync status between GUI and running system

    States:
    - Synced (green): GUI config matches running system
    - Out of sync (orange): GUI has unsaved changes
    - Not running (gray): System not running
    """

    # Signals
    apply_clicked = pyqtSignal()  # User wants to apply changes
    details_clicked = pyqtSignal()  # User wants to see diff details

    # Style constants
    STYLE_SYNCED = """
        QWidget {
            background-color: #27ae60;
            border-radius: 4px;
            padding: 2px 8px;
        }
        QLabel {
            color: white;
            font-size: 11px;
        }
    """

    STYLE_OUT_OF_SYNC = """
        QWidget {
            background-color: #e67e22;
            border-radius: 4px;
            padding: 2px 8px;
        }
        QLabel {
            color: white;
            font-size: 11px;
            font-weight: bold;
        }
    """

    STYLE_NOT_RUNNING = """
        QWidget {
            background-color: #7f8c8d;
            border-radius: 4px;
            padding: 2px 8px;
        }
        QLabel {
            color: white;
            font-size: 11px;
        }
    """

    STYLE_APPLY_BTN = """
        QPushButton {
            background-color: #3498db;
            color: white;
            border: none;
            border-radius: 3px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #2980b9;
        }
        QPushButton:pressed {
            background-color: #1f618d;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_synced = True
        self._is_running = False
        self._change_count = 0
        self._tooltip_text = ""
        self._blink_state = False

        self._setup_blink_timer()  # Must be before _init_ui() which calls _update_display()
        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Status icon/indicator
        self.status_icon = QLabel("●")
        self.status_icon.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.status_icon)

        # Status text
        self.status_label = QLabel("Config Synced")
        self.status_label.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.status_label)

        # Apply button (hidden when synced)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setStyleSheet(self.STYLE_APPLY_BTN)
        self.apply_btn.setFixedHeight(20)
        self.apply_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.apply_btn.setToolTip("Apply changes to running system (Hot-Reload)")
        self.apply_btn.hide()
        layout.addWidget(self.apply_btn)

        # Set initial state
        self._update_display()

        # Enable click for details
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _setup_blink_timer(self):
        """Setup timer for blinking when out of sync"""
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.setInterval(500)  # Blink every 500ms

    def _toggle_blink(self):
        """Toggle blink state for attention"""
        self._blink_state = not self._blink_state
        if self._blink_state:
            self.status_icon.setStyleSheet("color: #f39c12;")  # Orange
        else:
            self.status_icon.setStyleSheet("color: #e74c3c;")  # Red

    def set_synced(self, is_synced: bool, change_count: int = 0, tooltip: str = ""):
        """Set sync status"""
        self._is_synced = is_synced
        self._change_count = change_count
        self._tooltip_text = tooltip
        self._update_display()

    def set_running(self, is_running: bool):
        """Set whether trading system is running"""
        self._is_running = is_running
        self._update_display()

    def _update_display(self):
        """Update visual display based on current state"""
        if not self._is_running:
            # Not running - gray
            self.status_icon.setText("●")
            self.status_icon.setStyleSheet("color: #95a5a6;")
            self.status_label.setText("System Stopped")
            self.status_label.setStyleSheet("color: #95a5a6;")
            self.apply_btn.hide()
            self._blink_timer.stop()
            self.setToolTip("Start trading system to enable config sync")

        elif self._is_synced:
            # Synced - green
            self.status_icon.setText("✓")
            self.status_icon.setStyleSheet("color: #27ae60;")
            self.status_label.setText("Config Synced")
            self.status_label.setStyleSheet("color: #27ae60;")
            self.apply_btn.hide()
            self._blink_timer.stop()
            self.setToolTip("GUI settings match running system")

        else:
            # Out of sync - orange/red with blink
            self.status_icon.setText("⚠")
            self.status_label.setText(f"{self._change_count} Unsaved")
            self.status_label.setStyleSheet("color: #e67e22; font-weight: bold;")
            self.apply_btn.show()
            self._blink_timer.start()

            # Build tooltip
            if self._tooltip_text:
                self.setToolTip(f"Click 'Apply' to sync changes:\n{self._tooltip_text}")
            else:
                self.setToolTip(f"{self._change_count} setting(s) differ from running system.\nClick 'Apply' to hot-reload.")

    def _on_apply_clicked(self):
        """Handle apply button click"""
        self.apply_clicked.emit()

    def mousePressEvent(self, event):
        """Handle click on indicator"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.details_clicked.emit()
        super().mousePressEvent(event)


class ConfigSyncStatusBar(QFrame):
    """
    Full status bar showing config sync status with more details
    Can be placed at bottom of settings panel or main window
    """

    apply_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self._init_ui()

    def _init_ui(self):
        """Initialize UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Sync indicator
        self.indicator = ConfigSyncIndicator()
        self.indicator.apply_clicked.connect(self._on_apply)
        layout.addWidget(self.indicator)

        layout.addStretch()

        # Last sync time
        self.sync_time_label = QLabel("")
        self.sync_time_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        layout.addWidget(self.sync_time_label)

        # Minimal styling
        self.setStyleSheet("""
            QFrame {
                background-color: #3C3F41;
                border-top: 1px solid #2d2d2d;
            }
        """)

    def _on_apply(self):
        """Forward apply signal"""
        self.apply_clicked.emit()

    def set_status(self, is_running: bool, is_synced: bool,
                   change_count: int = 0, tooltip: str = "",
                   last_sync_time: str = ""):
        """Update status bar"""
        self.indicator.set_running(is_running)
        self.indicator.set_synced(is_synced, change_count, tooltip)

        if last_sync_time:
            self.sync_time_label.setText(f"Last sync: {last_sync_time}")
        else:
            self.sync_time_label.setText("")

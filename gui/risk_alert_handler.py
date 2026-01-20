"""
Risk Alert Handler for GUI
Receives risk alerts from RiskManagementThread and displays them
"""
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QScreen
import logging

logger = logging.getLogger(__name__)


class RiskAlertHandler(QObject):
    """
    Signal handler for risk alerts from background threads
    Thread-safe alert system using Qt signals
    Displays alerts at TOP of screen for visibility
    """
    alert_signal = pyqtSignal(str, str, str)  # level, title, message

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.alert_signal.connect(self._show_alert)
        logger.info("Risk alert handler initialized")

    def emit_alert(self, level: str, title: str, message: str):
        """
        Emit alert from background thread (thread-safe)

        Args:
            level: 'CRITICAL', 'WARNING', or 'INFO'
            title: Alert title
            message: Alert message
        """
        self.alert_signal.emit(level, title, message)

    def _show_alert(self, level: str, title: str, message: str):
        """Show alert in main GUI thread at TOP of screen (called by signal)"""
        try:
            # Create message box
            msg_box = QMessageBox(self.parent)
            msg_box.setWindowTitle(f"🚨 {title}" if level == 'CRITICAL' else
                                   f"⚠️  {title}" if level == 'WARNING' else
                                   f"ℹ️  {title}")
            msg_box.setText(message)

            # Set icon based on level
            if level == 'CRITICAL':
                msg_box.setIcon(QMessageBox.Icon.Critical)
            elif level == 'WARNING':
                msg_box.setIcon(QMessageBox.Icon.Warning)
            else:
                msg_box.setIcon(QMessageBox.Icon.Information)

            # Make it stay on top and modal
            msg_box.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
            msg_box.setModal(True)

            # Position at TOP of screen
            msg_box.show()  # Show first to get correct size

            # Get screen geometry
            screen = QScreen.availableGeometry(msg_box.screen())

            # Calculate position: horizontally centered, top of screen
            x = screen.x() + (screen.width() - msg_box.width()) // 2
            y = screen.y() + 50  # 50px from top

            msg_box.move(x, y)

            # Execute (blocking)
            msg_box.exec()

            logger.info(f"Displayed {level} alert at top of screen: {title}")
        except Exception as e:
            logger.error(f"Error showing alert: {e}")

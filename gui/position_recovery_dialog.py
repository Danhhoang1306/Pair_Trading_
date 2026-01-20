"""
Position Recovery Confirmation Dialog
Shows user what positions exist in MT5 and asks for confirmation
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QLabel, QGroupBox, QRadioButton, QButtonGroup)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from typing import List, Dict


class PositionRecoveryDialog(QDialog):
    """
    Dialog to confirm position recovery from MT5
    
    Shows:
    - List of positions found in MT5
    - Spread grouping
    - Validation status
    - Options: Resume, Close All, Cancel
    """
    
    def __init__(self, recovery_report: str, spreads: Dict[str, List[Dict]], parent=None):
        super().__init__(parent)
        
        self.recovery_report = recovery_report
        self.spreads = spreads
        self.user_choice = None  # 'resume', 'close_all', or 'cancel'
        
        self.setWindowTitle("Position Recovery - Confirm Action")
        self.setModal(True)
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("🔍 MT5 POSITIONS DETECTED")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Warning message
        warning = QLabel(
            "⚠️  Existing positions found in MT5!\n"
            "Please review and choose how to proceed:"
        )
        warning.setFont(QFont("Arial", 11))
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setStyleSheet("color: #e67e22; padding: 10px;")
        layout.addWidget(warning)
        
        # Report display
        report_group = QGroupBox("Position Details")
        report_layout = QVBoxLayout()
        
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setFont(QFont("Courier New", 9))
        self.report_text.setPlainText(self.recovery_report)
        report_layout.addWidget(self.report_text)
        
        report_group.setLayout(report_layout)
        layout.addWidget(report_group)
        
        # Options
        options_group = QGroupBox("Choose Action")
        options_layout = QVBoxLayout()
        
        self.button_group = QButtonGroup()
        
        # Option 1: Resume
        self.resume_radio = QRadioButton(
            f"✅ RESUME - Continue trading with {len(self.spreads)} existing spread(s)"
        )
        self.resume_radio.setFont(QFont("Arial", 10))
        self.resume_radio.setStyleSheet("color: #27ae60;")
        self.button_group.addButton(self.resume_radio, 1)
        options_layout.addWidget(self.resume_radio)
        
        resume_desc = QLabel(
            "   → System will manage existing positions\n"
            "   → Continue with current strategy\n"
            "   → Recommended if positions are valid"
        )
        resume_desc.setFont(QFont("Arial", 9))
        resume_desc.setStyleSheet("color: #95a5a6; margin-left: 30px;")
        options_layout.addWidget(resume_desc)
        
        # Option 2: Close All
        self.close_all_radio = QRadioButton(
            "🔴 CLOSE ALL - Close all positions and start fresh"
        )
        self.close_all_radio.setFont(QFont("Arial", 10))
        self.close_all_radio.setStyleSheet("color: #e74c3c;")
        self.button_group.addButton(self.close_all_radio, 2)
        options_layout.addWidget(self.close_all_radio)
        
        close_desc = QLabel(
            "   → Close all MT5 positions immediately\n"
            "   → Start with clean slate\n"
            "   → Use if positions are invalid or unknown"
        )
        close_desc.setFont(QFont("Arial", 9))
        close_desc.setStyleSheet("color: #95a5a6; margin-left: 30px;")
        options_layout.addWidget(close_desc)
        
        # Option 3: Cancel
        self.cancel_radio = QRadioButton(
            "⏸️  CANCEL - Exit without starting trading"
        )
        self.cancel_radio.setFont(QFont("Arial", 10))
        self.cancel_radio.setStyleSheet("color: #95a5a6;")
        self.button_group.addButton(self.cancel_radio, 3)
        options_layout.addWidget(self.cancel_radio)
        
        cancel_desc = QLabel(
            "   → Do not start trading system\n"
            "   → Manually review positions in MT5\n"
            "   → Safe option if unsure"
        )
        cancel_desc.setFont(QFont("Arial", 9))
        cancel_desc.setStyleSheet("color: #95a5a6; margin-left: 30px;")
        options_layout.addWidget(cancel_desc)
        
        # Set default
        self.resume_radio.setChecked(True)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.confirm_btn = QPushButton("✅ Confirm")
        self.confirm_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 10px 30px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.confirm_btn.clicked.connect(self.on_confirm)
        
        button_layout.addStretch()
        button_layout.addWidget(self.confirm_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def on_confirm(self):
        """Handle confirm button click"""
        selected_id = self.button_group.checkedId()
        
        if selected_id == 1:
            self.user_choice = 'resume'
        elif selected_id == 2:
            self.user_choice = 'close_all'
        else:
            self.user_choice = 'cancel'
        
        self.accept()
    
    def get_user_choice(self) -> str:
        """Get user's choice after dialog closes"""
        return self.user_choice


# Example usage
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Example report
    report = """
======================================================================
MT5 POSITION RECOVERY REPORT
======================================================================
Total positions found: 6

Spread groups found: 3

Spread ID: abc123
--------------------------------------------------
✅ Status: VALID HEDGE
   XAU: 0.0100 lots
   XAG: 0.0072 lots (ideal: 0.0072)
   Imbalance: +0.0000 lots (+0.00%)
   XAU: XAUUSD LONG 0.0100 @ $2650.50 | P&L: $+125.50
   XAG: XAGUSD SHORT 0.0072 @ $79.25 | P&L: $-23.10

Spread ID: def456
--------------------------------------------------
❌ Status: Missing XAG leg
   XAU: XAUUSD SHORT 0.0200 @ $2655.00 | P&L: $-85.00

Spread ID: unknown
--------------------------------------------------
❌ Status: Both legs are LONG (should be opposite)
   XAU: XAUUSD LONG 0.0100 @ $2648.00 | P&L: $+45.00
   XAG: XAGUSD LONG 0.0100 @ $79.10 | P&L: $+12.50

======================================================================
    """
    
    spreads = {
        'abc123': [],
        'def456': [],
        'unknown': []
    }
    
    dialog = PositionRecoveryDialog(report, spreads)
    result = dialog.exec()
    
    if result == QDialog.DialogCode.Accepted:
        print(f"User choice: {dialog.get_user_choice()}")
    else:
        print("Dialog rejected")

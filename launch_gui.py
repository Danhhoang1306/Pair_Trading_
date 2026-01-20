"""
Pair Trading System - GUI Launcher
Launch the professional trading interface with full integration
"""

import sys
from pathlib import Path

# Add project root to path (CRITICAL for imports to work)
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def check_license_gui():
    """
    Check license using GUI dialogs (works in windowed mode)
    """
    from licensing.license_validator import validate_license
    from licensing.license_manager import get_license_manager

    is_valid, message = validate_license()

    if not is_valid:
        # Import PyQt6 for dialogs
        from PyQt6.QtWidgets import (
            QApplication, QMessageBox, QDialog, QVBoxLayout,
            QLabel, QLineEdit, QPushButton, QFormLayout
        )
        from PyQt6.QtCore import Qt

        # Create app if not exists
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        # Show license required message
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("License Required")
        msg.setText("Pair Trading Pro - License Required")
        msg.setInformativeText(f"{message}\n\nDo you want to activate a license now?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)

        result = msg.exec()

        if result == QMessageBox.StandardButton.Yes:
            # Show activation dialog
            dialog = QDialog()
            dialog.setWindowTitle("License Activation")
            dialog.setMinimumWidth(400)

            layout = QVBoxLayout()

            # Title
            title = QLabel("Enter your license information:")
            title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
            layout.addWidget(title)

            # Form
            form = QFormLayout()

            key_input = QLineEdit()
            key_input.setPlaceholderText("PTP20-XXXX-XXXX-XXXX-XXXX")
            form.addRow("License Key:", key_input)

            name_input = QLineEdit()
            name_input.setPlaceholderText("Your Name")
            form.addRow("Your Name:", name_input)

            email_input = QLineEdit()
            email_input.setPlaceholderText("your@email.com")
            form.addRow("Your Email:", email_input)

            layout.addLayout(form)

            # Status label
            status_label = QLabel("")
            status_label.setStyleSheet("color: red; margin-top: 10px;")
            layout.addWidget(status_label)

            # Buttons
            activate_btn = QPushButton("Activate")
            activate_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    padding: 10px;
                    font-size: 14px;
                    border: none;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)

            def do_activate():
                license_key = key_input.text().strip()
                name = name_input.text().strip()
                email = email_input.text().strip()

                if not license_key or not name or not email:
                    status_label.setText("All fields are required!")
                    return

                manager = get_license_manager()
                success, msg = manager.activate_license(license_key, name, email)

                if success:
                    QMessageBox.information(
                        dialog,
                        "Success",
                        f"License activated successfully!\n\n{msg}"
                    )
                    dialog.accept()
                else:
                    status_label.setText(f"Activation failed: {msg}")

            activate_btn.clicked.connect(do_activate)
            layout.addWidget(activate_btn)

            # Cancel button
            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(dialog.reject)
            layout.addWidget(cancel_btn)

            # Contact info
            contact = QLabel("Contact: license@pairtradingpro.com")
            contact.setStyleSheet("color: gray; font-size: 11px; margin-top: 10px;")
            contact.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(contact)

            dialog.setLayout(layout)

            if dialog.exec() != QDialog.DialogCode.Accepted:
                # User cancelled
                QMessageBox.critical(
                    None,
                    "License Required",
                    "A valid license is required to use this software.\n\n"
                    "Please contact license@pairtradingpro.com to purchase."
                )
                sys.exit(1)

            # Verify license after activation
            is_valid, _ = validate_license()
            if not is_valid:
                sys.exit(1)

        else:
            # User chose not to activate
            QMessageBox.critical(
                None,
                "License Required",
                "A valid license is required to use this software.\n\n"
                "Please contact license@pairtradingpro.com to purchase."
            )
            sys.exit(1)

    return True


def main():
    """Main entry point"""
    # Check license first (using GUI dialogs)
    check_license_gui()

    # Show license status
    from licensing.license_manager import get_license_manager
    manager = get_license_manager()
    info = manager.get_license_info()
    if info:
        print(f"\n  License: {info.license_type.value.upper()} | "
              f"Expires: {info.expiry_date.strftime('%Y-%m-%d')} | "
              f"{info.days_remaining()} days remaining")

    # Continue with normal startup
    print(f"\n  Project root: {project_root}")
    print("")

    print("=" * 70)
    print("  Pair Trading System - Professional Edition")
    print("  Fully Integrated GUI with Trading Logic")
    print("=" * 70)
    print("")

    # Step 1: Initialize unified configuration system
    from config.manager import get_config
    print("Step 1: Loading Configuration (Unified System)...")
    config_manager = get_config()

    # Display loaded configuration
    pairs = config_manager.get_all_pairs()
    print(f"  Loaded {len(pairs)} trading pairs:")
    for name, pair in pairs.items():
        print(f"    - {name}: {pair.primary_symbol}/{pair.secondary_symbol} ({pair.risk_level})")
    print("")

    # Step 2: Launch GUI with unified configuration
    print("Step 2: Starting GUI...")

    from gui.main_window_integrated import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()

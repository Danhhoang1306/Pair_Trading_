"""
Pair Discovery Tab - GUI
User interface for discovering and analyzing trading pairs
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit,
    QComboBox, QCheckBox, QSplitter, QMessageBox, QTabWidget,
    QScrollArea
)
from PyQt6.QtCore import Qt, QDate, pyqtSlot
from PyQt6.QtGui import QFont, QColor
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analysis.discovery_engine import PairDiscoveryEngine
import logging

logger = logging.getLogger(__name__)


class PairDiscoveryTab(QWidget):
    """
    Tab for discovering and analyzing trading pairs
    Runs analysis in background without blocking GUI
    """
    
    def __init__(self):
        super().__init__()
        
        # Create discovery engine
        self.engine = PairDiscoveryEngine()
        
        # State
        self.current_results = []
        self.selected_pair = None
        
        # Setup UI
        self.setup_ui()
        
        # Connect engine signals
        self.connect_signals()
        
        logger.info("Pair Discovery Tab initialized")
    
    def setup_ui(self):
        """Setup the user interface"""
        main_layout = QVBoxLayout(self)
        
        # Create splitter for top/bottom sections
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # ========== TOP SECTION: PARAMETERS & PROGRESS ==========
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        # Parameters group
        params_group = self.create_parameters_group()
        top_layout.addWidget(params_group)
        
        # Progress group
        progress_group = self.create_progress_group()
        top_layout.addWidget(progress_group)
        
        splitter.addWidget(top_widget)
        
        # ========== BOTTOM SECTION: RESULTS ==========
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # Results table
        results_group = self.create_results_group()
        bottom_layout.addWidget(results_group)
        
        splitter.addWidget(bottom_widget)
        
        # Set splitter sizes (40% top, 60% bottom)
        splitter.setSizes([400, 600])
        
        main_layout.addWidget(splitter)
    
    def create_parameters_group(self):
        """Create parameters configuration group"""
        group = QGroupBox("📊 Analysis Parameters")
        layout = QGridLayout()
        
        # ========== ROW 0: DATE RANGE ==========
        layout.addWidget(QLabel("Start Date:"), 0, 0)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addYears(-1))  # 1 year ago
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        layout.addWidget(self.start_date, 0, 1)
        
        layout.addWidget(QLabel("End Date:"), 0, 2)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        layout.addWidget(self.end_date, 0, 3)
        
        # ========== ROW 1: WINDOW SIZE & CORRELATION ==========
        layout.addWidget(QLabel("Window Size:"), 1, 0)
        self.window_size = QComboBox()
        self.window_size.addItems(['200', '500', '1000', '2000', '5000'])
        self.window_size.setCurrentText('1000')
        layout.addWidget(self.window_size, 1, 1)
        
        layout.addWidget(QLabel("Min Correlation:"), 1, 2)
        self.min_correlation = QDoubleSpinBox()
        self.min_correlation.setRange(0.0, 1.0)
        self.min_correlation.setSingleStep(0.05)
        self.min_correlation.setValue(0.70)
        self.min_correlation.setDecimals(2)
        self.min_correlation.setSuffix(" (70%)")
        layout.addWidget(self.min_correlation, 1, 3)
        
        # Update suffix when value changes
        self.min_correlation.valueChanged.connect(
            lambda v: self.min_correlation.setSuffix(f" ({int(v*100)}%)")
        )
        
        # ========== ROW 2: SYMBOL SELECTION MODE ==========
        layout.addWidget(QLabel("Analysis Mode:"), 2, 0)
        self.auto_detect = QCheckBox("Auto-detect all MT5 symbols")
        self.auto_detect.setChecked(True)
        self.auto_detect.stateChanged.connect(self.on_mode_changed)
        layout.addWidget(self.auto_detect, 2, 1, 1, 3)
        
        # ========== ROW 3: SINGLE PAIR SELECTION (Hidden by default) ==========
        self.single_pair_label1 = QLabel("Symbol 1:")
        self.single_pair_label1.setVisible(False)
        layout.addWidget(self.single_pair_label1, 3, 0)
        
        self.symbol1_combo = QComboBox()
        self.symbol1_combo.setVisible(False)
        self.symbol1_combo.setEditable(True)  # Allow typing
        layout.addWidget(self.symbol1_combo, 3, 1)
        
        self.single_pair_label2 = QLabel("Symbol 2:")
        self.single_pair_label2.setVisible(False)
        layout.addWidget(self.single_pair_label2, 3, 2)
        
        self.symbol2_combo = QComboBox()
        self.symbol2_combo.setVisible(False)
        self.symbol2_combo.setEditable(True)  # Allow typing
        layout.addWidget(self.symbol2_combo, 3, 3)
        
        # ========== ROW 4: BUTTONS ==========
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("🚀 START ANALYSIS")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.start_btn.clicked.connect(self.on_start_analysis)
        button_layout.addWidget(self.start_btn)
        
        self.cancel_btn = QPushButton("❌ CANCEL")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.on_cancel_analysis)
        button_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("💾 SAVE RESULTS")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save_results)
        button_layout.addWidget(self.save_btn)
        
        self.load_btn = QPushButton("📂 LOAD RESULTS")
        self.load_btn.clicked.connect(self.on_load_results)
        button_layout.addWidget(self.load_btn)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout, 4, 0, 1, 4)
        
        group.setLayout(layout)
        
        # Load available symbols for combo boxes
        self.load_available_symbols()
        
        return group
    
    def create_progress_group(self):
        """Create progress tracking group"""
        group = QGroupBox("⏳ Analysis Progress")
        layout = QVBoxLayout()
        
        # Current phase label
        self.phase_label = QLabel("Ready to start analysis")
        self.phase_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.phase_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v/%m")
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # Log area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(100)
        self.log_area.setStyleSheet("background-color: #2c3e50; color: #ecf0f1; font-family: 'Courier New';")
        layout.addWidget(self.log_area)
        
        group.setLayout(layout)
        return group
    
    def create_results_group(self):
        """Create results display group"""
        group = QGroupBox("📊 Discovery Results")
        layout = QVBoxLayout()
        
        # Results summary
        summary_layout = QHBoxLayout()
        
        self.results_count_label = QLabel("Total Pairs: 0")
        self.results_count_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        summary_layout.addWidget(self.results_count_label)
        
        summary_layout.addStretch()
        
        # Sort/Filter options
        summary_layout.addWidget(QLabel("Sort by:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['Score', 'Correlation', 'Win Rate', 'Sharpe Ratio'])
        self.sort_combo.currentTextChanged.connect(self.on_sort_changed)
        summary_layout.addWidget(self.sort_combo)
        
        summary_layout.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(['All', 'Excellent (⭐⭐⭐⭐⭐)', 'Very Good (⭐⭐⭐⭐)', 'Good (⭐⭐⭐)'])
        self.filter_combo.currentTextChanged.connect(self.on_filter_changed)
        summary_layout.addWidget(self.filter_combo)
        
        layout.addLayout(summary_layout)
        
        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(8)
        self.results_table.setHorizontalHeaderLabels([
            "Rank", "Pair", "Score", "Correlation", "Win Rate", "Sharpe", "Trades", "Rating"
        ])
        
        # Table styling
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # Column widths
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Rank
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Pair
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Score
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Corr
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Win Rate
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Sharpe
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Trades
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)  # Rating
        
        # Double-click to view details
        self.results_table.doubleClicked.connect(self.on_view_details)
        
        layout.addWidget(self.results_table)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        self.view_details_btn = QPushButton("📊 View Details")
        self.view_details_btn.setEnabled(False)
        self.view_details_btn.clicked.connect(self.on_view_details)
        action_layout.addWidget(self.view_details_btn)
        
        self.apply_params_btn = QPushButton("✅ Apply Parameters")
        self.apply_params_btn.setEnabled(False)
        self.apply_params_btn.clicked.connect(self.on_apply_parameters)
        action_layout.addWidget(self.apply_params_btn)
        
        action_layout.addStretch()
        
        layout.addLayout(action_layout)
        
        group.setLayout(layout)
        return group
    
    def connect_signals(self):
        """Connect engine signals to GUI slots"""
        # Get worker signals (will be connected when worker is created)
        pass  # Signals connected in on_start_analysis
    
    def load_available_symbols(self):
        """Load available symbols from MT5 into combo boxes"""
        try:
            from analysis.data_loader import MT5DataLoader
            loader = MT5DataLoader()
            
            if loader.connect():
                symbols = loader.get_available_symbols()
                loader.disconnect()
                
                # Populate both combo boxes
                self.symbol1_combo.clear()
                self.symbol2_combo.clear()
                
                self.symbol1_combo.addItems(symbols)
                self.symbol2_combo.addItems(symbols)
                
                # Set defaults if available
                if 'BTCUSD' in symbols:
                    self.symbol1_combo.setCurrentText('BTCUSD')
                if 'ETHUSD' in symbols:
                    self.symbol2_combo.setCurrentText('ETHUSD')
                
                logger.info(f"Loaded {len(symbols)} symbols for selection")
            else:
                logger.warning("Could not load symbols - MT5 not connected")
                # Add some common defaults
                common = ['BTCUSD', 'ETHUSD', 'XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD']
                self.symbol1_combo.addItems(common)
                self.symbol2_combo.addItems(common)
                
        except Exception as e:
            logger.error(f"Failed to load symbols: {e}")
            # Fallback defaults
            common = ['BTCUSD', 'ETHUSD', 'XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD']
            self.symbol1_combo.addItems(common)
            self.symbol2_combo.addItems(common)
    
    @pyqtSlot()
    def on_mode_changed(self):
        """Handle analysis mode change (auto-detect vs single pair)"""
        is_auto = self.auto_detect.isChecked()
        
        # Show/hide single pair controls
        self.single_pair_label1.setVisible(not is_auto)
        self.symbol1_combo.setVisible(not is_auto)
        self.single_pair_label2.setVisible(not is_auto)
        self.symbol2_combo.setVisible(not is_auto)
        
        if is_auto:
            self.add_log("Mode: Auto-detect all symbols")
        else:
            sym1 = self.symbol1_combo.currentText()
            sym2 = self.symbol2_combo.currentText()
            self.add_log(f"Mode: Single pair analysis ({sym1}/{sym2})")
    
    def reset_for_new_analysis(self):
        """Reset UI state for new analysis"""
        # Reset progress
        self.progress_bar.setValue(0)
        self.phase_label.setText("Ready to start analysis")
        self.status_label.setText("")
        
        # Enable/disable buttons
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
        # Keep results and save button enabled if we have results
        # self.save_btn remains as is
        
        self.add_log("✓ Ready for new analysis")
        logger.info("UI reset for new analysis")
    
    # ========== EVENT HANDLERS ==========
    
    @pyqtSlot()
    def on_start_analysis(self):
        """Start analysis button clicked"""
        try:
            # Determine mode
            is_auto = self.auto_detect.isChecked()
            
            # Get parameters
            params = {
                'start_date': self.start_date.date().toString('yyyy-MM-dd'),
                'end_date': self.end_date.date().toString('yyyy-MM-dd'),
                'window_size': int(self.window_size.currentText()),
                'min_correlation': self.min_correlation.value(),
                'auto_detect_symbols': is_auto,
                'min_data_quality': 0.90
            }
            
            # If single pair mode, add custom symbols
            if not is_auto:
                sym1 = self.symbol1_combo.currentText().strip()
                sym2 = self.symbol2_combo.currentText().strip()
                
                if not sym1 or not sym2:
                    QMessageBox.warning(self, "Invalid Symbols", "Please enter both symbols")
                    return
                
                if sym1 == sym2:
                    QMessageBox.warning(self, "Invalid Symbols", "Please select different symbols")
                    return
                
                params['custom_symbols'] = [sym1, sym2]
                self.add_log(f"Analyzing single pair: {sym1} / {sym2}")
            
            # Validate dates
            if self.start_date.date() >= self.end_date.date():
                QMessageBox.warning(self, "Invalid Dates", "Start date must be before end date")
                return
            
            # Start analysis
            success = self.engine.start_analysis(params)
            
            if success:
                # Connect worker signals
                if self.engine.current_worker:
                    worker = self.engine.current_worker
                    worker.signals.progress.connect(self.on_progress_update)
                    worker.signals.phase_change.connect(self.on_phase_change)
                    worker.signals.status_update.connect(self.on_status_update)
                    worker.signals.partial_result.connect(self.on_partial_result)
                    worker.signals.completed.connect(self.on_analysis_complete)
                    worker.signals.error.connect(self.on_error)
                    worker.signals.log.connect(self.on_log)
                
                # Update UI
                self.start_btn.setEnabled(False)
                self.cancel_btn.setEnabled(True)
                self.save_btn.setEnabled(False)
                
                self.log_area.clear()
                self.add_log("Analysis started...")
                
            else:
                QMessageBox.critical(self, "Error", "Failed to start analysis")
                
        except Exception as e:
            logger.error(f"Failed to start analysis: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start: {str(e)}")
    
    @pyqtSlot()
    def on_cancel_analysis(self):
        """Cancel analysis button clicked"""
        self.engine.stop_analysis()
        self.add_log("Analysis cancelled by user")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
    
    @pyqtSlot()
    def on_save_results(self):
        """Save results button clicked"""
        if len(self.current_results) == 0:
            QMessageBox.warning(self, "No Results", "No results to save")
            return
        
        filepath = self.engine.save_results(self.current_results)
        if filepath:
            QMessageBox.information(self, "Saved", f"Results saved to:\n{filepath}")
            self.add_log(f"Results saved to {filepath}")
    
    @pyqtSlot()
    def on_load_results(self):
        """Load results button clicked"""
        # TODO: Implement file dialog to select results file
        recent = self.engine.get_recent_analyses()
        if recent:
            QMessageBox.information(self, "Load Results", 
                                  f"Found {len(recent)} recent analyses.\nLoad functionality coming soon!")
    
    @pyqtSlot()
    def on_view_details(self):
        """View details button clicked or table double-clicked"""
        selected_rows = self.results_table.selectedIndexes()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        if row < len(self.current_results):
            pair = self.current_results[row]
            self.show_pair_details(pair)
    
    @pyqtSlot()
    def on_apply_parameters(self):
        """Apply parameters button clicked"""
        selected_rows = self.results_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a pair first")
            return
        
        row = selected_rows[0].row()
        if row < len(self.current_results):
            pair = self.current_results[row]
            self.apply_pair_parameters(pair)
    
    @pyqtSlot()
    def on_sort_changed(self):
        """Sort combo changed"""
        self.populate_results_table(self.current_results)
    
    @pyqtSlot()
    def on_filter_changed(self):
        """Filter combo changed"""
        self.populate_results_table(self.current_results)
    
    # ========== SIGNAL SLOTS ==========
    
    @pyqtSlot(float)
    def on_progress_update(self, progress):
        """Progress update from worker"""
        self.progress_bar.setValue(int(progress))
    
    @pyqtSlot(str)
    def on_phase_change(self, phase):
        """Phase change from worker"""
        self.phase_label.setText(f"Current Phase: {phase}")
        self.add_log(f"→ {phase}")
    
    @pyqtSlot(dict)
    def on_status_update(self, status):
        """Detailed status update from worker"""
        phase = status.get('phase', '')
        current = status.get('current_item', '')
        current_idx = status.get('current_index', 0)
        total = status.get('total_items', 0)
        
        self.status_label.setText(
            f"{phase}: {current} ({current_idx}/{total})"
        )
    
    @pyqtSlot(dict)
    def on_partial_result(self, result):
        """Partial result from worker (one pair analyzed)"""
        # Could update a preview table here
        pass
    
    @pyqtSlot(list)
    def on_analysis_complete(self, results):
        """Analysis completed"""
        self.current_results = results
        
        # Update UI - AUTO RESET for new analysis
        self.start_btn.setEnabled(True)  # ✅ Enable START for new analysis
        self.cancel_btn.setEnabled(False)
        self.save_btn.setEnabled(True)
        
        # Populate results table
        self.populate_results_table(results)
        
        # Update count
        self.results_count_label.setText(f"Total Pairs: {len(results)}")
        
        # Enable action buttons
        self.view_details_btn.setEnabled(True)
        self.apply_params_btn.setEnabled(True)
        
        # Log
        self.add_log(f"✓ Analysis complete! Found {len(results)} pairs")
        self.add_log("─" * 50)
        self.add_log("✅ Ready for new analysis - Click START ANALYSIS again")
        
        # Show summary
        if len(results) > 0:
            top_pair = results[0]
            msg = (
                f"Analysis complete!\n\n"
                f"Found {len(results)} valid pairs\n"
                f"Top pair: {top_pair['symbol1']}/{top_pair['symbol2']}\n"
                f"Score: {top_pair['score']:.1f} ({top_pair['rating']})\n\n"
                f"✅ You can start a new analysis now!"
            )
            QMessageBox.information(self, "Analysis Complete", msg)
        else:
            QMessageBox.information(
                self, 
                "Analysis Complete",
                "No valid pairs found.\n\nTry:\n"
                "- Lower min correlation\n"
                "- Use different date range\n"
                "- Check if symbols have data"
            )
        
        # Auto-reset is already done - UI is ready for new analysis!
    
    @pyqtSlot(str)
    def on_error(self, error_msg):
        """Error from worker"""
        self.add_log(f"❌ ERROR: {error_msg}")
        QMessageBox.critical(self, "Analysis Error", error_msg)
        
        # Reset UI
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
    
    @pyqtSlot(str)
    def on_log(self, message):
        """Log message from worker"""
        self.add_log(message)
    
    # ========== HELPER METHODS ==========
    
    def add_log(self, message):
        """Add message to log area"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        self.log_area.verticalScrollBar().setValue(
            self.log_area.verticalScrollBar().maximum()
        )
    
    def populate_results_table(self, results):
        """Populate results table with data"""
        # Apply filter
        filter_text = self.filter_combo.currentText()
        if filter_text == 'All':
            filtered = results
        elif 'EXCELLENT' in filter_text:
            filtered = [r for r in results if '⭐⭐⭐⭐⭐' in r.get('rating', '')]
        elif 'VERY GOOD' in filter_text:
            filtered = [r for r in results if '⭐⭐⭐⭐' in r.get('rating', '')]
        elif 'GOOD' in filter_text:
            filtered = [r for r in results if '⭐⭐⭐' in r.get('rating', '') and '⭐⭐⭐⭐' not in r.get('rating', '')]
        else:
            filtered = results
        
        # Apply sort
        sort_by = self.sort_combo.currentText()
        if sort_by == 'Score':
            filtered = sorted(filtered, key=lambda x: x.get('score', 0), reverse=True)
        elif sort_by == 'Correlation':
            filtered = sorted(filtered, key=lambda x: x.get('correlation', {}).get('correlation', 0), reverse=True)
        elif sort_by == 'Win Rate':
            filtered = sorted(filtered, key=lambda x: x.get('backtest', {}).get('win_rate', 0) if x.get('backtest') else 0, reverse=True)
        elif sort_by == 'Sharpe Ratio':
            filtered = sorted(filtered, key=lambda x: x.get('backtest', {}).get('sharpe_ratio', 0) if x.get('backtest') else 0, reverse=True)
        
        # Clear and populate table
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(filtered))
        
        for i, pair in enumerate(filtered):
            # Rank
            rank_item = QTableWidgetItem(str(i + 1))
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if i == 0:
                rank_item.setText("🥇")
            elif i == 1:
                rank_item.setText("🥈")
            elif i == 2:
                rank_item.setText("🥉")
            self.results_table.setItem(i, 0, rank_item)
            
            # Pair
            pair_name = f"{pair['symbol1']} / {pair['symbol2']}"
            self.results_table.setItem(i, 1, QTableWidgetItem(pair_name))
            
            # Score
            score_item = QTableWidgetItem(f"{pair.get('score', 0):.1f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # Color code by score
            score = pair.get('score', 0)
            if score >= 90:
                score_item.setForeground(QColor("#27ae60"))  # Green
            elif score >= 80:
                score_item.setForeground(QColor("#2980b9"))  # Blue
            elif score >= 70:
                score_item.setForeground(QColor("#f39c12"))  # Orange
            else:
                score_item.setForeground(QColor("#95a5a6"))  # Gray
            self.results_table.setItem(i, 2, score_item)
            
            # Correlation
            corr = pair.get('correlation', {}).get('correlation', 0)
            corr_item = QTableWidgetItem(f"{corr:.3f}")
            corr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(i, 3, corr_item)
            
            # Win Rate
            backtest = pair.get('backtest')
            if backtest:
                win_rate = backtest.get('win_rate', 0)
                win_item = QTableWidgetItem(f"{win_rate:.1f}%")
            else:
                win_item = QTableWidgetItem("N/A")
            win_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(i, 4, win_item)
            
            # Sharpe
            if backtest:
                sharpe = backtest.get('sharpe_ratio', 0)
                sharpe_item = QTableWidgetItem(f"{sharpe:.2f}")
            else:
                sharpe_item = QTableWidgetItem("N/A")
            sharpe_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(i, 5, sharpe_item)
            
            # Trades
            if backtest:
                trades = backtest.get('total_trades', 0)
                trades_item = QTableWidgetItem(str(trades))
            else:
                trades_item = QTableWidgetItem("N/A")
            trades_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(i, 6, trades_item)
            
            # Rating
            rating = pair.get('rating', '')
            self.results_table.setItem(i, 7, QTableWidgetItem(rating))
    
    def show_pair_details(self, pair):
        """Show detailed analysis for a pair"""
        # Create detail dialog
        from PyQt6.QtWidgets import QDialog, QTabWidget, QTextEdit
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Pair Analysis: {pair['symbol1']} / {pair['symbol2']}")
        dialog.resize(800, 600)
        
        layout = QVBoxLayout(dialog)
        
        tabs = QTabWidget()
        
        # ========== TAB 1: SUMMARY ==========
        summary_text = QTextEdit()
        summary_text.setReadOnly(True)
        summary_text.setMarkdown(self._generate_summary_markdown(pair))
        tabs.addTab(summary_text, "Summary")
        
        # ========== TAB 2: STATISTICS ==========
        stats_text = QTextEdit()
        stats_text.setReadOnly(True)
        stats_text.setMarkdown(self._generate_statistics_markdown(pair))
        tabs.addTab(stats_text, "Statistics")
        
        # ========== TAB 3: RECOMMENDED PARAMETERS ==========
        params_text = QTextEdit()
        params_text.setReadOnly(True)
        params_text.setMarkdown(self._generate_parameters_markdown(pair))
        tabs.addTab(params_text, "Parameters")
        
        # ========== TAB 4: BACKTEST ==========
        if pair.get('backtest'):
            backtest_text = QTextEdit()
            backtest_text.setReadOnly(True)
            backtest_text.setMarkdown(self._generate_backtest_markdown(pair))
            tabs.addTab(backtest_text, "Backtest")
        
        layout.addWidget(tabs)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def apply_pair_parameters(self, pair):
        """Apply parameters from selected pair to trading system"""
        # TODO: Integrate with main trading system config
        msg = f"Apply parameters for {pair['symbol1']}/{pair['symbol2']}?\n\n"
        msg += "This will update the trading system configuration.\n"
        msg += "(Integration with main system coming soon)"
        
        reply = QMessageBox.question(self, "Apply Parameters", msg,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "Info", "Parameter application will be implemented in next update")
    
    def _generate_summary_markdown(self, pair):
        """Generate summary markdown for pair"""
        md = f"# {pair['symbol1']} / {pair['symbol2']}\n\n"
        md += f"## Overall Score: {pair.get('score', 0):.1f} / 100\n"
        md += f"**Rating:** {pair.get('rating', 'N/A')}\n\n"
        md += "---\n\n"
        md += "## Key Metrics\n\n"
        md += f"- **Correlation:** {pair.get('correlation', {}).get('correlation', 0):.3f}\n"
        md += f"- **Cointegration p-value:** {pair.get('cointegration', {}).get('p_value', 1):.4f}\n"
        md += f"- **Half-life:** {pair.get('half_life', 0):.2f} bars\n"
        
        if pair.get('backtest'):
            bt = pair['backtest']
            md += f"\n## Backtest Results\n\n"
            md += f"- **Win Rate:** {bt.get('win_rate', 0):.1f}%\n"
            md += f"- **Total Trades:** {bt.get('total_trades', 0)}\n"
            md += f"- **Sharpe Ratio:** {bt.get('sharpe_ratio', 0):.2f}\n"
            md += f"- **Max Drawdown:** {bt.get('max_drawdown', 0):.2f}%\n"
        
        return md
    
    def _generate_statistics_markdown(self, pair):
        """Generate statistics markdown"""
        md = "# Statistical Analysis\n\n"
        # Add detailed stats here
        md += "Complete statistics coming soon...\n"
        return md
    
    def _generate_parameters_markdown(self, pair):
        """Generate parameters markdown"""
        md = "# Recommended Parameters\n\n"
        
        if pair.get('recommended_params'):
            params = pair['recommended_params']
            for style in ['conservative', 'moderate', 'aggressive']:
                if style in params:
                    p = params[style]
                    md += f"## {style.capitalize()}\n\n"
                    md += f"- **Entry Z-Score:** ±{p.get('entry_zscore', 0)}\n"
                    md += f"- **Exit Z-Score:** ±{p.get('exit_zscore', 0)}\n"
                    md += f"- **Stop Loss Z-Score:** ±{p.get('stop_loss_zscore', 0)}\n"
                    md += f"- **Window Size:** {p.get('window_size', 0)}\n\n"
        
        return md
    
    def _generate_backtest_markdown(self, pair):
        """Generate backtest markdown"""
        md = "# Backtest Results\n\n"
        
        if pair.get('backtest'):
            bt = pair['backtest']
            md += f"- **Total Trades:** {bt.get('total_trades', 0)}\n"
            md += f"- **Win Rate:** {bt.get('win_rate', 0):.2f}%\n"
            md += f"- **Profit Factor:** {bt.get('profit_factor', 0):.2f}\n"
            md += f"- **Sharpe Ratio:** {bt.get('sharpe_ratio', 0):.2f}\n"
            md += f"- **Max Drawdown:** {bt.get('max_drawdown', 0):.2f}%\n"
        
        return md


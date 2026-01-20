"""
Real-time Chart Tab
Displays z-score, spread, and mean with historical data and live updates
"""

import numpy as np
from datetime import datetime
from collections import deque
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox
from PyQt6.QtCore import QTimer
import matplotlib
matplotlib.use('QtAgg')
# Disable toolbar
matplotlib.rcParams['toolbar'] = 'None'
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, HourLocator

class ChartWidget(QWidget):
    """Real-time chart widget with z-score, spread, and mean"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Data storage (will be populated from trading system)
        self.timestamps = deque(maxlen=500)
        self.zscores = deque(maxlen=500)
        self.spreads = deque(maxlen=500)
        self.means = deque(maxlen=500)
        self.stds = deque(maxlen=500)
        
        # Reference to trading system (set by parent)
        self.trading_system = None
        
        # Setup UI
        self.setup_ui()
        
        # Auto-update timer (every 5 seconds)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_chart)
        
    def setup_ui(self):
        """Setup chart UI"""
        layout = QVBoxLayout(self)
        
        # Control panel
        control_layout = QHBoxLayout()
        
        # Remove title - cleaner look
        control_layout.addStretch()
        
        # Timeframe selector
        control_layout.addWidget(QLabel("Timeframe:"))
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems([
            "Last 50 bars",
            "Last 100 bars", 
            "Last 200 bars",
            "Last 500 bars",
            "All data"
        ])
        self.timeframe_combo.setCurrentIndex(1)  # Default: 100 bars
        self.timeframe_combo.currentIndexChanged.connect(self.on_timeframe_changed)
        control_layout.addWidget(self.timeframe_combo)
        
        # Auto-update toggle
        self.auto_update_btn = QPushButton("🔄 Auto-Update: ON")
        self.auto_update_btn.setCheckable(True)
        self.auto_update_btn.setChecked(True)
        self.auto_update_btn.clicked.connect(self.toggle_auto_update)
        self.auto_update_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:checked {
                background-color: #c0392b;
            }
        """)
        control_layout.addWidget(self.auto_update_btn)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Now")
        refresh_btn.clicked.connect(self.force_refresh)
        control_layout.addWidget(refresh_btn)
        
        layout.addLayout(control_layout)
        
        # Create matplotlib figure with 3 subplots - DARCULA THEME
        self.figure = Figure(figsize=(12, 8), facecolor='#2B2B2B')  # Match Darcula background
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # Create subplots
        self.ax1 = self.figure.add_subplot(311)  # Z-Score
        self.ax2 = self.figure.add_subplot(312)  # Spread
        self.ax3 = self.figure.add_subplot(313)  # Mean ± Std
        
        # Initialize plots
        self.init_plots()
        
        # Status bar
        self.status_label = QLabel("Status: Waiting for data...")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(self.status_label)
        
    def init_plots(self):
        """Initialize empty plots with styling - DARCULA THEME"""
        
        # Darcula theme colors (match assets/darcula_theme.css)
        bg_color = '#2B2B2B'      # Main background
        text_color = '#A9B7C6'    # Normal text
        grid_color = '#3C3F41'    # Panel background
        
        # Z-Score plot
        self.ax1.set_facecolor(bg_color)
        self.ax1.set_title("Z-Score Over Time", fontsize=12, fontweight='bold', color=text_color)
        self.ax1.set_ylabel("Z-Score", fontsize=10, color=text_color)
        self.ax1.tick_params(colors=text_color)
        self.ax1.grid(True, alpha=0.3, color=grid_color)
        self.ax1.axhline(y=0, color='white', linestyle='-', linewidth=0.5, alpha=0.5)
        self.ax1.axhline(y=2, color='#BC3F3C', linestyle='--', linewidth=1, alpha=0.7, label='Entry (+2)')
        self.ax1.axhline(y=-2, color='#BC3F3C', linestyle='--', linewidth=1, alpha=0.7, label='Entry (-2)')
        self.ax1.axhline(y=0.5, color='#6A8759', linestyle='--', linewidth=1, alpha=0.7, label='Exit (+0.5)')
        self.ax1.axhline(y=-0.5, color='#6A8759', linestyle='--', linewidth=1, alpha=0.7, label='Exit (-0.5)')
        legend1 = self.ax1.legend(loc='upper right', fontsize=8)
        legend1.get_frame().set_facecolor(bg_color)
        legend1.get_frame().set_alpha(0.8)
        for text in legend1.get_texts():
            text.set_color(text_color)
        
        # Spread plot
        self.ax2.set_facecolor(bg_color)
        self.ax2.set_title("Spread (Primary - Hedge×Secondary)", fontsize=12, fontweight='bold', color=text_color)
        self.ax2.set_ylabel("Spread", fontsize=10, color=text_color)
        self.ax2.tick_params(colors=text_color)
        self.ax2.grid(True, alpha=0.3, color=grid_color)
        
        # Mean ± Std plot
        self.ax3.set_facecolor(bg_color)
        self.ax3.set_title("Rolling Mean ± Standard Deviation", fontsize=12, fontweight='bold', color=text_color)
        self.ax3.set_xlabel("Time", fontsize=10, color=text_color)
        self.ax3.set_ylabel("Value", fontsize=10, color=text_color)
        self.ax3.tick_params(colors=text_color)
        self.ax3.grid(True, alpha=0.3, color=grid_color)
        
        self.figure.tight_layout()
        self.canvas.draw()
        
    def load_historical_data(self, trading_system):
        """Load historical data from trading system"""
        self.trading_system = trading_system
        
        if not trading_system or not hasattr(trading_system, 'market_data'):
            self.status_label.setText("Status: No trading system connected")
            return
            
        market_data = trading_system.market_data
        
        if not hasattr(market_data, 'rolling_window') or len(market_data.rolling_window) == 0:
            self.status_label.setText("Status: No historical data available")
            return
        
        # Clear existing data
        self.timestamps.clear()
        self.zscores.clear()
        self.spreads.clear()
        self.means.clear()
        self.stds.clear()
        
        # Convert rolling window to list for easier processing
        rolling_bars = list(market_data.rolling_window)
        
        # Use a rolling window for calculations (e.g., 50 bars)
        calc_window = 50
        
        # Load from rolling window with PROPER rolling calculations
        for i, bar in enumerate(rolling_bars):
            self.timestamps.append(bar.timestamp)
            self.spreads.append(bar.spread)
            
            # Calculate rolling z-score using last N bars
            if i >= calc_window:
                # Use last 'calc_window' bars for calculation
                window_spreads = [rolling_bars[j].spread for j in range(i - calc_window, i)]
                mean = np.mean(window_spreads)
                std = np.std(window_spreads)
                
                if std > 0:
                    zscore = (bar.spread - mean) / std
                else:
                    zscore = 0
            else:
                # Not enough data yet, use available bars
                window_spreads = [rolling_bars[j].spread for j in range(0, i + 1)]
                mean = np.mean(window_spreads)
                std = np.std(window_spreads) if len(window_spreads) > 1 else 0
                
                if std > 0 and len(window_spreads) > 1:
                    zscore = (bar.spread - mean) / std
                else:
                    zscore = 0
                
            self.zscores.append(zscore)
            self.means.append(mean)
            self.stds.append(std)
        
        self.status_label.setText(f"Status: Loaded {len(self.timestamps)} historical bars")
        
        # Draw initial chart
        self.update_chart()
        
    def add_realtime_data(self, snapshot):
        """Add new real-time data point"""
        if not snapshot:
            return
            
        self.timestamps.append(snapshot.timestamp)
        self.zscores.append(snapshot.zscore)
        self.spreads.append(snapshot.spread)
        self.means.append(snapshot.spread_mean)
        self.stds.append(snapshot.spread_std)
        
        # Update chart if auto-update is on
        if self.auto_update_btn.isChecked():
            self.update_chart()
            
    def update_chart(self):
        """Update chart with current data"""
        if len(self.timestamps) == 0:
            return
            
        # Get timeframe
        timeframe_text = self.timeframe_combo.currentText()
        if "50" in timeframe_text:
            n = min(50, len(self.timestamps))
        elif "100" in timeframe_text:
            n = min(100, len(self.timestamps))
        elif "200" in timeframe_text:
            n = min(200, len(self.timestamps))
        elif "500" in timeframe_text:
            n = min(500, len(self.timestamps))
        else:  # All data
            n = len(self.timestamps)
        
        # Get data for selected timeframe
        times = list(self.timestamps)[-n:]
        zscores = list(self.zscores)[-n:]
        spreads = list(self.spreads)[-n:]
        means = list(self.means)[-n:]
        stds = list(self.stds)[-n:]
        
        # Clear plots
        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()
        
        # Dark theme colors
        bg_color = '#2b3e50'
        text_color = '#ecf0f1'
        grid_color = '#34495e'
        
        # Set backgrounds
        self.ax1.set_facecolor(bg_color)
        self.ax2.set_facecolor(bg_color)
        self.ax3.set_facecolor(bg_color)
        
        # Plot Z-Score with bright colors for dark background
        self.ax1.plot(times, zscores, '#3498db', linewidth=2, label='Z-Score')  # Bright blue
        self.ax1.axhline(y=0, color='white', linestyle='-', linewidth=0.5, alpha=0.5)
        self.ax1.axhline(y=2, color='#e74c3c', linestyle='--', linewidth=1.5, alpha=0.8, label='Entry (+2)')
        self.ax1.axhline(y=-2, color='#e74c3c', linestyle='--', linewidth=1.5, alpha=0.8, label='Entry (-2)')
        self.ax1.axhline(y=0.5, color='#2ecc71', linestyle='--', linewidth=1.5, alpha=0.8, label='Exit (±0.5)')
        self.ax1.axhline(y=-0.5, color='#2ecc71', linestyle='--', linewidth=1.5, alpha=0.8)
        self.ax1.fill_between(times, 2, [max(z, 2) for z in zscores], 
                             alpha=0.3, color='#e74c3c', label='Extreme Zone')
        self.ax1.fill_between(times, -2, [min(z, -2) for z in zscores], 
                             alpha=0.3, color='#e74c3c')
        self.ax1.set_title("Z-Score Over Time", fontsize=12, fontweight='bold', color=text_color)
        self.ax1.set_ylabel("Z-Score", fontsize=10, color=text_color)
        self.ax1.tick_params(colors=text_color)
        # Move y-axis to right
        self.ax1.yaxis.tick_right()
        self.ax1.yaxis.set_label_position("right")
        # Move legend to upper left
        legend1 = self.ax1.legend(loc='upper left', fontsize=8)
        legend1.get_frame().set_facecolor(bg_color)
        legend1.get_frame().set_alpha(0.8)
        for text in legend1.get_texts():
            text.set_color(text_color)
        self.ax1.grid(True, alpha=0.3, color=grid_color)
        
        # Plot Spread with purple/magenta
        self.ax2.plot(times, spreads, '#9b59b6', linewidth=2, label='Spread')  # Purple
        if len(means) > 0:
            self.ax2.axhline(y=means[-1], color='#f39c12', linestyle='--', 
                           linewidth=1.5, alpha=0.8, label=f'Current Mean: {means[-1]:.4f}')
        self.ax2.set_title("Spread (Primary - Hedge×Secondary)", fontsize=12, fontweight='bold', color=text_color)
        self.ax2.set_ylabel("Spread", fontsize=10, color=text_color)
        self.ax2.tick_params(colors=text_color)
        # Move y-axis to right
        self.ax2.yaxis.tick_right()
        self.ax2.yaxis.set_label_position("right")
        # Move legend to upper left
        legend2 = self.ax2.legend(loc='upper left', fontsize=8)
        legend2.get_frame().set_facecolor(bg_color)
        legend2.get_frame().set_alpha(0.8)
        for text in legend2.get_texts():
            text.set_color(text_color)
        self.ax2.grid(True, alpha=0.3, color=grid_color)
        
        # Plot Mean ± Std with green/red
        self.ax3.plot(times, means, '#2ecc71', linewidth=2, label='Mean')  # Green
        if len(stds) > 0 and len(means) > 0:
            upper_band = [m + s for m, s in zip(means, stds)]
            lower_band = [m - s for m, s in zip(means, stds)]
            upper_band_2 = [m + 2*s for m, s in zip(means, stds)]
            lower_band_2 = [m - 2*s for m, s in zip(means, stds)]
            
            self.ax3.plot(times, upper_band, '#e74c3c', linestyle='--', linewidth=1.5, alpha=0.7, label='Mean ± 1σ')
            self.ax3.plot(times, lower_band, '#e74c3c', linestyle='--', linewidth=1.5, alpha=0.7)
            self.ax3.plot(times, upper_band_2, '#e74c3c', linestyle=':', linewidth=1.5, alpha=0.5, label='Mean ± 2σ')
            self.ax3.plot(times, lower_band_2, '#e74c3c', linestyle=':', linewidth=1.5, alpha=0.5)
            self.ax3.fill_between(times, upper_band, lower_band, alpha=0.3, color='#2ecc71')
        
        self.ax3.set_title("Rolling Mean ± Standard Deviation", fontsize=12, fontweight='bold', color=text_color)
        self.ax3.set_xlabel("Time", fontsize=10, color=text_color)
        self.ax3.set_ylabel("Value", fontsize=10, color=text_color)
        self.ax3.tick_params(colors=text_color)
        # Move y-axis to right
        self.ax3.yaxis.tick_right()
        self.ax3.yaxis.set_label_position("right")
        # Move legend to upper left
        legend3 = self.ax3.legend(loc='upper left', fontsize=8)
        legend3.get_frame().set_facecolor(bg_color)
        legend3.get_frame().set_alpha(0.8)
        for text in legend3.get_texts():
            text.set_color(text_color)
        self.ax3.grid(True, alpha=0.3, color=grid_color)
        
        # Format x-axis
        for ax in [self.ax1, self.ax2, self.ax3]:
            ax.tick_params(axis='x', rotation=45)
            if len(times) > 0:
                # Format time axis
                ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
        
        self.figure.tight_layout()
        self.canvas.draw()
        
        # Update status
        if len(times) > 0:
            self.status_label.setText(
                f"Status: {len(times)} bars | "
                f"Latest: {times[-1].strftime('%Y-%m-%d %H:%M')} | "
                f"Z-Score: {zscores[-1]:.3f}"
            )
        
    def on_timeframe_changed(self):
        """Handle timeframe selection change"""
        self.update_chart()
        
    def toggle_auto_update(self):
        """Toggle auto-update"""
        if self.auto_update_btn.isChecked():
            self.auto_update_btn.setText("🔄 Auto-Update: ON")
            self.auto_update_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
            """)
            self.update_timer.start(5000)  # Update every 5 seconds
        else:
            self.auto_update_btn.setText("🔄 Auto-Update: OFF")
            self.auto_update_btn.setStyleSheet("""
                QPushButton {
                    background-color: #c0392b;
                    color: white;
                    border: none;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
            """)
            self.update_timer.stop()
            
    def force_refresh(self):
        """Force refresh chart"""
        if self.trading_system:
            self.load_historical_data(self.trading_system)
        else:
            self.update_chart()
            
    def start_auto_update(self):
        """Start auto-update timer"""
        if self.auto_update_btn.isChecked():
            self.update_timer.start(5000)  # Update every 5 seconds
            
    def stop_auto_update(self):
        """Stop auto-update timer"""
        self.update_timer.stop()

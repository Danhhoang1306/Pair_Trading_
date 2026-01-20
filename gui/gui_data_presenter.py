"""
GUI Data Presenter - Presentation Layer
=======================================
This module acts as a bridge between the trading system backend and the GUI.
It handles all data calculations, formatting, and normalization so the GUI
only needs to display values without any business logic.

Design principles:
- Backend returns raw data with *_value naming
- Presenter calculates derived values and formats for display
- GUI receives ready-to-display formatted strings
- Separation of concerns: Backend (data) -> Presenter (logic) -> GUI (display)
"""

from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


class GUIDataPresenter:
    """
    Presenter class that transforms backend data into GUI-ready display values.

    Responsibilities:
    1. Calculate derived metrics (e.g., mean drift, next entry z-score)
    2. Format numbers for display (decimals, currency, percentages)
    3. Apply styling rules (colors, bold text)
    4. Provide default values when data is unavailable
    5. Map backend field names (*_value) to GUI labels
    """

    def __init__(self):
        """Initialize presenter with default state"""
        self.last_status = {}
        # Path to spread states JSON file (unified state)
        self.state_file = Path(__file__).parent.parent / 'asset' / 'state' / 'spread_states.json'

    def present_status(self, raw_status: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform raw backend status into GUI-ready presentation data.

        Args:
            raw_status: Raw status dict from TradingSystemThread with *_value fields

        Returns:
            Dict with formatted display values ready for GUI labels
        """
        if not raw_status:
            return self._get_default_presentation()

        # Store for reference
        self.last_status = raw_status

        # Build presentation data
        presentation = {}

        # ========== LIVE STATISTICS ==========
        presentation['z_score_value'] = self._format_zscore(raw_status.get('zscore_value', 0.0))
        presentation['z_score_style'] = self._get_zscore_style(raw_status.get('zscore_value', 0.0))

        presentation['correlation_value'] = self._format_correlation(raw_status.get('correlation_value', 0.0))
        presentation['hedge_ratio_value'] = self._format_decimal(raw_status.get('hedge_ratio_value', 0.0), 4)
        presentation['spread_value'] = self._format_decimal(raw_status.get('spread_value', 0.0), 2)

        presentation['total_pnl_value'] = self._format_currency(raw_status.get('total_pnl_value', 0.0))
        presentation['total_pnl_style'] = self._get_pnl_style(raw_status.get('total_pnl_value', 0.0))

        presentation['signal_value'] = raw_status.get('signal_value', 'HOLD')
        presentation['signal_style'] = self._get_signal_style(raw_status.get('signal_value', 'HOLD'))

        # ========== MODEL METRICS ==========
        presentation['entry_threshold_value'] = self._format_decimal(raw_status.get('entry_threshold_value', 2.0), 1)
        presentation['exit_threshold_value'] = self._format_decimal(raw_status.get('exit_threshold_value', 0.5), 1)
        presentation['window_size_value'] = str(int(raw_status.get('window_size_value', 200)))

        presentation['spread_mean_value'] = self._format_decimal(raw_status.get('spread_mean_value', 0.0), 2)
        presentation['spread_std_value'] = self._format_decimal(raw_status.get('spread_std_value', 0.0), 2)

        # Calculate mean drift (read first_entry_spread_mean from state file)
        first_entry_mean = self._read_first_entry_spread_mean()
        presentation['mean_drift_value'] = self._calculate_mean_drift(
            current_mean=raw_status.get('spread_mean_value', 0.0),
            entry_mean=first_entry_mean
        )
        presentation['mean_drift_style'] = self._get_drift_style(presentation['mean_drift_value'])

        presentation['max_z_score_value'] = self._format_zscore(raw_status.get('max_zscore_value', 0.0))
        presentation['min_z_score_value'] = self._format_zscore(raw_status.get('min_zscore_value', 0.0))

        presentation['max_mean_value'] = self._format_decimal(raw_status.get('max_mean_value', 0.0), 2)
        presentation['min_mean_value'] = self._format_decimal(raw_status.get('min_mean_value', 0.0), 2)

        # Last update timestamp
        presentation['last_update_value'] = datetime.now().strftime("%H:%M:%S")

        # Status indicator
        presentation['status_value'] = self._get_status_text(raw_status.get('is_running', False))
        presentation['status_style'] = self._get_status_style(raw_status.get('is_running', False))

        # Entry tracking metrics (read from JSON file)
        scale_interval = raw_status.get('scale_interval_value', 0.5)
        last_z, next_z = self._read_entry_tracking(scale_interval)

        presentation['last_z_score_entries_value'] = self._format_zscore(last_z) if last_z is not None else "--"
        presentation['next_z_score_entries_value'] = self._format_zscore(next_z) if next_z is not None else "--"

        # Pyramiding parameters
        presentation['scalp_interval_value'] = self._format_decimal(
            raw_status.get('scale_interval_value', 0.5), 1
        )
        presentation['volume_multiplier_value'] = self._format_decimal(
            raw_status.get('volume_multiplier_value', 1.0), 2
        )

        # ========== ACCOUNT STATUS ==========
        presentation['balance_value'] = self._format_currency(raw_status.get('balance_value', 0.0))
        presentation['equity_value'] = self._format_currency(raw_status.get('equity_value', 0.0))

        presentation['unrealized_pnl_value'] = self._format_currency(raw_status.get('unrealized_pnl_value', 0.0))
        presentation['unrealized_pnl_style'] = self._get_pnl_style(raw_status.get('unrealized_pnl_value', 0.0))

        presentation['used_margin_value'] = self._format_currency(raw_status.get('used_margin_value', 0.0))
        presentation['free_margin_value'] = self._format_currency(raw_status.get('free_margin_value', 0.0))
        presentation['margin_level_value'] = self._format_percentage(raw_status.get('margin_level_value', 0.0), 1)

        # ========== POSITION OVERVIEW ==========
        presentation['open_spread_value'] = str(int(raw_status.get('open_positions_value', 0)))
        presentation['open_close_value'] = f"{raw_status.get('open_positions_value', 0)} / {raw_status.get('closed_positions_value', 0)}"

        # ========== HEDGE METRICS ==========
        # Get hedge metrics from MT5
        hedge_imbalance = raw_status.get('hedge_imbalance_value', 0.0)
        hedge_imbalance_pct = raw_status.get('hedge_imbalance_pct_value', 0.0)
        primary_lots = raw_status.get('primary_lots_value', 0.0)
        secondary_lots = raw_status.get('secondary_lots_value', 0.0)

        # Hedge Quality = 100% - abs(imbalance%)
        hedge_quality_pct = 100.0 - (abs(hedge_imbalance_pct) * 100.0) if hedge_imbalance_pct != 0 else 100.0

        # Format hedge quality with emoji indicator
        if hedge_quality_pct >= 98:
            presentation['hedge_quality_value'] = f"{hedge_quality_pct:.1f}% ✓"
            presentation['hedge_quality_style'] = "color: #27ae60; font-weight: bold;"
        elif hedge_quality_pct >= 95:
            presentation['hedge_quality_value'] = f"{hedge_quality_pct:.1f}% ⚠"
            presentation['hedge_quality_style'] = "color: #f39c12; font-weight: bold;"
        else:
            presentation['hedge_quality_value'] = f"{hedge_quality_pct:.1f}% ✗"
            presentation['hedge_quality_style'] = "color: #e74c3c; font-weight: bold;"

        # Format imbalance text
        if abs(hedge_imbalance) < 0.01:
            presentation['imbalance_value'] = "Balanced ✓"
            presentation['imbalance_style'] = "color: #27ae60;"
        elif hedge_imbalance > 0:
            presentation['imbalance_value'] = f"+{hedge_imbalance:.4f} lots (Primary)"
            presentation['imbalance_style'] = "color: #f39c12;" if abs(hedge_imbalance_pct) < 0.05 else "color: #e74c3c;"
        else:
            presentation['imbalance_value'] = f"{hedge_imbalance:.4f} lots (Secondary)"
            presentation['imbalance_style'] = "color: #f39c12;" if abs(hedge_imbalance_pct) < 0.05 else "color: #e74c3c;"

        # Format lots with absolute values (no +/- sign for Total Lots display)
        presentation['primary_lots_value'] = f"{abs(primary_lots):.4f}"
        presentation['secondary_lots_value'] = f"{abs(secondary_lots):.4f}"

        # ========== RISK MONITORING ==========
        # Setup risk (per trade)
        setup_risk_pct = raw_status.get('setup_risk_pct_value', 0.0)
        presentation['setup_risk_pct_value'] = self._format_percentage(setup_risk_pct, 2)

        balance = raw_status.get('balance_value', 0.0)
        setup_risk_amount = balance * (setup_risk_pct / 100.0) if balance > 0 else 0.0
        presentation['setup_risk_amount_value'] = self._format_currency(setup_risk_amount)

        # Risk unrealized (current unrealized P&L for risk monitoring)
        risk_unrealized = raw_status.get('unrealized_pnl_value', 0.0)
        presentation['risk_unrealized_value'] = self._format_currency(risk_unrealized)
        presentation['risk_unrealized_style'] = self._get_pnl_style(risk_unrealized)

        # Daily risk limit
        daily_limit_pct = raw_status.get('daily_limit_pct_value', 5.0)
        daily_risk_amount = balance * (daily_limit_pct / 100.0) if balance > 0 else 0.0
        presentation['daily_risk_pct_value'] = self._format_percentage(daily_limit_pct, 2)
        presentation['daily_risk_limit_value'] = self._format_currency(daily_risk_amount)

        # Daily total P&L
        daily_pnl = raw_status.get('daily_total_pnl_value', 0.0)
        presentation['daily_total_pnl_value'] = self._format_currency(daily_pnl)
        presentation['daily_total_pnl_style'] = self._get_pnl_style(daily_pnl)

        # Daily risk percentage used
        daily_risk_pct_used = (abs(daily_pnl) / daily_risk_amount * 100.0) if daily_risk_amount > 0 else 0.0
        presentation['daily_risk_pct_used_value'] = self._format_percentage(daily_risk_pct_used, 1)

        # ========== TRADING LOCK STATUS ==========
        is_locked = raw_status.get('trading_locked_value', False)
        presentation['trading_status_value'] = "LOCK" if is_locked else "UNLOCK"
        presentation['trading_status_style'] = self._get_lock_style(is_locked)

        # Lock timestamps
        if is_locked:
            locked_at = raw_status.get('lock_time_value')
            locked_until = raw_status.get('unlock_time_value')
            presentation['block_time_value'] = locked_at.strftime("%H:%M") if locked_at else "--"
            presentation['unlock_time_value'] = locked_until.strftime("%H:%M") if locked_until else "--"
        else:
            presentation['block_time_value'] = "--"
            presentation['unlock_time_value'] = "--"

        return presentation

    # ========== FORMATTING METHODS ==========

    def _format_zscore(self, value: float) -> str:
        """Format z-score with 2 decimal places, showing sign"""
        if value == 0.0:
            return "--"
        return f"{value:+.2f}"  # Always show sign

    def _format_correlation(self, value: float) -> str:
        """Format correlation coefficient"""
        if value == 0.0:
            return "--"
        return f"{value:.3f}"

    def _format_decimal(self, value: float, decimals: int) -> str:
        """Format decimal number"""
        if value == 0.0:
            return "--"
        return f"{value:.{decimals}f}"

    def _format_currency(self, value: float) -> str:
        """Format currency with $ sign and commas"""
        return f"${value:,.2f}"

    def _format_percentage(self, value: float, decimals: int) -> str:
        """Format percentage"""
        return f"{value:.{decimals}f}%"

    # ========== CALCULATION METHODS ==========

    def _calculate_mean_drift(self, current_mean: float, entry_mean: Optional[float]) -> str:
        """Calculate mean drift from entry point"""
        if entry_mean is None or entry_mean == 0.0:
            return "--"

        drift = current_mean - entry_mean
        drift_pct = (drift / entry_mean) * 100.0
        return f"{drift:+.2f} ({drift_pct:+.1f}%)"

    # ========== STYLING METHODS ==========

    def _get_zscore_style(self, zscore: float) -> str:
        """Get color style for z-score"""
        if abs(zscore) >= 2.0:
            return "color: #e74c3c; font-weight: bold;"  # Red for extreme
        elif abs(zscore) >= 1.0:
            return "color: #f39c12; font-weight: bold;"  # Orange for moderate
        else:
            return "color: #95a5a6;"  # Gray for normal

    def _get_pnl_style(self, pnl: float) -> str:
        """Get color style for P&L values"""
        if pnl > 0:
            return "color: #27ae60; font-weight: bold;"  # Green for profit
        elif pnl < 0:
            return "color: #e74c3c; font-weight: bold;"  # Red for loss
        else:
            return "color: #95a5a6;"  # Gray for zero

    def _get_signal_style(self, signal: str) -> str:
        """Get background style for signal"""
        signal_styles = {
            'HOLD': "background-color: #7f8c8d; color: white; padding: 2px; border-radius: 2px; font-weight: bold;",
            'LONG SPREAD': "background-color: #27ae60; color: white; padding: 2px; border-radius: 2px; font-weight: bold;",
            'SHORT SPREAD': "background-color: #e74c3c; color: white; padding: 2px; border-radius: 2px; font-weight: bold;"
        }
        return signal_styles.get(signal, signal_styles['HOLD'])

    def _get_drift_style(self, drift_str: str) -> str:
        """Get style for mean drift indicator"""
        if drift_str == "--":
            return "color: #95a5a6;"

        # Extract drift value (first number before parenthesis)
        try:
            drift_val = float(drift_str.split('(')[0].strip())
            if abs(drift_val) > 1.0:
                return "color: #e74c3c; font-weight: bold;"  # Red for large drift
            elif abs(drift_val) > 0.5:
                return "color: #f39c12; font-weight: bold;"  # Orange for moderate
            else:
                return "color: #27ae60;"  # Green for small drift
        except:
            return "color: #95a5a6;"

    def _get_status_style(self, is_running: bool) -> str:
        """Get style for status indicator"""
        if is_running:
            return "color: #27ae60; font-weight: bold;"  # Green running
        else:
            return "color: #7f8c8d; font-weight: bold;"  # Gray stopped

    def _get_status_text(self, is_running: bool) -> str:
        """Get status text"""
        return "🟢 Running" if is_running else "⚫ Stopped"

    def _get_lock_style(self, is_locked: bool) -> str:
        """Get style for trading lock status"""
        if is_locked:
            return "color: #e74c3c; font-weight: bold;"  # Red for locked
        else:
            return "color: #27ae60; font-weight: bold;"  # Green for unlocked

    def _read_entry_tracking(self, scale_interval: float) -> tuple[Optional[float], Optional[float]]:
        """
        Read entry tracking data from spread_states.json.

        Args:
            scale_interval: Scale interval (not used - values already in state file)

        Returns:
            Tuple of (last_entry_zscore, next_entry_zscore)
            Returns (None, None) if file doesn't exist or has no valid data
        """
        try:
            if not self.state_file.exists():
                return None, None

            with open(self.state_file, 'r') as f:
                state_data = json.load(f)

            spreads = state_data.get('spreads', {})
            if not spreads:
                return None, None

            # Get the first spread state (usually only one active)
            spread_state = None
            for spread_id, state in spreads.items():
                spread_state = state
                break

            if not spread_state:
                return None, None

            last_entry_z = spread_state.get('last_z_entry')
            next_entry_z = spread_state.get('next_z_entry')

            if last_entry_z is None:
                return None, None

            return last_entry_z, next_entry_z

        except Exception as e:
            logger.error(f"Error reading spread state data: {e}", exc_info=True)
            return None, None

    def _read_first_entry_spread_mean(self) -> Optional[float]:
        """
        Read first_entry_spread_mean from spread_states.json.

        This value is stored when the first entry is made and used to calculate
        mean drift (how much the spread mean has changed since entry).

        Returns:
            first_entry_spread_mean if exists and valid, None otherwise
        """
        try:
            if not self.state_file.exists():
                return None

            with open(self.state_file, 'r') as f:
                state_data = json.load(f)

            spreads = state_data.get('spreads', {})
            if not spreads:
                return None

            # Get the first spread state (usually only one active)
            for spread_id, state in spreads.items():
                first_mean = state.get('first_entry_spread_mean')
                if first_mean is not None and first_mean > 0:
                    return first_mean

            return None

        except Exception as e:
            logger.error(f"Error reading first_entry_spread_mean: {e}", exc_info=True)
            return None

    def _get_default_presentation(self) -> Dict[str, Any]:
        """Return default presentation when no data available"""
        return {
            # Live Statistics
            'z_score_value': '--',
            'z_score_style': 'color: #95a5a6;',
            'correlation_value': '--',
            'hedge_ratio_value': '--',
            'spread_value': '--',
            'total_pnl_value': '$0.00',
            'total_pnl_style': 'color: #95a5a6;',
            'signal_value': 'HOLD',
            'signal_style': 'background-color: #7f8c8d; color: white; padding: 5px; border-radius: 3px; font-weight: bold;',

            # Model Metrics
            'entry_threshold_value': '2.0',
            'exit_threshold_value': '0.5',
            'window_size_value': '200',
            'spread_mean_value': '--',
            'spread_std_value': '--',
            'mean_drift_value': '--',
            'mean_drift_style': 'color: #95a5a6;',
            'max_z_score_value': '--',
            'min_z_score_value': '--',
            'max_mean_value': '--',
            'min_mean_value': '--',
            'last_update_value': '--',
            'status_value': '⚫ Stopped',
            'status_style': 'color: #7f8c8d; font-weight: bold;',
            'last_z_score_entries_value': '--',
            'next_z_score_entries_value': '--',
            'scalp_interval_value': '0.5',
            'volume_multiplier_value': '1.0',

            # Account Status
            'balance_value': '$0.00',
            'equity_value': '$0.00',
            'unrealized_pnl_value': '$0.00',
            'unrealized_pnl_style': 'color: #95a5a6;',
            'used_margin_value': '$0.00',
            'free_margin_value': '$0.00',
            'margin_level_value': '0.0%',

            # Position Overview
            'open_spread_value': '0',
            'open_close_value': '0 / 0',

            # Hedge Metrics
            'hedge_quality_value': '100.0% ✓',
            'hedge_quality_style': 'color: #27ae60; font-weight: bold;',
            'imbalance_value': 'Balanced ✓',
            'imbalance_style': 'color: #27ae60;',
            'primary_lots_value': '+0.0000',
            'secondary_lots_value': '+0.0000',

            # Risk Monitoring
            'setup_risk_pct_value': '0%',
            'setup_risk_amount_value': '$0.00',
            'risk_unrealized_value': '$0.00',
            'risk_unrealized_style': 'color: #95a5a6;',
            'daily_risk_limit_value': '$0.00',
            'daily_total_pnl_value': '$0.00',
            'daily_total_pnl_style': 'color: #95a5a6;',
            'daily_risk_pct_used_value': '0.0%',

            # Trading Lock Status
            'trading_status_value': 'UNLOCK',
            'trading_status_style': 'color: #27ae60; font-weight: bold;',
            'block_time_value': '--',
            'unlock_time_value': '--',
        }

"""
Config Sync Manager - Hot-Reload Configuration System
Manages real-time synchronization between GUI, Config, and Trading System

Features:
1. Hot-reload config changes without restarting
2. Track config differences between GUI and running system
3. Symbol validation before trading
4. Config change notifications via signals
"""

import logging
from typing import Dict, Any, Optional, Callable, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class ConfigChangeType(Enum):
    """Type of configuration change"""
    HOT_RELOAD = "hot_reload"  # Can be applied without restart
    REQUIRES_RESTART = "requires_restart"  # Needs system restart
    SYMBOL_CHANGE = "symbol_change"  # Symbol changed - requires restart


@dataclass
class ConfigChange:
    """Represents a single configuration change"""
    key: str
    old_value: Any
    new_value: Any
    change_type: ConfigChangeType
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self):
        return f"{self.key}: {self.old_value} → {self.new_value}"


@dataclass
class ConfigDiff:
    """Represents differences between two configurations"""
    changes: List[ConfigChange] = field(default_factory=list)
    has_hot_reload_changes: bool = False
    has_restart_required_changes: bool = False
    has_symbol_changes: bool = False

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0

    @property
    def change_count(self) -> int:
        return len(self.changes)

    def get_summary(self) -> str:
        """Get human-readable summary of changes"""
        if not self.has_changes:
            return "No changes"

        lines = [f"📝 {len(self.changes)} change(s) detected:"]
        for change in self.changes[:5]:  # Show first 5
            icon = "🔄" if change.change_type == ConfigChangeType.HOT_RELOAD else "⚠️"
            lines.append(f"  {icon} {change}")

        if len(self.changes) > 5:
            lines.append(f"  ... and {len(self.changes) - 5} more")

        return "\n".join(lines)


class SymbolValidator:
    """Validates symbols exist in MT5 before trading"""

    @staticmethod
    def validate_symbol(symbol: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validate a single symbol exists in MT5

        Returns:
            Tuple of (is_valid, error_message, symbol_info)
        """
        try:
            from core.mt5_manager import get_mt5_manager

            mt5_mgr = get_mt5_manager()

            # Check connection
            if not mt5_mgr.is_connected():
                if not mt5_mgr.initialize():
                    return False, "MT5 not connected. Please start MT5 terminal.", None

            mt5 = mt5_mgr.mt5

            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)

            if symbol_info is None:
                # Try to find similar symbols
                all_symbols = mt5.symbols_get()
                similar = [s.name for s in all_symbols if symbol.lower() in s.name.lower()][:5]

                suggestion = ""
                if similar:
                    suggestion = f"\n\nDid you mean: {', '.join(similar)}?"

                return False, f"Symbol '{symbol}' not found in MT5.{suggestion}", None

            # Check if symbol is tradeable
            if not symbol_info.visible:
                # Try to enable it
                if not mt5.symbol_select(symbol, True):
                    return False, f"Symbol '{symbol}' exists but cannot be enabled for trading.", None

            # Return symbol details
            info = {
                'symbol': symbol,
                'contract_size': symbol_info.trade_contract_size,
                'min_lot': symbol_info.volume_min,
                'max_lot': symbol_info.volume_max,
                'lot_step': symbol_info.volume_step,
                'tick_size': symbol_info.point,
                'point_value': symbol_info.trade_tick_value,
                'bid': symbol_info.bid,
                'ask': symbol_info.ask,
                'spread': symbol_info.spread
            }

            return True, "", info

        except Exception as e:
            logger.error(f"Symbol validation error: {e}")
            return False, f"Error validating symbol: {e}", None

    @staticmethod
    def validate_pair(primary: str, secondary: str) -> Tuple[bool, str, Optional[Dict[str, Dict[str, Any]]]]:
        """
        Validate a trading pair

        Returns:
            Tuple of (is_valid, error_message, pair_info)
        """
        errors = []
        pair_info = {}

        # Validate primary
        valid_p, error_p, info_p = SymbolValidator.validate_symbol(primary)
        if not valid_p:
            errors.append(f"Primary symbol error: {error_p}")
        else:
            pair_info['primary'] = info_p

        # Validate secondary
        valid_s, error_s, info_s = SymbolValidator.validate_symbol(secondary)
        if not valid_s:
            errors.append(f"Secondary symbol error: {error_s}")
        else:
            pair_info['secondary'] = info_s

        if errors:
            return False, "\n".join(errors), None

        # Additional pair validation
        if primary == secondary:
            return False, "Primary and secondary symbols must be different.", None

        # Check if both symbols have valid prices
        if info_p['bid'] <= 0 or info_s['bid'] <= 0:
            return False, "One or both symbols have invalid prices. Market may be closed.", None

        return True, "", pair_info


class ConfigSyncManager(QObject):
    """
    Manages configuration synchronization between GUI and Trading System

    Signals:
        config_changed: Emitted when config changes are detected (ConfigDiff)
        config_applied: Emitted when config is applied to running system
        config_out_of_sync: Emitted when GUI config differs from running system (bool)
    """

    # Signals
    config_changed = pyqtSignal(object)  # ConfigDiff
    config_applied = pyqtSignal()
    config_out_of_sync = pyqtSignal(bool)  # True if out of sync

    # Parameters that require restart
    RESTART_REQUIRED_PARAMS = {
        'rolling_window_size',
        'magic_number',
        'position_data_dir'
    }

    # Parameters that can be hot-reloaded
    HOT_RELOAD_PARAMS = {
        'entry_threshold',
        'exit_threshold',
        'stop_loss_zscore',
        'max_positions',
        'volume_multiplier',
        'update_interval',
        'hedge_drift_threshold',
        'max_position_pct',
        'max_risk_pct',
        'daily_loss_limit_pct',
        'session_start_time',
        'session_end_time',
        'scale_interval',
        'initial_fraction',
        'min_adjustment_interval',
        'zscore_history_size',
        'enable_pyramiding',
        'enable_hedge_adjustment',
        'enable_volume_rebalancing',
        'enable_entry_cooldown',
        'enable_manual_position_sync'
    }

    def __init__(self):
        super().__init__()
        self._running_config: Optional[Dict[str, Any]] = None
        self._gui_config: Optional[Dict[str, Any]] = None
        self._trading_system = None
        self._is_synced = True
        self._last_sync_time: Optional[datetime] = None

    def set_trading_system(self, trading_system):
        """Set reference to running trading system"""
        self._trading_system = trading_system
        if trading_system and hasattr(trading_system, 'config'):
            self._running_config = trading_system.config.copy()
            self._last_sync_time = datetime.now()
            logger.info("ConfigSyncManager: Trading system connected")

    def clear_trading_system(self):
        """Clear trading system reference (when stopped)"""
        self._trading_system = None
        self._running_config = None
        self._is_synced = True
        self.config_out_of_sync.emit(False)
        logger.info("ConfigSyncManager: Trading system disconnected")

    def update_gui_config(self, config: Dict[str, Any]):
        """Update GUI config and check for differences"""
        self._gui_config = config.copy()

        if self._running_config:
            diff = self._compare_configs(self._gui_config, self._running_config)
            self._is_synced = not diff.has_changes
            self.config_out_of_sync.emit(not self._is_synced)

            if diff.has_changes:
                self.config_changed.emit(diff)
                logger.debug(f"Config diff detected: {diff.change_count} changes")

    def _compare_configs(self, gui_config: Dict[str, Any], running_config: Dict[str, Any]) -> ConfigDiff:
        """Compare GUI config with running config"""
        diff = ConfigDiff()

        # Check all known parameters
        all_params = self.HOT_RELOAD_PARAMS | self.RESTART_REQUIRED_PARAMS

        for key in all_params:
            gui_val = gui_config.get(key)
            running_val = running_config.get(key)

            if gui_val != running_val and gui_val is not None:
                # Determine change type
                if key in self.RESTART_REQUIRED_PARAMS:
                    change_type = ConfigChangeType.REQUIRES_RESTART
                    diff.has_restart_required_changes = True
                else:
                    change_type = ConfigChangeType.HOT_RELOAD
                    diff.has_hot_reload_changes = True

                change = ConfigChange(
                    key=key,
                    old_value=running_val,
                    new_value=gui_val,
                    change_type=change_type
                )
                diff.changes.append(change)

        # Check symbols separately
        gui_primary = gui_config.get('primary_symbol')
        gui_secondary = gui_config.get('secondary_symbol')
        running_primary = running_config.get('primary_symbol')
        running_secondary = running_config.get('secondary_symbol')

        if gui_primary != running_primary:
            diff.changes.append(ConfigChange(
                key='primary_symbol',
                old_value=running_primary,
                new_value=gui_primary,
                change_type=ConfigChangeType.SYMBOL_CHANGE
            ))
            diff.has_symbol_changes = True

        if gui_secondary != running_secondary:
            diff.changes.append(ConfigChange(
                key='secondary_symbol',
                old_value=running_secondary,
                new_value=gui_secondary,
                change_type=ConfigChangeType.SYMBOL_CHANGE
            ))
            diff.has_symbol_changes = True

        return diff

    def get_current_diff(self) -> Optional[ConfigDiff]:
        """Get current difference between GUI and running config"""
        if not self._gui_config or not self._running_config:
            return None
        return self._compare_configs(self._gui_config, self._running_config)

    def apply_hot_reload(self, gui_config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Apply hot-reloadable config changes to running system

        Returns:
            Tuple of (success, list of applied changes)
        """
        if not self._trading_system:
            return False, ["Trading system not running"]

        applied = []
        errors = []

        try:
            sys = self._trading_system

            # Signal Generator
            if hasattr(sys, 'signal_generator'):
                sg = sys.signal_generator
                if 'entry_threshold' in gui_config:
                    sg.entry_threshold = gui_config['entry_threshold']
                    applied.append(f"entry_threshold = {gui_config['entry_threshold']}")
                if 'exit_threshold' in gui_config:
                    sg.exit_threshold = gui_config['exit_threshold']
                    applied.append(f"exit_threshold = {gui_config['exit_threshold']}")
                if 'stop_loss_zscore' in gui_config:
                    sg.stop_loss_zscore = gui_config['stop_loss_zscore']
                    applied.append(f"stop_loss_zscore = {gui_config['stop_loss_zscore']}")

            # Rebalancer
            if hasattr(sys, 'rebalancer'):
                rb = sys.rebalancer
                if 'hedge_drift_threshold' in gui_config:
                    rb.hedge_drift_threshold = gui_config['hedge_drift_threshold']
                    applied.append(f"hedge_drift_threshold = {gui_config['hedge_drift_threshold']}")
                if 'enable_hedge_adjustment' in gui_config:
                    rb.enable_hedge_adjustment = gui_config['enable_hedge_adjustment']
                    applied.append(f"enable_hedge_adjustment = {gui_config['enable_hedge_adjustment']}")
                if 'scale_interval' in gui_config:
                    rb.scale_interval = gui_config['scale_interval']
                    applied.append(f"scale_interval = {gui_config['scale_interval']}")

            # Position Sizer
            if hasattr(sys, 'position_sizer'):
                ps = sys.position_sizer
                if 'max_position_pct' in gui_config:
                    ps.max_position_pct = gui_config['max_position_pct']
                    applied.append(f"max_position_pct = {gui_config['max_position_pct']}")
                if 'max_risk_pct' in gui_config:
                    ps.max_risk_pct = gui_config['max_risk_pct']
                    applied.append(f"max_risk_pct = {gui_config['max_risk_pct']}")

            # Risk Config
            if hasattr(sys, 'risk_config'):
                rc = sys.risk_config
                if 'daily_loss_limit_pct' in gui_config:
                    rc.daily_loss_limit_pct = gui_config['daily_loss_limit_pct']
                    applied.append(f"daily_loss_limit_pct = {gui_config['daily_loss_limit_pct']}")

            # Daily Risk Manager
            if hasattr(sys, 'daily_risk_manager'):
                drm = sys.daily_risk_manager
                if 'daily_loss_limit_pct' in gui_config:
                    drm.daily_loss_limit_pct = gui_config['daily_loss_limit_pct']
                if 'session_start_time' in gui_config:
                    drm.session_start_time = gui_config['session_start_time']
                    applied.append(f"session_start_time = {gui_config['session_start_time']}")

            # Volume Multiplier
            if 'volume_multiplier' in gui_config:
                sys.volume_multiplier = gui_config['volume_multiplier']
                if hasattr(sys, 'trade_executor'):
                    sys.trade_executor.volume_multiplier = gui_config['volume_multiplier']
                applied.append(f"volume_multiplier = {gui_config['volume_multiplier']}")

            # Update Interval
            if 'update_interval' in gui_config:
                sys.update_interval = gui_config['update_interval']
                applied.append(f"update_interval = {gui_config['update_interval']}")

            # Unified Executor
            if hasattr(sys, 'unified_executor'):
                ue = sys.unified_executor
                if 'scale_interval' in gui_config:
                    ue.scale_interval = gui_config['scale_interval']
                if 'max_positions' in gui_config:
                    ue.max_entries = gui_config['max_positions']
                    applied.append(f"max_positions = {gui_config['max_positions']}")
                if 'enable_pyramiding' in gui_config:
                    ue.enable_pyramiding = gui_config['enable_pyramiding']
                    applied.append(f"enable_pyramiding = {gui_config['enable_pyramiding']}")

            # Feature Flags
            if 'enable_entry_cooldown' in gui_config:
                sys.config['enable_entry_cooldown'] = gui_config['enable_entry_cooldown']
                applied.append(f"enable_entry_cooldown = {gui_config['enable_entry_cooldown']}")

            if 'enable_manual_position_sync' in gui_config:
                sys.config['enable_manual_position_sync'] = gui_config['enable_manual_position_sync']
                applied.append(f"enable_manual_position_sync = {gui_config['enable_manual_position_sync']}")

            # Update internal config
            for key in self.HOT_RELOAD_PARAMS:
                if key in gui_config:
                    sys.config[key] = gui_config[key]

            # Update running config tracking
            self._running_config = sys.config.copy()
            self._is_synced = True
            self._last_sync_time = datetime.now()

            self.config_out_of_sync.emit(False)
            self.config_applied.emit()

            logger.info(f"Hot-reload applied: {len(applied)} changes")
            return True, applied

        except Exception as e:
            logger.error(f"Hot-reload error: {e}", exc_info=True)
            return False, [f"Error: {e}"]

    @property
    def is_synced(self) -> bool:
        """Check if GUI and running system are in sync"""
        return self._is_synced

    @property
    def last_sync_time(self) -> Optional[datetime]:
        """Get last synchronization time"""
        return self._last_sync_time

    def get_sync_status_text(self) -> str:
        """Get human-readable sync status"""
        if not self._trading_system:
            return "System not running"

        if self._is_synced:
            if self._last_sync_time:
                return f"✅ Synced at {self._last_sync_time.strftime('%H:%M:%S')}"
            return "✅ Synced"

        diff = self.get_current_diff()
        if diff:
            return f"⚠️ {diff.change_count} unsaved change(s)"
        return "⚠️ Out of sync"


# Global instance
_config_sync_manager: Optional[ConfigSyncManager] = None


def get_config_sync_manager() -> ConfigSyncManager:
    """Get global ConfigSyncManager instance"""
    global _config_sync_manager
    if _config_sync_manager is None:
        _config_sync_manager = ConfigSyncManager()
    return _config_sync_manager

"""
Configuration Adapter for Backward Compatibility

This module provides adapters to convert between old config format (dict)
and new unified config format (dataclasses).

Use this when you have legacy code that expects flat dict configs.
"""

from typing import Dict, Any, Optional
from config.models import PairConfig
from config.manager import get_config


def pair_config_to_flat_dict(pair: PairConfig) -> Dict[str, Any]:
    """
    Convert PairConfig (new format) to flat dict (old format)

    This allows legacy code to work with new config system.

    Args:
        pair: PairConfig instance

    Returns:
        Flat dictionary with all settings

    Example:
        >>> from config.manager import get_config
        >>> from config.adapter import pair_config_to_flat_dict
        >>>
        >>> config = get_config()
        >>> pair = config.get_pair('BTC_ETH')
        >>> flat_dict = pair_config_to_flat_dict(pair)
        >>>
        >>> # Legacy code can use flat_dict
        >>> entry = flat_dict['entry_threshold']
        >>> risk = flat_dict['max_loss_per_setup_pct']
    """
    return pair.get_flat_dict()


def get_pair_as_dict(pair_name: str) -> Optional[Dict[str, Any]]:
    """
    Get pair configuration as flat dict (for legacy code)

    Args:
        pair_name: Name of pair (e.g., 'BTC_ETH')

    Returns:
        Flat dictionary or None if pair not found

    Example:
        >>> from config.adapter import get_pair_as_dict
        >>>
        >>> config = get_pair_as_dict('BTC_ETH')
        >>> if config:
        >>>     print(f"Entry: {config['entry_threshold']}")
    """
    config_manager = get_config()
    pair = config_manager.get_pair(pair_name)

    if pair is None:
        return None

    return pair_config_to_flat_dict(pair)


def make_legacy_compatible(pair: PairConfig) -> Dict[str, Any]:
    """
    Create a legacy-compatible config dict with attribute access

    Returns a dict that supports both dict['key'] and object.key access.
    This helps transition legacy code gradually.

    Args:
        pair: PairConfig instance

    Returns:
        LegacyConfig dict with attribute access

    Example:
        >>> from config.manager import get_config
        >>> from config.adapter import make_legacy_compatible
        >>>
        >>> config = get_config()
        >>> pair = config.get_pair('BTC_ETH')
        >>> legacy = make_legacy_compatible(pair)
        >>>
        >>> # Both styles work
        >>> entry1 = legacy['entry_threshold']  # Dict style
        >>> entry2 = legacy.entry_threshold     # Attribute style (not actually supported in plain dict)
    """
    class LegacyConfig(dict):
        """Dict with attribute access for backward compatibility"""
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError:
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")

        def __setattr__(self, key, value):
            self[key] = value

    flat_dict = pair_config_to_flat_dict(pair)
    return LegacyConfig(flat_dict)


# Convenience function for common use case
def get_active_pair_config() -> Optional[PairConfig]:
    """
    Get the first active pair configuration

    Useful for systems that only trade one pair at a time.

    Returns:
        First pair in configuration or None

    Example:
        >>> from config.adapter import get_active_pair_config
        >>>
        >>> pair = get_active_pair_config()
        >>> if pair:
        >>>     print(f"Trading: {pair.primary_symbol}/{pair.secondary_symbol}")
    """
    config_manager = get_config()
    pairs = config_manager.get_all_pairs()

    if not pairs:
        return None

    # Return first pair
    return next(iter(pairs.values()))


def get_default_pair_name() -> Optional[str]:
    """
    Get name of first pair in configuration

    Returns:
        Name of first pair or None
    """
    config_manager = get_config()
    pairs = config_manager.get_all_pairs()

    if not pairs:
        return None

    return next(iter(pairs.keys()))


# Legacy compatibility - provides old TradingSettings interface
class LegacyTradingSettings:
    """
    Backward compatibility wrapper for TradingSettingsManager

    Provides the old interface while using new unified config internally.

    Usage:
        >>> from config.adapter import LegacyTradingSettings
        >>>
        >>> settings = LegacyTradingSettings()
        >>> entry = settings.entry_threshold
        >>> symbols = settings.primary_symbol, settings.secondary_symbol
    """

    def __init__(self, pair_name: Optional[str] = None):
        """
        Initialize with pair configuration

        Args:
            pair_name: Name of pair to load (default: first pair)
        """
        config_manager = get_config()

        if pair_name is None:
            pair_name = get_default_pair_name()

        if pair_name is None:
            raise ValueError("No pairs configured in unified.yaml")

        self._pair = config_manager.get_pair(pair_name)
        if self._pair is None:
            raise ValueError(f"Pair '{pair_name}' not found in configuration")

    # Symbols
    @property
    def primary_symbol(self):
        return self._pair.primary_symbol

    @property
    def secondary_symbol(self):
        return self._pair.secondary_symbol

    # Trading parameters
    @property
    def entry_threshold(self):
        return self._pair.trading.entry_threshold

    @property
    def exit_threshold(self):
        return self._pair.trading.exit_threshold

    @property
    def stop_loss_zscore(self):
        return self._pair.trading.stop_loss_zscore

    @property
    def max_positions(self):
        return self._pair.trading.max_positions

    @property
    def volume_multiplier(self):
        return self._pair.trading.volume_multiplier

    # Model parameters
    @property
    def rolling_window_size(self):
        return self._pair.model.rolling_window_size

    @property
    def update_interval(self):
        return self._pair.model.update_interval

    @property
    def hedge_drift_threshold(self):
        return self._pair.model.hedge_drift_threshold

    # Risk parameters
    @property
    def max_position_pct(self):
        return self._pair.risk.max_position_pct

    @property
    def max_risk_pct(self):
        # Map to new parameter name
        return self._pair.risk.max_loss_per_setup_pct

    @property
    def max_drawdown_pct(self):
        return self._pair.risk.max_drawdown_pct

    @property
    def daily_loss_limit_pct(self):
        return self._pair.risk.daily_loss_limit_pct

    @property
    def session_start_time(self):
        return self._pair.risk.session_start_time

    @property
    def session_end_time(self):
        return self._pair.risk.session_end_time

    # Rebalancer parameters
    @property
    def scale_interval(self):
        return self._pair.rebalancer.scale_interval

    @property
    def initial_fraction(self):
        return self._pair.rebalancer.initial_fraction

    @property
    def min_adjustment_interval(self):
        return self._pair.rebalancer.min_adjustment_interval

    # Feature flags
    @property
    def enable_pyramiding(self):
        return self._pair.features.enable_pyramiding

    @property
    def enable_volume_rebalancing(self):
        return self._pair.features.enable_volume_rebalancing

    @property
    def enable_hedge_adjustment(self):
        # Legacy name for volume_rebalancing
        return self._pair.features.enable_volume_rebalancing

    @property
    def enable_regime_filter(self):
        return self._pair.features.enable_regime_filter

    # System parameters
    @property
    def magic_number(self):
        return self._pair.system.magic_number

    @property
    def zscore_history_size(self):
        return self._pair.system.zscore_history_size

    @property
    def position_data_dir(self):
        return self._pair.system.position_data_dir

    @property
    def log_level(self):
        return self._pair.system.log_level

    def to_dict(self) -> Dict[str, Any]:
        """Convert to flat dictionary"""
        return pair_config_to_flat_dict(self._pair)


# Export convenience function
__all__ = [
    'pair_config_to_flat_dict',
    'get_pair_as_dict',
    'make_legacy_compatible',
    'get_active_pair_config',
    'get_default_pair_name',
    'LegacyTradingSettings',
]

"""
Default Configuration Values
Single source of truth for all defaults
"""

from config.models import (
    GlobalConfig,
    MT5Config,
    PairConfig,
    TradingParameters,
    ModelParameters,
    RiskParameters,
    RebalancerParameters,
    FeatureFlags,
    SystemParameters,
    TransactionCosts,
)


def get_default_global_config() -> GlobalConfig:
    """
    Get default global configuration

    This is the SINGLE SOURCE OF TRUTH for all default values.
    No more scattered defaults across multiple files!
    """
    return GlobalConfig(
        version="2.0.0",
        config_format="unified_v1",

        # MT5 connection (empty - must be provided by user)
        mt5=MT5Config(),

        # Global defaults
        default_risk=RiskParameters(
            max_loss_per_setup_pct=2.0,
            max_total_unrealized_loss_pct=5.0,
            daily_loss_limit_pct=10.0,
            max_position_pct=20.0,
            max_drawdown_pct=20.0,
            max_daily_trades=50,
            max_consecutive_losses=5,
            session_start_time="00:00",
            session_end_time="23:59",
        ),

        default_features=FeatureFlags(
            enable_pyramiding=True,
            enable_volume_rebalancing=True,
            enable_regime_filter=False,
            enable_entry_cooldown=True,
            enable_manual_position_sync=True,
            enable_state_persistence=True,
        ),

        default_system=SystemParameters(
            magic_number=234000,
            zscore_history_size=200,
            position_data_dir="positions",
            log_level="INFO",
            timezone="UTC",
        ),

        # Default pairs (examples)
        pairs={
            'BTC_ETH': get_default_crypto_pair(),
            'XAU_XAG': get_default_metals_pair(),
        }
    )


def get_default_crypto_pair() -> PairConfig:
    """
    Default configuration for BTC/ETH pair
    Conservative settings for crypto volatility
    """
    return PairConfig(
        name='BTC_ETH',
        primary_symbol='BTCUSD',
        secondary_symbol='ETHUSD',
        description='Bitcoin/Ethereum crypto pair - high volatility',
        risk_level='HIGH',

        trading=TradingParameters(
            entry_threshold=2.5,  # Higher threshold for crypto
            exit_threshold=0.5,
            stop_loss_zscore=3.5,
            max_positions=10,
            volume_multiplier=1.0,
        ),

        model=ModelParameters(
            rolling_window_size=1000,
            update_interval=60,
            hedge_drift_threshold=0.05,
            cointegration_lookback=252,
            adf_significance=0.05,
            min_half_life=5,
            max_half_life=30,
        ),

        risk=RiskParameters(
            max_loss_per_setup_pct=1.0,  # Conservative for crypto
            max_total_unrealized_loss_pct=3.0,
            daily_loss_limit_pct=5.0,
            max_position_pct=15.0,  # Lower for crypto
            max_drawdown_pct=20.0,
            max_daily_trades=30,
            max_consecutive_losses=5,
            session_start_time="00:00",
            session_end_time="23:59",
        ),

        rebalancer=RebalancerParameters(
            scale_interval=0.5,
            initial_fraction=0.33,
            min_adjustment_interval=3600,
            volume_imbalance_threshold=0.10,
            entry_min_time_between=60,
        ),

        features=FeatureFlags(
            enable_pyramiding=True,
            enable_volume_rebalancing=True,
            enable_regime_filter=False,
            enable_entry_cooldown=True,
            enable_manual_position_sync=True,
            enable_state_persistence=True,
        ),

        system=SystemParameters(
            magic_number=234000,
            zscore_history_size=200,
            position_data_dir="positions",
            log_level="INFO",
            timezone="UTC",
        ),

        costs=TransactionCosts(
            commission_per_lot=2.50,
            spread_bps=3.0,  # Higher spread for crypto
            slippage_bps=3.0,
        ),
    )


def get_default_metals_pair() -> PairConfig:
    """
    Default configuration for Gold/Silver pair
    More aggressive settings due to stable correlation
    """
    return PairConfig(
        name='XAU_XAG',
        primary_symbol='XAUUSD',
        secondary_symbol='XAGUSD',
        description='Gold/Silver precious metals pair - stable correlation',
        risk_level='LOW',

        trading=TradingParameters(
            entry_threshold=2.0,  # Standard threshold
            exit_threshold=0.5,
            stop_loss_zscore=3.5,
            max_positions=10,
            volume_multiplier=1.0,
        ),

        model=ModelParameters(
            rolling_window_size=1000,
            update_interval=60,
            hedge_drift_threshold=0.05,
            cointegration_lookback=252,
            adf_significance=0.05,
            min_half_life=5,
            max_half_life=30,
        ),

        risk=RiskParameters(
            max_loss_per_setup_pct=2.0,  # Standard risk
            max_total_unrealized_loss_pct=5.0,
            daily_loss_limit_pct=10.0,
            max_position_pct=20.0,
            max_drawdown_pct=20.0,
            max_daily_trades=50,
            max_consecutive_losses=5,
            session_start_time="00:00",
            session_end_time="23:59",
        ),

        rebalancer=RebalancerParameters(
            scale_interval=0.5,
            initial_fraction=0.33,
            min_adjustment_interval=3600,
            volume_imbalance_threshold=0.10,
            entry_min_time_between=60,
        ),

        features=FeatureFlags(
            enable_pyramiding=True,
            enable_volume_rebalancing=True,
            enable_regime_filter=False,
            enable_entry_cooldown=True,
            enable_manual_position_sync=True,
            enable_state_persistence=True,
        ),

        system=SystemParameters(
            magic_number=234000,
            zscore_history_size=200,
            position_data_dir="positions",
            log_level="INFO",
            timezone="UTC",
        ),

        costs=TransactionCosts(
            commission_per_lot=2.50,
            spread_bps=2.0,
            slippage_bps=2.0,
        ),
    )


def get_default_indices_pair() -> PairConfig:
    """
    Default configuration for indices pairs (NAS100/SP500)
    Medium risk settings
    """
    return PairConfig(
        name='NAS_SP',
        primary_symbol='NAS100.r',
        secondary_symbol='SP500.r',
        description='NASDAQ/S&P500 indices pair',
        risk_level='MEDIUM',

        trading=TradingParameters(
            entry_threshold=2.0,
            exit_threshold=0.5,
            stop_loss_zscore=3.5,
            max_positions=10,
            volume_multiplier=1.0,
        ),

        model=ModelParameters(
            rolling_window_size=1000,
            update_interval=60,
            hedge_drift_threshold=0.05,
            cointegration_lookback=252,
            adf_significance=0.05,
            min_half_life=5,
            max_half_life=30,
        ),

        risk=RiskParameters(
            max_loss_per_setup_pct=2.0,
            max_total_unrealized_loss_pct=5.0,
            daily_loss_limit_pct=10.0,
            max_position_pct=20.0,
            max_drawdown_pct=20.0,
            max_daily_trades=50,
            max_consecutive_losses=5,
            session_start_time="00:00",
            session_end_time="23:59",
        ),

        rebalancer=RebalancerParameters(
            scale_interval=0.5,
            initial_fraction=0.33,
            min_adjustment_interval=3600,
            volume_imbalance_threshold=0.10,
            entry_min_time_between=60,
        ),

        features=FeatureFlags(
            enable_pyramiding=True,
            enable_volume_rebalancing=True,
            enable_regime_filter=False,
            enable_entry_cooldown=True,
            enable_manual_position_sync=True,
            enable_state_persistence=True,
        ),

        system=SystemParameters(
            magic_number=234000,
            zscore_history_size=200,
            position_data_dir="positions",
            log_level="INFO",
            timezone="UTC",
        ),

        costs=TransactionCosts(
            commission_per_lot=2.50,
            spread_bps=2.0,
            slippage_bps=2.0,
        ),
    )


# Quick access to defaults
DEFAULT_GLOBAL_CONFIG = get_default_global_config()
DEFAULT_CRYPTO_PAIR = get_default_crypto_pair()
DEFAULT_METALS_PAIR = get_default_metals_pair()
DEFAULT_INDICES_PAIR = get_default_indices_pair()

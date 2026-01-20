"""
Risk management limits and parameters
"""

# Strategy parameters
STRATEGY_PARAMS = {
    # Cointegration
    'cointegration_lookback': 252,
    'adf_significance': 0.05,
    'min_half_life': 5,
    'max_half_life': 30,
    'retest_interval_hours': 6,
    
    # Signal generation
    'entry_zscore': 2.0,
    'exit_zscore': 0.5,
    'stop_loss_zscore': 4.0,
    'min_correlation': 0.6,
    'zscore_lookback': 60,
    
    # Hedge ratio calculation
    'ols_weight': 0.30,
    'dollar_neutral_weight': 0.30,
    'vol_adjusted_weight': 0.20,
    'kalman_weight': 0.20,
    
    # Regime detection
    'regime_lookback': 60,
    'high_vol_threshold': 2.0,
    'low_corr_threshold': 0.5,
}

# Risk limits
RISK_LIMITS = {
    # Account
    'account_size': 100000,  # USD
    'currency': 'USD',
    
    # Position limits
    'max_position_size': 10.0,  # lots
    'min_position_size': 0.01,  # lots
    'max_portfolio_heat': 0.03,  # 3% of account
    
    # Risk metrics
    'max_drawdown_limit': 0.02,  # 2%
    'target_var_95': 0.02,  # 2%
    'kelly_fraction': 0.10,  # 10% of Kelly
    
    # Stop loss
    'use_stop_loss': True,
    'stop_loss_multiplier': 2.0,  # x stop_loss_zscore
    
    # Daily limits
    'max_daily_loss': -2000,  # USD
    'max_daily_trades': 20,
    'max_consecutive_losses': 5,
}

# Transaction costs
TRANSACTION_COSTS = {
    'primary_commission': 2.50,  # USD per lot
    'secondary_commission': 2.50,  # USD per lot
    'gold_spread_bps': 2.0,  # basis points
    'secondary_spread_bps': 3.0,
    'expected_slippage_bps': 2.0,
}

# Execution settings
EXECUTION_CONFIG = {
    'magic_number': 123456,
    'deviation': 20,  # price deviation in points
    'trade_comment': 'XAU_XAG_Pair',
    'fill_type': 'FOK',  # FOK or IOC
    'enable_trading': False,  # Set True for live trading
}

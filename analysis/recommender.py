"""
Parameter Recommender Module
Recommends optimal trading parameters based on historical analysis
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


class ParameterRecommender:
    """
    Recommend optimal parameters for pair trading
    """
    
    def __init__(self):
        pass
    
    def recommend_parameters(self, pair_analysis, strategy_style='moderate'):
        """
        Recommend parameters based on analysis and strategy style
        
        Args:
            pair_analysis: Dict with statistical analysis
            strategy_style: 'conservative', 'moderate', or 'aggressive'
            
        Returns:
            dict: Recommended parameters for each style
        """
        try:
            zscore_dist = pair_analysis.get('zscore_distribution', {})
            percentiles = zscore_dist.get('abs_percentiles', {})
            half_life = pair_analysis.get('half_life', 15)
            
            # Get percentile values
            p75 = abs(percentiles.get('75%', 1.5))
            p90 = abs(percentiles.get('90%', 2.0))
            p95 = abs(percentiles.get('95%', 2.5))
            p99 = abs(percentiles.get('99%', 3.0))
            
            # Determine optimal window size based on half-life
            window_size = self._recommend_window_size(half_life)
            
            # Generate recommendations for each style
            recommendations = {
                'conservative': self._get_conservative_params(p95, p99, window_size),
                'moderate': self._get_moderate_params(p90, p95, window_size),
                'aggressive': self._get_aggressive_params(p75, p90, window_size)
            }
            
            # Add expected performance (from backtest if available)
            for style, params in recommendations.items():
                params['expected_performance'] = self._estimate_performance(
                    params, pair_analysis
                )
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Parameter recommendation failed: {e}")
            return self._get_default_recommendations()
    
    def _get_conservative_params(self, p95, p99, window_size):
        """Conservative parameters - high win rate, low frequency"""
        return {
            'entry_zscore': round(p95, 2),
            'exit_zscore': round(p95 * 0.2, 2),  # Exit at 20% of entry
            'stop_loss_zscore': round(p99, 2),
            'window_size': window_size,
            'pyramiding_enabled': False,
            'pyramiding_levels': 0,
            'max_position_pct': 0.5,  # 0.5% of account per setup
            'description': 'High selectivity, high win rate, low frequency',
            'style': 'conservative'
        }
    
    def _get_moderate_params(self, p90, p95, window_size):
        """Moderate parameters - balanced approach"""
        return {
            'entry_zscore': round(p90, 2),
            'exit_zscore': round(p90 * 0.25, 2),
            'stop_loss_zscore': round(p95, 2),
            'window_size': window_size,
            'pyramiding_enabled': True,
            'pyramiding_levels': 2,
            'max_position_pct': 1.0,  # 1.0% of account per setup
            'description': 'Balanced win rate and frequency',
            'style': 'moderate'
        }
    
    def _get_aggressive_params(self, p75, p90, window_size):
        """Aggressive parameters - higher frequency, moderate win rate"""
        return {
            'entry_zscore': round(p75, 2),
            'exit_zscore': round(p75 * 0.4, 2),
            'stop_loss_zscore': round(p90, 2),
            'window_size': int(window_size * 0.8),  # Smaller window for faster signals
            'pyramiding_enabled': True,
            'pyramiding_levels': 3,
            'max_position_pct': 2.0,  # 2.0% of account per setup
            'description': 'Higher frequency, moderate win rate',
            'style': 'aggressive'
        }
    
    def _recommend_window_size(self, half_life):
        """Recommend window size based on mean reversion speed"""
        if np.isinf(half_life) or half_life <= 0:
            return 1000  # Default
        
        # Window should be ~50-100x half-life for stable statistics
        recommended = int(half_life * 75)
        
        # Clamp to reasonable range
        if recommended < 200:
            return 500
        elif recommended > 5000:
            return 2000
        elif recommended > 2000:
            return 2000
        elif recommended > 1000:
            return 1000
        elif recommended > 500:
            return 500
        else:
            return 500
    
    def _estimate_performance(self, params, pair_analysis):
        """
        Estimate expected performance based on parameters
        This is a simplified estimate - actual backtest will be more accurate
        """
        try:
            # Get base metrics
            corr = pair_analysis.get('correlation', {}).get('correlation', 0.8)
            coint_pvalue = pair_analysis.get('cointegration', {}).get('p_value', 0.05)
            half_life = pair_analysis.get('half_life', 15)
            
            # Estimate win rate based on entry threshold
            entry_z = params['entry_zscore']
            if entry_z > 2.5:
                base_winrate = 75
            elif entry_z > 2.0:
                base_winrate = 70
            elif entry_z > 1.5:
                base_winrate = 65
            else:
                base_winrate = 60
            
            # Adjust for correlation quality
            if corr > 0.9:
                base_winrate += 5
            elif corr < 0.75:
                base_winrate -= 5
            
            # Adjust for cointegration
            if coint_pvalue < 0.01:
                base_winrate += 3
            elif coint_pvalue > 0.10:
                base_winrate -= 3
            
            # Estimate profit per trade (as % of position)
            # Higher entry threshold = higher profit potential
            avg_profit_pct = entry_z * 0.4  # ~0.4% per z-score unit
            
            # Estimate Sharpe ratio
            # Good cointegration + high correlation = high Sharpe
            if corr > 0.85 and coint_pvalue < 0.05 and 5 < half_life < 25:
                sharpe = 2.0 + (corr - 0.85) * 10
            elif corr > 0.75 and coint_pvalue < 0.10:
                sharpe = 1.5
            else:
                sharpe = 1.0
            
            # Estimate max drawdown
            if params['style'] == 'conservative':
                max_dd = 5
            elif params['style'] == 'moderate':
                max_dd = 8
            else:
                max_dd = 12
            
            # Estimate trades per month
            if entry_z > 2.5:
                trades_per_month = 8
            elif entry_z > 2.0:
                trades_per_month = 15
            else:
                trades_per_month = 25
            
            return {
                'expected_winrate': round(min(95, max(50, base_winrate)), 1),
                'expected_profit_per_trade': round(avg_profit_pct, 2),
                'expected_sharpe': round(min(3.0, sharpe), 2),
                'expected_max_drawdown': round(max_dd, 1),
                'expected_trades_per_month': trades_per_month
            }
            
        except Exception as e:
            logger.error(f"Performance estimation failed: {e}")
            return {
                'expected_winrate': 65.0,
                'expected_profit_per_trade': 0.8,
                'expected_sharpe': 1.5,
                'expected_max_drawdown': 10.0,
                'expected_trades_per_month': 15
            }
    
    def _get_default_recommendations(self):
        """Fallback default recommendations"""
        return {
            'conservative': {
                'entry_zscore': 2.5,
                'exit_zscore': 0.5,
                'stop_loss_zscore': 3.5,
                'window_size': 1000,
                'pyramiding_enabled': False,
                'pyramiding_levels': 0,
                'max_position_pct': 0.5,
                'description': 'Default conservative',
                'style': 'conservative',
                'expected_performance': {
                    'expected_winrate': 70.0,
                    'expected_profit_per_trade': 1.0,
                    'expected_sharpe': 1.8,
                    'expected_max_drawdown': 5.0,
                    'expected_trades_per_month': 10
                }
            },
            'moderate': {
                'entry_zscore': 2.0,
                'exit_zscore': 0.5,
                'stop_loss_zscore': 3.0,
                'window_size': 1000,
                'pyramiding_enabled': True,
                'pyramiding_levels': 2,
                'max_position_pct': 1.0,
                'description': 'Default moderate',
                'style': 'moderate',
                'expected_performance': {
                    'expected_winrate': 65.0,
                    'expected_profit_per_trade': 0.8,
                    'expected_sharpe': 1.5,
                    'expected_max_drawdown': 8.0,
                    'expected_trades_per_month': 15
                }
            },
            'aggressive': {
                'entry_zscore': 1.5,
                'exit_zscore': 0.8,
                'stop_loss_zscore': 2.5,
                'window_size': 800,
                'pyramiding_enabled': True,
                'pyramiding_levels': 3,
                'max_position_pct': 2.0,
                'description': 'Default aggressive',
                'style': 'aggressive',
                'expected_performance': {
                    'expected_winrate': 60.0,
                    'expected_profit_per_trade': 0.6,
                    'expected_sharpe': 1.2,
                    'expected_max_drawdown': 12.0,
                    'expected_trades_per_month': 25
                }
            }
        }

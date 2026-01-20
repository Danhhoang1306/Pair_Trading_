"""
Pair Scoring Module
Calculates quality score for trading pairs (0-100)
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


class PairScorer:
    """
    Score trading pairs based on multiple factors
    """
    
    def __init__(self):
        # Scoring weights (must sum to 1.0)
        self.weights = {
            'correlation': 0.30,       # 30%
            'cointegration': 0.25,     # 25%
            'mean_reversion': 0.20,    # 20%
            'stationarity': 0.15,      # 15%
            'volatility_ratio': 0.10   # 10%
        }
        
        # Bonus points (max +10)
        self.bonus_thresholds = {
            'high_winrate': {'threshold': 75, 'points': 5},
            'high_sharpe': {'threshold': 2.0, 'points': 3},
            'low_drawdown': {'threshold': 10, 'points': 2}
        }
    
    def calculate_score(self, pair_analysis, backtest_results=None):
        """
        Calculate overall quality score for a pair
        
        Args:
            pair_analysis: Dict with statistical analysis results
            backtest_results: Optional backtest results for bonus points
            
        Returns:
            dict: Scoring breakdown
        """
        try:
            # Calculate individual scores
            corr_score = self._score_correlation(pair_analysis.get('correlation', {}))
            coint_score = self._score_cointegration(pair_analysis.get('cointegration', {}))
            reversion_score = self._score_mean_reversion(pair_analysis.get('half_life', np.inf))
            stationarity_score = self._score_stationarity(pair_analysis.get('stationarity', {}))
            vol_ratio_score = self._score_volatility_ratio(pair_analysis.get('volatility_ratio', {}))
            
            # Weighted sum
            base_score = (
                corr_score * self.weights['correlation'] +
                coint_score * self.weights['cointegration'] +
                reversion_score * self.weights['mean_reversion'] +
                stationarity_score * self.weights['stationarity'] +
                vol_ratio_score * self.weights['volatility_ratio']
            )
            
            # Calculate bonus points
            bonus_points = 0
            if backtest_results:
                bonus_points = self._calculate_bonus_points(backtest_results)
            
            # Final score (capped at 100)
            final_score = min(100.0, base_score + bonus_points)
            
            # Determine rating
            rating = self._get_rating(final_score)
            
            return {
                'final_score': round(final_score, 1),
                'base_score': round(base_score, 1),
                'bonus_points': round(bonus_points, 1),
                'rating': rating,
                'breakdown': {
                    'correlation': round(corr_score, 1),
                    'cointegration': round(coint_score, 1),
                    'mean_reversion': round(reversion_score, 1),
                    'stationarity': round(stationarity_score, 1),
                    'volatility_ratio': round(vol_ratio_score, 1)
                },
                'weighted_contributions': {
                    'correlation': round(corr_score * self.weights['correlation'], 1),
                    'cointegration': round(coint_score * self.weights['cointegration'], 1),
                    'mean_reversion': round(reversion_score * self.weights['mean_reversion'], 1),
                    'stationarity': round(stationarity_score * self.weights['stationarity'], 1),
                    'volatility_ratio': round(vol_ratio_score * self.weights['volatility_ratio'], 1)
                }
            }
            
        except Exception as e:
            logger.error(f"Score calculation failed: {e}")
            return {'final_score': 0.0, 'rating': '⚠️ ERROR'}
    
    def _score_correlation(self, corr_data):
        """Score correlation (0-100)"""
        corr = abs(corr_data.get('correlation', 0.0))
        
        if corr > 0.90:
            return 100
        elif corr > 0.80:
            return 80 + (corr - 0.80) * 200
        elif corr > 0.70:
            return 50 + (corr - 0.70) * 300
        elif corr > 0.60:
            return 20 + (corr - 0.60) * 300
        else:
            return 0
    
    def _score_cointegration(self, coint_data):
        """Score cointegration (0-100)"""
        p_value = coint_data.get('p_value', 1.0)
        
        if p_value < 0.01:
            return 100
        elif p_value < 0.05:
            return 75
        elif p_value < 0.10:
            return 50
        elif p_value < 0.15:
            return 25
        else:
            return 0
    
    def _score_mean_reversion(self, half_life):
        """Score mean reversion speed (0-100)"""
        if np.isinf(half_life) or half_life <= 0:
            return 0
        
        # Ideal half-life: 5-20 bars
        if 5 <= half_life <= 20:
            return 100
        elif 3 <= half_life < 5:
            # Too fast
            return 70 + (half_life - 3) * 15
        elif 20 < half_life <= 30:
            # A bit slow but acceptable
            return 70 + (30 - half_life) * 3
        elif 30 < half_life <= 50:
            return 40 + (50 - half_life) * 1.5
        else:
            # Too slow or too fast
            return 20
    
    def _score_stationarity(self, stat_data):
        """Score stationarity (0-100)"""
        adf_stat = stat_data.get('adf_statistic', 0.0)
        
        if adf_stat < -4.0:
            return 100  # Very stationary
        elif adf_stat < -3.0:
            return 80
        elif adf_stat < -2.5:
            return 60
        elif adf_stat < -2.0:
            return 40
        else:
            return 0  # Non-stationary
    
    def _score_volatility_ratio(self, vol_data):
        """Score volatility similarity (0-100)"""
        ratio = vol_data.get('ratio', 1.0)
        
        if np.isinf(ratio):
            return 0
        
        # Ideal: ratio close to 1.0
        deviation = abs(np.log(ratio))  # Log scale for symmetry
        
        if deviation < 0.15:  # Very similar (ratio 0.86-1.16)
            return 100
        elif deviation < 0.30:  # Similar (ratio 0.74-1.35)
            return 80 + (0.30 - deviation) * 133
        elif deviation < 0.50:  # Moderately similar (ratio 0.61-1.65)
            return 50 + (0.50 - deviation) * 150
        else:
            return 30  # Very different
    
    def _calculate_bonus_points(self, backtest_results):
        """Calculate bonus points from backtest results"""
        bonus = 0
        
        # High win rate bonus
        win_rate = backtest_results.get('win_rate', 0)
        if win_rate > self.bonus_thresholds['high_winrate']['threshold']:
            bonus += self.bonus_thresholds['high_winrate']['points']
        
        # High Sharpe ratio bonus
        sharpe = backtest_results.get('sharpe_ratio', 0)
        if sharpe > self.bonus_thresholds['high_sharpe']['threshold']:
            bonus += self.bonus_thresholds['high_sharpe']['points']
        
        # Low drawdown bonus
        max_dd = abs(backtest_results.get('max_drawdown', 100))
        if max_dd < self.bonus_thresholds['low_drawdown']['threshold']:
            bonus += self.bonus_thresholds['low_drawdown']['points']
        
        return bonus
    
    def _get_rating(self, score):
        """Convert score to star rating"""
        if score >= 90:
            return '⭐⭐⭐⭐⭐ EXCELLENT'
        elif score >= 80:
            return '⭐⭐⭐⭐ VERY GOOD'
        elif score >= 70:
            return '⭐⭐⭐ GOOD'
        elif score >= 60:
            return '⭐⭐ FAIR'
        elif score >= 50:
            return '⭐ POOR'
        else:
            return '⚠️ UNSUITABLE'

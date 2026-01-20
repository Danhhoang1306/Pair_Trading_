"""
Analysis Worker Module
QRunnable worker that performs pair discovery analysis in background
"""

from PyQt6.QtCore import QRunnable

import pandas as pd
import numpy as np
from datetime import datetime
import logging
from core.mt5_manager import get_mt5

from .signals import AnalysisSignals
from .data_loader import MT5DataLoader
from .statistics import StatisticsCalculator
from .scorer import PairScorer
from .recommender import ParameterRecommender
from .backtester import SimpleBacktester

logger = logging.getLogger(__name__)


class AnalysisWorker(QRunnable):
    """
    Worker that runs pair discovery analysis in background thread
    Completely isolated from trading system
    """
    
    def __init__(self, params):
        super().__init__()
        self.params = params
        self.signals = AnalysisSignals()
        self.should_stop = False
        
        # Initialize components
        self.data_loader = MT5DataLoader()
        self.stats_calc = StatisticsCalculator()
        self.scorer = PairScorer()
        self.recommender = ParameterRecommender()
        self.backtester = SimpleBacktester()
        
    def run(self):
        """Main analysis workflow"""
        try:
            self.signals.log.emit("Starting pair discovery analysis...")
            
            # ========== PHASE 1: LOAD DATA ==========
            self.signals.phase_change.emit("Phase 1: Loading Data")
            symbols_data = self._load_all_data()
            
            if self.should_stop:
                self.signals.log.emit("Analysis cancelled")
                return
            
            if len(symbols_data) < 2:
                self.signals.error.emit("Insufficient data loaded. Need at least 2 symbols.")
                return
            
            # ========== PHASE 2: CALCULATE CORRELATIONS ==========
            self.signals.phase_change.emit("Phase 2: Calculating Correlations")
            valid_pairs = self._find_correlated_pairs(symbols_data)
            
            if self.should_stop:
                return
            
            if len(valid_pairs) == 0:
                self.signals.error.emit("No pairs found with sufficient correlation")
                return
            
            self.signals.log.emit(f"Found {len(valid_pairs)} pairs with correlation > {self.params['min_correlation']}")
            
            # ========== PHASE 3: DEEP ANALYSIS ==========
            self.signals.phase_change.emit("Phase 3: Analyzing Pairs")
            analyzed_pairs = self._analyze_pairs(valid_pairs, symbols_data)
            
            if self.should_stop:
                return
            
            # ========== PHASE 4: BACKTEST ==========
            self.signals.phase_change.emit("Phase 4: Backtesting Pairs")
            backtested_pairs = self._backtest_pairs(analyzed_pairs, symbols_data)
            
            if self.should_stop:
                return
            
            # ========== PHASE 5: RANK RESULTS ==========
            self.signals.phase_change.emit("Phase 5: Ranking Results")
            final_results = self._rank_and_score(backtested_pairs)
            
            # ========== COMPLETE ==========
            self.signals.progress.emit(100.0)
            self.signals.completed.emit(final_results)
            self.signals.log.emit(f"Analysis complete! Found {len(final_results)} valid pairs")
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            self.signals.error.emit(f"Analysis failed: {str(e)}")
        
        finally:
            # Cleanup
            self.data_loader.disconnect()
    
    def _load_all_data(self):
        """Load historical data for all symbols"""
        try:
            # Connect to MT5
            if not self.data_loader.connect():
                raise ConnectionError("Cannot connect to MT5")
            
            # Get symbols to analyze
            if self.params.get('auto_detect_symbols', True):
                all_symbols = self.data_loader.get_available_symbols()
            else:
                all_symbols = self.params.get('custom_symbols', [])
            
            if len(all_symbols) == 0:
                raise ValueError("No symbols to analyze")
            
            self.signals.log.emit(f"Loading data for {len(all_symbols)} symbols...")
            
            # Load data for each symbol
            symbols_data = {}
            start_date = self.params.get('start_date')
            end_date = self.params.get('end_date')
            
            for i, symbol in enumerate(all_symbols):
                if self.should_stop:
                    break
                
                # Update progress
                progress = (i / len(all_symbols)) * 20  # Phase 1 = 0-20%
                self.signals.progress.emit(progress)
                self.signals.status_update.emit({
                    'phase': 'Loading Data',
                    'current_item': symbol,
                    'current_index': i + 1,
                    'total_items': len(all_symbols)
                })
                
                # Load data
                mt5 = get_mt5()
                df = self.data_loader.load_historical_data(
                    symbol,
                    timeframe=mt5.TIMEFRAME_H1,
                    start_date=start_date,
                    end_date=end_date,
                    use_cache=True
                )
                
                # Quality check
                if len(df) < 1000:
                    logger.warning(f"{symbol}: Insufficient data ({len(df)} bars)")
                    continue
                
                # Check for gaps - only in close column
                data_quality = self._check_data_quality(df)
                # Lower threshold since we're only checking close column now
                if data_quality < self.params.get('min_data_quality', 0.90):
                    logger.warning(f"{symbol}: Poor data quality ({data_quality:.1%})")
                    continue
                
                symbols_data[symbol] = df
            
            self.signals.log.emit(f"Loaded data for {len(symbols_data)} symbols")
            return symbols_data
            
        except Exception as e:
            logger.error(f"Data loading failed: {e}")
            raise
    
    def _check_data_quality(self, df):
        """Check data quality (% completeness)"""
        # Only check 'close' column which is what we actually use
        if 'close' not in df.columns:
            return 0.0
        
        close_series = df['close']
        completeness = (len(close_series) - close_series.isnull().sum()) / len(close_series)
        return completeness
    
    def _find_correlated_pairs(self, symbols_data):
        """Find pairs with high correlation"""
        symbols = list(symbols_data.keys())
        total_pairs = len(symbols) * (len(symbols) - 1) // 2
        
        valid_pairs = []
        pair_count = 0
        
        min_corr = self.params.get('min_correlation', 0.70)
        
        for i, sym1 in enumerate(symbols):
            if self.should_stop:
                break
            
            for sym2 in symbols[i+1:]:
                pair_count += 1
                
                # Update progress
                progress = 20 + (pair_count / total_pairs) * 25  # Phase 2 = 20-45%
                self.signals.progress.emit(progress)
                
                if pair_count % 100 == 0:
                    self.signals.status_update.emit({
                        'phase': 'Calculating Correlations',
                        'current_item': f"{sym1}/{sym2}",
                        'current_index': pair_count,
                        'total_items': total_pairs
                    })
                
                # Get close prices
                data1 = symbols_data[sym1]['close'].values
                data2 = symbols_data[sym2]['close'].values
                
                # Ensure same length
                min_len = min(len(data1), len(data2))
                data1 = data1[-min_len:]
                data2 = data2[-min_len:]
                
                # Calculate correlation
                corr_result = self.stats_calc.calculate_correlation(data1, data2)
                corr = abs(corr_result['correlation'])
                
                if corr >= min_corr:
                    valid_pairs.append({
                        'symbol1': sym1,
                        'symbol2': sym2,
                        'correlation': corr
                    })
        
        return valid_pairs
    
    def _analyze_pairs(self, pairs, symbols_data):
        """Perform deep statistical analysis on each pair"""
        analyzed_pairs = []
        window_size = self.params.get('window_size', 1000)
        
        for i, pair in enumerate(pairs):
            if self.should_stop:
                break
            
            # Update progress
            progress = 45 + (i / len(pairs)) * 25  # Phase 3 = 45-70%
            self.signals.progress.emit(progress)
            self.signals.status_update.emit({
                'phase': 'Analyzing Pairs',
                'current_item': f"{pair['symbol1']}/{pair['symbol2']}",
                'current_index': i + 1,
                'total_items': len(pairs)
            })
            
            try:
                # Get data
                data1 = symbols_data[pair['symbol1']]['close'].values
                data2 = symbols_data[pair['symbol2']]['close'].values
                
                # Ensure same length
                min_len = min(len(data1), len(data2))
                data1 = data1[-min_len:]
                data2 = data2[-min_len:]
                
                # Calculate spread
                spread = data1 - data2
                
                # Calculate statistics
                analysis = {
                    'symbol1': pair['symbol1'],
                    'symbol2': pair['symbol2'],
                    'correlation': self.stats_calc.calculate_correlation(data1, data2),
                    'rolling_correlation': self.stats_calc.calculate_rolling_correlation(data1, data2),
                    'cointegration': self.stats_calc.test_cointegration(data1, data2),
                    'stationarity': self.stats_calc.test_stationarity(spread),
                    'half_life': self.stats_calc.calculate_half_life(pd.Series(spread)),
                    'spread_stats': self.stats_calc.calculate_spread_stats(pd.Series(spread)),
                    'volatility_ratio': self.stats_calc.calculate_volatility_ratio(
                        pd.Series(data1), pd.Series(data2)
                    ),
                    # ✅ CRITICAL: Store data for backtest!
                    '_data1': data1,
                    '_data2': data2
                }
                
                # Calculate z-scores for distribution
                mean = np.mean(spread)
                std = np.std(spread)
                zscores = (spread - mean) / std if std > 0 else spread * 0
                analysis['zscore_distribution'] = self.stats_calc.calculate_zscore_distribution(
                    pd.Series(zscores)
                )
                
                analyzed_pairs.append(analysis)
                
                # Emit partial result
                self.signals.partial_result.emit(analysis)
                
            except Exception as e:
                logger.error(f"Analysis failed for {pair['symbol1']}/{pair['symbol2']}: {e}")
                continue
        
        return analyzed_pairs
    
    def _backtest_pairs(self, analyzed_pairs, symbols_data):
        """Backtest recommended parameters on each pair"""
        backtested_pairs = []
        
        for i, pair_analysis in enumerate(analyzed_pairs):
            if self.should_stop:
                break
            
            # Update progress
            progress = 70 + (i / len(analyzed_pairs)) * 20  # Phase 4 = 70-90%
            self.signals.progress.emit(progress)
            self.signals.status_update.emit({
                'phase': 'Backtesting Pairs',
                'current_item': f"{pair_analysis['symbol1']}/{pair_analysis['symbol2']}",
                'current_index': i + 1,
                'total_items': len(analyzed_pairs)
            })
            
            try:
                # ✅ CRITICAL: Use stored data from analysis phase
                # This ensures data is always available for backtest
                if '_data1' in pair_analysis and '_data2' in pair_analysis:
                    data1 = pair_analysis['_data1']
                    data2 = pair_analysis['_data2']
                    logger.debug(f"Using stored data for backtest: {pair_analysis['symbol1']}/{pair_analysis['symbol2']}")
                else:
                    # Fallback: Try to get from symbols_data (shouldn't happen)
                    logger.warning(f"No stored data for {pair_analysis['symbol1']}/{pair_analysis['symbol2']}, fetching from symbols_data")
                    try:
                        data1 = symbols_data[pair_analysis['symbol1']]['close'].values
                        data2 = symbols_data[pair_analysis['symbol2']]['close'].values
                    except KeyError as e:
                        logger.error(f"Symbol data not found: {e}")
                        raise
                
                # Validate data
                if len(data1) < 100 or len(data2) < 100:
                    logger.warning(f"Insufficient data for backtest: {len(data1)}, {len(data2)} bars")
                    raise ValueError("Insufficient data for backtest")
                
                # Get recommended parameters
                recommendations = self.recommender.recommend_parameters(pair_analysis)
                moderate_params = recommendations['moderate']
                
                logger.debug(f"Backtesting with params: entry={moderate_params['entry_zscore']}, window={moderate_params['window_size']}")
                
                # Backtest
                backtest_results = self.backtester.backtest_parameters(
                    data1, data2,
                    moderate_params,
                    window_size=moderate_params['window_size']
                )
                
                # Validate backtest results
                if backtest_results and backtest_results.get('total_trades', 0) > 0:
                    logger.info(f"Backtest complete: {backtest_results['total_trades']} trades, {backtest_results['win_rate']:.1f}% win rate")
                else:
                    logger.warning(f"Backtest generated no trades for {pair_analysis['symbol1']}/{pair_analysis['symbol2']}")
                
                # Add results
                pair_analysis['backtest'] = backtest_results
                pair_analysis['recommended_params'] = recommendations
                
                # ✅ Clean up stored data to save memory (optional)
                # Keep data for now in case needed later
                # del pair_analysis['_data1']
                # del pair_analysis['_data2']
                
                backtested_pairs.append(pair_analysis)
                
            except Exception as e:
                logger.error(f"Backtest failed for {pair_analysis['symbol1']}/{pair_analysis['symbol2']}: {e}", exc_info=True)
                # Still add pair without backtest
                pair_analysis['backtest'] = None
                pair_analysis['recommended_params'] = None
                backtested_pairs.append(pair_analysis)
        
        return backtested_pairs
    
    def _rank_and_score(self, pairs):
        """Calculate scores and rank pairs"""
        scored_pairs = []
        
        for i, pair in enumerate(pairs):
            # Update progress
            progress = 90 + (i / len(pairs)) * 10  # Phase 5 = 90-100%
            self.signals.progress.emit(progress)
            
            try:
                # Calculate score
                backtest_results = pair['backtest'] if pair.get('backtest') else None
                score_result = self.scorer.calculate_score(pair, backtest_results)
                
                pair['score'] = score_result['final_score']
                pair['rating'] = score_result['rating']
                pair['score_breakdown'] = score_result
                
                scored_pairs.append(pair)
                
            except Exception as e:
                logger.error(f"Scoring failed for {pair['symbol1']}/{pair['symbol2']}: {e}")
                pair['score'] = 0
                pair['rating'] = '⚠️ ERROR'
                scored_pairs.append(pair)
        
        # Sort by score (highest first)
        scored_pairs.sort(key=lambda x: x['score'], reverse=True)
        
        # Add rank
        for rank, pair in enumerate(scored_pairs, 1):
            pair['rank'] = rank
        
        return scored_pairs
    
    def stop(self):
        """Request worker to stop gracefully"""
        self.should_stop = True

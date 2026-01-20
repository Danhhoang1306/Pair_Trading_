"""
Pair Discovery Engine
Main engine that manages analysis workers and coordinates the discovery process
"""

from PyQt6.QtCore import QThreadPool, QObject
import json
from pathlib import Path
from datetime import datetime
import logging

from .analysis_worker import AnalysisWorker

logger = logging.getLogger(__name__)


class PairDiscoveryEngine(QObject):
    """
    Main engine for pair discovery analysis
    Manages worker threads and coordinates analysis
    Completely isolated from trading system
    """
    
    def __init__(self):
        super().__init__()
        
        # Separate thread pool for analysis
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)  # 4 worker threads
        
        # State
        self.is_running = False
        self.current_worker = None
        self.current_params = None
        
        # Results storage
        self.latest_results = []
        self.results_dir = Path("analysis_results/")
        self.results_dir.mkdir(exist_ok=True)
        
        logger.info("Pair Discovery Engine initialized")
    
    def start_analysis(self, params):
        """
        Start pair discovery analysis
        
        Args:
            params: Dict with analysis parameters
                - start_date: Start date for historical data
                - end_date: End date for historical data
                - window_size: Window size for calculations
                - min_correlation: Minimum correlation threshold
                - auto_detect_symbols: Auto-detect all MT5 symbols
                - custom_symbols: Custom symbol list (if not auto-detect)
                - min_data_quality: Minimum data quality (0-1)
                
        Returns:
            bool: True if started successfully
        """
        if self.is_running:
            logger.warning("Analysis already running")
            return False
        
        try:
            # Validate params
            validated_params = self._validate_params(params)
            
            # Create worker
            self.current_worker = AnalysisWorker(validated_params)
            self.current_params = validated_params
            
            # ✅ CRITICAL: Connect completed signal to reset is_running flag
            self.current_worker.signals.completed.connect(self._on_worker_completed)
            self.current_worker.signals.error.connect(self._on_worker_error)
            
            # Set as running
            self.is_running = True
            
            # Start worker in thread pool
            self.thread_pool.start(self.current_worker)
            
            logger.info("Analysis started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start analysis: {e}")
            self.is_running = False
            return False
    
    def _on_worker_completed(self, results):
        """Worker completed - reset state"""
        self.latest_results = results
        self.is_running = False  # ✅ RESET FLAG
        logger.info(f"Analysis completed with {len(results)} results - Ready for new analysis")
    
    def _on_worker_error(self, error_msg):
        """Worker error - reset state"""
        self.is_running = False  # ✅ RESET FLAG ON ERROR TOO
        logger.error(f"Analysis failed: {error_msg} - Ready for new analysis")
    
    def stop_analysis(self):
        """Stop current analysis"""
        if not self.is_running or self.current_worker is None:
            return
        
        # Request worker to stop
        self.current_worker.stop()
        self.is_running = False  # ✅ RESET FLAG
        logger.info("Analysis stop requested - Ready for new analysis")
    
    def pause_analysis(self):
        """Pause current analysis (not implemented yet)"""
        # TODO: Implement pause/resume functionality
        logger.warning("Pause not yet implemented")
    
    def resume_analysis(self):
        """Resume paused analysis (not implemented yet)"""
        # TODO: Implement pause/resume functionality
        logger.warning("Resume not yet implemented")
    
    def save_results(self, results, filename=None):
        """
        Save analysis results to file
        
        Args:
            results: List of pair analysis results
            filename: Optional custom filename
            
        Returns:
            Path: Path to saved file
        """
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"pair_discovery_{timestamp}.json"
            
            filepath = self.results_dir / filename
            
            # Prepare results for JSON (remove non-serializable objects)
            serializable_results = self._make_serializable(results)
            
            # Save
            with open(filepath, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'parameters': self.current_params,
                    'total_pairs': len(results),
                    'results': serializable_results
                }, f, indent=2)
            
            logger.info(f"Results saved to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            return None
    
    def load_results(self, filepath):
        """
        Load previously saved results
        
        Args:
            filepath: Path to results file
            
        Returns:
            dict: Loaded results
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            logger.info(f"Loaded results from {filepath}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to load results: {e}")
            return None
    
    def get_recent_analyses(self, limit=10):
        """
        Get list of recent analysis files
        
        Args:
            limit: Maximum number of files to return
            
        Returns:
            list: List of file paths
        """
        try:
            files = sorted(
                self.results_dir.glob("pair_discovery_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            return files[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get recent analyses: {e}")
            return []
    
    def _validate_params(self, params):
        """Validate and set defaults for parameters"""
        validated = {
            'start_date': params.get('start_date', '2024-01-01'),
            'end_date': params.get('end_date', datetime.now().strftime('%Y-%m-%d')),
            'window_size': int(params.get('window_size', 1000)),
            'min_correlation': float(params.get('min_correlation', 0.70)),
            'auto_detect_symbols': params.get('auto_detect_symbols', True),
            'custom_symbols': params.get('custom_symbols', []),
            'min_data_quality': float(params.get('min_data_quality', 0.90))  # Lower from 0.95
        }
        
        # Validation
        if validated['window_size'] < 100:
            raise ValueError("Window size must be >= 100")
        
        if not (0 <= validated['min_correlation'] <= 1):
            raise ValueError("Min correlation must be between 0 and 1")
        
        if not (0 <= validated['min_data_quality'] <= 1):
            raise ValueError("Min data quality must be between 0 and 1")
        
        return validated
    
    def _make_serializable(self, results):
        """Convert results to JSON-serializable format"""
        serializable = []
        
        for pair in results:
            # Create clean copy
            clean_pair = {
                'rank': pair.get('rank', 0),
                'symbol1': pair.get('symbol1', ''),
                'symbol2': pair.get('symbol2', ''),
                'score': round(pair.get('score', 0), 2),
                'rating': pair.get('rating', ''),
                'correlation': round(pair.get('correlation', {}).get('correlation', 0), 4),
                'cointegration_pvalue': round(pair.get('cointegration', {}).get('p_value', 1), 4),
                'half_life': round(pair.get('half_life', 0), 2) if pair.get('half_life') else None,
                'recommended_params': pair.get('recommended_params', {}),
                'backtest': {
                    'win_rate': pair.get('backtest', {}).get('win_rate', 0),
                    'total_trades': pair.get('backtest', {}).get('total_trades', 0),
                    'sharpe_ratio': pair.get('backtest', {}).get('sharpe_ratio', 0),
                    'max_drawdown': pair.get('backtest', {}).get('max_drawdown', 0)
                } if pair.get('backtest') else None
            }
            
            serializable.append(clean_pair)
        
        return serializable
    
    def get_status(self):
        """Get current engine status"""
        return {
            'is_running': self.is_running,
            'active_threads': self.thread_pool.activeThreadCount(),
            'max_threads': self.thread_pool.maxThreadCount(),
            'has_results': len(self.latest_results) > 0,
            'results_count': len(self.latest_results)
        }

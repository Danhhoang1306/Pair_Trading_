"""
Simple Backtester Module
Simulate trades based on parameters and calculate performance metrics
"""

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class SimpleBacktester:
    """
    Simple backtester for pair trading strategies
    Tests parameters on historical data
    """
    
    def __init__(self):
        pass
    
    def backtest_parameters(self, data1, data2, params, window_size=1000):
        """
        Backtest parameters on historical data
        
        Args:
            data1: First symbol price data (close prices)
            data2: Second symbol price data (close prices)
            params: Dict with 'entry_zscore', 'exit_zscore', 'stop_loss_zscore'
            window_size: Window for calculating z-score
            
        Returns:
            dict: Backtest results
        """
        try:
            # Prepare data
            df = pd.DataFrame({
                's1': data1,
                's2': data2
            })
            
            # Calculate spread
            df['spread'] = df['s1'] - df['s2']
            
            # Calculate rolling statistics
            df['spread_mean'] = df['spread'].rolling(window_size).mean()
            df['spread_std'] = df['spread'].rolling(window_size).std()
            
            # Calculate z-score
            df['zscore'] = (df['spread'] - df['spread_mean']) / df['spread_std']
            
            # Drop NaN rows (first window_size rows)
            df = df.dropna()
            
            if len(df) < 100:
                logger.warning("Insufficient data for backtest")
                return self._get_empty_results()
            
            # Simulate trades
            trades = self._simulate_trades(df, params)
            
            if len(trades) == 0:
                logger.warning("No trades generated in backtest")
                return self._get_empty_results()
            
            # Calculate metrics
            results = self._calculate_metrics(trades)
            
            return results
            
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return self._get_empty_results()
    
    def _simulate_trades(self, df, params):
        """
        Simulate trades based on z-score signals
        
        Args:
            df: DataFrame with z-scores
            params: Trading parameters
            
        Returns:
            list: List of trade dicts
        """
        trades = []
        position = None  # Current position: 'long' or 'short' or None
        entry_idx = None
        entry_zscore = None
        entry_spread = None
        
        entry_threshold = params.get('entry_zscore', 2.0)
        exit_threshold = params.get('exit_zscore', 0.5)
        stop_threshold = params.get('stop_loss_zscore', 3.0)
        
        for idx, row in df.iterrows():
            z = row['zscore']
            
            # Entry logic
            if position is None:
                if z < -entry_threshold:
                    # Enter LONG spread (buy spread)
                    position = 'long'
                    entry_idx = idx
                    entry_zscore = z
                    entry_spread = row['spread']
                    
                elif z > entry_threshold:
                    # Enter SHORT spread (sell spread)
                    position = 'short'
                    entry_idx = idx
                    entry_zscore = z
                    entry_spread = row['spread']
            
            # Exit logic
            elif position == 'long':
                exit_triggered = False
                exit_reason = None
                
                # Normal exit: z-score returns to near mean
                if z >= -exit_threshold:
                    exit_triggered = True
                    exit_reason = 'mean_reversion'
                
                # Stop loss: z-score moves further away
                elif z < -stop_threshold:
                    exit_triggered = True
                    exit_reason = 'stop_loss'
                
                if exit_triggered:
                    # Close position
                    exit_spread = row['spread']
                    spread_pnl = exit_spread - entry_spread  # Long spread profit (absolute)
                    
                    # Calculate percentage return based on entry spread
                    # Avoid division by zero
                    if abs(entry_spread) > 0.01:
                        pnl_pct = (spread_pnl / abs(entry_spread)) * 100
                    else:
                        pnl_pct = 0.0
                    
                    # Calculate bars held
                    bars_held = (idx - entry_idx).days if hasattr((idx - entry_idx), 'days') else 1
                    
                    trades.append({
                        'entry_time': entry_idx,
                        'exit_time': idx,
                        'side': 'long',
                        'entry_zscore': entry_zscore,
                        'exit_zscore': z,
                        'entry_spread': entry_spread,
                        'exit_spread': exit_spread,
                        'spread_pnl': spread_pnl,
                        'pnl_pct': pnl_pct,  # ✅ NEW: Percentage return
                        'bars_held': bars_held,
                        'exit_reason': exit_reason
                    })
                    
                    position = None
                    
            elif position == 'short':
                exit_triggered = False
                exit_reason = None
                
                # Normal exit: z-score returns to near mean
                if z <= exit_threshold:
                    exit_triggered = True
                    exit_reason = 'mean_reversion'
                
                # Stop loss: z-score moves further away
                elif z > stop_threshold:
                    exit_triggered = True
                    exit_reason = 'stop_loss'
                
                if exit_triggered:
                    # Close position
                    exit_spread = row['spread']
                    spread_pnl = entry_spread - exit_spread  # Short spread profit (absolute)
                    
                    # Calculate percentage return based on entry spread
                    if abs(entry_spread) > 0.01:
                        pnl_pct = (spread_pnl / abs(entry_spread)) * 100
                    else:
                        pnl_pct = 0.0
                    
                    bars_held = (idx - entry_idx).days if hasattr((idx - entry_idx), 'days') else 1
                    
                    trades.append({
                        'entry_time': entry_idx,
                        'exit_time': idx,
                        'side': 'short',
                        'entry_zscore': entry_zscore,
                        'exit_zscore': z,
                        'entry_spread': entry_spread,
                        'exit_spread': exit_spread,
                        'spread_pnl': spread_pnl,
                        'pnl_pct': pnl_pct,  # ✅ NEW: Percentage return
                        'bars_held': bars_held,
                        'exit_reason': exit_reason
                    })
                    
                    position = None
        
        return trades
    
    def _calculate_metrics(self, trades):
        """
        Calculate performance metrics from trades
        
        Args:
            trades: List of trade dicts
            
        Returns:
            dict: Performance metrics
        """
        if len(trades) == 0:
            return self._get_empty_results()
        
        # Extract trade data - USE PERCENTAGE RETURNS
        pnls_pct = [t.get('pnl_pct', 0) for t in trades]
        pnls_abs = [t['spread_pnl'] for t in trades]  # Keep for reference
        bars_held = [t['bars_held'] for t in trades]
        
        # Win/loss stats (based on percentage returns)
        wins = [p for p in pnls_pct if p > 0]
        losses = [p for p in pnls_pct if p < 0]
        
        win_count = len(wins)
        loss_count = len(losses)
        total_trades = len(trades)
        
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        # Profit stats (percentage)
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        avg_pnl = np.mean(pnls_pct)
        
        total_profit = sum(wins)
        total_loss = abs(sum(losses))
        
        profit_factor = (total_profit / total_loss) if total_loss > 0 else np.inf
        
        # Return stats (percentage)
        total_return = sum(pnls_pct)
        
        # Risk metrics - USE PERCENTAGE RETURNS
        max_drawdown = self._calculate_max_drawdown(pnls_pct)
        
        # Sharpe ratio (using percentage returns)
        returns = np.array(pnls_pct)
        if np.std(returns) > 0:
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = np.std(downside_returns)
        else:
            downside_std = np.std(returns) if len(returns) > 0 else 1
        
        if downside_std > 0:
            sortino_ratio = (np.mean(returns) / downside_std) * np.sqrt(252)
        else:
            sortino_ratio = 0
        
        # Trade duration
        avg_bars_held = np.mean(bars_held) if bars_held else 0
        
        # Exit reasons
        stop_loss_count = len([t for t in trades if t['exit_reason'] == 'stop_loss'])
        mean_reversion_count = len([t for t in trades if t['exit_reason'] == 'mean_reversion'])
        
        return {
            'total_trades': total_trades,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': round(win_rate, 2),
            'avg_win': round(avg_win, 4),  # % return
            'avg_loss': round(avg_loss, 4),  # % return
            'avg_pnl': round(avg_pnl, 4),  # % return
            'total_return': round(total_return, 4),  # % return
            'profit_factor': round(profit_factor, 2) if not np.isinf(profit_factor) else 999.0,
            'max_drawdown': round(max_drawdown, 2),  # % drawdown (0-100)
            'sharpe_ratio': round(sharpe_ratio, 2),
            'sortino_ratio': round(sortino_ratio, 2),
            'avg_bars_held': round(avg_bars_held, 1),
            'stop_loss_exits': stop_loss_count,
            'mean_reversion_exits': mean_reversion_count,
            'trades': trades  # Include full trade list
        }
    
    def _calculate_max_drawdown(self, pnls):
        """
        Calculate maximum drawdown as percentage of peak equity
        
        Args:
            pnls: List of trade PnLs (in spread units)
            
        Returns:
            float: Maximum drawdown as percentage (0-100)
        """
        if len(pnls) == 0:
            return 0.0
        
        # Build equity curve (cumulative PnL)
        equity = np.cumsum(pnls)
        
        # Add starting equity of 0
        equity = np.insert(equity, 0, 0)
        
        # Track running maximum equity
        running_max = np.maximum.accumulate(equity)
        
        # Calculate drawdown at each point (absolute)
        drawdown = running_max - equity
        
        # Find maximum drawdown (absolute)
        max_dd_abs = np.max(drawdown)
        
        # Convert to percentage of peak
        # If peak is 0 or negative, drawdown is 0 (no profit to lose)
        peak_equity = np.max(running_max)
        
        if peak_equity > 0:
            max_dd_pct = (max_dd_abs / peak_equity) * 100
        else:
            # No positive equity achieved, use absolute max loss
            # as percentage of a nominal starting capital (e.g., 1000)
            nominal_capital = 1000
            max_dd_pct = (max_dd_abs / nominal_capital) * 100
        
        # Cap at reasonable maximum (100% = total loss)
        max_dd_pct = min(max_dd_pct, 100.0)
        
        return max_dd_pct
    
    def _get_empty_results(self):
        """Return empty results structure"""
        return {
            'total_trades': 0,
            'win_count': 0,
            'loss_count': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'avg_pnl': 0.0,
            'total_return': 0.0,
            'profit_factor': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'avg_bars_held': 0.0,
            'stop_loss_exits': 0,
            'mean_reversion_exits': 0,
            'trades': []
        }

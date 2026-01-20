"""
Z-Score Monitor Utility
Track and display z-score changes in real-time
"""

from collections import deque
from datetime import datetime


class ZScoreMonitor:
    """Monitor z-score changes over time"""
    
    def __init__(self, max_history: int = 100):
        """
        Initialize monitor
        
        Args:
            max_history: Maximum number of z-scores to keep
        """
        self.max_history = max_history
        self.history = deque(maxlen=max_history)
        self.timestamps = deque(maxlen=max_history)
    
    def add(self, zscore: float):
        """Add new z-score"""
        self.history.append(zscore)
        self.timestamps.append(datetime.now())
    
    def get_change(self) -> float:
        """Get change from last reading"""
        if len(self.history) < 2:
            return 0.0
        return self.history[-1] - self.history[-2]
    
    def get_trend(self, window: int = 10) -> str:
        """
        Get trend direction
        
        Returns:
            'WIDENING', 'NARROWING', 'STABLE'
        """
        if len(self.history) < window:
            return 'STABLE'
        
        recent = list(self.history)[-window:]
        
        # Linear regression
        x = list(range(window))
        y = recent
        
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        
        # Slope
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        if abs(slope) < 0.01:
            return 'STABLE'
        elif slope > 0:
            return 'WIDENING'
        else:
            return 'NARROWING'
    
    def get_stats(self) -> dict:
        """Get statistics"""
        if not self.history:
            return {
                'current': 0.0,
                'min': 0.0,
                'max': 0.0,
                'mean': 0.0,
                'change': 0.0,
                'trend': 'STABLE'
            }
        
        return {
            'current': self.history[-1],
            'min': min(self.history),
            'max': max(self.history),
            'mean': sum(self.history) / len(self.history),
            'change': self.get_change(),
            'trend': self.get_trend(),
            'count': len(self.history)
        }
    
    def format_status(self) -> str:
        """Get formatted status string"""
        stats = self.get_stats()
        
        change_symbol = "↑" if stats['change'] > 0 else "↓" if stats['change'] < 0 else "→"
        
        return (f"Z-Score: {stats['current']:.3f} {change_symbol} "
                f"(Δ{stats['change']:+.3f}) | "
                f"Range: [{stats['min']:.2f}, {stats['max']:.2f}] | "
                f"Trend: {stats['trend']}")
    
    def should_alert(self, threshold: float = 0.5) -> bool:
        """Check if z-score change exceeds threshold"""
        return abs(self.get_change()) >= threshold

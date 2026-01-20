"""
Real-Time Market Data Manager
TRUE rolling window implementation

Architecture:
- Historical data: Bootstrap initial window
- Real-time data: Rolling window updates with each tick
- Statistics: Recalculated with each new bar
"""


import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import deque
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from core.mt5_manager import get_mt5

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """Real-time market snapshot"""
    timestamp: datetime
    
    # Current prices
    primary_bid: float
    primary_ask: float
    secondary_bid: float
    secondary_ask: float
    
    # Calculated values
    spread: float
    zscore: float
    
    # Historical context (ROLLING)
    spread_mean: float
    spread_std: float
    hedge_ratio: float
    window_size: int  # How many bars in rolling window
    correlation: float  # Real-time correlation coefficient
    
    def __str__(self):
        return (f"Market @ {self.timestamp.strftime('%H:%M:%S')}: "
                f"Primary ${self.primary_bid:.2f}, Secondary ${self.secondary_bid:.4f}, "
                f"Z-Score {self.zscore:.3f}, Corr {self.correlation:.3f} (window={self.window_size})")


@dataclass  
class PriceBar:
    """OHLC bar for rolling window"""
    timestamp: datetime
    primary_price: float
    secondary_price: float
    spread: float


class RealTimeMarketData:
    """
    TRUE Rolling Window Market Data
    
    Strategy:
    1. Bootstrap: Load historical bars into rolling window
    2. Update: Add new bar, remove oldest (automatic with deque)
    3. Recalculate: Mean/Std updated with each new bar
    4. Z-score: Always uses current rolling statistics
    """
    
    def __init__(self, 
                 data_manager,
                 preprocessor,
                 hedge_calculator,
                 rolling_window_size: int = 100,
                 historical_update_interval: int = 3600):
        """
        Initialize with ROLLING WINDOW
        
        Args:
            rolling_window_size: Size of rolling window (bars)
            historical_update_interval: Hedge ratio recalc interval (seconds)
        """
        self.data_manager = data_manager
        self.preprocessor = preprocessor
        self.hedge_calculator = hedge_calculator
        self.rolling_window_size = rolling_window_size
        self.historical_update_interval = historical_update_interval
        
        # ROLLING WINDOW (deque auto-removes oldest)
        self.rolling_window = deque(maxlen=rolling_window_size)
        
        # Historical data cache (for hedge ratio only)
        self.current_hedge_ratio: Optional[float] = None
        self.current_primary_vol: Optional[float] = None
        self.current_secondary_vol: Optional[float] = None
        self.last_historical_update: Optional[datetime] = None
        
        logger.info(f"RealTimeMarketData initialized (rolling_window={rolling_window_size})")
    
    def bootstrap_window(self, 
                        days: int = 30,
                        primary_symbol: str = None,
                        secondary_symbol: str = None, 
                        primary_contract_size: float = None,
                        secondary_contract_size: float = None):
        """
        Bootstrap rolling window with historical data
        Called once at startup
        
        Args:
            days: Historical days to load
            primary_symbol: Primary instrument symbol (uses self.primary_symbol if not provided)
            secondary_symbol: Secondary instrument symbol (uses self.secondary_symbol if not provided)
            primary_contract_size: Contract size for primary (uses self.primary_contract_size if not provided)
            secondary_contract_size: Contract size for secondary (uses self.secondary_contract_size if not provided)
        """
        # Use provided params OR fall back to instance attributes OR use defaults
        primary_symbol = primary_symbol or getattr(self, 'primary_symbol', 'XAUUSD')
        secondary_symbol = secondary_symbol or getattr(self, 'secondary_symbol', 'XAGUSD')
        primary_contract_size = primary_contract_size or getattr(self, 'primary_contract_size', 100)
        secondary_contract_size = secondary_contract_size or getattr(self, 'secondary_contract_size', 5000)
        
        logger.info(f"Bootstrapping rolling window with {days} days of data...")
        logger.info(f"  Pair: {primary_symbol} / {secondary_symbol}")
        logger.info(f"  Contract sizes: {primary_contract_size} / {secondary_contract_size}")
        
        # Store for later use
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol
        self.primary_contract_size = primary_contract_size
        self.secondary_contract_size = secondary_contract_size
        
        # CRITICAL: Update data_manager's symbols BEFORE fetching data!
        # Otherwise it will fetch cached data for old symbols (XAUUSD/XAGUSD)
        self.data_manager.primary_symbol = primary_symbol
        self.data_manager.secondary_symbol = secondary_symbol
        
        # Force re-initialization of MT5Connector with new symbols
        # This ensures we connect to correct symbols, not defaults
        if hasattr(self.data_manager, '_connector_initialized'):
            self.data_manager._connector_initialized = False
            self.data_manager.connector = None
        
        logger.info(f"  → DataManager updated to: {primary_symbol} / {secondary_symbol}")
        
        # Fetch historical bars (will now use correct symbols!)
        # Try multiple approaches to get sufficient data
        primary_df, secondary_df = None, None
        
        # Approach 1: Try days=30
        try:
            logger.info(f"  → Attempting to fetch {days} days of data...")
            primary_df, secondary_df = self.data_manager.get_pair_data(days=days)
        except ValueError as e:
            if "Insufficient data" in str(e):
                logger.warning(f"  ⚠️  Days-based fetch failed: {e}")
                # Approach 2: Try count=500
                try:
                    logger.info(f"  → Trying count-based fetch (500 bars)...")
                    primary_df, secondary_df = self.data_manager.get_pair_data(count=500)
                except Exception as e2:
                    logger.warning(f"  ⚠️  Count-based fetch also failed: {e2}")
                    # Approach 3: Use whatever we got
                    logger.warning(f"  → Using limited available data...")
                    primary_df, secondary_df = self.data_manager.get_pair_data(
                        days=days, validate=False
                    )
            else:
                raise
        
        if primary_df is None or secondary_df is None or len(primary_df) < 7:
            raise ValueError(f"Cannot fetch sufficient data for {primary_symbol}/{secondary_symbol}")
        
        # Preprocess
        primary_clean, secondary_clean = self.preprocessor.preprocess_pair(
            primary_df, secondary_df, add_returns=True
        )
        
        # CORRECT hedge ratio calculation for CFD contracts
        # Use provided contract sizes (flexible for any pair)
        
        # Get latest prices
        primary_price = primary_clean['close'].iloc[-1]
        secondary_price = secondary_clean['close'].iloc[-1]
        
        # Calculate lot values using provided contract sizes
        primary_lot_value = primary_price * primary_contract_size
        secondary_lot_value = secondary_price * secondary_contract_size
        
        # Dollar-neutral ratio (lot-to-lot)
        dollar_neutral_ratio = primary_lot_value / secondary_lot_value
        
        # Calculate volatility
        self.current_primary_vol = primary_clean['returns'].dropna().std() * np.sqrt(252 * 24)
        self.current_secondary_vol = secondary_clean['returns'].dropna().std() * np.sqrt(252 * 24)
        
        # Volatility adjustment
        vol_adjustment = np.sqrt(self.current_secondary_vol / self.current_primary_vol)
        
        # Final hedge ratio (lot-to-lot)
        self.current_hedge_ratio = dollar_neutral_ratio / vol_adjustment
        
        logger.info(f"Rolling window bootstrapped:")
        logger.info(f"  Window size: {self.rolling_window_size} bars")
        logger.info(f"  {primary_symbol} price: ${primary_price:.2f}")
        logger.info(f"  {secondary_symbol} price: ${secondary_price:.4f}")
        logger.info(f"  {primary_symbol} lot value: ${primary_lot_value:,.2f}")
        logger.info(f"  {secondary_symbol} lot value: ${secondary_lot_value:,.2f}")
        logger.info(f"  Dollar-neutral ratio: {dollar_neutral_ratio:.4f}")
        logger.info(f"  Vol adjustment: {vol_adjustment:.4f}")
        logger.info(f"  HEDGE RATIO (lot-to-lot): {self.current_hedge_ratio:.4f}")
        logger.info(f"  {primary_symbol} vol: {self.current_primary_vol:.2%}")
        logger.info(f"  {secondary_symbol} vol: {self.current_secondary_vol:.2%}")
        
        # Fill rolling window with last N bars
        total_bars = len(primary_clean)
        start_idx = max(0, total_bars - self.rolling_window_size)
        
        for i in range(start_idx, total_bars):
            # Get timestamp from DataFrame index
            ts = primary_clean.index[i]
            
            # Convert to datetime based on type
            if isinstance(ts, (int, float)):
                # Check if it's Unix timestamp in seconds or milliseconds
                if ts > 1e10:  # Milliseconds (> year 2286 if in seconds)
                    timestamp = datetime.fromtimestamp(ts / 1000)
                elif ts > 1e6:  # Likely Unix timestamp in seconds (after 1970-01-12)
                    timestamp = datetime.fromtimestamp(ts)
                else:
                    # Invalid or too small - likely index position, not timestamp
                    # Use bar position to estimate time (assuming H1 bars)
                    logger.debug(f"Using bar position {i} as timestamp proxy (value was {ts})")
                    # Start from recent time and go back
                    hours_back = (total_bars - i - 1)
                    timestamp = datetime.now() - timedelta(hours=hours_back)
            elif hasattr(ts, 'to_pydatetime'):
                # Pandas Timestamp
                timestamp = ts.to_pydatetime()
            elif isinstance(ts, datetime):
                # Already datetime
                timestamp = ts
            else:
                # Unknown type - try to convert
                try:
                    timestamp = pd.to_datetime(ts).to_pydatetime()
                except Exception as e:
                    # Last resort: estimate from bar position
                    logger.debug(f"Cannot convert timestamp {ts}, using bar position")
                    hours_back = (total_bars - i - 1)
                    timestamp = datetime.now() - timedelta(hours=hours_back)
            
            bar = PriceBar(
                timestamp=timestamp,
                primary_price=primary_clean['close'].iloc[i],
                secondary_price=secondary_clean['close'].iloc[i],
                spread=primary_clean['close'].iloc[i] - self.current_hedge_ratio * secondary_clean['close'].iloc[i]
            )
            self.rolling_window.append(bar)
        
        self.last_historical_update = datetime.now()
        
        logger.info(f"Rolling window bootstrapped:")
        logger.info(f"  Window size: {len(self.rolling_window)} bars")
        logger.info(f"  Primary price: ${primary_price:.2f}/oz")
        logger.info(f"  Secondary price: ${secondary_price:.4f}/oz")
        logger.info(f"  Primary lot value: ${primary_lot_value:,.2f}")
        logger.info(f"  Secondary lot value: ${secondary_lot_value:,.2f}")
        logger.info(f"  Dollar-neutral ratio: {dollar_neutral_ratio:.4f}")
        logger.info(f"  Vol adjustment: {vol_adjustment:.4f}")
        logger.info(f"  HEDGE RATIO (lot-to-lot): {self.current_hedge_ratio:.4f}")
        logger.info(f"  Primary vol: {self.current_primary_vol:.2%}")
        logger.info(f"  Secondary vol: {self.current_secondary_vol:.2%}")
        
        # Calculate initial statistics
        spreads = [bar.spread for bar in self.rolling_window]
        logger.info(f"  Spread mean: {np.mean(spreads):.2f}")
        logger.info(f"  Spread std: {np.std(spreads):.2f}")
    
    def should_update_hedge_ratio(self) -> bool:
        """Check if hedge ratio needs recalculation"""
        if self.last_historical_update is None:
            return True
        
        elapsed = (datetime.now() - self.last_historical_update).total_seconds()
        return elapsed >= self.historical_update_interval
    
    def update_hedge_ratio(self, days: int = 30):
        """
        Recalculate hedge ratio (infrequent - hourly)
        Does NOT reload entire window, just updates hedge ratio
        """
        logger.info("Updating hedge ratio (keeping rolling window)...")
        
        # Fetch recent data for hedge ratio
        primary_df, secondary_df = self.data_manager.get_pair_data(days=days)
        primary_clean, secondary_clean = self.preprocessor.preprocess_pair(
            primary_df, secondary_df, add_returns=True
        )
        
        # CORRECT hedge ratio calculation using stored contract sizes
        # Get latest prices
        primary_price = primary_clean['close'].iloc[-1]
        secondary_price = secondary_clean['close'].iloc[-1]
        
        # Calculate lot values using stored contract sizes
        primary_lot_value = primary_price * self.primary_contract_size
        secondary_lot_value = secondary_price * self.secondary_contract_size
        
        # Dollar-neutral ratio (lot-to-lot)
        dollar_neutral_ratio = primary_lot_value / secondary_lot_value
        
        # Recalculate volatility
        self.current_primary_vol = primary_clean['returns'].dropna().std() * np.sqrt(252 * 24)
        self.current_secondary_vol = secondary_clean['returns'].dropna().std() * np.sqrt(252 * 24)
        
        # Volatility adjustment
        vol_adjustment = np.sqrt(self.current_secondary_vol / self.current_primary_vol)
        
        # Final hedge ratio (lot-to-lot)
        old_hedge = self.current_hedge_ratio
        self.current_hedge_ratio = dollar_neutral_ratio / vol_adjustment
        
        self.last_historical_update = datetime.now()
        
        logger.info(f"Hedge ratio updated: {old_hedge:.4f} → {self.current_hedge_ratio:.4f}")
        logger.info(f"  Dollar-neutral: {dollar_neutral_ratio:.4f}")
        logger.info(f"  Vol adjustment: {vol_adjustment:.4f}")
        
        # Recalculate spreads in rolling window with new hedge ratio
        for bar in self.rolling_window:
            bar.spread = bar.primary_price - self.current_hedge_ratio * bar.secondary_price
        
        logger.info("Rolling window spreads recalculated with new hedge ratio")
    
    def add_new_tick(self, primary_price: float, secondary_price: float):
        """
        DEPRECATED: Use update_current_h1_bar() instead
        
        This method is kept for backward compatibility but should not be used
        for rolling window updates as it mixes timeframes (1-min ticks vs H1 bars)
        """
        logger.warning("add_new_tick() is deprecated - use update_current_h1_bar()")
    
    def update_current_h1_bar(self, primary_price: float, secondary_price: float):
        """
        Update CLOSE price of current incomplete H1 bar
        Called every minute to keep stats up-to-date
        
        Logic:
        1. Every minute: Update close/high/low of current H1 bar
        2. On new hour: Complete current bar, create new bar, remove oldest
        
        This maintains:
        - Real-time responsiveness (stats update every minute)
        - Consistent timeframe (always H1 bars)
        - Historical context (500 H1 bars = 21 days)
        
        Args:
            primary_price: Current primary price
            secondary_price: Current secondary price
        """
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        # Calculate spread with current hedge ratio
        spread = primary_price - self.current_hedge_ratio * secondary_price
        
        # Check if we have bars in window
        if not self.rolling_window:
            logger.warning("Rolling window empty, call bootstrap_window() first")
            return
        
        # Get last bar in window
        last_bar = self.rolling_window[-1]
        
        # Convert last_bar.timestamp to datetime if needed
        last_timestamp = last_bar.timestamp
        if isinstance(last_timestamp, (int, float)):
            last_timestamp = datetime.fromtimestamp(last_timestamp)
        elif hasattr(last_timestamp, 'to_pydatetime'):
            last_timestamp = last_timestamp.to_pydatetime()
        
        # Check if new hour started
        if last_timestamp < current_hour:
            # NEW HOUR STARTED!
            logger.info(f"=== NEW H1 BAR STARTED AT {current_hour} ===")
            logger.info(f"  Previous bar COMPLETED: {last_timestamp}")
            logger.info(f"  Final close: Primary ${last_bar.primary_price:.2f}, Secondary ${last_bar.secondary_price:.4f}")
            
            # Create NEW incomplete H1 bar
            new_bar = PriceBar(
                timestamp=current_hour,
                primary_price=primary_price,
                secondary_price=secondary_price,
                spread=spread
            )
            
            # Add to rolling window (automatically removes oldest)
            self.rolling_window.append(new_bar)
            
            logger.info(f"  New bar created: {current_hour}")
            logger.info(f"  Rolling window: {len(self.rolling_window)} H1 bars")
            
            # Show date range
            first_ts = self.rolling_window[0].timestamp
            if isinstance(first_ts, (int, float)):
                first_ts = datetime.fromtimestamp(first_ts)
            elif hasattr(first_ts, 'to_pydatetime'):
                first_ts = first_ts.to_pydatetime()
            
            logger.info(f"  Date range: {first_ts} to {self.rolling_window[-1].timestamp}")
        
        else:
            # SAME HOUR - Update current bar's close
            # Update close price (and high/low if needed)
            last_bar.primary_price = primary_price
            last_bar.secondary_price = secondary_price
            last_bar.spread = spread
            
            logger.debug(f"Updated H1 bar {last_timestamp}: Close = Primary ${primary_price:.2f}, Secondary ${secondary_price:.4f}")
    
    def update_rolling_window_hourly(self):
        """
        DEPRECATED: Use update_current_h1_bar() instead
        
        The new approach updates the current H1 bar every minute,
        which is more responsive than updating once per hour.
        """
        logger.warning("update_rolling_window_hourly() is deprecated - use update_current_h1_bar()")
    
    def get_rolling_statistics(self) -> Dict:
        """
        Calculate statistics from CURRENT rolling window (ALL bars)
        
        RESPONSIVE APPROACH:
        - Uses all 1000 bars including current incomplete bar
        - Mean/std update every tick → real-time market adaptation
        - Fast response to market changes
        - May have some noise but catches trends quickly
        
        Returns:
            Dict with mean, std, min, max, correlation
        """
        if len(self.rolling_window) < 10:
            logger.warning("Rolling window too small for statistics")
            return {
                'mean': 0.0,
                'std': 1.0,
                'min': 0.0,
                'max': 0.0,
                'count': len(self.rolling_window),
                'correlation': 0.0
            }
        
        # Use ALL bars for responsive statistics
        spreads = [bar.spread for bar in self.rolling_window]
        primary_prices = [bar.primary_price for bar in self.rolling_window]
        secondary_prices = [bar.secondary_price for bar in self.rolling_window]
        
        # Calculate correlation
        correlation = np.corrcoef(primary_prices, secondary_prices)[0, 1]
        
        return {
            'mean': np.mean(spreads),
            'std': np.std(spreads),
            'min': np.min(spreads),
            'max': np.max(spreads),
            'count': len(spreads),
            'correlation': correlation
        }
    
    def get_realtime_snapshot(self) -> Optional[MarketSnapshot]:
        """
        Get real-time market snapshot with ROLLING statistics

        Updates current H1 bar's close price every minute, maintaining
        real-time responsiveness while keeping consistent H1 timeframe.

        Returns:
            MarketSnapshot with current prices and rolling z-score
        """
        # Get current prices from MT5 using stored symbols
        mt5 = get_mt5()
        primary_tick = mt5.symbol_info_tick(self.primary_symbol)
        secondary_tick = mt5.symbol_info_tick(self.secondary_symbol)
        
        if primary_tick is None or secondary_tick is None:
            logger.error("Failed to get current prices from MT5")
            return None
        
        # SAFETY: Validate prices are not zero (market must be open)
        if primary_tick.bid == 0 or secondary_tick.bid == 0:
            logger.error(f"Zero price detected - market may be closed!")
            logger.error(f"  {self.primary_symbol} bid: ${primary_tick.bid:.2f}")
            logger.error(f"  {self.secondary_symbol} bid: ${secondary_tick.bid:.4f}")
            logger.warning(f"Skipping snapshot - waiting for valid prices")
            return None
        
        if self.current_hedge_ratio is None:
            logger.error("Hedge ratio not initialized - call bootstrap_window() first")
            return None
        
        # Update current H1 bar with new close price
        # This maintains real-time stats while keeping H1 timeframe
        self.update_current_h1_bar(primary_tick.bid, secondary_tick.bid)
        
        # Get CURRENT rolling statistics (from updated H1 bars)
        stats = self.get_rolling_statistics()
        
        # Calculate current spread from LIVE tick
        current_spread = primary_tick.bid - self.current_hedge_ratio * secondary_tick.bid
        
        # Calculate z-score using ROLLING mean/std
        if stats['std'] > 0:
            current_zscore = (current_spread - stats['mean']) / stats['std']
        else:
            current_zscore = 0.0
        
        snapshot = MarketSnapshot(
            timestamp=datetime.now(),
            primary_bid=primary_tick.bid,
            primary_ask=primary_tick.ask,
            secondary_bid=secondary_tick.bid,
            secondary_ask=secondary_tick.ask,
            spread=current_spread,
            zscore=current_zscore,
            spread_mean=stats['mean'],
            spread_std=stats['std'],
            hedge_ratio=self.current_hedge_ratio,
            window_size=stats['count'],
            correlation=stats['correlation']
        )
        
        return snapshot
    
    def get_volatility(self) -> Tuple[float, float]:
        """Get current volatility estimates"""
        return (self.current_primary_vol or 0.0, self.current_secondary_vol or 0.0)
    
    def calculate_hedge_quantities(self,
                                   primary_lots: float) -> Tuple[float, float]:
        """
        Calculate hedge quantities for given primary position
        Uses current prices and volatility
        """
        if self.current_hedge_ratio is None:
            return (primary_lots, 0.0)

        # Get current prices using stored symbols
        mt5 = get_mt5()
        primary_tick = mt5.symbol_info_tick(self.primary_symbol)
        secondary_tick = mt5.symbol_info_tick(self.secondary_symbol)
        
        if not primary_tick or not secondary_tick:
            return (primary_lots, 0.0)
        
        primary_price = primary_tick.bid
        secondary_price = secondary_tick.bid
        
        # Use stored contract sizes
        primary_lot_value = primary_price * self.primary_contract_size
        secondary_lot_value = secondary_price * self.secondary_contract_size
        
        # SAFETY: Check for zero prices (market closed or data error)
        if primary_lot_value == 0 or secondary_lot_value == 0:
            logger.error(f"Cannot calculate hedge: Zero price detected!")
            logger.error(f"  Primary price: ${primary_price:.2f}")
            logger.error(f"  Secondary price: ${secondary_price:.4f}")
            logger.error(f"  Primary lot value: ${primary_lot_value:.2f}")
            logger.error(f"  Secondary lot value: ${secondary_lot_value:.2f}")
            raise ValueError(f"Zero price detected - market may be closed or data unavailable. "
                           f"Primary=${primary_price}, Secondary=${secondary_price}")
        
        # Dollar-neutral ratio
        dollar_neutral_ratio = primary_lot_value / secondary_lot_value
        
        # Volatility adjustment
        if self.current_primary_vol and self.current_secondary_vol and self.current_primary_vol > 0:
            vol_adjustment = np.sqrt(self.current_secondary_vol / self.current_primary_vol)
        else:
            vol_adjustment = 1.0
        
        # Final hedge ratio
        hedge_ratio = dollar_neutral_ratio / vol_adjustment
        
        # Calculate secondary lots
        secondary_lots = primary_lots * hedge_ratio
        
        return (primary_lots, secondary_lots)

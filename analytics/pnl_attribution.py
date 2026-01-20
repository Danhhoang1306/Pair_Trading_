"""
Real-time P&L Attribution System
Decompose P&L into 7 components in real-time

Components:
1. Spread P&L - From spread compression/expansion
2. Mean Drift P&L - From mean movement  
3. Directional P&L - From market trending
4. Hedge Imbalance P&L - From imperfect hedge
5. Transaction Costs - Spread, commission, swap
6. Slippage - Execution difference
7. Rebalance Alpha - From rebalancing timing
"""

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PositionSnapshot:
    """Snapshot of position state"""
    timestamp: datetime
    xau_bid: float
    xau_ask: float
    xag_bid: float
    xag_ask: float
    spread: float
    mean: float
    std: float
    zscore: float
    hedge_ratio: float
    xau_volume: float
    xag_volume: float
    xau_side: str
    xag_side: str
    xau_price: float
    xag_price: float
    xau_contract_size: float = 100.0
    xag_contract_size: float = 5000.0


@dataclass  
class AttributionComponents:
    """7 components of P&L attribution"""
    spread_pnl: float = 0.0
    spread_pnl_pct: float = 0.0
    mean_drift_pnl: float = 0.0
    mean_drift_pnl_pct: float = 0.0
    directional_pnl: float = 0.0
    directional_pnl_pct: float = 0.0
    hedge_imbalance_pnl: float = 0.0
    hedge_imbalance_pnl_pct: float = 0.0
    transaction_costs: float = 0.0
    transaction_costs_pct: float = 0.0
    slippage: float = 0.0
    slippage_pct: float = 0.0
    rebalance_alpha: float = 0.0
    rebalance_alpha_pct: float = 0.0
    total_pnl: float = 0.0
    hedge_quality: float = 0.0
    strategy_purity: float = 0.0
    classification: str = "UNKNOWN"


class RealtimePnLAttribution:
    """Real-time P&L attribution calculator"""
    
    def __init__(self):
        self.positions = {}
        
    def register_position(self, spread_id: str, entry_snapshot: PositionSnapshot):
        """Register new position"""
        self.positions[spread_id] = {
            'entry': entry_snapshot,
            'rebalances': [],
            'price_history': [entry_snapshot],
        }
        logger.info(f"Registered position {spread_id}")
    
    def calculate_attribution(self, spread_id: str, current_snapshot: PositionSnapshot,
                             current_pnl_mt5: float) -> AttributionComponents:
        """Calculate full attribution"""
        if spread_id not in self.positions:
            return AttributionComponents(total_pnl=current_pnl_mt5)
        
        entry = self.positions[spread_id]['entry']
        components = AttributionComponents(total_pnl=current_pnl_mt5)
        
        # 1. Spread P&L
        spread_change = entry.spread - current_snapshot.spread
        if entry.spread > entry.mean:
            components.spread_pnl = spread_change * entry.xau_volume * entry.xau_contract_size
        else:
            components.spread_pnl = -spread_change * entry.xau_volume * entry.xau_contract_size
        
        # 2. Mean Drift P&L
        mean_change = current_snapshot.mean - entry.mean
        if entry.spread > entry.mean:
            components.mean_drift_pnl = mean_change * entry.xau_volume * entry.xau_contract_size
        else:
            components.mean_drift_pnl = -mean_change * entry.xau_volume * entry.xau_contract_size
        
        # 4. Hedge Imbalance
        current_hedge = abs(current_snapshot.xag_volume / current_snapshot.xau_volume) if current_snapshot.xau_volume != 0 else 0
        hedge_deviation = current_hedge - entry.hedge_ratio
        deviation_lots = hedge_deviation * current_snapshot.xau_volume
        xag_price_change = current_snapshot.xag_price - entry.xag_price
        if entry.xag_side == 'SHORT':
            components.hedge_imbalance_pnl = -xag_price_change * deviation_lots * current_snapshot.xag_contract_size
        else:
            components.hedge_imbalance_pnl = xag_price_change * deviation_lots * current_snapshot.xag_contract_size
        
        # 5. Transaction Costs (estimated)
        xau_spread_cost = (entry.xau_ask - entry.xau_bid) * entry.xau_volume * entry.xau_contract_size
        xag_spread_cost = (entry.xag_ask - entry.xag_bid) * entry.xag_volume * entry.xag_contract_size
        exit_spread_cost = ((current_snapshot.xau_ask - current_snapshot.xau_bid) * current_snapshot.xau_volume * current_snapshot.xau_contract_size +
                           (current_snapshot.xag_ask - current_snapshot.xag_bid) * current_snapshot.xag_volume * current_snapshot.xag_contract_size)
        commission = (entry.xau_volume + entry.xag_volume) * 250 * 2
        components.transaction_costs = -(xau_spread_cost + xag_spread_cost + exit_spread_cost + commission)
        
        # 6. Slippage (entry only for now)
        components.slippage = 0.0
        
        # 7. Rebalance Alpha
        components.rebalance_alpha = 0.0
        
        # 3. Directional (residual)
        explained = (components.spread_pnl + components.mean_drift_pnl + 
                    components.hedge_imbalance_pnl + components.transaction_costs + 
                    components.slippage + components.rebalance_alpha)
        components.directional_pnl = current_pnl_mt5 - explained
        
        # Percentages
        if abs(current_pnl_mt5) > 0.01:
            components.spread_pnl_pct = (components.spread_pnl / current_pnl_mt5) * 100
            components.mean_drift_pnl_pct = (components.mean_drift_pnl / current_pnl_mt5) * 100
            components.directional_pnl_pct = (components.directional_pnl / current_pnl_mt5) * 100
            components.hedge_imbalance_pnl_pct = (components.hedge_imbalance_pnl / current_pnl_mt5) * 100
            components.transaction_costs_pct = (components.transaction_costs / current_pnl_mt5) * 100
            components.slippage_pct = (components.slippage / current_pnl_mt5) * 100
            components.rebalance_alpha_pct = (components.rebalance_alpha / current_pnl_mt5) * 100
        
        # Quality metric
        # Use absolute values when PnL is small to avoid division issues
        if abs(current_pnl_mt5) > 1.0:  # If PnL > $1, use percentage
            directional_ratio = abs(components.directional_pnl / current_pnl_mt5)
            components.hedge_quality = max(0.0, min(1.0, 1.0 - directional_ratio))
        else:
            # For small PnL (near breakeven), use absolute directional exposure
            # Consider hedge good if directional PnL < $5
            abs_directional = abs(components.directional_pnl)
            if abs_directional < 5.0:
                components.hedge_quality = 1.0  # Excellent
            elif abs_directional < 20.0:
                components.hedge_quality = 0.8  # Good
            elif abs_directional < 50.0:
                components.hedge_quality = 0.6  # Fair
            else:
                components.hedge_quality = 0.3  # Poor
        
        statistical_pnl = components.spread_pnl + components.mean_drift_pnl
        components.strategy_purity = (statistical_pnl / current_pnl_mt5 * 100) if abs(current_pnl_mt5) > 0.01 else 100
        
        # Classification
        if abs(components.spread_pnl_pct) > 70 and abs(components.directional_pnl_pct) < 20:
            components.classification = "PURE_STAT_ARB"
        elif abs(components.directional_pnl_pct) > 50:
            components.classification = "DIRECTIONAL"
        else:
            components.classification = "MIXED"
        
        return components
    
    def unregister_position(self, spread_id: str):
        """Remove position"""
        if spread_id in self.positions:
            del self.positions[spread_id]


_attribution_engine = RealtimePnLAttribution()

def get_attribution_engine() -> RealtimePnLAttribution:
    return _attribution_engine

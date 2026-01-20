"""
MT5 Risk Monitor
Tracks real MT5 positions and calculates hedge imbalance
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from core.mt5_manager import get_mt5

logger = logging.getLogger(__name__)


@dataclass
class MT5RiskMetrics:
    """MT5 real-time risk metrics"""
    # Account
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float  # %
    profit: float  # Unrealized P&L
    
    # Positions
    total_positions: int
    primary_lots: float
    secondary_lots: float
    
    # Hedge Analysis
    target_hedge_ratio: float
    actual_hedge_ratio: float
    hedge_imbalance: float  # How much imbalance in secondary lots
    hedge_imbalance_pct: float  # % imbalance
    hedge_imbalance_value: float  # Dollar value of imbalance
    
    # Risk
    drawdown: float
    drawdown_pct: float
    max_risk_pct: float  # Max allowed risk %
    stop_loss_level: float  # Equity level that triggers stop
    risk_amount: float  # Amount at risk (balance - stop_loss_level)
    distance_to_sl_pct: float  # % distance to stop loss
    
    timestamp: datetime
    
    def __str__(self):
        return (f"MT5 Risk Metrics:\n"
                f"  Balance: ${self.balance:,.2f}\n"
                f"  Equity: ${self.equity:,.2f}\n"
                f"  Margin Level: {self.margin_level:.1f}%\n"
                f"  Positions: {self.total_positions}\n"
                f"  Hedge Imbalance: {self.hedge_imbalance:.4f} lots ({self.hedge_imbalance_pct:.2%})\n"
                f"  Stop Loss: ${self.stop_loss_level:,.2f} ({self.distance_to_sl_pct:.1f}% away)")


class MT5RiskMonitor:
    """
    Monitor real MT5 positions and calculate hedge imbalance
    
    Example:
        >>> monitor = MT5RiskMonitor()
        >>> metrics = monitor.get_metrics(primary_symbol='XAUUSD', secondary_symbol='XAGUSD')
        >>> print(f"Imbalance: {metrics.hedge_imbalance:.4f} lots")
    """
    
    def __init__(self):
        self.last_metrics: Optional[MT5RiskMetrics] = None
        
    def get_metrics(self,
                   primary_symbol: str = 'XAUUSD',
                   secondary_symbol: str = 'XAGUSD',
                   target_hedge_ratio: float = None,
                   max_risk_pct: float = 0.20) -> Optional[MT5RiskMetrics]:
        """
        Get current MT5 risk metrics with hedge imbalance calculation

        Args:
            primary_symbol: Primary symbol (e.g., XAUUSD)
            secondary_symbol: Secondary symbol (e.g., XAGUSD)
            target_hedge_ratio: Target hedge ratio from market data
            max_risk_pct: Maximum risk percentage (default 20%)

        Returns:
            MT5RiskMetrics or None if MT5 not available
        """
        try:
            mt5 = get_mt5()

            # Get account info
            account_info = mt5.account_info()
            if not account_info:
                logger.warning("Failed to get MT5 account info")
                return None
            
            # DEBUG: Log account info
            logger.debug(f"MT5 Account Info: Balance=${account_info.balance:,.2f}, "
                        f"Equity=${account_info.equity:,.2f}, "
                        f"Profit=${account_info.profit:,.2f}")
            
            # Get all positions
            positions = mt5.positions_get()
            if positions is None:
                positions = []
            
            logger.debug(f"MT5 Positions: {len(positions)} total")
            
            # Separate primary and secondary positions
            primary_positions = [p for p in positions if p.symbol == primary_symbol]
            secondary_positions = [p for p in positions if p.symbol == secondary_symbol]
            
            # Calculate total lots (LONG - SHORT)
            primary_long_lots = sum(p.volume for p in primary_positions if p.type == mt5.ORDER_TYPE_BUY)
            primary_short_lots = sum(p.volume for p in primary_positions if p.type == mt5.ORDER_TYPE_SELL)
            primary_net_lots = primary_long_lots - primary_short_lots
            
            secondary_long_lots = sum(p.volume for p in secondary_positions if p.type == mt5.ORDER_TYPE_BUY)
            secondary_short_lots = sum(p.volume for p in secondary_positions if p.type == mt5.ORDER_TYPE_SELL)
            secondary_net_lots = secondary_long_lots - secondary_short_lots
            
            # Calculate hedge imbalance (EXACT MATCH with HybridRebalancer.check_volume_imbalance)
            if target_hedge_ratio and target_hedge_ratio > 0:
                # Actual hedge ratio
                if abs(secondary_net_lots) > 0 and abs(primary_net_lots) > 0:
                    actual_hedge_ratio = abs(secondary_net_lots) / abs(primary_net_lots)
                else:
                    actual_hedge_ratio = 0.0

                # Imbalance formula (EXACT MATCH with check_volume_imbalance Line 299-300)
                # primary_lots_target = secondary_lots / hedge_ratio
                # imbalance = primary_lots - primary_lots_target
                primary_lots_target = abs(secondary_net_lots) / target_hedge_ratio
                hedge_imbalance = abs(primary_net_lots) - primary_lots_target

                # Interpretation:
                # Positive = primary oversized, Negative = secondary oversized

                # Imbalance percentage (relative to total hedge size)
                total_hedge_size = abs(primary_net_lots) + (target_hedge_ratio * abs(secondary_net_lots))
                if total_hedge_size > 0:
                    hedge_imbalance_pct = abs(hedge_imbalance) / total_hedge_size
                else:
                    hedge_imbalance_pct = 0.0
                
                # Get secondary price to calculate dollar value
                secondary_tick = mt5.symbol_info_tick(secondary_symbol)
                if secondary_tick:
                    # Dollar value of imbalance
                    # For forex: lots * contract_size * price
                    symbol_info = mt5.symbol_info(secondary_symbol)
                    if symbol_info:
                        contract_size = symbol_info.trade_contract_size
                        hedge_imbalance_value = abs(hedge_imbalance) * contract_size * secondary_tick.bid
                    else:
                        hedge_imbalance_value = 0.0
                else:
                    hedge_imbalance_value = 0.0
            else:
                actual_hedge_ratio = 0.0
                hedge_imbalance = 0.0
                hedge_imbalance_pct = 0.0
                hedge_imbalance_value = 0.0
            
            # Calculate drawdown
            # Assuming initial balance = current balance + total closed P&L
            # For simplicity, use current profit as drawdown indicator
            drawdown = max(0, -account_info.profit)
            drawdown_pct = (drawdown / account_info.balance) if account_info.balance > 0 else 0.0
            
            # Calculate risk limits
            stop_loss_level = account_info.balance * (1 - max_risk_pct)
            risk_amount = account_info.balance - stop_loss_level
            
            # Distance to stop loss
            if stop_loss_level > 0:
                distance_to_sl = account_info.equity - stop_loss_level
                distance_to_sl_pct = (distance_to_sl / account_info.balance) * 100
            else:
                distance_to_sl_pct = 0.0
            
            metrics = MT5RiskMetrics(
                balance=account_info.balance,
                equity=account_info.equity,
                margin=account_info.margin,
                margin_free=account_info.margin_free,
                margin_level=account_info.margin_level if account_info.margin > 0 else 0.0,
                profit=account_info.profit,
                total_positions=len(positions),
                primary_lots=primary_net_lots,
                secondary_lots=secondary_net_lots,
                target_hedge_ratio=target_hedge_ratio or 0.0,
                actual_hedge_ratio=actual_hedge_ratio,
                hedge_imbalance=hedge_imbalance,
                hedge_imbalance_pct=hedge_imbalance_pct,
                hedge_imbalance_value=hedge_imbalance_value,
                drawdown=drawdown,
                drawdown_pct=drawdown_pct,
                max_risk_pct=max_risk_pct,
                stop_loss_level=stop_loss_level,
                risk_amount=risk_amount,
                distance_to_sl_pct=distance_to_sl_pct,
                timestamp=datetime.now()
            )
            
            # DEBUG: Log metrics being returned
            logger.debug(f"MT5RiskMetrics created: Balance=${metrics.balance:,.2f}, "
                        f"Equity=${metrics.equity:,.2f}, "
                        f"Imbalance={metrics.hedge_imbalance:+.4f} lots")
            
            self.last_metrics = metrics
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting MT5 metrics: {e}")
            return None
    
    def get_position_details(self,
                            primary_symbol: str = 'XAUUSD',
                            secondary_symbol: str = 'XAGUSD') -> Dict:
        """
        Get detailed position breakdown

        Returns:
            Dict with position details
        """
        try:
            mt5 = get_mt5()

            positions = mt5.positions_get()
            if not positions:
                return {
                    'primary': [],
                    'secondary': [],
                    'other': []
                }
            
            primary_list = []
            secondary_list = []
            other_list = []
            
            for pos in positions:
                pos_info = {
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': 'LONG' if pos.type == mt5.ORDER_TYPE_BUY else 'SHORT',
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'price_current': pos.price_current,
                    'profit': pos.profit,
                    'swap': pos.swap,
                    'time': datetime.fromtimestamp(pos.time)
                }
                
                if pos.symbol == primary_symbol:
                    primary_list.append(pos_info)
                elif pos.symbol == secondary_symbol:
                    secondary_list.append(pos_info)
                else:
                    other_list.append(pos_info)
            
            return {
                'primary': primary_list,
                'secondary': secondary_list,
                'other': other_list,
                'total': len(positions)
            }
            
        except Exception as e:
            logger.error(f"Error getting position details: {e}")
            return {'primary': [], 'secondary': [], 'other': [], 'total': 0}

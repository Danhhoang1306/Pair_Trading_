"""
Position Tracker Module
Track open positions and calculate P&L

Includes:
- Position tracking
- P&L calculation
- Position statistics
- Risk metrics
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, List, Tuple
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Position representation"""
    position_id: str
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    quantity: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    
    def __str__(self):
        return (f"Position {self.position_id[:8]}: {self.side} {self.quantity} {self.symbol} "
                f"@ {self.entry_price:.2f} (PnL: ${self.unrealized_pnl:,.2f})")


class PositionTracker:
    """
    Track trading positions and calculate P&L
    
    Example:
        >>> tracker = PositionTracker()
        >>> pos = tracker.open_position(
        >>>     symbol='XAUUSD',
        >>>     side='LONG',
        >>>     quantity=0.1,
        >>>     entry_price=2650
        >>> )
        >>> tracker.update_position_price(pos.position_id, 2660)
        >>> print(f"PnL: ${pos.unrealized_pnl:.2f}")
    """
    
    def __init__(self):
        """Initialize position tracker"""
        self.positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        
        logger.info("PositionTracker initialized")
    
    def open_position(self,
                     symbol: str,
                     side: str,
                     quantity: float,
                     entry_price: float,
                     position_id: Optional[str] = None,
                     metadata: Dict = None) -> Position:
        """
        Open a new position
        
        Args:
            symbol: Trading symbol
            side: 'LONG' or 'SHORT'
            quantity: Position quantity
            entry_price: Entry price
            position_id: Optional position ID
            metadata: Additional metadata
            
        Returns:
            Position object
        """
        import uuid
        
        if position_id is None:
            position_id = str(uuid.uuid4())
        
        if side not in ['LONG', 'SHORT']:
            raise ValueError(f"Invalid side: {side}")
        
        position = Position(
            position_id=position_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            metadata=metadata or {}
        )
        
        self.positions[position_id] = position
        
        logger.info(f"Opened position: {side} {quantity} {symbol} @ {entry_price:.2f}")
        
        return position
    
    def open_spread_position(self,
                           primary_quantity: float,
                           silver_quantity: float,
                           primary_entry: float,
                           silver_entry: float,
                           side: str,
                           hedge_ratio: float) -> Tuple[Position, Position]:
        """
        Open spread position (primary + Silver)
        
        Args:
            primary_quantity: primary quantity
            silver_quantity: Silver quantity
            primary_entry: primary entry price
            silver_entry: Silver entry price
            side: 'LONG' or 'SHORT'
            hedge_ratio: Hedge ratio
            
        Returns:
            (primary_position, silver_position)
        """
        import uuid
        spread_id = str(uuid.uuid4())
        
        # Create primary position
        primary_side = 'LONG' if side == 'LONG' else 'SHORT'
        primary_pos = self.open_position(
            symbol='XAUUSD',
            side=primary_side,
            quantity=primary_quantity,
            entry_price=primary_entry,
            metadata={'spread_id': spread_id, 'leg': 'primary', 'hedge_ratio': hedge_ratio}
        )
        
        # Create Silver position (opposite side)
        silver_side = 'SHORT' if side == 'LONG' else 'LONG'
        silver_pos = self.open_position(
            symbol='XAGUSD',
            side=silver_side,
            quantity=silver_quantity,
            entry_price=silver_entry,
            metadata={'spread_id': spread_id, 'leg': 'silver', 'hedge_ratio': hedge_ratio}
        )
        
        # Link positions
        primary_pos.metadata['paired_position_id'] = silver_pos.position_id
        silver_pos.metadata['paired_position_id'] = primary_pos.position_id
        
        logger.info(f"Opened spread position: {side} (spread_id={spread_id[:8]})")
        
        return (primary_pos, silver_pos)
    
    def update_position_price(self,
                            position_id: str,
                            current_price: float):
        """
        Update position current price and calculate P&L
        
        Args:
            position_id: Position ID
            current_price: Current market price
        """
        if position_id not in self.positions:
            raise ValueError(f"Position not found: {position_id}")
        
        position = self.positions[position_id]
        position.current_price = current_price
        position.updated_at = datetime.now()
        
        # Calculate unrealized P&L
        if position.side == 'LONG':
            pnl = (current_price - position.entry_price) * position.quantity
        else:  # SHORT
            pnl = (position.entry_price - current_price) * position.quantity
        
        position.unrealized_pnl = pnl
        
        logger.debug(f"Updated position {position_id[:8]}: price={current_price:.2f}, PnL=${pnl:.2f}")
    
    def close_position(self,
                      position_id: str,
                      exit_price: float,
                      close_quantity: Optional[float] = None) -> float:
        """
        Close position and calculate realized P&L
        
        Args:
            position_id: Position ID
            exit_price: Exit price
            close_quantity: Quantity to close (None = full position)
            
        Returns:
            Realized P&L
        """
        if position_id not in self.positions:
            raise ValueError(f"Position not found: {position_id}")
        
        position = self.positions[position_id]
        
        if close_quantity is None:
            close_quantity = position.quantity
        
        if close_quantity > position.quantity:
            raise ValueError("Close quantity exceeds position quantity")
        
        # Calculate realized P&L
        if position.side == 'LONG':
            realized_pnl = (exit_price - position.entry_price) * close_quantity
        else:  # SHORT
            realized_pnl = (position.entry_price - exit_price) * close_quantity
        
        position.realized_pnl = realized_pnl
        
        # Full close or partial
        if close_quantity == position.quantity:
            # Full close
            self.closed_positions.append(position)
            del self.positions[position_id]
            
            logger.info(f"Closed position {position_id[:8]}: "
                       f"PnL=${realized_pnl:,.2f}")
        else:
            # Partial close
            position.quantity -= close_quantity
            logger.info(f"Partially closed position {position_id[:8]}: "
                       f"{close_quantity} units, PnL=${realized_pnl:,.2f}")
        
        return realized_pnl
    
    def close_spread_position(self,
                            spread_id: str,
                            primary_exit: float,
                            silver_exit: float) -> Dict:
        """
        Close spread position
        
        Args:
            spread_id: Spread ID
            primary_exit: primary exit price
            silver_exit: Silver exit price
            
        Returns:
            Dict with P&L details
        """
        # Find positions with this spread_id
        spread_positions = [
            p for p in self.positions.values()
            if p.metadata.get('spread_id') == spread_id
        ]
        
        if len(spread_positions) != 2:
            raise ValueError(f"Spread not found or incomplete: {spread_id}")
        
        # Try to find primary/silver or primary/secondary legs
        # Check metadata['leg'] for: 'primary', 'primary', 'XAU', 'primary', 'BTC'
        primary_pos = None
        silver_pos = None
        
        for p in spread_positions:
            leg = p.metadata.get('leg', '').upper()
            symbol = p.symbol.upper()
            
            # Check if this is primary/primary leg
            if any(x in leg or x in symbol for x in ['primary', 'XAU', 'BTC', 'PRIMARY']):
                primary_pos = p
            else:
                silver_pos = p
        
        # Fallback: if still not found, use first as primary
        if not primary_pos or not silver_pos:
            primary_pos = spread_positions[0]
            silver_pos = spread_positions[1]
        
        # Close both positions
        primary_pnl = self.close_position(primary_pos.position_id, primary_exit)
        silver_pnl = self.close_position(silver_pos.position_id, silver_exit)
        
        total_pnl = primary_pnl + silver_pnl
        
        logger.info(f"Closed spread {spread_id[:8]}: "
                   f"primary PnL=${primary_pnl:.2f}, Silver PnL=${silver_pnl:.2f}, "
                   f"Total=${total_pnl:.2f}")
        
        return {
            'spread_id': spread_id,
            'primary_pnl': primary_pnl,
            'silver_pnl': silver_pnl,
            'total_pnl': total_pnl,
            'primary_entry': primary_pos.entry_price,
            'primary_exit': primary_exit,
            'silver_entry': silver_pos.entry_price,
            'silver_exit': silver_exit
        }
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID"""
        return self.positions.get(position_id)
    
    def get_all_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get all open positions"""
        positions = list(self.positions.values())
        
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        
        return positions
    
    def get_total_pnl(self) -> Dict:
        """Get total P&L across all positions"""
        unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        realized_pnl = sum(p.realized_pnl for p in self.closed_positions)
        total_pnl = unrealized_pnl + realized_pnl
        
        return {
            'unrealized_pnl': unrealized_pnl,
            'realized_pnl': realized_pnl,
            'total_pnl': total_pnl,
            'open_positions': len(self.positions),
            'closed_positions': len(self.closed_positions)
        }
    
    def get_statistics(self) -> Dict:
        """Get position statistics"""
        if not self.closed_positions:
            return {}
        
        pnls = [p.realized_pnl for p in self.closed_positions]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]
        
        return {
            'total_trades': len(self.closed_positions),
            'winning_trades': len(winners),
            'losing_trades': len(losers),
            'win_rate': len(winners) / len(pnls) if pnls else 0,
            'avg_win': np.mean(winners) if winners else 0,
            'avg_loss': np.mean(losers) if losers else 0,
            'total_pnl': sum(pnls),
            'max_win': max(pnls) if pnls else 0,
            'max_loss': min(pnls) if pnls else 0
        }
    
    def clear_all(self):
        """Clear all tracked positions"""
        self.positions.clear()
        logger.info("PositionTracker: Cleared all open positions")

    def __repr__(self):
        return f"PositionTracker(open={len(self.positions)}, closed={len(self.closed_positions)})"

"""
MT5 Position Recovery System
Recovers positions from MT5 comments instead of relying only on disk files

This solves the critical problem:
- User manually closes position in MT5
- System still thinks it exists (from file)
- Creates imbalanced exposure!

Solution:
- Write metadata to MT5 comment field
- On startup, read ALL positions from MT5
- Compare with disk files
- Show confirmation dialog
- User decides: Keep MT5 positions or start fresh
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from core.mt5_manager import get_mt5

logger = logging.getLogger(__name__)


class MT5PositionRecovery:
    """
    Recover trading positions from MT5 comments
    
    Comment Format:
    SPR:{spread_id}|LEG:{leg}|PAIR:{pair}|ENTRY:{zscore}|TIME:{timestamp}
    
    Example:
    SPR:abc123def456|LEG:XAU|PAIR:XAUUSD/XAGUSD|ENTRY:2.15|TIME:20251228-103045
    """
    
    # Magic number to identify our trades
    MAGIC_NUMBER = 234000
    
    def __init__(self):
        self.recovered_positions: List[Dict] = []
        
    @staticmethod
    def create_comment(spread_id: str,
                      leg: str,
                      pair: str,
                      entry_zscore: float,
                      timestamp: datetime = None) -> str:
        """
        Create comment string for MT5 order
        
        Args:
            spread_id: Unique spread identifier
            leg: 'XAU' or 'XAG'
            pair: 'XAUUSD/XAGUSD'
            entry_zscore: Z-score at entry
            timestamp: Entry time (default: now)
            
        Returns:
            Comment string (max 31 characters for MT5)
            
        Example:
            >>> create_comment('abc123', 'XAU', 'XAUUSD/XAGUSD', 2.15)
            'SPR:abc123|LEG:XAU|Z:2.15'
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Short format to fit MT5 31-char limit
        time_str = timestamp.strftime("%y%m%d-%H%M%S")
        
        # Compact format
        comment = f"SPR:{spread_id[:8]}|{leg}|Z:{entry_zscore:.2f}|{time_str}"
        
        # Ensure within MT5 limit (31 chars)
        if len(comment) > 31:
            # Ultra-compact: just spread_id and leg
            comment = f"S:{spread_id[:12]}|{leg}"
        
        return comment
    
    @staticmethod
    def parse_comment(comment: str) -> Optional[Dict]:
        """
        Parse MT5 comment to extract metadata
        
        Args:
            comment: MT5 order comment
            
        Returns:
            Dict with metadata or None if not our trade
            
        Example formats:
            New: 'S:20251228_162345_XAU' → {spread_id: '20251228_162345', leg: 'XAU'}
            Old: 'SPR:abc123|XAU|Z:2.15' → {spread_id: 'abc123', leg: 'XAU', entry_zscore: 2.15}
        """
        if not comment:
            return None
        
        try:
            # NEW FORMAT: S:20251228_162345_XAU
            if comment.startswith('S:') and '_' in comment:
                parts = comment[2:].split('_')  # Remove 'S:' prefix
                if len(parts) >= 3:  # date_time_leg
                    spread_id = f"{parts[0]}_{parts[1]}"  # Reconstruct spread_id
                    leg = parts[2] if len(parts) > 2 else None
                    metadata = {'spread_id': spread_id}
                    if leg and leg in ['XAU', 'XAG', 'BTC', 'ETH', 'primary', 'secondary']:
                        metadata['leg'] = leg
                    return metadata
            
            # OLD FORMAT: SPR:abc123|XAU|Z:2.15
            if '|' not in comment:
                return None
            
            parts = comment.split('|')
            metadata = {}
            
            for part in parts:
                if ':' in part:
                    key, value = part.split(':', 1)
                    
                    if key == 'SPR' or key == 'S':
                        metadata['spread_id'] = value
                    elif key == 'Z':
                        metadata['entry_zscore'] = float(value)
                else:
                    # Assume it's leg if no colon
                    if part in ['XAU', 'XAG', 'primary', 'secondary', 'BTC', 'ETH']:
                        metadata['leg'] = part
            
            return metadata if 'spread_id' in metadata else None
            
        except Exception as e:
            logger.debug(f"Failed to parse comment '{comment}': {e}")
            return None
    
    def scan_mt5_positions(self,
                          primary_symbol: str = 'XAUUSD',
                          secondary_symbol: str = 'XAGUSD') -> List[Dict]:
        """
        Scan all MT5 positions and extract our trades

        Returns:
            List of position dicts with metadata

        Example:
            [{
                'ticket': 12345,
                'symbol': 'XAUUSD',
                'volume': 0.01,
                'side': 'LONG',
                'price': 2650.50,
                'profit': 125.50,
                'spread_id': 'abc123',
                'leg': 'XAU',
                'entry_zscore': 2.15,
                'comment': 'SPR:abc123|XAU|Z:2.15'
            }, ...]
        """
        positions = []

        try:
            # Get MT5 instance
            mt5 = get_mt5()

            # Get all MT5 positions
            mt5_positions = mt5.positions_get()
            if not mt5_positions:
                logger.info("No positions found in MT5")
                return []
            
            logger.info(f"Found {len(mt5_positions)} total positions in MT5")
            
            # Filter our positions (by magic number or symbols)
            for pos in mt5_positions:
                # Check if it's our symbol
                if pos.symbol not in [primary_symbol, secondary_symbol]:
                    continue
                
                # Check magic number if set
                if hasattr(pos, 'magic') and pos.magic != self.MAGIC_NUMBER:
                    continue
                
                # Parse comment
                metadata = self.parse_comment(pos.comment)
                
                # Determine side
                side = 'LONG' if pos.type == mt5.ORDER_TYPE_BUY else 'SHORT'
                
                # Determine leg from symbol
                if pos.symbol == primary_symbol:
                    leg = 'XAU'
                else:
                    leg = 'XAG'
                
                # Build position dict
                position_data = {
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'volume': pos.volume,
                    'side': side,
                    'price': pos.price_open,
                    'current_price': pos.price_current,
                    'profit': pos.profit,
                    'comment': pos.comment,
                    'leg': leg,
                    'time': datetime.fromtimestamp(pos.time)
                }
                
                # Add metadata if available
                if metadata:
                    position_data.update(metadata)
                    logger.info(f"Found our position: {pos.symbol} {side} {pos.volume} "
                              f"(Spread: {metadata.get('spread_id', 'unknown')})")
                else:
                    # Position without metadata (manual trade or old format)
                    logger.warning(f"Found position without metadata: {pos.symbol} "
                                 f"{side} {pos.volume} - Comment: '{pos.comment}'")
                
                positions.append(position_data)
            
            logger.info(f"Found {len(positions)} of our positions in MT5")
            self.recovered_positions = positions
            return positions
            
        except Exception as e:
            logger.error(f"Error scanning MT5 positions: {e}")
            return []
    
    def group_by_spread(self, positions: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group positions by spread_id
        
        Returns:
            {spread_id: [position1, position2], ...}
        """
        spreads = {}
        
        for pos in positions:
            spread_id = pos.get('spread_id', 'unknown')
            if spread_id not in spreads:
                spreads[spread_id] = []
            spreads[spread_id].append(pos)
        
        return spreads
    
    def validate_spread(self, spread_positions: List[Dict]) -> Dict:
        """
        Validate if a spread is properly hedged
        
        Returns:
            {
                'valid': True/False,
                'reason': 'description',
                'legs': {'XAU': {...}, 'XAG': {...}},
                'imbalance': float
            }
        """
        legs = {'XAU': None, 'XAG': None}
        
        # Organize by leg
        for pos in spread_positions:
            leg = pos.get('leg', 'unknown')
            if leg in legs:
                legs[leg] = pos
        
        # Check if both legs exist
        if not legs['XAU']:
            return {
                'valid': False,
                'reason': 'Missing XAU leg',
                'legs': legs,
                'imbalance': 0
            }
        
        if not legs['XAG']:
            return {
                'valid': False,
                'reason': 'Missing XAG leg',
                'legs': legs,
                'imbalance': 0
            }
        
        # Check if sides are opposite
        xau_side = legs['XAU']['side']
        xag_side = legs['XAG']['side']
        
        if xau_side == xag_side:
            return {
                'valid': False,
                'reason': f'Both legs are {xau_side} (should be opposite)',
                'legs': legs,
                'imbalance': 0
            }
        
        # Calculate hedge ratio
        xau_lots = legs['XAU']['volume']
        xag_lots = legs['XAG']['volume']
        
        # Ideal ratio (example: 0.7179)
        ideal_ratio = 0.7179  # Should be from config
        ideal_xag = xau_lots * ideal_ratio
        imbalance = xag_lots - ideal_xag
        
        return {
            'valid': True,
            'reason': 'Valid spread',
            'legs': legs,
            'xau_lots': xau_lots,
            'xag_lots': xag_lots,
            'ideal_xag': ideal_xag,
            'imbalance': imbalance,
            'imbalance_pct': (imbalance / ideal_xag) if ideal_xag > 0 else 0
        }
    
    def generate_recovery_report(self) -> str:
        """
        Generate human-readable recovery report
        
        Returns:
            Formatted string report
        """
        if not self.recovered_positions:
            return "No positions found in MT5"
        
        report = []
        report.append("="*70)
        report.append("MT5 POSITION RECOVERY REPORT")
        report.append("="*70)
        report.append(f"Total positions found: {len(self.recovered_positions)}")
        report.append("")
        
        # Group by spread
        spreads = self.group_by_spread(self.recovered_positions)
        
        report.append(f"Spread groups found: {len(spreads)}")
        report.append("")
        
        for spread_id, positions in spreads.items():
            report.append(f"Spread ID: {spread_id}")
            report.append("-" * 50)
            
            # Validate
            validation = self.validate_spread(positions)
            
            if validation['valid']:
                report.append(f"✅ Status: VALID HEDGE")
                report.append(f"   XAU: {validation['xau_lots']:.4f} lots")
                report.append(f"   XAG: {validation['xag_lots']:.4f} lots (ideal: {validation['ideal_xag']:.4f})")
                report.append(f"   Imbalance: {validation['imbalance']:+.4f} lots ({validation['imbalance_pct']:+.2%})")
            else:
                report.append(f"❌ Status: {validation['reason']}")
            
            # List positions
            for pos in positions:
                profit_str = f"${pos['profit']:+,.2f}" if pos['profit'] != 0 else "$0.00"
                report.append(f"   {pos['leg']}: {pos['symbol']} {pos['side']} "
                            f"{pos['volume']:.4f} @ ${pos['price']:.2f} | P&L: {profit_str}")
            
            report.append("")
        
        report.append("="*70)
        
        return "\n".join(report)


def create_position_comment(spread_id: str, leg: str, entry_zscore: float) -> str:
    """
    Helper function to create MT5 comment
    Use this when placing orders
    """
    return MT5PositionRecovery.create_comment(
        spread_id=spread_id,
        leg=leg,
        pair='XAUUSD/XAGUSD',
        entry_zscore=entry_zscore
    )


# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*70)
    print("MT5 POSITION RECOVERY TEST")
    print("="*70)

    # Initialize MT5
    from core.mt5_manager import get_mt5_manager
    mt5_mgr = get_mt5_manager()
    if not mt5_mgr.initialize():
        print("❌ MT5 initialization failed")
        exit()

    # Create recovery instance
    recovery = MT5PositionRecovery()

    # Scan MT5 positions
    print("\nScanning MT5 positions...")
    positions = recovery.scan_mt5_positions()

    if positions:
        # Generate report
        report = recovery.generate_recovery_report()
        print("\n" + report)

        # Show what would happen
        spreads = recovery.group_by_spread(positions)

        print("\n" + "="*70)
        print("RECOVERY OPTIONS:")
        print("="*70)
        print(f"Found {len(spreads)} spread(s) in MT5")
        print()
        print("Options:")
        print("  1. RESUME - Continue with MT5 positions")
        print("  2. CLOSE ALL - Close all positions and start fresh")
        print("  3. CANCEL - Exit without trading")
        print("="*70)
    else:
        print("\n✅ No positions found - starting fresh")

    mt5_mgr.shutdown()

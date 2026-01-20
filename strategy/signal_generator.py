"""
Signal Generator Module
Generate trading signals based on pair trading strategy

Strategy:
- LONG SPREAD when z-score < -2.0 (primary undervalued)
- SHORT SPREAD when z-score > +2.0 (primary overvalued)
- CLOSE when z-score reverts to mean
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict, Any
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Signal type"""
    LONG_SPREAD = "LONG_SPREAD"      # Buy primary, Sell secondary
    SHORT_SPREAD = "SHORT_SPREAD"    # Sell primary, Buy secondary
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    HOLD = "HOLD"


class SignalStrength(Enum):
    """Signal strength"""
    WEAK = "WEAK"
    MEDIUM = "MEDIUM"
    STRONG = "STRONG"
    EXTREME = "EXTREME"


@dataclass
class TradingSignal:
    """Trading signal"""
    signal_type: SignalType
    strength: SignalStrength
    zscore: float
    spread: float
    hedge_ratio: float
    confidence: float
    timestamp: datetime
    metadata: dict = None
    
    def __str__(self):
        return (f"Signal: {self.signal_type.value} ({self.strength.value})\n"
                f"  Z-score: {self.zscore:.2f}\n"
                f"  Confidence: {self.confidence:.1%}")


class SignalGenerator:
    """
    Generate trading signals for pair trading
    
    Example:
        >>> generator = SignalGenerator()
        >>> signal = generator.generate_signal(
        >>>     primary_price=2650, secondary_price=30,
        >>>     zscore=-2.5, hedge_ratio=88.33
        >>> )
    """
    
    def __init__(self,
                 entry_threshold: float = 2.0,
                 exit_threshold: float = 0.5,
                 stop_loss_zscore: float = 3.0,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize signal generator
        
        Args:
            entry_threshold: Z-score for entry (2.0 = 2 std dev)
            exit_threshold: Z-score for exit (0.5)
            stop_loss_zscore: Stop loss z-score (3.0)
            config: Optional config dict
        """
        # Extract from config if provided
        if config:
            entry_threshold = config.get('entry_threshold', entry_threshold)
            exit_threshold = config.get('exit_threshold', exit_threshold)
            stop_loss_zscore = config.get('stop_loss_zscore', stop_loss_zscore)
        
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.stop_loss_zscore = stop_loss_zscore
        
        logger.info(f"SignalGenerator initialized (entry={entry_threshold}, "
                   f"exit={exit_threshold}, stop={stop_loss_zscore})")
    
    def generate_signal(self,
                       primary_price: float,
                       secondary_price: float,
                       zscore: float,
                       hedge_ratio: float,
                       current_position: Optional[str] = None) -> TradingSignal:
        """
        Generate trading signal
        
        Args:
            primary_price: Current primary instrument price
            secondary_price: Current secondary instrument price
            secondary_price: Current secondary price
            zscore: Current z-score
            hedge_ratio: Hedge ratio
            current_position: Current position ('LONG', 'SHORT', or None)
            
        Returns:
            TradingSignal
        """
        spread = primary_price - hedge_ratio * secondary_price
        
        # Determine signal
        if current_position is None:
            # No positions - allow entry signals
            signal_type, strength = self._get_entry_signal(zscore, current_position=None)

        else:
            # Have positions - check exit OR reverse
            signal_type, strength = self._get_exit_signal(zscore, current_position)
            
            # If no exit signal, check if we should REVERSE direction
            # (this allows entry signal with current_position passed for blocking)
            if signal_type == SignalType.HOLD:
                signal_type, strength = self._get_entry_signal(zscore, current_position=current_position)
        
        confidence = self._calculate_confidence(zscore)
        
        signal = TradingSignal(
            signal_type=signal_type,
            strength=strength,
            zscore=zscore,
            spread=spread,
            hedge_ratio=hedge_ratio,
            confidence=confidence,
            timestamp=datetime.now(),
            metadata={
                'primary_price': primary_price,
                'secondary_price': secondary_price
            }
        )
        
        logger.debug(f"Signal: {signal_type.value} (z={zscore:.2f})")
        
        return signal
    
    def _get_entry_signal(self, zscore: float, current_position: Optional[str] = None) -> Tuple[SignalType, SignalStrength]:
        """
        Get entry signal based on z-score
        
        CRITICAL: Blocks duplicate entry signals!
        - If current_position = 'LONG', blocks new LONG signals
        - If current_position = 'SHORT', blocks new SHORT signals
        
        Args:
            zscore: Current z-score
            current_position: Current position direction ('LONG', 'SHORT', or None)
        """
        abs_z = abs(zscore)
        
        if zscore < -self.entry_threshold:
            # LONG spread entry signal
            
            # BLOCK if we already have LONG positions!
            if current_position == 'LONG':
                logger.info(f"🚫 BLOCKED LONG entry - already have LONG positions (z={zscore:.3f})")
                return (SignalType.HOLD, SignalStrength.WEAK)
            
            # Allow LONG entry
            if abs_z >= self.stop_loss_zscore:
                return (SignalType.LONG_SPREAD, SignalStrength.EXTREME)
            elif abs_z >= self.entry_threshold * 1.2:
                return (SignalType.LONG_SPREAD, SignalStrength.STRONG)
            else:
                return (SignalType.LONG_SPREAD, SignalStrength.MEDIUM)
        
        elif zscore > self.entry_threshold:
            # SHORT spread entry signal
            
            # BLOCK if we already have SHORT positions!
            if current_position == 'SHORT':
                logger.info(f"🚫 BLOCKED SHORT entry - already have SHORT positions (z={zscore:.3f})")
                return (SignalType.HOLD, SignalStrength.WEAK)
            
            # Allow SHORT entry
            if abs_z >= self.stop_loss_zscore:
                return (SignalType.SHORT_SPREAD, SignalStrength.EXTREME)
            elif abs_z >= self.entry_threshold * 1.2:
                return (SignalType.SHORT_SPREAD, SignalStrength.STRONG)
            else:
                return (SignalType.SHORT_SPREAD, SignalStrength.MEDIUM)
        
        return (SignalType.HOLD, SignalStrength.WEAK)
    
    def _get_exit_signal(self, zscore: float, position: str) -> Tuple[SignalType, SignalStrength]:
        """Get exit signal"""
        if position == 'LONG':
            if zscore >= -self.exit_threshold:
                strength = SignalStrength.STRONG if zscore > 0 else SignalStrength.MEDIUM
                return (SignalType.CLOSE_LONG, strength)
            elif zscore < -self.stop_loss_zscore:
                return (SignalType.CLOSE_LONG, SignalStrength.EXTREME)
        
        elif position == 'SHORT':
            if zscore <= self.exit_threshold:
                strength = SignalStrength.STRONG if zscore < 0 else SignalStrength.MEDIUM
                return (SignalType.CLOSE_SHORT, strength)
            elif zscore > self.stop_loss_zscore:
                return (SignalType.CLOSE_SHORT, SignalStrength.EXTREME)
        
        return (SignalType.HOLD, SignalStrength.WEAK)
    
    def _calculate_confidence(self, zscore: float) -> float:
        """Calculate confidence (0.0 to 1.0)"""
        abs_z = abs(zscore)
        
        if abs_z < self.entry_threshold:
            return 0.0
        elif abs_z >= self.stop_loss_zscore:
            return 1.0
        else:
            return (abs_z - self.entry_threshold) / (self.stop_loss_zscore - self.entry_threshold)
    
    def __repr__(self):
        return f"SignalGenerator(entry={self.entry_threshold})"


def quick_signal(primary_price: float, secondary_price: float, 
                zscore: float, hedge_ratio: float) -> SignalType:
    """Quick signal generation"""
    gen = SignalGenerator()
    signal = gen.generate_signal(primary_price, secondary_price, zscore, hedge_ratio)
    return signal.signal_type

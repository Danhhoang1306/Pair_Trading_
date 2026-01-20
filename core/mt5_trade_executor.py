"""
MT5 Trade Executor
Execute real trades on MetaTrader 5

Features:
- Place market orders
- Place limit orders
- Modify orders
- Close positions
- Get order/position status

IMPORTANT: Does NOT initialize MT5. Uses MT5Manager singleton.
MT5 must be initialized in main_cli.py before creating this executor.
"""

from core.mt5_manager import get_mt5
import logging
from typing import Optional, Tuple, Dict
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """MT5 Order types - Values set dynamically"""
    BUY = 0
    SELL = 1
    BUY_LIMIT = 2
    SELL_LIMIT = 3
    BUY_STOP = 4
    SELL_STOP = 5


@dataclass
class TradeResult:
    """Result from trade execution"""
    success: bool
    order_ticket: Optional[int]
    volume: float
    price: float
    comment: str
    error_code: Optional[int] = None
    error_description: Optional[str] = None
    
    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"Trade {status}: Ticket={self.order_ticket}, Vol={self.volume}, Price={self.price}"


class MT5TradeExecutor:
    """
    Execute trades on MT5
    
    Example:
        >>> executor = MT5TradeExecutor()
        >>> result = executor.place_market_order(
        >>>     symbol='XAUUSD',
        >>>     order_type='BUY',
        >>>     volume=0.01,
        >>>     sl=2600,
        >>>     tp=2700
        >>> )
    """
    
    def __init__(self, 
                 magic_number: int = 234000, 
                 volume_multiplier: float = 1.0,
                 primary_symbol: str = 'XAUUSD',
                 secondary_symbol: str = 'XAGUSD'):
        """
        Initialize trade executor
        
        Args:
            magic_number: Magic number for identifying bot trades
            volume_multiplier: Multiplier for all order volumes (default 1.0)
                              Examples:
                              - 1.0  = Normal size (0.02 lots)
                              - 10.0 = 10x size (0.20 lots) - Better hedge ratio accuracy!
                              - 0.1  = 0.1x size (0.002 lots) - For testing
            primary_symbol: Primary symbol (default: XAUUSD)
            secondary_symbol: Secondary symbol (default: XAGUSD)
        """
        self.magic_number = magic_number
        self.volume_multiplier = volume_multiplier
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol

        # Get MT5 instance (assumes already initialized in main_cli.py)
        self.mt5 = get_mt5()

        logger.info(f"MT5TradeExecutor initialized (magic={magic_number}, "
                   f"volume_multiplier={volume_multiplier}x, "
                   f"symbols={primary_symbol}/{secondary_symbol})")
    
    def place_market_order(self,
                          symbol: str,
                          order_type: str,
                          volume: float,
                          sl: Optional[float] = None,
                          tp: Optional[float] = None,
                          deviation: int = 20,
                          comment: str = "PairBot") -> TradeResult:
        """
        Place market order
        
        Args:
            symbol: Trading symbol (XAUUSD, XAGUSD)
            order_type: 'BUY' or 'SELL'
            volume: Order volume (lots)
            sl: Stop loss price
            tp: Take profit price
            deviation: Max price deviation (points)
            comment: Order comment
            
        Returns:
            TradeResult
        """
        # Get symbol info
        symbol_info = self.mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol {symbol} not found")
            return TradeResult(
                success=False,
                order_ticket=None,
                volume=0,
                price=0,
                comment=f"Symbol {symbol} not found"
            )
        
        if not symbol_info.visible:
            if not self.mt5.symbol_select(symbol, True):
                logger.error(f"Failed to select {symbol}")
                return TradeResult(
                    success=False,
                    order_ticket=None,
                    volume=0,
                    price=0,
                    comment=f"Failed to select {symbol}"
                )
        
        # VALIDATE AND ROUND VOLUME
        volume_min = symbol_info.volume_min
        volume_max = symbol_info.volume_max
        volume_step = symbol_info.volume_step
        
        # Round to volume step
        volume = round(volume / volume_step) * volume_step
        
        # Check limits
        if volume < volume_min:
            logger.warning(f"Volume {volume} < min {volume_min}, using min")
            volume = volume_min
        elif volume > volume_max:
            logger.warning(f"Volume {volume} > max {volume_max}, using max")
            volume = volume_max
        
        logger.info(f"Adjusted volume: {volume} (min={volume_min}, max={volume_max}, step={volume_step})")
        
        # Get current price
        if order_type.upper() == 'BUY':
            price = self.mt5.symbol_info_tick(symbol).ask
            order_type_mt5 = self.mt5.ORDER_TYPE_BUY
        else:
            price = self.mt5.symbol_info_tick(symbol).bid
            order_type_mt5 = self.mt5.ORDER_TYPE_SELL
        
        # Prepare request
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type_mt5,
            "price": price,
            "deviation": deviation,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        
        # Add SL/TP if provided
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp
        
        # Send order
        logger.info(f"Sending {order_type} order: {symbol} {volume} lots @ {price:.5f}")
        
        result = self.mt5.order_send(request)
        
        if result is None:
            logger.error("order_send failed, result is None")
            return TradeResult(
                success=False,
                order_ticket=None,
                volume=volume,
                price=price,
                comment="order_send returned None"
            )
        
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.retcode} - {result.comment}")
            return TradeResult(
                success=False,
                order_ticket=result.order,
                volume=volume,
                price=price,
                comment=result.comment,
                error_code=result.retcode,
                error_description=result.comment
            )
        
        logger.info(f"[SUCCESS] Order executed: Ticket={result.order}, "
                   f"Volume={result.volume}, Price={result.price}")
        
        return TradeResult(
            success=True,
            order_ticket=result.order,
            volume=result.volume,
            price=result.price,
            comment="Order executed successfully"
        )
    
    def place_spread_orders(self,
                           primary_volume: float,
                           secondary_volume: float,
                           side: str,
                           entry_zscore: float = 0.0,
                           sl_primary: Optional[float] = None,
                           tp_primary: Optional[float] = None,
                           sl_secondary: Optional[float] = None,
                           tp_secondary: Optional[float] = None) -> Tuple[Tuple[TradeResult, TradeResult], str]:
        """
        Place spread orders (primary + secondary) with attribution tracking
        CRITICAL: Maintains hedge ratio after volume adjustment
        
        Args:
            primary_volume: primary volume (lots)
            secondary_volume: secondary volume (lots) - calculated from primary × hedge_ratio
            side: 'LONG' or 'SHORT'
            entry_zscore: Entry z-score for attribution tracking
            sl_primary: primary stop loss
            tp_primary: primary take profit
            sl_secondary: secondary stop loss
            tp_secondary: secondary take profit
            
        Returns:
            ((primary_result, secondary_result), spread_id)
        """
        from datetime import datetime
        
        # Generate timestamp for logging/tracking
        time_now = datetime.now()
        timestamp = time_now.strftime("%Y%m%d_%H%M%S")
        short_id = time_now.strftime("%H%M%S")  # HHMMSS = 6 chars
        
        # MT5 COMMENT: Keep short for 15-char limit
        # We'll use tickets as spread_id, but comment can be anything short
        primary_comment = f"ID:{short_id}"
        secondary_comment = f"ID:{short_id}"
        
        # Note: spread_id will be created AFTER orders are placed (using tickets)
        # For now, use timestamp for logging
        temp_id = timestamp
        
        # Store full setup_id for file tracking
        setup_id = getattr(self, 'current_setup_id', f"s{timestamp}")
        
        logger.info(f"Creating spread (temp: {temp_id}, setup: {setup_id}) with zscore={entry_zscore:.2f}")
        logger.info(f"  MT5 comments: '{primary_comment}' ({len(primary_comment)} chars)")
        logger.debug(f"Comments: Primary='{primary_comment}', Secondary='{secondary_comment}'")
        if side.upper() == 'LONG':
            # LONG SPREAD: Buy primary, Sell secondary
            primary_type = 'BUY'
            secondary_type = 'SELL'
        elif side.upper() == 'SHORT':
            # SHORT SPREAD: Sell primary, Buy secondary
            primary_type = 'SELL'
            secondary_type = 'BUY'
        else:
            raise ValueError(f"Invalid side: {side}")
        
        # APPLY VOLUME MULTIPLIER (before any calculations)
        primary_volume_original = primary_volume
        secondary_volume_original = secondary_volume
        
        primary_volume *= self.volume_multiplier
        secondary_volume *= self.volume_multiplier
        
        if self.volume_multiplier != 1.0:
            logger.info(f"📊 Volume Multiplier: {self.volume_multiplier}x")
            logger.info(f"   Original: primary {primary_volume_original:.6f}, secondary {secondary_volume_original:.6f}")
            logger.info(f"   Scaled:   primary {primary_volume:.6f}, secondary {secondary_volume:.6f}")
        
        # CRITICAL: Calculate hedge ratio from original volumes
        # This preserves the correct relationship between primary and secondary
        hedge_ratio = secondary_volume / primary_volume if primary_volume > 0 else 1.0
        
        logger.info(f"Placing {side} SPREAD orders...")
        logger.info(f"  Original: primary {primary_volume:.6f} lots, secondary {secondary_volume:.6f} lots")
        logger.info(f"  Hedge ratio (secondary/primary): {hedge_ratio:.4f}")
        
        # Adjust primary volume first (rounds to MT5 step)
        primary_info = self.mt5.symbol_info(self.primary_symbol)
        if primary_info:
            primary_step = primary_info.volume_step
            primary_min = primary_info.volume_min
            primary_max = primary_info.volume_max
            
            # Round to step
            primary_adjusted = round(primary_volume / primary_step) * primary_step
            primary_adjusted = max(primary_min, min(primary_max, primary_adjusted))
            
            logger.info(f"  primary adjusted: {primary_adjusted} (step={primary_step})")
        else:
            primary_adjusted = round(primary_volume, 2)
            logger.warning(f"  Could not get {self.primary_symbol} info, using {primary_adjusted}")
        
        # CRITICAL: Calculate secondary volume FROM adjusted primary volume
        # This maintains the hedge ratio!
        secondary_from_hedge = primary_adjusted * hedge_ratio
        
        # Now adjust secondary to MT5 step
        secondary_info = self.mt5.symbol_info(self.secondary_symbol)
        if secondary_info:
            secondary_step = secondary_info.volume_step
            secondary_min = secondary_info.volume_min
            secondary_max = secondary_info.volume_max
            
            # Round to step
            secondary_adjusted = round(secondary_from_hedge / secondary_step) * secondary_step
            secondary_adjusted = max(secondary_min, min(secondary_max, secondary_adjusted))
            
            logger.info(f"  secondary adjusted: {secondary_adjusted} (step={secondary_step})")
        else:
            secondary_adjusted = round(secondary_from_hedge, 2)
            logger.warning(f"  Could not get {self.secondary_symbol} info, using {secondary_adjusted}")
        
        # Verify final ratio
        final_ratio = secondary_adjusted / primary_adjusted if primary_adjusted > 0 else 0
        ratio_error = abs(final_ratio - hedge_ratio) / hedge_ratio * 100 if hedge_ratio > 0 else 0
        
        logger.info(f"  Final volumes: primary {primary_adjusted}, secondary {secondary_adjusted}")
        logger.info(f"  Final ratio: {final_ratio:.4f} (error: {ratio_error:.2f}%)")
        
        if ratio_error > 5:
            logger.warning(f"  ⚠ Hedge ratio error {ratio_error:.2f}% > 5%!")
        
        # Place primary order (use adjusted volume directly, skip adjustment in place_market_order)
        primary_result = self._place_order_no_adjustment(
            symbol=self.primary_symbol,
            order_type=primary_type,
            volume=primary_adjusted,
            sl=sl_primary,
            tp=tp_primary,
            comment=primary_comment
        )
        
        if not primary_result.success:
            logger.error(f"primary order failed: {primary_result.comment}")
            return ((primary_result, TradeResult(
                success=False, order_ticket=None, volume=0, price=0,
                comment="primary order failed, secondary order skipped"
            )), spread_id)
        
        # Place secondary order (use adjusted volume directly)
        secondary_result = self._place_order_no_adjustment(
            symbol=self.secondary_symbol,
            order_type=secondary_type,
            volume=secondary_adjusted,
            sl=sl_secondary,
            tp=tp_secondary,
            comment=secondary_comment
        )
        
        # Check if both orders succeeded
        if not primary_result.success or not secondary_result.success:
            logger.error(f"Failed to place spread orders:")
            if not primary_result.success:
                logger.error(f"  Primary: {primary_result.comment}")
            if not secondary_result.success:
                logger.error(f"  Secondary: {secondary_result.comment}")
            
            # Return with None spread_id and entry_zscore
            return ((primary_result, secondary_result), None, None)
        
        # CREATE SPREAD_ID FROM TICKETS (guaranteed unique and synced!)
        spread_id = f"{primary_result.order_ticket}-{secondary_result.order_ticket}"
        
        logger.info(f"[MT5 SUCCESS] Spread {spread_id} filled:")
        logger.info(f"  Primary: {primary_adjusted} lots @ ${primary_result.price:.2f} (Ticket {primary_result.order_ticket})")
        logger.info(f"  Secondary: {secondary_adjusted} lots @ ${secondary_result.price:.4f} (Ticket {secondary_result.order_ticket})")
        logger.info(f"  Entry Z-Score: {entry_zscore:.3f}")
        
        # Return tuple: (results, spread_id, entry_zscore)
        return ((primary_result, secondary_result), spread_id, entry_zscore)
    
    def _place_order_no_adjustment(self,
                                   symbol: str,
                                   order_type: str,
                                   volume: float,
                                   sl: Optional[float] = None,
                                   tp: Optional[float] = None,
                                   deviation: int = 20,
                                   comment: str = "PairBot") -> TradeResult:
        """
        Place order with pre-adjusted volume (skip volume adjustment)
        Used internally by place_spread_orders
        """
        # Get symbol info
        symbol_info = self.mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol {symbol} not found")
            return TradeResult(
                success=False, order_ticket=None, volume=0, price=0,
                comment=f"Symbol {symbol} not found"
            )
        
        if not symbol_info.visible:
            if not self.mt5.symbol_select(symbol, True):
                logger.error(f"Failed to select {symbol}")
                return TradeResult(
                    success=False, order_ticket=None, volume=0, price=0,
                    comment=f"Failed to select {symbol}"
                )
        
        # Get current price
        if order_type.upper() == 'BUY':
            price = self.mt5.symbol_info_tick(symbol).ask
            order_type_mt5 = self.mt5.ORDER_TYPE_BUY
        else:
            price = self.mt5.symbol_info_tick(symbol).bid
            order_type_mt5 = self.mt5.ORDER_TYPE_SELL
        
        # Prepare request
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type_mt5,
            "price": price,
            "deviation": deviation,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        
        # Add SL/TP if provided
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp
        
        # Send order
        logger.info(f"Sending {order_type} order: {symbol} {volume} lots @ {price:.5f}")
        
        # DEBUG: Log request details
        logger.debug(f"MT5 Request: {request}")
        
        result = self.mt5.order_send(request)
        
        if result is None:
            # Get last error from MT5
            error_code = self.mt5.last_error()
            logger.error(f"Order send failed: result is None")
            logger.error(f"MT5 last_error: {error_code}")
            
            # Check symbol info
            symbol_info = self.mt5.symbol_info(symbol)
            if symbol_info:
                logger.error(f"Symbol {symbol} info:")
                logger.error(f"  Trade mode: {symbol_info.trade_mode}")
                logger.error(f"  Trade allowed: {symbol_info.trade_mode in [self.mt5.SYMBOL_TRADE_MODE_FULL, self.mt5.SYMBOL_TRADE_MODE_LONGONLY, self.mt5.SYMBOL_TRADE_MODE_SHORTONLY]}")
                logger.error(f"  Volume min: {symbol_info.volume_min}")
                logger.error(f"  Volume max: {symbol_info.volume_max}")
                logger.error(f"  Volume step: {symbol_info.volume_step}")
            else:
                logger.error(f"Cannot get symbol_info for {symbol}")
            
            # Check account info
            account_info = self.mt5.account_info()
            if account_info:
                logger.error(f"Account info:")
                logger.error(f"  Trade allowed: {account_info.trade_allowed}")
                logger.error(f"  Trade expert: {account_info.trade_expert}")
                logger.error(f"  Balance: ${account_info.balance:,.2f}")
                logger.error(f"  Margin free: ${account_info.margin_free:,.2f}")
            
            return TradeResult(
                success=False, order_ticket=None, volume=0, price=0,
                comment=f"MT5 order_send returned None (error: {error_code})"
            )
        
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.retcode} - {result.comment}")
            return TradeResult(
                success=False,
                order_ticket=result.order if hasattr(result, 'order') else None,
                volume=0,
                price=0,
                comment=f"{result.retcode}: {result.comment}"
            )
        
        logger.info(f"[SUCCESS] Order executed: Ticket={result.order}, "
                   f"Volume={result.volume}, Price={result.price}")
        
        return TradeResult(
            success=True,
            order_ticket=result.order,
            volume=result.volume,
            price=result.price,
            comment="Success"
        )

    # ========================================
    # CLOSE METHODS REMOVED - Use fast_close_all instead
    # ========================================
    # All close_position(), close_spread_positions(), close_all_positions_by_magic()
    # have been REMOVED to prevent slow sequential closing.
    #
    # USE THIS INSTEAD:
    #   from utils.fast_close_all import CloseManager
    #   manager = CloseManager(magic_number=234000, max_workers=100)
    #   result = manager.close_all()
    #
    # Benefits:
    #   - 10-100x faster (parallel execution)
    #   - Auto-retry mechanism
    #   - Better error handling
    # ========================================
    
    def get_position_count_by_magic(self, 
                                    magic_number: Optional[int] = None) -> int:
        """
        Get count of open positions by magic number
        
        Args:
            magic_number: Magic number filter (None = use default)
            
        Returns:
            Count of matching positions
        """
        if magic_number is None:
            magic_number = self.magic_number
        
        all_positions = self.mt5.positions_get()
        
        if all_positions is None:
            return 0
        
        matching = [pos for pos in all_positions if pos.magic == magic_number]
        
        return len(matching)
    
    def get_open_positions(self, symbol: Optional[str] = None) -> list:
        """
        Get all open positions
        
        Args:
            symbol: Filter by symbol (None = all)
            
        Returns:
            List of positions
        """
        if symbol:
            positions = self.mt5.positions_get(symbol=symbol)
        else:
            positions = self.mt5.positions_get()
        
        if positions is None:
            return []
        
        return list(positions)
    
    def get_position_by_ticket(self, ticket: int) -> Optional[Dict]:
        """Get position by ticket"""
        positions = self.mt5.positions_get(ticket=ticket)
        
        if positions is None or len(positions) == 0:
            return None
        
        pos = positions[0]
        
        return {
            'ticket': pos.ticket,
            'symbol': pos.symbol,
            'type': 'BUY' if pos.type == self.mt5.POSITION_TYPE_BUY else 'SELL',
            'volume': pos.volume,
            'price_open': pos.price_open,
            'price_current': pos.price_current,
            'sl': pos.sl,
            'tp': pos.tp,
            'profit': pos.profit,
            'comment': pos.comment,
            'time': datetime.fromtimestamp(pos.time)
        }
    
    def modify_position(self,
                       ticket: int,
                       sl: Optional[float] = None,
                       tp: Optional[float] = None) -> TradeResult:
        """
        Modify position SL/TP
        
        Args:
            ticket: Position ticket
            sl: New stop loss
            tp: New take profit
            
        Returns:
            TradeResult
        """
        position = self.mt5.positions_get(ticket=ticket)
        
        if position is None or len(position) == 0:
            return TradeResult(
                success=False,
                order_ticket=ticket,
                volume=0,
                price=0,
                comment=f"Position {ticket} not found"
            )
        
        position = position[0]
        
        request = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "sl": sl if sl is not None else position.sl,
            "tp": tp if tp is not None else position.tp,
        }
        
        result = self.mt5.order_send(request)
        
        if result is None or result.retcode != self.mt5.TRADE_RETCODE_DONE:
            return TradeResult(
                success=False,
                order_ticket=ticket,
                volume=position.volume,
                price=position.price_open,
                comment=result.comment if result else "Modify failed"
            )
        
        logger.info(f"[SUCCESS] Position {ticket} modified (SL={sl}, TP={tp})")
        
        return TradeResult(
            success=True,
            order_ticket=ticket,
            volume=position.volume,
            price=position.price_open,
            comment="Position modified successfully"
        )
    
    def shutdown(self):
        """Shutdown MT5 connection"""
        self.mt5.shutdown()
        logger.info("MT5TradeExecutor shutdown")


# Convenience functions
def quick_buy(symbol: str, volume: float, sl: float = None, tp: float = None) -> TradeResult:
    """Quick buy market order"""
    executor = MT5TradeExecutor()
    result = executor.place_market_order(symbol, 'BUY', volume, sl, tp)
    executor.shutdown()
    return result


def quick_sell(symbol: str, volume: float, sl: float = None, tp: float = None) -> TradeResult:
    """Quick sell market order"""
    executor = MT5TradeExecutor()
    result = executor.place_market_order(symbol, 'SELL', volume, sl, tp)
    executor.shutdown()
    return result


def quick_close(ticket: int) -> TradeResult:
    """Quick close position"""
    executor = MT5TradeExecutor()
    result = executor.close_position(ticket)
    executor.shutdown()
    return result

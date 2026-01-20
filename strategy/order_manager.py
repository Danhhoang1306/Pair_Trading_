"""
Order Manager Module
Manage order creation, modification, and tracking

Includes:
- Order creation
- Order validation
- Order tracking
- Order history
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order type"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(Enum):
    """Order side"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status"""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Order:
    """Order representation"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    
    def __str__(self):
        return (f"Order {self.order_id[:8]}: {self.side.value} {self.quantity} {self.symbol} "
                f"@ {self.order_type.value} ({self.status.value})")


class OrderManager:
    """
    Manage orders for pair trading
    
    Example:
        >>> manager = OrderManager()
        >>> order = manager.create_order(
        >>>     symbol='XAUUSD',
        >>>     side=OrderSide.BUY,
        >>>     quantity=0.1,
        >>>     order_type=OrderType.MARKET
        >>> )
    """
    
    def __init__(self):
        """Initialize order manager"""
        self.orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        
        logger.info("OrderManager initialized")
    
    def create_order(self,
                    symbol: str,
                    side: OrderSide,
                    quantity: float,
                    order_type: OrderType = OrderType.MARKET,
                    price: Optional[float] = None,
                    stop_price: Optional[float] = None,
                    metadata: Dict = None) -> Order:
        """
        Create a new order
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Order quantity
            order_type: Order type
            price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
            metadata: Additional metadata
            
        Returns:
            Order object
        """
        # Generate unique order ID
        order_id = str(uuid.uuid4())
        
        # Validate order
        if quantity <= 0:
            raise ValueError("Order quantity must be positive")
        
        if order_type == OrderType.LIMIT and price is None:
            raise ValueError("LIMIT order requires price")
        
        if order_type == OrderType.STOP and stop_price is None:
            raise ValueError("STOP order requires stop_price")
        
        # Create order
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            metadata=metadata or {}
        )
        
        # Store order
        self.orders[order_id] = order
        
        logger.info(f"Created order: {order.side.value} {order.quantity} {order.symbol}")
        
        return order
    
    def create_spread_orders(self,
                           primary_quantity: float,
                           secondary_quantity: float,
                           side: str,
                           order_type: OrderType = OrderType.MARKET,
                           primary_price: Optional[float] = None,
                           secondary_price: Optional[float] = None) -> Tuple[Order, Order]:
        """
        Create paired orders for spread trading
        
        Args:
            primary_quantity: primary order quantity
            secondary_quantity: secondary order quantity
            side: 'LONG' or 'SHORT'
            order_type: Order type
            primary_price: primary price (for LIMIT)
            secondary_price: secondary price (for LIMIT)
            
        Returns:
            (primary_order, secondary_order)
        """
        if side == 'LONG':
            # LONG SPREAD: Buy primary, Sell secondary
            primary_side = OrderSide.BUY
            secondary_side = OrderSide.SELL
        elif side == 'SHORT':
            # SHORT SPREAD: Sell primary, Buy secondary
            primary_side = OrderSide.SELL
            secondary_side = OrderSide.BUY
        else:
            raise ValueError(f"Invalid side: {side}")
        
        # Create primary order
        primary_order = self.create_order(
            symbol='XAUUSD',
            side=primary_side,
            quantity=primary_quantity,
            order_type=order_type,
            price=primary_price,
            metadata={'pair': 'spread', 'leg': 'primary'}
        )
        
        # Create secondary order
        secondary_order = self.create_order(
            symbol='XAGUSD',
            side=secondary_side,
            quantity=secondary_quantity,
            order_type=order_type,
            price=secondary_price,
            metadata={'pair': 'spread', 'leg': 'secondary'}
        )
        
        # Link orders
        primary_order.metadata['paired_order_id'] = secondary_order.order_id
        secondary_order.metadata['paired_order_id'] = primary_order.order_id
        
        logger.info(f"Created spread orders: {side} "
                   f"(primary: {primary_quantity}, secondary: {secondary_quantity})")
        
        return (primary_order, secondary_order)
    
    def update_order_status(self,
                          order_id: str,
                          status: OrderStatus,
                          filled_quantity: float = 0.0,
                          filled_price: float = 0.0):
        """
        Update order status
        
        Args:
            order_id: Order ID
            status: New status
            filled_quantity: Filled quantity
            filled_price: Average filled price
        """
        if order_id not in self.orders:
            raise ValueError(f"Order not found: {order_id}")
        
        order = self.orders[order_id]
        old_status = order.status
        
        order.status = status
        order.filled_quantity = filled_quantity
        order.filled_price = filled_price
        order.updated_at = datetime.now()
        
        logger.info(f"Order {order_id[:8]} status: {old_status.value} -> {status.value}")
        
        # Move to history if terminal status
        if status in [OrderStatus.FILLED, OrderStatus.CANCELLED, 
                     OrderStatus.REJECTED, OrderStatus.EXPIRED]:
            self.order_history.append(order)
            del self.orders[order_id]
    
    def cancel_order(self, order_id: str):
        """Cancel an order"""
        self.update_order_status(order_id, OrderStatus.CANCELLED)
        logger.info(f"Cancelled order {order_id[:8]}")
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        return self.orders.get(order_id)
    
    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all active orders"""
        orders = list(self.orders.values())
        
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        
        return orders
    
    def get_order_history(self, 
                         symbol: Optional[str] = None,
                         limit: int = 100) -> List[Order]:
        """Get order history"""
        history = self.order_history
        
        if symbol:
            history = [o for o in history if o.symbol == symbol]
        
        return history[-limit:]
    
    def get_statistics(self) -> Dict:
        """Get order statistics"""
        all_orders = list(self.orders.values()) + self.order_history
        
        if not all_orders:
            return {}
        
        filled_orders = [o for o in all_orders if o.status == OrderStatus.FILLED]
        cancelled_orders = [o for o in all_orders if o.status == OrderStatus.CANCELLED]
        
        return {
            'total_orders': len(all_orders),
            'active_orders': len(self.orders),
            'filled_orders': len(filled_orders),
            'cancelled_orders': len(cancelled_orders),
            'fill_rate': len(filled_orders) / len(all_orders) if all_orders else 0
        }
    
    def clear_history(self):
        """Clear order history"""
        count = len(self.order_history)
        self.order_history.clear()
        logger.info(f"Cleared {count} orders from history")
    
    def __repr__(self):
        return f"OrderManager(active={len(self.orders)}, history={len(self.order_history)})"

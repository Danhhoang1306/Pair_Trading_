"""
Grid Executor - Handles unified grid level execution
Replaces separate Entry and Pyramiding executors

Responsibilities:
1. Execute grid level orders (both entry and pyramid)
2. Update grid state after execution
3. Track order tickets
4. Handle execution failures
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from strategy.unified_grid import UnifiedZScoreGrid, GridLevel, LevelStatus, GridCheckResult

logger = logging.getLogger(__name__)


class GridExecutor:
    """
    Executes grid level orders

    Handles both initial entry and pyramiding as unified grid levels.
    Each level execution places 2-leg spread orders.
    """

    def __init__(self,
                 trade_executor,
                 grid: UnifiedZScoreGrid,
                 position_monitor,
                 mt5_tickets: Dict,
                 primary_symbol: str,
                 secondary_symbol: str,
                 volume_calculator=None):
        """
        Initialize Grid Executor

        Args:
            trade_executor: MT5 trade executor for placing orders
            grid: UnifiedZScoreGrid instance
            position_monitor: Position monitor for tracking
            mt5_tickets: Dict to store order tickets
            primary_symbol: Primary symbol (e.g., 'XAUUSD')
            secondary_symbol: Secondary symbol (e.g., 'XAGUSD')
            volume_calculator: Optional calculator for position sizing
        """
        self.trade_executor = trade_executor
        self.grid = grid
        self.position_monitor = position_monitor
        self.mt5_tickets = mt5_tickets
        self.primary_symbol = primary_symbol
        self.secondary_symbol = secondary_symbol
        self.volume_calculator = volume_calculator

        logger.info("GridExecutor initialized")
        logger.info(f"  Symbols: {primary_symbol}/{secondary_symbol}")

    def process_grid_check(self,
                           result: GridCheckResult,
                           snapshot,
                           account_balance: float) -> bool:
        """
        Process grid check result - mark skipped and execute triggered level

        Args:
            result: GridCheckResult from grid.check_levels()
            snapshot: MarketSnapshot with current prices and hedge ratio
            account_balance: Current account balance for position sizing

        Returns:
            True if level was executed successfully
        """
        # Mark skipped levels as BLOCKED
        if result.has_skipped:
            self.grid.mark_skipped(result.skipped_levels)
            logger.info(f"[GRID] {len(result.skipped_levels)} levels BLOCKED (z-score jumped)")

        # Execute triggered level
        if result.has_trigger:
            return self.execute_level(result.triggered_level, snapshot, account_balance)

        return False

    def execute_level(self,
                      level: GridLevel,
                      snapshot,
                      account_balance: float) -> bool:
        """
        Execute a single grid level

        Args:
            level: GridLevel to execute
            snapshot: MarketSnapshot with prices and hedge_ratio
            account_balance: Account balance for position sizing

        Returns:
            True if execution successful
        """
        # Check cooldown
        can_execute, reason = self.grid.can_execute()
        if not can_execute:
            logger.info(f"[GRID] Execution blocked: {reason}")
            return False

        side = self.grid.side
        if not side:
            logger.error("[GRID] Grid not activated - no side set")
            return False

        logger.info(f"[GRID] ====== EXECUTING LEVEL: {level.name} ======")
        logger.info(f"  Z-score target: {level.zscore:.2f}")
        logger.info(f"  Current z-score: {snapshot.zscore:.3f}")
        logger.info(f"  Position fraction: {level.fraction:.1%}")
        logger.info(f"  Side: {side}")

        # Calculate volumes
        primary_volume, secondary_volume = self._calculate_volumes(
            level, snapshot, account_balance
        )

        if primary_volume <= 0 or secondary_volume <= 0:
            logger.error(f"[GRID] Invalid volumes: {primary_volume:.4f} / {secondary_volume:.4f}")
            return False

        logger.info(f"  Primary volume: {primary_volume:.4f} lots")
        logger.info(f"  Secondary volume: {secondary_volume:.4f} lots")

        # Determine order types based on side
        if side == 'LONG':
            # LONG spread: BUY primary, SELL secondary
            primary_type = 'BUY'
            secondary_type = 'SELL'
        else:  # SHORT
            # SHORT spread: SELL primary, BUY secondary
            primary_type = 'SELL'
            secondary_type = 'BUY'

        logger.info(f"  Orders: {primary_type} {self.primary_symbol}, "
                   f"{secondary_type} {self.secondary_symbol}")

        # Execute orders
        try:
            # Execute primary order
            primary_result = self.trade_executor.place_market_order(
                symbol=self.primary_symbol,
                order_type=primary_type,
                volume=primary_volume,
                comment=f"GRID:{level.name}:{self.grid.spread_id[:8] if self.grid.spread_id else 'NEW'}"
            )

            if not primary_result.success:
                logger.error(f"[GRID] Primary order failed: {primary_result.error_description}")
                return False

            primary_ticket = primary_result.order_ticket
            logger.info(f"  ✅ Primary: {primary_type} {primary_volume:.4f} @ ticket {primary_ticket}")

            # Execute secondary order
            secondary_result = self.trade_executor.place_market_order(
                symbol=self.secondary_symbol,
                order_type=secondary_type,
                volume=secondary_volume,
                comment=f"GRID:{level.name}:{self.grid.spread_id[:8] if self.grid.spread_id else 'NEW'}"
            )

            if not secondary_result.success:
                logger.error(f"[GRID] Secondary order failed: {secondary_result.error_description}")
                logger.warning("[GRID] ⚠️ Primary executed but secondary failed - HEDGE INCOMPLETE!")
                # Still mark level as executed but with warning
                self._mark_level_executed(
                    level,
                    primary_result.volume,
                    0,  # No secondary
                    [primary_ticket]
                )
                return False

            secondary_ticket = secondary_result.order_ticket
            logger.info(f"  ✅ Secondary: {secondary_type} {secondary_volume:.4f} @ ticket {secondary_ticket}")

            # Register tickets for monitoring
            self.mt5_tickets[primary_ticket] = self.primary_symbol
            self.mt5_tickets[secondary_ticket] = self.secondary_symbol

            # Register positions for monitoring
            if self.position_monitor:
                self.position_monitor.register_position(primary_ticket, self.primary_symbol)
                self.position_monitor.register_position(secondary_ticket, self.secondary_symbol)

            # Mark level as executed
            self._mark_level_executed(
                level,
                primary_result.volume,
                secondary_result.volume,
                [primary_ticket, secondary_ticket]
            )

            logger.info(f"[GRID] ====== LEVEL {level.name} EXECUTED ======")
            return True

        except Exception as e:
            logger.error(f"[GRID] Execution error: {e}", exc_info=True)
            return False

    def _calculate_volumes(self,
                           level: GridLevel,
                           snapshot,
                           account_balance: float) -> Tuple[float, float]:
        """
        Calculate volumes for a grid level

        Args:
            level: Grid level with fraction
            snapshot: Market snapshot with hedge_ratio
            account_balance: Account balance

        Returns:
            (primary_volume, secondary_volume)
        """
        # Position value based on fraction
        position_value = account_balance * level.fraction

        # Get prices (use bid prices for execution)
        primary_price = snapshot.primary_bid
        secondary_price = snapshot.secondary_bid
        hedge_ratio = snapshot.hedge_ratio

        # Use volume calculator if available
        if self.volume_calculator:
            try:
                volumes = self.volume_calculator.calculate(
                    position_value=position_value,
                    primary_price=primary_price,
                    secondary_price=secondary_price,
                    hedge_ratio=hedge_ratio
                )
                return volumes['primary'], volumes['secondary']
            except Exception as e:
                logger.warning(f"Volume calculator failed: {e}, using fallback")

        # Fallback: Simple calculation
        # Assume contract sizes (should come from symbol info)
        primary_contract = 100  # e.g., XAUUSD = 100 oz
        secondary_contract = 5000  # e.g., XAGUSD = 5000 oz

        # Calculate primary lots
        primary_lots = position_value / (primary_price * primary_contract)

        # Calculate secondary lots based on hedge ratio
        # hedge_ratio = primary_value / secondary_value
        secondary_value = position_value / hedge_ratio if hedge_ratio > 0 else position_value
        secondary_lots = secondary_value / (secondary_price * secondary_contract)

        # Round to broker requirements
        primary_lots = round(primary_lots, 2)
        secondary_lots = round(secondary_lots, 2)

        # Ensure minimum
        primary_lots = max(0.01, primary_lots)
        secondary_lots = max(0.01, secondary_lots)

        return primary_lots, secondary_lots

    def _mark_level_executed(self,
                             level: GridLevel,
                             primary_lots: float,
                             secondary_lots: float,
                             order_tickets: List[int]):
        """Mark level as executed in grid"""
        self.grid.mark_executed(
            level=level,
            primary_lots=primary_lots,
            secondary_lots=secondary_lots,
            order_tickets=order_tickets
        )

    def get_total_position(self) -> Dict:
        """Get total position across all executed levels"""
        stats = self.grid.get_statistics()
        return {
            'total_primary_lots': stats['total_primary_lots'],
            'total_secondary_lots': stats['total_secondary_lots'],
            'executed_fraction': stats['executed_fraction'],
            'executed_levels': stats['executed_count'],
            'remaining_levels': stats['waiting_count']
        }


class VolumeCalculator:
    """
    Helper class to calculate order volumes

    Takes into account:
    - Account balance
    - Position fraction
    - Hedge ratio
    - Symbol contract sizes
    """

    def __init__(self,
                 primary_contract_size: float = 100,
                 secondary_contract_size: float = 5000,
                 primary_min_lot: float = 0.01,
                 secondary_min_lot: float = 0.01,
                 primary_lot_step: float = 0.01,
                 secondary_lot_step: float = 0.01):
        """
        Initialize volume calculator

        Args:
            primary_contract_size: Contract size for primary (e.g., 100 for XAUUSD)
            secondary_contract_size: Contract size for secondary (e.g., 5000 for XAGUSD)
            primary_min_lot: Minimum lot for primary
            secondary_min_lot: Minimum lot for secondary
            primary_lot_step: Lot step for primary
            secondary_lot_step: Lot step for secondary
        """
        self.primary_contract_size = primary_contract_size
        self.secondary_contract_size = secondary_contract_size
        self.primary_min_lot = primary_min_lot
        self.secondary_min_lot = secondary_min_lot
        self.primary_lot_step = primary_lot_step
        self.secondary_lot_step = secondary_lot_step

    def calculate(self,
                  position_value: float,
                  primary_price: float,
                  secondary_price: float,
                  hedge_ratio: float) -> Dict[str, float]:
        """
        Calculate order volumes

        Args:
            position_value: Dollar value to invest
            primary_price: Current primary price
            secondary_price: Current secondary price
            hedge_ratio: Hedge ratio (beta)

        Returns:
            {'primary': lots, 'secondary': lots}
        """
        # Primary lots
        primary_notional = primary_price * self.primary_contract_size
        primary_lots = position_value / primary_notional if primary_notional > 0 else 0

        # Secondary lots (based on hedge ratio)
        # hedge_ratio = primary_value / secondary_value
        # secondary_value = primary_value / hedge_ratio
        if hedge_ratio > 0:
            secondary_value = position_value / hedge_ratio
        else:
            secondary_value = position_value

        secondary_notional = secondary_price * self.secondary_contract_size
        secondary_lots = secondary_value / secondary_notional if secondary_notional > 0 else 0

        # Round to lot step
        primary_lots = self._round_to_step(primary_lots, self.primary_lot_step)
        secondary_lots = self._round_to_step(secondary_lots, self.secondary_lot_step)

        # Ensure minimum
        primary_lots = max(self.primary_min_lot, primary_lots)
        secondary_lots = max(self.secondary_min_lot, secondary_lots)

        return {
            'primary': primary_lots,
            'secondary': secondary_lots
        }

    def _round_to_step(self, value: float, step: float) -> float:
        """Round value to nearest step"""
        if step <= 0:
            return value
        return round(value / step) * step

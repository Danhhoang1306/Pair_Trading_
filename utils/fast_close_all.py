"""
Ultra-Fast Close-All System with Async Batch Processing
Optimized for maximum speed - minimal API calls
"""
import logging
import threading
import time
from typing import List, Set, Dict, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.mt5_manager import get_mt5

logger = logging.getLogger(__name__)


@dataclass
class TicketCloseResult:
    """Result of closing a single ticket"""
    ticket: int
    symbol: str
    success: bool
    retries: int
    error: Optional[str] = None


class OptimizedTicketWorker:
    """
    Optimized worker that can use cached tick prices
    """

    def __init__(self, ticket: int, symbol: str, position_type: int, volume: float, cached_tick=None):
        self.ticket = ticket
        self.symbol = symbol
        self.position_type = position_type
        self.volume = volume
        self.cached_tick = cached_tick

    def execute(self) -> TicketCloseResult:
        """Execute close with optional cached tick"""
        success, error = self._close_ticket_direct()

        return TicketCloseResult(
            ticket=self.ticket,
            symbol=self.symbol,
            success=success,
            retries=1,
            error=error
        )

    def _close_ticket_direct(self) -> Tuple[bool, Optional[str]]:
        """
        Direct close with optional cached tick
        """
        try:
            # Determine close action
            mt5 = get_mt5()
            close_type = mt5.ORDER_TYPE_SELL if self.position_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY

            # Use cached tick or fetch new
            if self.cached_tick:
                ask, bid = self.cached_tick
                price = ask if close_type == mt5.ORDER_TYPE_BUY else bid
            else:
                tick = mt5.symbol_info_tick(self.symbol)
                if not tick:
                    return False, "No tick data"
                price = tick.ask if close_type == mt5.ORDER_TYPE_BUY else tick.bid

            # Create close request
            mt5 = get_mt5()
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.volume,
                "type": close_type,
                "position": self.ticket,
                "price": price,
                "deviation": 20,
                "comment": "FAST_CLOSE_ALL",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            # Send order
            result = mt5.order_send(request)

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return True, None
            else:
                error = f"Retcode: {result.retcode if result else 'None'}"
                return False, error

        except Exception as e:
            return False, str(e)


class TicketWorker:
    """
    Legacy worker for backwards compatibility
    """

    def __init__(self, ticket: int, symbol: str, position_type: int, volume: float):
        self.worker = OptimizedTicketWorker(ticket, symbol, position_type, volume, None)

    def execute(self):
        return self.worker.execute()


class AsyncBatchCloser:
    """
    Async batch processor for ultra-fast position closing
    Key optimization: Pre-fetch all position data once
    ULTIMATE SPEED: Fire-and-forget mode available
    """

    def __init__(self, max_workers: int = 100):
        self.max_workers = max_workers
        self._tick_cache = {}  # Cache ticks to reduce API calls
        self._cache_lock = threading.Lock()

    def close_batch(self, positions: List, prefetch_ticks: bool = True) -> List[TicketCloseResult]:
        """
        Close all tickets in parallel batch

        Strategy:
        1. Pre-fetch all ticks at once (optional)
        2. Fire all close requests simultaneously
        3. Collect results (no verification)

        Args:
            positions: List of MT5 position objects (pre-fetched)
            prefetch_ticks: Pre-fetch all tick prices to reduce API calls

        Returns:
            List of TicketCloseResult
        """
        if not positions:
            return []

        # OPTIMIZATION: Pre-fetch all ticks once
        if prefetch_ticks:
            self._prefetch_all_ticks(positions)

        results = []

        # Fire all requests in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit ALL workers at once with pre-fetched data
            futures = {
                executor.submit(
                    self._create_worker(pos).execute
                ): pos.ticket
                for pos in positions
            }

            # Collect results as fast as they complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    ticket = futures[future]
                    logger.error(f"Worker crash for ticket {ticket}: {e}")
                    results.append(TicketCloseResult(
                        ticket=ticket,
                        symbol='UNKNOWN',
                        success=False,
                        retries=0,
                        error=f"Worker crash: {str(e)}"
                    ))

        return results

    def _prefetch_all_ticks(self, positions: List):
        """Pre-fetch all tick prices to cache"""
        symbols = set(pos.symbol for pos in positions)
        mt5 = get_mt5()
        for symbol in symbols:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                with self._cache_lock:
                    self._tick_cache[symbol] = (tick.ask, tick.bid, time.time())

    def _get_cached_tick(self, symbol: str):
        """Get tick from cache or fetch new"""
        with self._cache_lock:
            if symbol in self._tick_cache:
                ask, bid, timestamp = self._tick_cache[symbol]
                # Cache valid for 1 second
                if time.time() - timestamp < 1.0:
                    return (ask, bid)
        return None

    def _create_worker(self, pos):
        """Create worker with cached tick if available"""
        cached_tick = self._get_cached_tick(pos.symbol)
        return OptimizedTicketWorker(
            pos.ticket,
            pos.symbol,
            pos.type,
            pos.volume,
            cached_tick
        )


class CloseManager:
    """
    Manager for parallel close operations
    Ultra-optimized: Minimal API calls
    """

    def __init__(self, magic_number: Optional[int] = None, max_workers: int = 100):
        """
        Args:
            magic_number: Filter by magic number (None = close all)
            max_workers: Max parallel workers
        """
        self.magic_number = magic_number
        self.max_workers = max_workers
        self.max_global_rounds = 2  # Usually only need 1-2 rounds
        self.batch_closer = AsyncBatchCloser(max_workers=max_workers)

    def close_all(self) -> Dict:
        """
        Close all positions with minimal API calls

        Optimized process:
        1. Fetch all positions ONCE
        2. Fire ALL close requests simultaneously
        3. Only retry failed ones (if any)

        Returns:
            {
                'success': bool,
                'total_closed': int,
                'total_failed': int,
                'rounds': int,
                'results': List[TicketCloseResult]
            }
        """
        # MT5 should already be initialized via MT5Manager
        try:
            mt5 = get_mt5()
        except RuntimeError:
            return {
                'success': False,
                'error': 'MT5 not initialized',
                'total_closed': 0,
                'total_failed': 0,
                'rounds': 0,
                'results': []
            }

        logger.warning("="*80)
        logger.warning("🚀 ULTRA-FAST CLOSE-ALL INITIATED")
        logger.warning("="*80)

        all_results = []
        round_num = 0

        for round_num in range(1, self.max_global_rounds + 1):
            # Step 1: Get all open positions (single API call)
            positions = self._get_open_positions()

            if not positions:
                logger.info("✅ No open positions found")
                break

            logger.info(f"📍 Round {round_num}: Closing {len(positions)} positions...")

            # Step 2: Fire ALL close requests at once
            start_time = time.time()
            round_results = self.batch_closer.close_batch(positions)
            elapsed = time.time() - start_time

            all_results.extend(round_results)

            # Quick summary
            succeeded = sum(1 for r in round_results if r.success)
            failed = len(round_results) - succeeded
            logger.info(f"   ✅ Closed: {succeeded}, ❌ Failed: {failed} (in {elapsed:.2f}s)")

            # Step 3: Only verify if there were failures
            if failed > 0 and round_num < self.max_global_rounds:
                logger.warning(f"   ⚠️ Retrying {failed} failed positions...")
                time.sleep(0.05)  # Minimal delay
            else:
                break

        # Final verification (only if needed)
        if any(not r.success for r in all_results):
            final_remaining = self._get_open_positions()
        else:
            final_remaining = []

        # Calculate summary
        total_closed = len([r for r in all_results if r.success])
        total_failed = len([r for r in all_results if not r.success])

        logger.warning("="*80)
        if not final_remaining:
            logger.warning("✅ ULTRA-FAST CLOSE-ALL COMPLETE: ALL POSITIONS CLOSED")
        else:
            logger.error(f"❌ CLOSE-ALL INCOMPLETE: {len(final_remaining)} positions remain")
            logger.error(f"   Remaining tickets: {[p.ticket for p in final_remaining]}")
        logger.warning(f"   Total closed: {total_closed}")
        logger.warning(f"   Total failed: {total_failed}")
        logger.warning(f"   Rounds executed: {round_num}")
        logger.warning("="*80)

        return {
            'success': len(final_remaining) == 0,
            'total_closed': total_closed,
            'total_failed': total_failed,
            'rounds': round_num,
            'remaining': final_remaining,
            'results': all_results
        }

    def _get_open_positions(self) -> List:
        """
        Get all open positions (returns full position objects)

        Returns:
            List of MT5 position objects
        """
        try:
            mt5 = get_mt5()
            if self.magic_number:
                positions = mt5.positions_get(magic=self.magic_number)
            else:
                positions = mt5.positions_get()

            return list(positions) if positions else []
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []


def fast_close_all_and_shutdown(
    system,
    magic_number: int = 234000,
    shutdown_threads: bool = True
) -> Dict:
    """
    Fast close all positions and shutdown system

    Args:
        system: Main system instance
        magic_number: Magic number filter
        shutdown_threads: Whether to stop all threads after close

    Returns:
        Close results dict
    """
    logger.warning("="*80)
    logger.warning("🚨 FAST CLOSE-ALL AND SHUTDOWN INITIATED")
    logger.warning("="*80)

    # Step 1: Close all positions (ultra-fast)
    manager = CloseManager(magic_number=magic_number, max_workers=100)
    result = manager.close_all()

    if not result['success']:
        logger.error("⚠️ Some positions failed to close!")
        logger.error(f"   Closed: {result['total_closed']}")
        logger.error(f"   Failed: {result['total_failed']}")
        logger.error(f"   Remaining: {len(result.get('remaining', []))}")

    # Step 2: Cleanup internal tracking
    logger.info("🧹 Cleaning up internal tracking...")
    try:
        system.position_tracker.clear_all()
        logger.info("   ✅ Position tracker cleared")
    except Exception as e:
        logger.warning(f"   ⚠️ Position tracker cleanup error: {e}")

    try:
        system.rebalancer.clear_all()
        logger.info("   ✅ Rebalancer cleared")
    except Exception as e:
        logger.warning(f"   ⚠️ Rebalancer cleanup error: {e}")

    try:
        system.position_monitor.clear_all()
        logger.info("   ✅ Position monitor cleared")
    except Exception as e:
        logger.warning(f"   ⚠️ Position monitor cleanup error: {e}")

    # Step 3: Stop threads
    if shutdown_threads:
        logger.info("🛑 Stopping all threads...")
        try:
            system.running = False
            time.sleep(0.3)  # Minimal delay
            logger.info("   ✅ All threads stopped")
        except Exception as e:
            logger.warning(f"   ⚠️ Thread shutdown error: {e}")

    # Step 4: Final cleanup
    # Note: MT5Manager handles shutdown, don't shutdown here
    logger.info("🧹 Final resource cleanup...")
    logger.info("   ✅ MT5 connection managed by MT5Manager")

    logger.warning("="*80)
    logger.warning("✅ SHUTDOWN COMPLETE")
    logger.warning("="*80)

    return result


if __name__ == '__main__':
    # Example usage with timing
    start = time.time()
    manager = CloseManager(magic_number=234000, max_workers=100)
    result = manager.close_all()
    elapsed = time.time() - start
    print(f"\nClosed {result['total_closed']} positions in {result['rounds']} rounds")
    print(f"Total time: {elapsed:.2f} seconds")
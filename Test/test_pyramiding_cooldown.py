"""
Test Pyramiding Entry Cooldown Fix
Verify that pyramiding updates last_z_entry to prevent duplicate entries
"""

import logging
from unittest.mock import Mock, MagicMock
from executors.pyramiding_executor import PyramidingExecutor
from strategy.entry_cooldown import EntryCooldownManager
from strategy.hybrid_rebalancer import RebalanceLevel

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def test_pyramiding_updates_cooldown():
    """
    Test scenario:
    1. Pyramiding executes at z=-2.5
    2. Verify entry_cooldown.mark_entry() was called with z=-2.5
    3. Verify last_z_entry is updated to -2.5

    This prevents duplicate pyramiding when z-score oscillates around -2.5
    """

    logger.info("="*80)
    logger.info("TEST: Pyramiding Entry Cooldown Update")
    logger.info("="*80)

    # Setup mocks
    trade_executor = Mock()
    rebalancer = Mock()
    position_monitor = Mock()
    mt5_tickets = {}

    # Setup entry cooldown (min_time_between=1 for testing)
    entry_cooldown = EntryCooldownManager(
        scale_interval=0.5,
        min_time_between=1,  # 1 second for testing (not 60s)
        persist_path=None  # Use default
    )

    # Create pyramiding executor WITH entry cooldown
    pyramiding_executor = PyramidingExecutor(
        trade_executor=trade_executor,
        rebalancer=rebalancer,
        position_monitor=position_monitor,
        mt5_tickets=mt5_tickets,
        primary_symbol='XAUUSD',
        secondary_symbol='XAGUSD',
        entry_cooldown=entry_cooldown,
        enable_entry_cooldown=True
    )

    # Mock successful trade execution
    primary_result = Mock()
    primary_result.success = True
    primary_result.order_ticket = 123456
    primary_result.volume = 0.33

    secondary_result = Mock()
    secondary_result.success = True
    secondary_result.order_ticket = 123457
    secondary_result.volume = 29.04

    trade_executor.place_market_order.side_effect = [primary_result, secondary_result]

    # Mock rebalancer active_positions
    spread_id = 'test_spread_001'
    rebalancer.active_positions = {
        spread_id: {
            'primary_lots': 0.33,
            'secondary_lots': 29.04
        }
    }

    # Mock snapshot
    snapshot = Mock()
    snapshot.hedge_ratio = 88.0
    snapshot.primary_bid = 2700.0
    snapshot.secondary_bid = 30.68

    # Create pyramiding action
    level = RebalanceLevel(zscore=-2.5, executed=False)

    pyramiding_action = {
        'type': 'PYRAMIDING',
        'spread_id': spread_id,
        'side': 'LONG',
        'level': level,
        'position_size': 0.33,
        'current_zscore': -2.5,
        'reason': 'Grid scale-in at z=-2.5'
    }

    # ========== BEFORE: Check cooldown status ==========
    logger.info("\n[BEFORE] Entry cooldown status:")
    status_before = entry_cooldown.get_status('LONG')
    logger.info(f"  Has last entry: {status_before['has_last_entry']}")
    logger.info(f"  Last z-score: {status_before['last_zscore']}")

    # ========== EXECUTE PYRAMIDING ==========
    logger.info("\n[EXECUTE] Running pyramiding...")
    success = pyramiding_executor.execute(pyramiding_action, snapshot)

    logger.info(f"\n[RESULT] Pyramiding execution: {'SUCCESS' if success else 'FAILED'}")

    # ========== AFTER: Check cooldown status ==========
    logger.info("\n[AFTER] Entry cooldown status:")
    status_after = entry_cooldown.get_status('LONG')
    logger.info(f"  Has last entry: {status_after['has_last_entry']}")
    logger.info(f"  Last z-score: {status_after['last_zscore']}")

    # ========== VERIFY ==========
    logger.info("\n[VERIFY]")

    if status_after['has_last_entry']:
        logger.info(f"  ✅ Entry cooldown was updated")
    else:
        logger.error(f"  ❌ Entry cooldown was NOT updated!")
        return False

    if status_after['last_zscore'] == -2.5:
        logger.info(f"  ✅ last_z_entry = {status_after['last_zscore']} (correct!)")
    else:
        logger.error(f"  ❌ last_z_entry = {status_after['last_zscore']} (expected -2.5)")
        return False

    # ========== TEST OSCILLATION BLOCKING ==========
    logger.info("\n[TEST] Oscillation blocking:")
    logger.info("  Testing if z=-2.52 would be blocked...")

    can_enter_252 = entry_cooldown.can_enter('LONG', -2.52)
    if not can_enter_252:
        logger.info(f"  ✅ z=-2.52 is BLOCKED (Δz=0.02 < 0.5)")
    else:
        logger.error(f"  ❌ z=-2.52 is ALLOWED (should be blocked!)")
        return False

    logger.info("  Testing if z=-3.0 would be allowed...")
    logger.info("  Waiting 2 seconds for min_time_between to pass...")
    import time
    time.sleep(2)

    can_enter_30 = entry_cooldown.can_enter('LONG', -3.0)
    if can_enter_30:
        logger.info(f"  ✅ z=-3.0 is ALLOWED (Δz=0.5 >= 0.5)")
    else:
        logger.error(f"  ❌ z=-3.0 is BLOCKED (should be allowed!)")
        return False

    logger.info("\n" + "="*80)
    logger.info("✅ ALL TESTS PASSED")
    logger.info("="*80)

    return True


if __name__ == '__main__':
    success = test_pyramiding_updates_cooldown()
    exit(0 if success else 1)

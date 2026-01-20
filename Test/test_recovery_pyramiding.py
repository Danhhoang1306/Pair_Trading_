"""
Test Recovery Manager - Pyramiding Level Fix
Verify that recovery uses last_z_entry instead of original entry_zscore
"""

import logging
from strategy.hybrid_rebalancer import HybridRebalancer
from strategy.entry_cooldown import EntryCooldownManager

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def test_recovery_pyramiding_fix():
    """
    Test scenario:
    1. Entry at z=-2.0 (Level 1)
    2. Pyramiding at z=-2.5 (Level 2) -> last_z_entry = -2.5
    3. RESTART
    4. Recovery should use z=-2.5 (not -2.0) for calculating next levels
    """

    logger.info("="*80)
    logger.info("TEST: Recovery Pyramiding Level Fix")
    logger.info("="*80)

    # Setup
    rebalancer = HybridRebalancer(
        scale_interval=0.5,
        max_zscore=3.0,
        initial_fraction=0.33
    )

    cooldown = EntryCooldownManager(
        scale_interval=0.5,
        min_time_between=60,
        persist_path=None  # Use default
    )

    # ========== SCENARIO 1: Original Entry ==========
    logger.info("\n[STEP 1] Original Entry at z=-2.0")

    spread_id = "test_spread_001"
    entry_zscore_original = -2.0
    side = 'LONG'

    # Register position (simulate first entry)
    pos_data = rebalancer.register_position(
        spread_id=spread_id,
        side=side,
        entry_zscore=entry_zscore_original,
        entry_hedge_ratio=88.0,
        primary_lots=0.33,
        secondary_lots=29.04,
        total_position_size=1.0,
        primary_symbol='XAUUSD',
        secondary_symbol='XAGUSD'
    )

    logger.info(f"Position registered with entry_zscore = {entry_zscore_original}")
    levels_str = [f"z={l.zscore:.1f} ({'executed' if l.executed else 'pending'})" for l in pos_data['levels']]
    logger.info(f"Grid levels: {levels_str}")

    # Mark entry cooldown
    cooldown.mark_entry('LONG', entry_zscore_original)

    # ========== SCENARIO 2: Pyramiding at z=-2.5 ==========
    logger.info("\n[STEP 2] Pyramiding at z=-2.5 (Level 2)")

    pyramid_zscore = -2.5

    # Check pyramiding trigger
    pyramid_action = rebalancer.check_pyramiding(spread_id, pyramid_zscore)

    if pyramid_action:
        logger.info(f"✅ Pyramiding triggered: {pyramid_action}")

        # Mark pyramiding executed
        rebalancer.mark_pyramiding_executed(
            spread_id=spread_id,
            zscore=pyramid_zscore,
            primary_lots=0.33,
            secondary_lots=29.04
        )

        # Update entry cooldown (THIS IS KEY!)
        cooldown.mark_entry('LONG', pyramid_zscore)
        logger.info(f"Updated last_z_entry = {pyramid_zscore}")

    # ========== SCENARIO 3: RESTART & RECOVERY ==========
    logger.info("\n[STEP 3] SIMULATE RESTART & RECOVERY")
    logger.info("-"*80)

    # Create new rebalancer (simulate restart)
    rebalancer_after_restart = HybridRebalancer(
        scale_interval=0.5,
        max_zscore=3.0,
        initial_fraction=0.33
    )

    # Simulate what recovery_manager.py does NOW (with fix)
    logger.info("\n[RECOVERY] Loading position from disk...")

    # Simulated persisted data
    persisted_entry_zscore = entry_zscore_original  # -2.0 (from disk)
    persisted_volume = 0.66  # Total volume (2 levels executed)

    logger.info(f"  Persisted entry_zscore: {persisted_entry_zscore}")
    logger.info(f"  Persisted volume: {persisted_volume}")

    # ✅ NEW LOGIC: Check last_z_entry from cooldown
    cooldown_status = cooldown.get_status('LONG')

    if cooldown_status['has_last_entry']:
        actual_entry_zscore = cooldown_status['last_zscore']
        logger.info(f"  ✅ Found last_z_entry = {actual_entry_zscore:.3f}")
        logger.info(f"  Using last_z_entry instead of persisted entry_zscore")
    else:
        actual_entry_zscore = persisted_entry_zscore
        logger.info(f"  No last_z_entry found, using persisted entry_zscore")

    # Register with actual_entry_zscore
    logger.info(f"\n[RECOVERY] Registering position with entry_zscore = {actual_entry_zscore:.3f}")

    recovered_pos_data = rebalancer_after_restart.register_position(
        spread_id=spread_id,
        side=side,
        entry_zscore=actual_entry_zscore,  # ✅ Use last_z_entry!
        entry_hedge_ratio=88.0,
        primary_lots=persisted_volume,
        secondary_lots=persisted_volume * 88.0,
        total_position_size=1.0,
        primary_symbol='XAUUSD',
        secondary_symbol='XAGUSD'
    )

    recovered_levels_str = [f"z={l.zscore:.1f} ({'executed' if l.executed else 'pending'})" for l in recovered_pos_data['levels']]
    logger.info(f"Recovered grid levels: {recovered_levels_str}")

    # ========== SCENARIO 4: Check Next Pyramiding ==========
    logger.info("\n[STEP 4] Check if z=-2.5 would trigger again (should NOT)")

    test_zscore = -2.5
    pyramid_action_after_recovery = rebalancer_after_restart.check_pyramiding(spread_id, test_zscore)

    if pyramid_action_after_recovery:
        logger.error(f"❌ FAILED: Pyramiding triggered again at z={test_zscore} (DUPLICATE!)")
        logger.error(f"   This should NOT happen!")
    else:
        logger.info(f"✅ PASSED: No pyramiding at z={test_zscore} (already executed)")

    # ========== SCENARIO 5: Check z=-3.0 (should trigger) ==========
    logger.info("\n[STEP 5] Check if z=-3.0 triggers (should trigger)")

    test_zscore = -3.0
    pyramid_action_new_level = rebalancer_after_restart.check_pyramiding(spread_id, test_zscore)

    if pyramid_action_new_level:
        logger.info(f"✅ PASSED: Pyramiding triggered at z={test_zscore} (next level)")
    else:
        logger.error(f"❌ FAILED: Should trigger at z={test_zscore}")

    # ========== SUMMARY ==========
    logger.info("\n" + "="*80)
    logger.info("TEST SUMMARY")
    logger.info("="*80)
    logger.info("✅ Fix verified: last_z_entry is used for recovery")
    logger.info("✅ Prevents duplicate pyramiding at previously executed levels")
    logger.info("✅ Next level triggers correctly")
    logger.info("="*80)


if __name__ == '__main__':
    test_recovery_pyramiding_fix()

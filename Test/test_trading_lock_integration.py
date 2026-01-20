"""
Test Trading Lock Integration with DailyRiskManager

Verifies:
1. TradingLockManager can lock/unlock
2. DailyRiskManager integrates with TradingLockManager
3. Lock state is persisted to file
4. check_risk() triggers lock when daily limit breached
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_trading_lock_integration():
    """Test full integration"""
    print("=" * 80)
    print("TEST: TRADING LOCK INTEGRATION")
    print("=" * 80)

    from risk.trading_lock_manager import TradingLockManager
    from risk.daily_risk_manager import DailyRiskManager

    # Clean up any existing lock file
    lock_file = Path("asset/trading_lock.json")
    if lock_file.exists():
        lock_file.unlink()
        print("[OK] Cleaned up existing lock file")

    # Test 1: Initialize TradingLockManager
    print("\n--- Test 1: TradingLockManager ---")
    lock_mgr = TradingLockManager(session_start_time="00:00")
    assert not lock_mgr.is_locked(), "Should start unlocked"
    print("[PASS] TradingLockManager initialized - unlocked")

    # Test 2: Initialize DailyRiskManager with TradingLockManager
    print("\n--- Test 2: DailyRiskManager Integration ---")
    daily_risk_mgr = DailyRiskManager(
        account_balance=100000.0,
        max_risk_pct=1.5,  # 1.5%
        daily_loss_limit=3000.0,  # $3,000
        session_start_time="00:00",
        session_end_time="23:59",
        magic_number=234000,
        trading_lock_manager=lock_mgr  # Pass lock manager
    )
    print("[PASS] DailyRiskManager initialized with TradingLockManager")

    # Test 3: Normal scenario - no breach
    print("\n--- Test 3: Normal Scenario (No Breach) ---")
    unrealized_pnl = -500.0  # Small loss
    risk_status = daily_risk_mgr.check_risk(unrealized_pnl)

    assert not risk_status.max_risk_breached, "Should not breach max risk"
    assert not risk_status.daily_limit_breached, "Should not breach daily limit"
    assert not risk_status.trading_locked, "Should not be locked"
    assert daily_risk_mgr.can_trade(), "Should allow trading"
    assert not lock_mgr.is_locked(), "TradingLockManager should be unlocked"
    print(f"[PASS] Normal scenario: P&L=${unrealized_pnl:,.2f}, can trade")

    # Test 4: Daily limit breach - should lock
    print("\n--- Test 4: Daily Limit Breach (Should Lock) ---")
    daily_risk_mgr.session_realized_pnl = -2500.0  # Already lost $2,500
    unrealized_pnl = -600.0  # Current loss $600
    total_pnl = -3100.0  # Total: -$3,100

    print(f"Setting up breach scenario:")
    print(f"  Realized P&L: ${daily_risk_mgr.session_realized_pnl:,.2f}")
    print(f"  Unrealized P&L: ${unrealized_pnl:,.2f}")
    print(f"  Total P&L: ${total_pnl:,.2f}")
    print(f"  Daily Limit: $3,000.00")

    risk_status = daily_risk_mgr.check_risk(unrealized_pnl)

    print(f"\nAfter check_risk():")
    print(f"  Daily limit breached: {risk_status.daily_limit_breached}")
    print(f"  Trading locked: {risk_status.trading_locked}")
    print(f"  Lock reason: {risk_status.lock_reason}")

    assert risk_status.daily_limit_breached, "Should breach daily limit"
    assert risk_status.trading_locked, "Should be locked"
    assert not daily_risk_mgr.can_trade(), "Should NOT allow trading"

    # CRITICAL: Check TradingLockManager was called
    assert lock_mgr.is_locked(), "TradingLockManager should be LOCKED"
    print("[PASS] Daily limit breached - system locked via TradingLockManager")

    # Test 5: Verify lock persisted to file
    print("\n--- Test 5: Lock Persistence ---")
    assert lock_file.exists(), "Lock file should exist"

    import json
    with open(lock_file, 'r') as f:
        lock_data = json.load(f)

    print(f"Lock file contents:")
    print(f"  trading_locked: {lock_data['trading_locked']}")
    print(f"  lock_reason: {lock_data['lock_reason']}")
    print(f"  daily_pnl_at_lock: ${lock_data['daily_pnl_at_lock']:,.2f}")

    assert lock_data['trading_locked'] == True, "Lock file should show locked"
    print("[PASS] Lock state persisted to file")

    # Test 6: Session reset should unlock
    print("\n--- Test 6: Session Reset (Should Unlock) ---")
    daily_risk_mgr.reset_session()

    assert not daily_risk_mgr.trading_locked, "Internal flag should be unlocked"
    assert daily_risk_mgr.can_trade(), "Should allow trading after reset"
    assert not lock_mgr.is_locked(), "TradingLockManager should be unlocked"
    print("[PASS] Session reset - system unlocked via TradingLockManager")

    # Test 7: Verify unlock persisted to file
    print("\n--- Test 7: Unlock Persistence ---")
    with open(lock_file, 'r') as f:
        lock_data = json.load(f)

    print(f"Lock file after reset:")
    print(f"  trading_locked: {lock_data['trading_locked']}")

    assert lock_data['trading_locked'] == False, "Lock file should show unlocked"
    print("[PASS] Unlock state persisted to file")

    # Cleanup
    if lock_file.exists():
        lock_file.unlink()
        print("\n[OK] Cleaned up lock file")

    print("\n" + "=" * 80)
    print("[SUCCESS] ALL TESTS PASSED")
    print("=" * 80)
    print("\nIntegration verified:")
    print("  1. TradingLockManager can lock/unlock")
    print("  2. DailyRiskManager integrates with TradingLockManager")
    print("  3. Lock state persisted to asset/trading_lock.json")
    print("  4. check_risk() triggers lock when daily limit breached")
    print("  5. Session reset unlocks trading")
    print("  6. can_trade() checks both internal flag AND TradingLockManager")
    print("=" * 80)

    return 0

if __name__ == "__main__":
    try:
        sys.exit(test_trading_lock_integration())
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

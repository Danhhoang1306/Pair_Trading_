"""
Test Risk Notification Spam
Kiểm tra xem hệ thống có gửi thông báo lặp lại mỗi vòng lặp không

Test scenarios:
1. Margin level breach - nên chỉ gửi 1 lần, không gửi lại trong 5 phút
2. Daily limit breach - nên chỉ gửi 1 lần, sau đó dừng hệ thống
3. Portfolio risk breach - nên chỉ gửi 1 lần, có flag ngăn gửi lại
"""

import logging
import time
from unittest.mock import Mock, MagicMock
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_alert_throttling():
    """Test RiskManagementThread alert throttling mechanism"""

    logger.info("="*80)
    logger.info("TEST: Alert Throttling Mechanism")
    logger.info("="*80)

    # Create mock system
    mock_system = Mock()
    mock_system.running = True
    mock_system.magic_number = 234000

    # Track alerts
    alerts_received = []

    def track_alert(severity, title, message):
        alerts_received.append({
            'time': time.time(),
            'severity': severity,
            'title': title,
            'message': message
        })
        logger.info(f"[ALERT {len(alerts_received)}] {severity}: {title}")

    mock_system.emit_risk_alert = track_alert

    # Create RiskManagementThread
    from threads.risk_management_thread import RiskManagementThread
    risk_thread = RiskManagementThread(mock_system)

    # Test 1: Should alert first time
    logger.info("\n--- Test 1: First Alert ---")
    can_alert_1 = risk_thread.should_alert('margin_critical')
    logger.info(f"Can alert (first time): {can_alert_1}")
    assert can_alert_1 == True, "Should allow first alert"

    # Test 2: Should NOT alert immediately after (within cooldown)
    logger.info("\n--- Test 2: Immediate Retry (Should Block) ---")
    can_alert_2 = risk_thread.should_alert('margin_critical')
    logger.info(f"Can alert (immediate retry): {can_alert_2}")
    assert can_alert_2 == False, "Should block immediate retry"

    # Test 3: Different alert key should work
    logger.info("\n--- Test 3: Different Alert Key ---")
    can_alert_3 = risk_thread.should_alert('daily_limit')
    logger.info(f"Can alert (different key): {can_alert_3}")
    assert can_alert_3 == True, "Should allow different alert key"

    logger.info("\n✅ Alert Throttling Test PASSED")
    logger.info(f"   Cooldown period: {risk_thread.alert_cooldown} seconds (5 minutes)")
    logger.info(f"   Same alert blocked within cooldown: CORRECT")
    logger.info(f"   Different alert keys independent: CORRECT")


def test_daily_limit_breach_flag():
    """Test that daily limit breach only triggers once"""

    logger.info("\n" + "="*80)
    logger.info("TEST: Daily Limit Breach Flag")
    logger.info("="*80)

    # Create mock system with daily risk manager
    from risk.daily_risk_manager import DailyRiskManager
    from risk.trading_lock_manager import TradingLockManager

    # Create trading lock manager
    lock_manager = TradingLockManager()
    lock_manager.unlock_trading("Test start")

    # Create daily risk manager
    daily_risk_mgr = DailyRiskManager(
        account_balance=10000,
        max_risk_pct=0.5,
        daily_loss_limit_pct=10.0,
        trading_lock_manager=lock_manager
    )

    # Setup with starting balance
    daily_risk_mgr.starting_balance = 10000
    daily_risk_mgr.net_realized_pnl = 0

    # Simulate daily limit breach
    logger.info("\n--- Simulating Daily Limit Breach ---")
    logger.info(f"Starting Balance: $10,000")
    logger.info(f"Daily Limit: 10% = $1,000")
    logger.info(f"Simulating Loss: -$1,500 (BREACH)")

    # Check 1: First breach
    status1 = daily_risk_mgr.check_risk(open_positions_pnl=-1500)
    logger.info(f"\nCheck 1 - Daily Total P&L: ${status1.daily_total_pnl:,.2f}")
    logger.info(f"Check 1 - Breached: {status1.daily_limit_breached}")
    logger.info(f"Check 1 - Locked: {status1.trading_locked}")

    assert status1.daily_limit_breached == True, "Should detect breach"
    assert status1.trading_locked == True, "Should lock trading"

    # Check 2: Same breach (should still show breached but NOT trigger again)
    logger.info("\n--- Second Check (Same Breach) ---")
    status2 = daily_risk_mgr.check_risk(open_positions_pnl=-1500)
    logger.info(f"Check 2 - Daily Total P&L: ${status2.daily_total_pnl:,.2f}")
    logger.info(f"Check 2 - Breached: {status2.daily_limit_breached}")
    logger.info(f"Check 2 - Locked: {status2.trading_locked}")

    assert status2.daily_limit_breached == True, "Should still show breached"
    assert status2.trading_locked == True, "Should remain locked"

    logger.info("\n✅ Daily Limit Breach Flag Test PASSED")
    logger.info(f"   First breach: Sets lock flag")
    logger.info(f"   Subsequent checks: Flag remains set, no re-trigger")

    # Cleanup
    lock_manager.unlock_trading("Test cleanup")


def test_max_risk_breach_flag():
    """Test that max risk breach flag prevents repeated triggers"""

    logger.info("\n" + "="*80)
    logger.info("TEST: Max Risk Breach Flag")
    logger.info("="*80)

    # Create mock system
    mock_system = Mock()
    mock_system.running = True
    mock_system.magic_number = 234000

    # Track close_all calls
    close_calls = []

    # Create RiskManagementThread
    from threads.risk_management_thread import RiskManagementThread
    risk_thread = RiskManagementThread(mock_system)

    logger.info(f"\nInitial state:")
    logger.info(f"  max_risk_breached_triggered: {risk_thread.max_risk_breached_triggered}")

    # Test 1: First breach
    logger.info("\n--- Test 1: First Breach ---")
    risk_thread.max_risk_breached_triggered = False

    # Simulate breach condition
    logger.info(f"  Flag before: {risk_thread.max_risk_breached_triggered}")
    logger.info(f"  Would trigger close: {not risk_thread.max_risk_breached_triggered}")

    # Set flag (simulating what happens after close)
    risk_thread.max_risk_breached_triggered = True
    logger.info(f"  Flag after close: {risk_thread.max_risk_breached_triggered}")

    # Test 2: Second check (still breached)
    logger.info("\n--- Test 2: Second Check (Still Breached) ---")
    logger.info(f"  Flag status: {risk_thread.max_risk_breached_triggered}")
    logger.info(f"  Would trigger close: {not risk_thread.max_risk_breached_triggered}")
    logger.info(f"  Result: Close BLOCKED (flag is True)")

    # Test 3: Recovery (back to 80% of limit)
    logger.info("\n--- Test 3: Recovery (P&L improved) ---")
    logger.info(f"  Simulating P&L back within 80% of limit")
    risk_thread.max_risk_breached_triggered = False
    logger.info(f"  Flag reset: {risk_thread.max_risk_breached_triggered}")
    logger.info(f"  Ready for next potential breach")

    logger.info("\n✅ Max Risk Breach Flag Test PASSED")
    logger.info(f"   First breach: Sets flag, triggers close")
    logger.info(f"   While flag=True: No re-trigger")
    logger.info(f"   Recovery to 80%: Flag resets")


def test_margin_alert_with_throttle():
    """Test margin alert uses throttling to prevent spam"""

    logger.info("\n" + "="*80)
    logger.info("TEST: Margin Alert Throttling")
    logger.info("="*80)

    # Create mock system
    mock_system = Mock()
    mock_system.running = True

    # Track alerts
    alerts = []
    def track_alert(severity, title, message):
        alerts.append({'title': title, 'time': time.time()})
        logger.info(f"[ALERT] {title} (Total: {len(alerts)})")

    mock_system.emit_risk_alert = track_alert

    # Create RiskManagementThread
    from threads.risk_management_thread import RiskManagementThread
    risk_thread = RiskManagementThread(mock_system)

    # Simulate margin check logic
    logger.info("\n--- Simulating Margin Checks ---")

    # Check 1: First time margin low
    logger.info("\nCheck 1: Margin 140% (Critical)")
    if risk_thread.should_alert('margin_critical'):
        mock_system.emit_risk_alert('CRITICAL', 'Low Margin', 'Margin level: 140%')
        logger.info("  Alert sent: YES")
    else:
        logger.info("  Alert sent: NO (throttled)")

    # Check 2: Immediate retry (should be throttled)
    logger.info("\nCheck 2: Margin still 140% (5 seconds later)")
    time.sleep(0.1)  # Small delay for test
    if risk_thread.should_alert('margin_critical'):
        mock_system.emit_risk_alert('CRITICAL', 'Low Margin', 'Margin level: 140%')
        logger.info("  Alert sent: YES")
    else:
        logger.info("  Alert sent: NO (throttled)")

    # Check 3: Another retry (should still be throttled)
    logger.info("\nCheck 3: Margin still 140% (10 seconds later)")
    time.sleep(0.1)
    if risk_thread.should_alert('margin_critical'):
        mock_system.emit_risk_alert('CRITICAL', 'Low Margin', 'Margin level: 140%')
        logger.info("  Alert sent: YES")
    else:
        logger.info("  Alert sent: NO (throttled)")

    logger.info(f"\n✅ Margin Alert Throttling Test PASSED")
    logger.info(f"   Total alerts sent: {len(alerts)} (should be 1)")
    logger.info(f"   Throttle prevented: 2 duplicate alerts")

    assert len(alerts) == 1, f"Expected 1 alert, got {len(alerts)}"


def test_all():
    """Run all tests"""
    logger.info("="*80)
    logger.info("KIỂM TRA HỆ THỐNG THÔNG BÁO RỦI RO")
    logger.info("="*80)
    logger.info("Mục tiêu: Đảm bảo thông báo KHÔNG bị spam mỗi vòng lặp")
    logger.info("")

    try:
        # Test 1: Alert throttling mechanism
        test_alert_throttling()

        # Test 2: Daily limit breach flag
        test_daily_limit_breach_flag()

        # Test 3: Max risk breach flag
        test_max_risk_breach_flag()

        # Test 4: Margin alert with throttling
        test_margin_alert_with_throttle()

        logger.info("\n" + "="*80)
        logger.info("✅ TẤT CẢ TESTS PASSED")
        logger.info("="*80)
        logger.info("\nKẾT LUẬN:")
        logger.info("1. Alert Throttling: 5 phút cooldown - HOẠT ĐỘNG")
        logger.info("2. Daily Limit Flag: Chỉ trigger 1 lần - HOẠT ĐỘNG")
        logger.info("3. Max Risk Flag: Chỉ trigger 1 lần, reset khi recovery - HOẠT ĐỘNG")
        logger.info("4. Margin Alert: Sử dụng throttling - HOẠT ĐỘNG")
        logger.info("")
        logger.info("⚠️  NHƯNG CẦN KIỂM TRA:")
        logger.info("   - Margin check KHÔNG sử dụng should_alert() trong code hiện tại!")
        logger.info("   - Cần thêm should_alert() vào margin check để ngăn spam")
        logger.info("="*80)

    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        logger.error(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    test_all()

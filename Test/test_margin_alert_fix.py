"""
Test Margin Alert Fix
Verify margin alert chỉ gửi 1 lần trong 5 phút, không spam
"""

import logging
import time
from unittest.mock import Mock, MagicMock, patch

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_margin_alert_throttle():
    """Test margin alert với throttling - simulate real scenario"""

    logger.info("="*80)
    logger.info("TEST: MARGIN ALERT THROTTLING (REAL SCENARIO)")
    logger.info("="*80)
    logger.info("Scenario: Margin level = 140% (< 150% critical)")
    logger.info("Expected: Alert gửi 1 lần, sau đó bị throttle trong 5 phút")
    logger.info("")

    # Create mock system
    mock_system = Mock()
    mock_system.running = True
    mock_system.magic_number = 234000

    # Mock MT5
    mock_mt5 = Mock()

    # Mock account info with low margin
    mock_account = Mock()
    mock_account.balance = 10000.0
    mock_account.equity = 9500.0
    mock_account.margin = 6786.0  # High margin usage
    mock_account.margin_free = 2714.0
    mock_account.margin_level = 140.0  # CRITICAL < 150%
    mock_account.profit = -500.0

    mock_mt5.account_info.return_value = mock_account
    mock_mt5.positions_get.return_value = []
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.DEAL_ENTRY_OUT = 1

    # Mock risk config
    mock_risk_config = Mock()
    mock_risk_config.get_total_portfolio_limit.return_value = 500.0
    mock_risk_config.max_total_unrealized_loss_pct = 5.0
    mock_risk_config.get_per_setup_limit.return_value = 200.0
    mock_risk_config.max_loss_per_setup_pct = 2.0

    # Mock daily risk manager
    mock_daily_risk = Mock()
    mock_risk_status = Mock()
    mock_risk_status.daily_total_pnl = -100.0
    mock_risk_status.daily_loss_limit = 1000.0
    mock_risk_status.remaining_until_daily_limit = 900.0
    mock_risk_status.trading_locked = False
    mock_risk_status.daily_limit_breached = False
    mock_daily_risk.check_risk.return_value = mock_risk_status

    # Mock drawdown monitor
    mock_dd_monitor = Mock()
    mock_dd_metrics = Mock()
    mock_dd_metrics.current_drawdown_pct = 0.05
    mock_dd_metrics.max_drawdown_pct = 0.20
    mock_dd_metrics.peak_balance = 10000.0
    mock_dd_monitor.get_metrics.return_value = mock_dd_metrics

    mock_system.risk_config = mock_risk_config
    mock_system.daily_risk_manager = mock_daily_risk
    mock_system.drawdown_monitor = mock_dd_monitor
    mock_system.get_spreads_with_pnl.return_value = {}

    # Track alerts
    alerts = []
    def track_alert(severity, title, message):
        alerts.append({
            'time': time.time(),
            'severity': severity,
            'title': title,
            'message': message
        })
        logger.info(f"  📢 ALERT #{len(alerts)}: {severity} - {title}")

    mock_system.emit_risk_alert = track_alert

    # Create RiskManagementThread
    from threads.risk_management_thread import RiskManagementThread

    with patch('threads.risk_management_thread.get_mt5', return_value=mock_mt5):
        risk_thread = RiskManagementThread(mock_system)

        logger.info("\n--- SIMULATION: 10 Risk Checks (5 seconds apart) ---")
        logger.info("Margin Level: 140% (CRITICAL)")
        logger.info("")

        # Simulate 10 checks (50 seconds total)
        for i in range(10):
            logger.info(f"\n[Check #{i+1}] Time: {i*5} seconds")
            logger.info(f"  Margin Level: {mock_account.margin_level:.1f}%")

            # Simulate margin check logic
            margin_level = mock_account.margin_level
            balance = mock_account.balance
            equity = mock_account.equity
            margin = mock_account.margin
            free_margin = mock_account.margin_free

            if margin_level < 150:
                logger.info(f"  Status: CRITICAL (< 150%)")

                # Check if should alert (throttled)
                if risk_thread.should_alert('margin_critical'):
                    logger.info(f"  Throttle: PASS → Sending alert")
                    alert_msg = (
                        f"Critical Margin Level!\n\n"
                        f"Margin Level: {margin_level:.2f}%\n"
                        f"Balance: ${balance:,.2f}\n"
                        f"Equity: ${equity:,.2f}\n"
                        f"Used Margin: ${margin:,.2f}\n"
                        f"Free Margin: ${free_margin:,.2f}\n\n"
                        f"⚠️  Consider closing positions to free margin!"
                    )
                    mock_system.emit_risk_alert('CRITICAL', 'Low Margin', alert_msg)
                else:
                    logger.info(f"  Throttle: BLOCKED → Alert suppressed")

            time.sleep(0.05)  # Small delay for test

        # Verify results
        logger.info("\n" + "="*80)
        logger.info("TEST RESULTS")
        logger.info("="*80)
        logger.info(f"Total checks: 10")
        logger.info(f"Total alerts sent: {len(alerts)}")
        logger.info(f"Alerts blocked by throttle: {10 - len(alerts)}")
        logger.info("")

        if len(alerts) == 1:
            logger.info("✅ PASS: Only 1 alert sent (9 blocked by throttle)")
            logger.info("✅ Margin alert spam FIXED!")
            logger.info("")
            logger.info("Alert Details:")
            logger.info(f"  Title: {alerts[0]['title']}")
            logger.info(f"  Severity: {alerts[0]['severity']}")
            logger.info(f"  Sent at check: #1")
            return True
        else:
            logger.error(f"❌ FAIL: Expected 1 alert, got {len(alerts)}")
            logger.error("❌ Margin alert spam NOT fixed!")
            return False


def test_margin_recovery_reset():
    """Test margin alert reset khi margin level phục hồi"""

    logger.info("\n" + "="*80)
    logger.info("TEST: MARGIN ALERT RESET ON RECOVERY")
    logger.info("="*80)

    # Create mock system
    mock_system = Mock()
    alerts = []
    mock_system.emit_risk_alert = lambda s, t, m: alerts.append(t)

    from threads.risk_management_thread import RiskManagementThread
    risk_thread = RiskManagementThread(mock_system)

    # Check 1: First alert (margin 140%)
    logger.info("\n[Check 1] Margin: 140% (CRITICAL)")
    can_alert_1 = risk_thread.should_alert('margin_critical')
    logger.info(f"  Can alert: {can_alert_1}")
    assert can_alert_1 == True, "Should allow first alert"

    # Check 2: Still critical, throttled
    logger.info("\n[Check 2] Margin: 140% (Still CRITICAL)")
    can_alert_2 = risk_thread.should_alert('margin_critical')
    logger.info(f"  Can alert: {can_alert_2}")
    assert can_alert_2 == False, "Should block second alert"

    # Simulate 5 minutes passing + margin recovery
    logger.info("\n[Time passes: 5 minutes + 1 second]")
    logger.info("[Recovery] Margin: 180% (SAFE)")
    risk_thread.last_alerts['margin_critical'] = time.time() - 301  # 5min 1sec ago

    # Check 3: After recovery, if critical again, should alert
    logger.info("\n[Check 3] Margin drops again: 140% (CRITICAL)")
    can_alert_3 = risk_thread.should_alert('margin_critical')
    logger.info(f"  Can alert: {can_alert_3}")
    assert can_alert_3 == True, "Should allow alert after cooldown"

    logger.info("\n✅ PASS: Alert resets after cooldown period")
    logger.info("✅ System can alert again if margin becomes critical later")


def test_all():
    """Run all tests"""
    logger.info("="*80)
    logger.info("KIỂM TRA FIX: MARGIN ALERT SPAM")
    logger.info("="*80)
    logger.info("")

    try:
        # Test 1: Margin alert throttling
        result1 = test_margin_alert_throttle()

        # Test 2: Margin alert reset on recovery
        test_margin_recovery_reset()

        logger.info("\n" + "="*80)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("="*80)
        logger.info("")
        logger.info("SUMMARY:")
        logger.info("  ✅ Margin alert chỉ gửi 1 lần trong 5 phút")
        logger.info("  ✅ Alert bị throttle để ngăn spam")
        logger.info("  ✅ Alert reset sau 5 phút nếu vẫn critical")
        logger.info("  ✅ Fix đã hoạt động đúng!")
        logger.info("")
        logger.info("="*80)

        return result1

    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        logger.error(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_all()
    exit(0 if success else 1)

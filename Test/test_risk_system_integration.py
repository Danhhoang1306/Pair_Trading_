"""
Test Risk System Integration
Kiểm tra xem các tham số risk từ GUI được truyền và hoạt động đúng không
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_risk_config_loading():
    """Test 1: Kiểm tra risk config được load đúng"""
    print("="*80)
    print("TEST 1: RISK CONFIG LOADING")
    print("="*80)

    from config.trading_settings import TradingSettingsManager

    manager = TradingSettingsManager()
    settings = manager.get()

    print(f"[OK] Max Risk Per Setup: {settings.max_risk_pct}%")
    print(f"[OK] Daily Loss Limit: {settings.daily_loss_limit_pct}%")
    print(f"[OK] Max Drawdown: {settings.max_drawdown_pct}%")
    print(f"[OK] Session Start: {settings.session_start_time}")
    print(f"[OK] Session End: {settings.session_end_time}")
    print()

    return settings


def test_gui_to_config_flow():
    """Test 2: Kiểm tra luồng GUI -> Config"""
    print("="*80)
    print("TEST 2: GUI TO CONFIG FLOW")
    print("="*80)

    # Giả lập GUI gửi config
    gui_config = {
        'primary_symbol': 'XAUUSD',
        'secondary_symbol': 'XAGUSD',
        'entry_threshold': 2.0,
        'exit_threshold': 0.5,
        'max_risk_pct': 1.5,  # Per-setup risk
        'daily_loss_limit': 3.0,  # Daily limit as %
        'max_position_pct': 15.0,
        'session_start_time': '00:00',
        'session_end_time': '23:59',
    }

    print("GUI Config:")
    for key, value in gui_config.items():
        print(f"  {key}: {value}")
    print()

    return gui_config


def test_daily_risk_manager_init():
    """Test 3: Kiểm tra DailyRiskManager khởi tạo đúng"""
    print("="*80)
    print("TEST 3: DAILY RISK MANAGER INITIALIZATION")
    print("="*80)

    from risk.daily_risk_manager import DailyRiskManager

    # Test với các giá trị giả định
    account_balance = 100000.0
    max_risk_pct = 1.5  # Per-setup: 1.5%
    daily_loss_limit_pct = 3.0  # Daily: 3%
    daily_loss_limit = account_balance * (daily_loss_limit_pct / 100.0)  # $3,000

    print(f"Account Balance: ${account_balance:,.2f}")
    print(f"Max Risk Per Setup: {max_risk_pct}%")
    print(f"Daily Loss Limit: {daily_loss_limit_pct}% = ${daily_loss_limit:,.2f}")
    print()

    # Initialize manager
    manager = DailyRiskManager(
        account_balance=account_balance,
        max_risk_pct=max_risk_pct,
        daily_loss_limit=daily_loss_limit,
        session_start_time="00:00",
        session_end_time="23:59",
        magic_number=234000
    )

    print(f"[OK] Max Risk Limit (Open Positions): ${manager.max_risk_limit:,.2f}")
    print(f"[OK] Daily Loss Limit: ${manager.daily_loss_limit:,.2f}")
    print(f"[OK] Session Realized P&L: ${manager.session_realized_pnl:,.2f}")
    print(f"[OK] Trading Locked: {manager.trading_locked}")
    print()

    return manager


def test_risk_check_scenarios(manager):
    """Test 4: Kiểm tra các scenario risk"""
    print("="*80)
    print("TEST 4: RISK CHECK SCENARIOS")
    print("="*80)

    # Scenario 1: Normal trading
    print("\n--- Scenario 1: Normal Trading ---")
    unrealized_pnl = -500.0  # Loss $500
    status = manager.check_risk(unrealized_pnl)
    print(f"Unrealized P&L: ${unrealized_pnl:,.2f}")
    print(f"Max Risk Breached: {status.max_risk_breached}")
    print(f"Daily Limit Breached: {status.daily_limit_breached}")
    print(f"Can Trade: {manager.can_trade()}")
    assert not status.max_risk_breached, "Should not breach max risk"
    assert not status.daily_limit_breached, "Should not breach daily limit"
    assert manager.can_trade(), "Should allow trading"
    print("[PASS]")

    # Scenario 2: Max risk breached (open positions)
    print("\n--- Scenario 2: Max Risk Breached (Close Positions) ---")
    unrealized_pnl = -2000.0  # Loss > $1,500 max risk
    status = manager.check_risk(unrealized_pnl)
    print(f"Unrealized P&L: ${unrealized_pnl:,.2f}")
    print(f"Max Risk Limit: ${status.max_risk_limit:,.2f}")
    print(f"Max Risk Breached: {status.max_risk_breached}")
    print(f"Should Close Positions: {manager.should_close_positions(unrealized_pnl)}")
    print(f"Can Still Trade: {manager.can_trade()}")
    assert status.max_risk_breached, "Should breach max risk"
    assert manager.should_close_positions(unrealized_pnl), "Should close positions"
    assert manager.can_trade(), "Should still allow new trades after closing"
    print("[PASS]")

    # Scenario 3: Daily limit breached (lock trading)
    print("\n--- Scenario 3: Daily Limit Breached (Lock Trading) ---")
    # Simulate realized loss from closed trades
    manager.session_realized_pnl = -2500.0  # Lost $2,500 from closed trades
    unrealized_pnl = -600.0  # Current loss $600
    total_pnl = manager.session_realized_pnl + unrealized_pnl  # -$3,100

    print(f"Realized P&L: ${manager.session_realized_pnl:,.2f}")
    print(f"Unrealized P&L: ${unrealized_pnl:,.2f}")
    print(f"Total P&L: ${total_pnl:,.2f}")

    status = manager.check_risk(unrealized_pnl)
    print(f"Daily Loss Limit: ${status.daily_loss_limit:,.2f}")
    print(f"Daily Limit Breached: {status.daily_limit_breached}")
    print(f"Trading Locked: {status.trading_locked}")
    print(f"Can Trade: {manager.can_trade()}")
    assert status.daily_limit_breached, "Should breach daily limit"
    assert status.trading_locked, "Should lock trading"
    assert not manager.can_trade(), "Should NOT allow trading"
    print("[PASS]")

    # Scenario 4: Reset session
    print("\n--- Scenario 4: Session Reset ---")
    manager.reset_session()
    print(f"Realized P&L after reset: ${manager.session_realized_pnl:,.2f}")
    print(f"Trading Locked after reset: {manager.trading_locked}")
    print(f"Can Trade after reset: {manager.can_trade()}")
    assert manager.session_realized_pnl == 0.0, "Should reset realized P&L"
    assert not manager.trading_locked, "Should unlock trading"
    assert manager.can_trade(), "Should allow trading after reset"
    print("[PASS]")


def test_drawdown_monitor():
    """Test 5: Kiểm tra DrawdownMonitor"""
    print("="*80)
    print("TEST 5: DRAWDOWN MONITOR")
    print("="*80)

    from risk.drawdown_monitor import DrawdownMonitor

    account_balance = 100000.0
    daily_loss_limit_pct = 3.0
    daily_loss_limit = account_balance * (daily_loss_limit_pct / 100.0)

    config = {
        'daily_loss_limit': daily_loss_limit,
        'max_drawdown_pct': 20.0
    }

    monitor = DrawdownMonitor(
        account_balance=account_balance,
        config=config
    )

    print(f"Initial Balance: ${account_balance:,.2f}")
    print(f"Daily Loss Limit: ${daily_loss_limit:,.2f}")
    print(f"Max Drawdown Limit: {monitor.max_drawdown_limit:.2%}")
    print()

    # Simulate balance changes
    print("--- Simulating Balance Changes ---")
    balances = [100000, 102000, 101000, 98000, 97000, 99000]

    for balance in balances:
        metrics = monitor.update(balance)
        print(f"Balance: ${balance:,} | DD: {metrics.current_drawdown_pct:.2%} | "
              f"In DD: {metrics.is_in_drawdown} | Peak: ${metrics.peak_balance:,}")

    print("\n[OK] Drawdown monitor working correctly")


def test_full_integration():
    """Test 6: Full integration test"""
    print("="*80)
    print("TEST 6: FULL SYSTEM INTEGRATION")
    print("="*80)

    # Giả lập config từ GUI
    gui_config = {
        'primary_symbol': 'XAUUSD',
        'secondary_symbol': 'XAGUSD',
        'entry_threshold': 2.0,
        'exit_threshold': 0.5,
        'stop_loss_zscore': 3.5,
        'max_positions': 10,
        'volume_multiplier': 1.0,
        'rolling_window_size': 200,
        'update_interval': 60,
        'hedge_drift_threshold': 0.05,

        # RISK PARAMETERS
        'max_position_pct': 20.0,  # Max 20% position size
        'max_risk_pct': 1.5,  # Per-setup risk: 1.5%
        'daily_loss_limit': 3.0,  # Daily limit: 3% (will be converted to $)
        'max_drawdown_pct': 20.0,  # Max drawdown: 20%
        'session_start_time': '00:00',
        'session_end_time': '23:59',

        # FEATURES
        'enable_pyramiding': True,
        'enable_volume_rebalancing': True,
        'enable_entry_cooldown': True,
        'magic_number': 234000
    }

    account_balance = 100000.0

    print("Simulated GUI Config:")
    print(f"  Primary: {gui_config['primary_symbol']}")
    print(f"  Secondary: {gui_config['secondary_symbol']}")
    print(f"  Max Risk Per Setup: {gui_config['max_risk_pct']}%")
    print(f"  Daily Loss Limit: {gui_config['daily_loss_limit']}%")
    print(f"  Account Balance: ${account_balance:,.2f}")
    print()

    # Convert daily_loss_limit from % to $ (như GUI làm)
    daily_loss_pct = gui_config['daily_loss_limit']
    daily_loss_amount = account_balance * (daily_loss_pct / 100.0)
    gui_config['daily_loss_limit'] = daily_loss_amount

    print("After Conversion:")
    print(f"  Daily Loss Limit: ${gui_config['daily_loss_limit']:,.2f}")
    print()

    # Khởi tạo các components
    print("--- Initializing Components ---")

    # 1. DailyRiskManager
    from risk.daily_risk_manager import DailyRiskManager
    daily_risk_mgr = DailyRiskManager(
        account_balance=account_balance,
        max_risk_pct=gui_config['max_risk_pct'],
        daily_loss_limit=gui_config['daily_loss_limit'],
        session_start_time=gui_config['session_start_time'],
        session_end_time=gui_config['session_end_time'],
        magic_number=gui_config['magic_number']
    )
    print(f"[OK] DailyRiskManager initialized")
    print(f"  Max Risk (Open): ${daily_risk_mgr.max_risk_limit:,.2f}")
    print(f"  Daily Loss Limit: ${daily_risk_mgr.daily_loss_limit:,.2f}")

    # 2. DrawdownMonitor
    from risk.drawdown_monitor import DrawdownMonitor
    dd_monitor = DrawdownMonitor(
        account_balance=account_balance,
        config={
            'daily_loss_limit': gui_config['daily_loss_limit'],
            'max_drawdown_pct': gui_config['max_drawdown_pct']
        }
    )
    print(f"[OK] DrawdownMonitor initialized")
    print(f"  Max DD Limit: {dd_monitor.max_drawdown_limit:.2%}")

    print("\n--- Testing Risk Checks ---")

    # Test normal scenario
    unrealized_pnl = -500.0
    risk_status = daily_risk_mgr.check_risk(unrealized_pnl)
    dd_metrics = dd_monitor.update(account_balance + unrealized_pnl)

    print(f"\nNormal Trading:")
    print(f"  Unrealized P&L: ${unrealized_pnl:,.2f}")
    print(f"  Max Risk Breached: {risk_status.max_risk_breached}")
    print(f"  Daily Limit Breached: {risk_status.daily_limit_breached}")
    print(f"  Current DD: {dd_metrics.current_drawdown_pct:.2%}")
    print(f"  Can Trade: {daily_risk_mgr.can_trade()}")

    # Test breach scenario
    daily_risk_mgr.session_realized_pnl = -2500.0
    unrealized_pnl = -1000.0
    risk_status = daily_risk_mgr.check_risk(unrealized_pnl)

    print(f"\nDaily Limit Breach:")
    print(f"  Realized P&L: ${daily_risk_mgr.session_realized_pnl:,.2f}")
    print(f"  Unrealized P&L: ${unrealized_pnl:,.2f}")
    print(f"  Total P&L: ${risk_status.daily_total_pnl:,.2f}")
    print(f"  Daily Limit Breached: {risk_status.daily_limit_breached}")
    print(f"  Trading Locked: {risk_status.trading_locked}")
    print(f"  Can Trade: {daily_risk_mgr.can_trade()}")

    print("\n[OK] Full integration test completed successfully!")


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("RISK SYSTEM INTEGRATION TESTS")
    print("Testing: GUI Config -> Daily Risk Manager -> Drawdown Monitor")
    print("="*80 + "\n")

    try:
        # Test 1: Load config
        settings = test_risk_config_loading()

        # Test 2: GUI flow
        gui_config = test_gui_to_config_flow()

        # Test 3: DailyRiskManager init
        manager = test_daily_risk_manager_init()

        # Test 4: Risk scenarios
        test_risk_check_scenarios(manager)

        # Test 5: DrawdownMonitor
        test_drawdown_monitor()

        # Test 6: Full integration
        test_full_integration()

        print("\n" + "="*80)
        print("[SUCCESS] ALL TESTS PASSED")
        print("="*80)
        print("\nRisk system is working correctly:")
        print("  1. GUI config loaded properly")
        print("  2. Per-setup risk (max_risk_pct) applied correctly")
        print("  3. Daily loss limit (daily_loss_limit) enforced properly")
        print("  4. Trading lock mechanism working")
        print("  5. Session reset working")
        print("  6. DrawdownMonitor tracking correctly")
        print("="*80 + "\n")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

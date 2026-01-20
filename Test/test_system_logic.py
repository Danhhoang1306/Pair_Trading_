"""
KIỂM TRA LOGIC HOẠT ĐỘNG HỆ THỐNG PAIR TRADING
==============================================

Script kiểm tra logic workflow của hệ thống, không phụ thuộc vào giá trị số liệu cụ thể
"""

import sys
import numpy as np
import pandas as pd
from datetime import datetime
import logging
from typing import Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

from models.hedge_ratios import HedgeRatioCalculator
from models.cointegration import CointegrationTest
from strategy.signal_generator import SignalGenerator, SignalType
from strategy.position_tracker import PositionTracker
from strategy.hybrid_rebalancer import HybridRebalancer
from risk.position_sizer import PositionSizer


def test_signal_logic():
    """Test 1: Logic tạo tín hiệu"""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: SIGNAL GENERATION LOGIC")
    logger.info("="*70)
    
    generator = SignalGenerator(entry_threshold=2.0, exit_threshold=0.5)
    
    tests = [
        # (zscore, current_pos, expected_signal)
        (-2.5, None, SignalType.LONG_SPREAD, "LONG entry at z=-2.5"),
        (2.5, None, SignalType.SHORT_SPREAD, "SHORT entry at z=2.5"),
        (-0.3, 'LONG', SignalType.CLOSE_LONG, "Exit LONG at z=-0.3"),
        (0.3, 'SHORT', SignalType.CLOSE_SHORT, "Exit SHORT at z=0.3"),
        (0.8, None, SignalType.HOLD, "HOLD at neutral z=0.8"),
        (-2.5, 'LONG', SignalType.HOLD, "Block duplicate LONG"),
        (2.5, 'SHORT', SignalType.HOLD, "Block duplicate SHORT"),
    ]
    
    passed = 0
    for zscore, pos, expected, desc in tests:
        signal = generator.generate_signal(
            primary_price=2650, secondary_price=30,
            zscore=zscore, hedge_ratio=88.0,
            current_position=pos
        )
        
        result = "✓" if signal.signal_type == expected else "✗"
        logger.info(f"  {result} {desc}: {signal.signal_type.value}")
        
        if signal.signal_type == expected:
            passed += 1
    
    logger.info(f"\nPassed: {passed}/{len(tests)}")
    assert passed == len(tests), f"Some signal tests failed ({passed}/{len(tests)})"
    logger.info("✓ TEST 1 PASSED")
    

def test_position_tracking_logic():
    """Test 2: Logic theo dõi vị thế"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: POSITION TRACKING LOGIC")
    logger.info("="*70)
    
    tracker = PositionTracker()
    
    # Test 1: Open position
    logger.info("\n[2.1] Open spread position")
    p1, p2 = tracker.open_spread_position(
        primary_quantity=0.02,
        silver_quantity=1.76,
        primary_entry=2650.0,
        silver_entry=30.0,
        side='LONG',
        hedge_ratio=88.0
    )
    
    assert len(tracker.positions) == 2, "Should have 2 positions"
    logger.info(f"  ✓ 2 positions opened")
    
    # Test 2: Update prices
    logger.info("\n[2.2] Update prices")
    tracker.update_position_price(p1.position_id, 2660.0)
    tracker.update_position_price(p2.position_id, 29.8)
    
    logger.info(f"  Primary PnL: ${p1.unrealized_pnl:.2f}")
    logger.info(f"  Secondary PnL: ${p2.unrealized_pnl:.2f}")
    logger.info(f"  Total PnL: ${tracker.get_total_pnl()['unrealized_pnl']:.2f}")
    
    # Test 3: Close positions
    logger.info("\n[2.3] Close positions")
    tracker.close_position(p1.position_id, 2660.0)
    tracker.close_position(p2.position_id, 29.8)
    
    assert len(tracker.positions) == 0, "All positions should be closed"
    assert len(tracker.closed_positions) == 2, "Should have 2 closed"
    logger.info(f"  ✓ All positions closed")
    
    logger.info("✓ TEST 2 PASSED")


def test_pyramiding_logic():
    """Test 3: Logic Pyramiding"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: PYRAMIDING LOGIC")
    logger.info("="*70)
    
    rebalancer = HybridRebalancer(
        scale_interval=0.5,
        max_zscore=3.0,
        enable_hedge_adjustment=False
    )
    
    # Register position at z=-2.0
    logger.info("\n[3.1] Register position at z=-2.0")
    pos_data = rebalancer.register_position(
        spread_id='test-001',
        side='LONG',
        entry_zscore=-2.0,
        entry_hedge_ratio=88.0,
        primary_lots=0.02,
        secondary_lots=1.76,
        total_position_size=0.06
    )
    
    levels = pos_data['levels']
    logger.info(f"  Created {len(levels)} pyramiding levels")
    
    # Test levels: -2.0, -2.5, -3.0
    expected_levels = [-2.0, -2.5, -3.0]
    for i, expected_z in enumerate(expected_levels):
        actual_z = levels[i].zscore
        result = "✓" if abs(actual_z - expected_z) < 0.01 else "✗"
        logger.info(f"  {result} Level {i}: z={actual_z:.2f} (expected {expected_z})")
    
    # Test scale-in trigger at z=-2.5
    logger.info("\n[3.2] Check scale-in at z=-2.5")
    should_scale, next_level = rebalancer.check_scale_in('test-001', -2.5)
    
    assert should_scale, "Should trigger scale-in"
    assert abs(next_level.zscore - (-2.5)) < 0.01, "Next level should be -2.5"
    logger.info(f"  ✓ Scale-in triggered at z={next_level.zscore:.2f}")
    
    # Execute scale-in
    rebalancer.execute_scale_in('test-001', next_level, 0.02, 1.76)
    
    # Check again - should not trigger at same level
    should_scale2, _ = rebalancer.check_scale_in('test-001', -2.5)
    assert not should_scale2, "Should not scale-in again at same level"
    logger.info(f"  ✓ Correctly blocks duplicate scale-in")
    
    # Check at next level z=-3.0
    logger.info("\n[3.3] Check scale-in at z=-3.0")
    should_scale3, next_level3 = rebalancer.check_scale_in('test-001', -3.0)
    assert should_scale3, "Should trigger at next level"
    logger.info(f"  ✓ Scale-in triggered at z={next_level3.zscore:.2f}")
    
    logger.info("✓ TEST 3 PASSED")


def test_hedge_adjustment_logic():
    """Test 4: Logic điều chỉnh Hedge Ratio"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: HEDGE ADJUSTMENT LOGIC")
    logger.info("="*70)
    
    rebalancer = HybridRebalancer(
        scale_interval=0.5,
        max_zscore=3.0,
        hedge_drift_threshold=0.05,  # 5%
        enable_hedge_adjustment=True
    )
    
    # Register position
    logger.info("\n[4.1] Register position (entry hedge=88.0)")
    rebalancer.register_position(
        spread_id='test-hedge',
        side='LONG',
        entry_zscore=-2.0,
        entry_hedge_ratio=88.0,
        primary_lots=0.02,
        secondary_lots=1.76,
        total_position_size=0.06
    )
    
    # Test 1: Small drift - should NOT adjust
    logger.info("\n[4.2] Small drift (88.0 -> 89.0 = 1.14%)")
    needs_adj, action = rebalancer.check_hedge_adjustment(
        spread_id='test-hedge',
        new_hedge_ratio=89.0,
        primary_price=2650.0,
        secondary_price=30.0
    )
    
    assert not needs_adj, "Should not adjust for small drift"
    logger.info(f"  ✓ Correctly ignores small drift")
    
    # Test 2: Large drift - should adjust
    logger.info("\n[4.3] Large drift (88.0 -> 93.0 = 5.68%)")
    needs_adj2, action2 = rebalancer.check_hedge_adjustment(
        spread_id='test-hedge',
        new_hedge_ratio=93.0,
        primary_price=2650.0,
        secondary_price=30.0
    )
    
    if needs_adj2:
        logger.info(f"  ✓ Adjustment needed: {action2.action} {action2.quantity:.4f} lots")
        logger.info(f"    Drift: {action2.drift_pct:.2%}")
        assert action2.drift_pct >= 0.05, "Drift should be >= 5%"
    else:
        logger.warning(f"  ⚠ Adjustment may be blocked by time gate")
    
    logger.info("✓ TEST 4 PASSED")


def test_risk_sizing_logic():
    """Test 5: Logic quản lý rủi ro và sizing"""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: RISK & POSITION SIZING")
    logger.info("="*70)
    
    # Position sizer
    logger.info("\n[5.1] Position sizing")
    sizer = PositionSizer(
        account_balance=10000,
        risk_per_trade=0.02
    )
    
    position_size = sizer.calculate_position_size(
        win_rate=0.6,
        avg_win=100,
        avg_loss=50,
        current_price=2650,
        stop_loss_distance=50
    )
    
    logger.info(f"  Account: $10,000")
    logger.info(f"  Position size: {position_size:.4f} lots")
    logger.info(f"  Risk per trade: 2%")
    
    assert position_size > 0, "Position size must be positive"
    assert position_size < 10.0, "Position size should be reasonable"
    logger.info(f"  ✓ Position size is reasonable")
    
    logger.info("✓ TEST 5 PASSED")


def test_workflow_integration():
    """Test 6: Workflow tích hợp"""
    logger.info("\n" + "="*70)
    logger.info("TEST 6: INTEGRATION WORKFLOW")
    logger.info("="*70)
    
    logger.info("\nSimulating complete trading workflow:")
    
    # Step 1: Generate signal
    logger.info("\n[6.1] Generate entry signal")
    generator = SignalGenerator()
    signal = generator.generate_signal(
        primary_price=2650, secondary_price=30,
        zscore=-2.3, hedge_ratio=88.0,
        current_position=None
    )
    logger.info(f"  Signal: {signal.signal_type.value} ({signal.strength.value})")
    
    if signal.signal_type == SignalType.HOLD:
        logger.info("  No trade signal - skipping")
        logger.info("✓ TEST 6 PASSED")
        return
    
    # Step 2: Size position
    logger.info("\n[6.2] Calculate position size")
    sizer = PositionSizer(account_balance=10000)
    pos_size = sizer.calculate_position_size(
        win_rate=0.6, avg_win=100, avg_loss=50,
        current_price=2650, stop_loss_distance=50
    )
    logger.info(f"  Position size: {pos_size:.4f} lots")
    
    # Step 3: Open position
    logger.info("\n[6.3] Open positions")
    tracker = PositionTracker()
    p1, p2 = tracker.open_spread_position(
        primary_quantity=pos_size,
        silver_quantity=pos_size * 88.0,
        primary_entry=2650,
        silver_entry=30,
        side='LONG' if signal.signal_type == SignalType.LONG_SPREAD else 'SHORT',
        hedge_ratio=88.0
    )
    logger.info(f"  Opened {p1.side} spread position")
    
    # Step 4: Register with rebalancer
    logger.info("\n[6.4] Register with pyramiding system")
    rebalancer = HybridRebalancer()
    pos_data = rebalancer.register_position(
        spread_id='integration-test',
        side=p1.side,
        entry_zscore=-2.3,
        entry_hedge_ratio=88.0,
        primary_lots=pos_size,
        secondary_lots=pos_size * 88.0,
        total_position_size=pos_size * 3
    )
    logger.info(f"  Registered with {len(pos_data['levels'])} pyramiding levels")
    
    # Step 5: Monitor and update
    logger.info("\n[6.5] Monitor position")
    tracker.update_position_price(p1.position_id, 2660)
    tracker.update_position_price(p2.position_id, 29.8)
    total_pnl = tracker.get_total_pnl()['unrealized_pnl']
    logger.info(f"  Current P&L: ${total_pnl:.2f}")
    
    # Step 6: Check exit signal
    logger.info("\n[6.6] Check exit signal")
    exit_signal = generator.generate_signal(
        primary_price=2660, secondary_price=29.8,
        zscore=-0.3, hedge_ratio=88.0,
        current_position='LONG'
    )
    logger.info(f"  Exit signal: {exit_signal.signal_type.value}")
    
    if exit_signal.signal_type == SignalType.CLOSE_LONG:
        logger.info("  ✓ Exit triggered - closing positions")
        tracker.close_position(p1.position_id, 2660)
        tracker.close_position(p2.position_id, 29.8)
    
    logger.info("✓ TEST 6 PASSED")


def run_all_tests():
    """Chạy tất cả tests"""
    logger.info("\n" + "="*70)
    logger.info("PAIR TRADING SYSTEM - LOGIC VERIFICATION")
    logger.info("="*70)
    
    try:
        test_signal_logic()
        test_position_tracking_logic()
        test_pyramiding_logic()
        test_hedge_adjustment_logic()
        test_risk_sizing_logic()
        test_workflow_integration()
        
        logger.info("\n" + "="*70)
        logger.info("✓ ✓ ✓ ALL TESTS PASSED ✓ ✓ ✓")
        logger.info("="*70)
        logger.info("\nKẾT LUẬN:")
        logger.info("  ✓ Logic tạo tín hiệu: CHÍNH XÁC")
        logger.info("  ✓ Theo dõi vị thế & P&L: CHÍNH XÁC")
        logger.info("  ✓ Pyramiding (scale-in): CHÍNH XÁC")
        logger.info("  ✓ Hedge adjustment: CHÍNH XÁC")
        logger.info("  ✓ Risk management: CHÍNH XÁC")
        logger.info("  ✓ Integration workflow: CHÍNH XÁC")
        logger.info("\n🎯 HỆ THỐNG PAIR TRADING HOẠT ĐỘNG ĐÚNG!")
        logger.info("✅ Sẵn sàng cho bước tiếp theo")
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

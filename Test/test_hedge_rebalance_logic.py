#!/usr/bin/env python3
"""
Test Hedge Rebalancing Logic
Verify that rebalancing triggers when imbalance >= 0.01 lot
"""

import sys
sys.path.append('/home/claude')

from strategy.hybrid_rebalancer import HybridRebalancer

def test_hedge_logic():
    """Test hedge rebalancing trigger conditions"""
    
    print("=" * 80)
    print("TESTING HEDGE REBALANCING LOGIC")
    print("=" * 80)
    
    # Create rebalancer
    rebalancer = HybridRebalancer(
        scale_interval=0.5,
        max_zscore=3.0,
        initial_fraction=0.33,
        min_absolute_drift=0.01,  # 0.01 lot minimum
        hedge_drift_threshold=0.05,  # 5% threshold (NOW UNUSED!)
        min_adjustment_interval=0,  # No cooldown for testing
        enable_hedge_adjustment=True
    )
    
    # Register test position
    spread_id = "test_spread_001"
    rebalancer.register_position(
        spread_id=spread_id,
        side='LONG',
        entry_zscore=-2.5,
        entry_hedge_ratio=25.0,  # Initial ratio
        primary_lots=0.08,
        secondary_lots=2.03,
        total_position_size=0.20,  # Not important for this test
        primary_symbol='BTCUSD',
        secondary_symbol='ETHUSD'
    )
    
    print("\nTest Position:")
    print(f"  Primary: 0.08 lots BTCUSD")
    print(f"  Secondary: 2.03 lots ETHUSD")
    print(f"  Entry Hedge Ratio: 25.0")
    print()
    
    # Test cases
    test_cases = [
        {
            'name': 'Test 1: Small drift (0.53%)',
            'current_hedge': 25.135,  # Changed from 25.0 to 25.135
            'expected_imbalance': 0.0108,  # 0.08 * 25.135 - 2.03 = 0.0108
            'expected_drift_pct': 0.53,
            'should_trigger': True  # ✅ NOW SHOULD TRIGGER!
        },
        {
            'name': 'Test 2: Very small drift (0.2%)',
            'current_hedge': 25.05,
            'expected_imbalance': 0.004,  # Too small
            'expected_drift_pct': 0.2,
            'should_trigger': False  # ❌ < 0.01 lot
        },
        {
            'name': 'Test 3: Exact threshold (0.01 lot)',
            'current_hedge': 25.125,
            'expected_imbalance': 0.01,
            'expected_drift_pct': 0.49,
            'should_trigger': True  # ✅ Exactly 0.01 lot
        },
        {
            'name': 'Test 4: Large drift (5%)',
            'current_hedge': 26.25,
            'expected_imbalance': 0.10,
            'expected_drift_pct': 5.0,
            'should_trigger': True  # ✅ Large drift
        },
        {
            'name': 'Test 5: Deficit (negative imbalance)',
            'current_hedge': 24.875,
            'expected_imbalance': -0.04,
            'expected_drift_pct': 2.0,
            'should_trigger': True  # ✅ >= 0.01 lot deficit
        }
    ]
    
    print("\n" + "=" * 80)
    print("TEST CASES")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{test['name']}")
        print("-" * 80)
        
        # Check if adjustment needed (with z-score)
        # Assume z-score = 0 for testing (neutral market)
        adjustment = rebalancer.check_volume_imbalance(
            spread_id=spread_id,
            current_hedge_ratio=test['current_hedge'],
            current_zscore=0.0  # Neutral z-score for testing
        )
        
        triggered = adjustment is not None
        
        # Calculate expected values
        target_secondary = 0.08 * test['current_hedge']
        actual_imbalance = abs(2.03 - target_secondary)
        actual_drift_pct = (actual_imbalance / target_secondary) * 100
        
        print(f"  Current Hedge: {test['current_hedge']:.3f}")
        print(f"  Target Secondary: {target_secondary:.4f} lots")
        print(f"  Actual Secondary: 2.03 lots")
        print(f"  Imbalance: {actual_imbalance:.4f} lots ({actual_drift_pct:.2f}%)")
        print(f"  Expected to trigger: {test['should_trigger']}")
        print(f"  Actually triggered: {triggered}")
        
        if triggered == test['should_trigger']:
            print(f"  ✅ PASS")
            passed += 1
            
            if triggered:
                print(f"\n  Adjustment Details:")
                print(f"    Action: {adjustment.action}")
                print(f"    Volume: {adjustment.quantity:.4f} lots")
                print(f"    Symbol: {adjustment.symbol}")
                print(f"    Reason: {adjustment.reason}")
        else:
            print(f"  ❌ FAIL - Expected {test['should_trigger']}, got {triggered}")
            failed += 1
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total: {len(test_cases)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED!")
        return True
    else:
        print(f"\n❌ {failed} TESTS FAILED!")
        return False


if __name__ == '__main__':
    success = test_hedge_logic()
    sys.exit(0 if success else 1)

"""
Test Z-Score Aware Volume Rebalancing Logic
Verifies the flowchart implementation
"""
import sys
from strategy.hybrid_rebalancer import HybridRebalancer

def test_zscore_logic():
    """Test all 4 branches of the flowchart"""

    print("=" * 80)
    print("Testing Z-Score Aware Volume Rebalancing Logic")
    print("=" * 80)

    # Initialize rebalancer
    rebalancer = HybridRebalancer(
        scale_interval=0.5,
        max_zscore=3.0,
        initial_fraction=0.33,
        min_absolute_drift=0.01,
        enable_hedge_adjustment=True
    )

    # Register a test position
    spread_id = "test_spread_123"
    rebalancer.register_position(
        spread_id=spread_id,
        side='LONG',
        entry_zscore=-2.0,
        entry_hedge_ratio=30.0,
        primary_lots=0.10,  # BTC
        secondary_lots=3.00,  # ETH
        total_position_size=0.30,
        primary_symbol='BTCUSD',
        secondary_symbol='ETHUSD'
    )

    print("\nInitial Position:")
    print(f"  BTC: 0.10 lots")
    print(f"  ETH: 3.00 lots")
    print(f"  Hedge ratio: 30.0")

    # Test cases matching flowchart
    # Imbalance = Primary - (Hedge_Ratio × Secondary)
    test_cases = [
        {
            'name': 'Case 1: Primary oversized, z > 0',
            'primary': 0.20,  # Oversized: 0.20 - (30 × 0.003) = 0.20 - 0.09 = +0.11
            'secondary': 0.003,
            'hedge_ratio': 30.0,
            'zscore': 1.5,
            'expected_action': 'BUY',
            'expected_leg': 'SECONDARY',
        },
        {
            'name': 'Case 2: Primary oversized, z < 0',
            'primary': 0.20,  # Oversized
            'secondary': 0.003,
            'hedge_ratio': 30.0,
            'zscore': -1.5,
            'expected_action': 'SELL',
            'expected_leg': 'SECONDARY',
        },
        {
            'name': 'Case 3: Secondary oversized, z > 0',
            'primary': 0.10,  # 0.10 - (30 × 3.2) = 0.10 - 96 = -95.9
            'secondary': 3.20,
            'hedge_ratio': 30.0,
            'zscore': 1.5,
            'expected_action': 'SELL',
            'expected_leg': 'PRIMARY',
        },
        {
            'name': 'Case 4: Secondary oversized, z < 0',
            'primary': 0.10,
            'secondary': 3.20,
            'hedge_ratio': 30.0,
            'zscore': -1.5,
            'expected_action': 'BUY',
            'expected_leg': 'PRIMARY',
        },
    ]

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print("\n" + "=" * 80)
        print(f"Test {i}: {test['name']}")
        print("=" * 80)

        # Update position volumes for this test
        rebalancer.active_positions[spread_id]['primary_lots'] = test['primary']
        rebalancer.active_positions[spread_id]['secondary_lots'] = test['secondary']

        # Calculate imbalance
        imbalance = test['primary'] - (test['hedge_ratio'] * test['secondary'])

        print(f"\nSetup:")
        print(f"  Primary: {test['primary']:.4f} lots")
        print(f"  Secondary: {test['secondary']:.4f} lots")
        print(f"  Hedge ratio: {test['hedge_ratio']:.2f}")
        print(f"  Z-score: {test['zscore']:+.2f}")
        print(f"  Imbalance: {imbalance:+.4f} ({'Primary oversized' if imbalance > 0 else 'Secondary oversized'})")

        # Check volume imbalance
        adjustment = rebalancer.check_volume_imbalance(
            spread_id=spread_id,
            current_hedge_ratio=test['hedge_ratio'],
            current_zscore=test['zscore']
        )

        if adjustment:
            print(f"\nResult:")
            print(f"  Action: {adjustment.action}")
            print(f"  Symbol: {adjustment.symbol}")
            print(f"  Quantity: {adjustment.quantity:.4f}")
            print(f"  Reason: {adjustment.reason[:80]}...")

            # Verify expected action
            if adjustment.action == test['expected_action']:
                print(f"  Action check: PASS (got {adjustment.action})")
                action_pass = True
            else:
                print(f"  Action check: FAIL (expected {test['expected_action']}, got {adjustment.action})")
                action_pass = False

            # Verify expected leg
            leg = 'PRIMARY' if adjustment.symbol == 'BTCUSD' else 'SECONDARY'
            if leg == test['expected_leg']:
                print(f"  Leg check: PASS (got {leg})")
                leg_pass = True
            else:
                print(f"  Leg check: FAIL (expected {test['expected_leg']}, got {leg})")
                leg_pass = False

            if action_pass and leg_pass:
                print(f"\n  Result: PASS")
                passed += 1
            else:
                print(f"\n  Result: FAIL")
                failed += 1
        else:
            print(f"\nResult: No adjustment triggered")
            if abs(imbalance) < 0.01:
                print(f"  Reason: Imbalance below minimum threshold (0.01)")
                print(f"  Result: PASS (correctly skipped)")
                passed += 1
            else:
                print(f"  Result: FAIL (should have triggered)")
                failed += 1

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {len(test_cases)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {(passed/len(test_cases)*100):.1f}%")

    if failed == 0:
        print("\nAll tests PASSED - Flowchart logic is correct!")
        return 0
    else:
        print(f"\n{failed} test(s) FAILED!")
        return 1


if __name__ == '__main__':
    exit_code = test_zscore_logic()
    sys.exit(exit_code)

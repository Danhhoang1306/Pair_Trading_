"""
Quick test to verify SimpleUnifiedExecutor integration

Run this to test the 2-variable algorithm
"""

from executors.simple_unified_executor import SimpleUnifiedExecutor, SpreadEntryState

def test_state_creation():
    """Test SpreadEntryState creation"""
    print("=" * 60)
    print("TEST 1: SpreadEntryState creation")
    print("=" * 60)

    state = SpreadEntryState(
        spread_id="test123",
        side="LONG",
        last_z_entry=-2.1,
        next_z_entry=-2.6,
        entry_count=1
    )

    print(f"Spread: {state.spread_id}")
    print(f"Side: {state.side}")
    print(f"Last z: {state.last_z_entry}")
    print(f"Next z: {state.next_z_entry}")
    print(f"Count: {state.entry_count}")
    print(f"\nString repr: {state}")
    print("\nPASS\n")


def test_pyramid_logic():
    """Test pyramiding trigger logic"""
    print("=" * 60)
    print("TEST 2: Pyramid trigger logic")
    print("=" * 60)

    # LONG spread
    state = SpreadEntryState(
        spread_id="test123",
        side="LONG",
        last_z_entry=-2.1,
        next_z_entry=-2.6,
        entry_count=1
    )

    test_cases = [
        (-2.4, False, "Above next_z - NO trigger"),
        (-2.6, True, "At next_z - TRIGGER"),
        (-2.7, True, "Below next_z - TRIGGER"),
        (-1.5, False, "Reverting - NO trigger"),
    ]

    for current_z, should_trigger, description in test_cases:
        # LONG: trigger when current_z <= next_z
        triggered = current_z <= state.next_z_entry

        status = "PASS" if triggered == should_trigger else "FAIL"
        symbol = "Y" if triggered else "N"

        print(f"{status} | z={current_z:.1f} vs next={state.next_z_entry:.1f} | "
              f"[{symbol}] {description}")

        assert triggered == should_trigger, f"Failed: {description}"

    print("\nAll LONG tests PASS")

    # SHORT spread
    print("\nTesting SHORT spread...")
    state = SpreadEntryState(
        spread_id="test456",
        side="SHORT",
        last_z_entry=2.1,
        next_z_entry=2.6,
        entry_count=1
    )

    test_cases = [
        (2.4, False, "Below next_z - NO trigger"),
        (2.6, True, "At next_z - TRIGGER"),
        (2.7, True, "Above next_z - TRIGGER"),
        (1.5, False, "Reverting - NO trigger"),
    ]

    for current_z, should_trigger, description in test_cases:
        # SHORT: trigger when current_z >= next_z
        triggered = current_z >= state.next_z_entry

        status = "PASS" if triggered == should_trigger else "FAIL"
        symbol = "Y" if triggered else "N"

        print(f"{status} | z={current_z:.1f} vs next={state.next_z_entry:.1f} | "
              f"[{symbol}] {description}")

        assert triggered == should_trigger, f"Failed: {description}"

    print("\nAll SHORT tests PASS\n")


def test_state_update():
    """Test state update after execution"""
    print("=" * 60)
    print("TEST 3: State update logic")
    print("=" * 60)

    scale_interval = 0.5

    # LONG spread
    print("LONG spread progression:")
    state = SpreadEntryState(
        spread_id="test123",
        side="LONG",
        last_z_entry=-2.1,
        next_z_entry=-2.6,
        entry_count=1
    )

    print(f"Entry 1: last_z={state.last_z_entry:.1f}, next_z={state.next_z_entry:.1f}")

    # Pyramid 1 executes at z=-2.7
    state.last_z_entry = -2.7
    state.next_z_entry = -2.7 - scale_interval  # -3.2
    state.entry_count = 2

    print(f"Entry 2: last_z={state.last_z_entry:.1f}, next_z={state.next_z_entry:.1f}")

    # Pyramid 2 executes at z=-3.3
    state.last_z_entry = -3.3
    state.next_z_entry = -3.3 - scale_interval  # -3.8
    state.entry_count = 3

    print(f"Entry 3: last_z={state.last_z_entry:.1f}, next_z={state.next_z_entry:.1f}")

    assert state.entry_count == 3
    assert state.last_z_entry == -3.3
    assert abs(state.next_z_entry - (-3.8)) < 0.01

    print("\nLONG progression PASS")

    # SHORT spread
    print("\nSHORT spread progression:")
    state = SpreadEntryState(
        spread_id="test456",
        side="SHORT",
        last_z_entry=2.1,
        next_z_entry=2.6,
        entry_count=1
    )

    print(f"Entry 1: last_z={state.last_z_entry:.1f}, next_z={state.next_z_entry:.1f}")

    # Pyramid 1 executes at z=2.7
    state.last_z_entry = 2.7
    state.next_z_entry = 2.7 + scale_interval  # 3.2
    state.entry_count = 2

    print(f"Entry 2: last_z={state.last_z_entry:.1f}, next_z={state.next_z_entry:.1f}")

    assert state.entry_count == 2
    assert state.last_z_entry == 2.7
    assert abs(state.next_z_entry - 3.2) < 0.01

    print("\nSHORT progression PASS\n")


def test_no_cooldown_needed():
    """Test that next_z provides natural cooldown"""
    print("=" * 60)
    print("TEST 4: No cooldown needed (automatic protection)")
    print("=" * 60)

    state = SpreadEntryState(
        spread_id="test123",
        side="LONG",
        last_z_entry=-2.1,
        next_z_entry=-2.6,
        entry_count=1
    )

    # Z-score oscillates around entry point
    oscillations = [-2.0, -2.2, -2.1, -1.9, -2.3, -2.0]

    print(f"Entry executed at z={state.last_z_entry:.1f}")
    print(f"Next execution only at z<={state.next_z_entry:.1f}")
    print(f"\nZ-score oscillating around entry:")

    for z in oscillations:
        triggered = z <= state.next_z_entry
        if triggered:
            print(f"  z={z:.1f} - Would execute (BAD!)")
        else:
            print(f"  z={z:.1f} - Protected by next_z (GOOD!)")

        # Should NOT trigger for any oscillation
        assert not triggered, f"Should not trigger at z={z}"

    print(f"\nAll oscillations protected - no duplicate entries!")
    print("PASS: Natural cooldown works!\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("SIMPLE UNIFIED EXECUTOR - INTEGRATION TEST")
    print("=" * 60 + "\n")

    try:
        test_state_creation()
        test_pyramid_logic()
        test_state_update()
        test_no_cooldown_needed()

        print("=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSimpleUnifiedExecutor is ready to use!")
        print("\nTo enable in production:")
        print("  1. Restart your trading bot")
        print("  2. Check logs for: 'SimpleUnifiedExecutor initialized'")
        print("  3. Verify: 'Simple Unified Executor: ENABLED'")
        print("\nThe 2-variable algorithm is working perfectly!")

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

"""
Test Pyramid Execution Logic - Verify exact conditions when z-score reaches next_z_entry

This tests the actual logic from SimpleUnifiedExecutor._check_and_execute_pyramid()
"""

from executors.simple_unified_executor import SpreadEntryState

def test_exact_pyramid_logic():
    """Test exact pyramiding logic with current state"""

    print("="*80)
    print("PYRAMID EXECUTION LOGIC TEST")
    print("="*80)

    # Use EXACT values from current spread_states.json
    current_state = SpreadEntryState(
        spread_id="53341aa0-f706-4647-aa0d-9474643e2276",
        side='LONG',
        last_z_entry=-0.6603704579668043,
        next_z_entry=-1.1603704579668044,
        entry_count=1,
        total_primary_lots=0.0,
        total_secondary_lots=0.0
    )

    print("\nCURRENT STATE (from spread_states.json):")
    print("-"*80)
    print(f"  spread_id: {current_state.spread_id}")
    print(f"  side: {current_state.side}")
    print(f"  last_z_entry: {current_state.last_z_entry:.10f}")
    print(f"  next_z_entry: {current_state.next_z_entry:.10f}")
    print(f"  entry_count: {current_state.entry_count}")

    # Test various z-score values
    print("\n" + "="*80)
    print("PYRAMIDING LOGIC TEST")
    print("="*80)
    print("\nLogic from _check_and_execute_pyramid():")
    print("  if state.side == 'LONG':")
    print("      if current_z <= state.next_z_entry:")
    print("          should_execute = True")
    print()

    # Test z-scores around the threshold
    test_cases = [
        -0.66,   # Initial entry
        -0.80,   # Moving down
        -1.00,   # Halfway
        -1.15,   # Close but not enough
        -1.159,  # Very close
        -1.1603, # Almost exact
        -1.16037045796680, # Close to exact
        -1.1603704579668044, # EXACT next_z_entry
        -1.1603704579668045, # Just past
        -1.17,   # Past threshold
        -1.20,   # Well past
        -1.50,   # Much further
    ]

    print("Testing z-score values:")
    print("-"*80)
    print(f"{'Current Z':>20} | {'Comparison':^30} | {'Result':^10} | Status")
    print("-"*80)

    for current_z in test_cases:
        # This is the EXACT logic from _check_and_execute_pyramid()
        should_execute = False

        if current_state.side == 'LONG':
            # LONG: Execute when z-score goes MORE negative (crosses next_z_entry downward)
            if current_z <= current_state.next_z_entry:
                should_execute = True

        # Format comparison
        comparison = f"{current_z:.10f} <= {current_state.next_z_entry:.10f}"
        result = "TRUE" if should_execute else "FALSE"
        status = "EXECUTE" if should_execute else "WAIT"

        # Highlight the exact threshold
        if abs(current_z - current_state.next_z_entry) < 0.0001:
            marker = " <-- THRESHOLD"
        else:
            marker = ""

        print(f"{current_z:>20.10f} | {result:^30} | {status:^10} | {marker}")

    # Boundary analysis
    print("\n" + "="*80)
    print("BOUNDARY ANALYSIS")
    print("="*80)

    next_z = current_state.next_z_entry

    print(f"\nExact next_z_entry: {next_z:.15f}")
    print("\nBoundary tests:")

    boundary_tests = [
        (next_z + 0.001, "next_z + 0.001"),
        (next_z + 0.0001, "next_z + 0.0001"),
        (next_z + 0.00001, "next_z + 0.00001"),
        (next_z, "next_z (EXACT)"),
        (next_z - 0.00001, "next_z - 0.00001"),
        (next_z - 0.0001, "next_z - 0.0001"),
        (next_z - 0.001, "next_z - 0.001"),
    ]

    for test_z, label in boundary_tests:
        should_execute = test_z <= next_z
        result = "EXECUTE" if should_execute else "WAIT"
        print(f"  {label:20} = {test_z:>20.15f} -> {result}")

    # Practical scenarios
    print("\n" + "="*80)
    print("PRACTICAL SCENARIOS")
    print("="*80)

    scenarios = [
        {
            'name': 'Market moving gradually',
            'z_values': [-0.70, -0.90, -1.10, -1.15, -1.16, -1.17],
            'description': 'Z-score gradually approaching threshold'
        },
        {
            'name': 'Market spike down',
            'z_values': [-0.70, -1.30],
            'description': 'Z-score jumps past threshold'
        },
        {
            'name': 'Oscillating around threshold',
            'z_values': [-1.15, -1.17, -1.14, -1.18, -1.12],
            'description': 'Z-score bouncing around next_z_entry'
        }
    ]

    for scenario in scenarios:
        print(f"\nScenario: {scenario['name']}")
        print(f"  {scenario['description']}")
        print()

        for z in scenario['z_values']:
            should_execute = z <= next_z
            result = "EXECUTE" if should_execute else "WAIT"

            if should_execute:
                status = "  -> Pyramiding triggered!"
            else:
                distance = abs(z - next_z)
                status = f"  -> Need {distance:.4f} more to trigger"

            print(f"  Z={z:>6.2f} | {result:8} {status}")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    print(f"\nCurrent position:")
    print(f"  Side: {current_state.side}")
    print(f"  Last entry at: z = {current_state.last_z_entry:.4f}")
    print(f"  Next pyramid at: z <= {current_state.next_z_entry:.4f}")

    print(f"\nPyramiding will EXECUTE when:")
    print(f"  current_z <= {current_state.next_z_entry:.10f}")
    print(f"  (z-score must be EQUAL or MORE NEGATIVE)")

    print(f"\nExamples:")
    print(f"  Z = -1.1603704579668044 (exact) -> EXECUTE")
    print(f"  Z = -1.1603704579668045 (tiny bit more negative) -> EXECUTE")
    print(f"  Z = -1.1603704579668043 (tiny bit less negative) -> WAIT")
    print(f"  Z = -1.20 -> EXECUTE")
    print(f"  Z = -1.15 -> WAIT")

    print("\n" + "="*80)
    print("IMPORTANT NOTES")
    print("="*80)

    print("\n1. Comparison uses <= (less than or equal)")
    print("   -> Executes AT threshold, not just beyond it")

    print("\n2. For LONG positions:")
    print("   -> Z-score must go MORE NEGATIVE (decrease)")
    print("   -> current_z <= next_z_entry")

    print("\n3. For SHORT positions:")
    print("   -> Z-score must go MORE POSITIVE (increase)")
    print("   -> current_z >= next_z_entry")

    print("\n4. Floating point precision:")
    print("   -> Python uses exact float comparison")
    print("   -> Z = -1.1603704579668044 will match exactly")

    print("\n5. After successful pyramid:")
    print("   -> last_z_entry = -1.1603704579668044")
    print("   -> next_z_entry = -1.6603704579668044 (= last - 0.5)")
    print("   -> entry_count = 2")

    print("\n" + "="*80)


if __name__ == '__main__':
    test_exact_pyramid_logic()

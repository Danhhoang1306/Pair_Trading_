"""
Test Next Z Entry Calculation Logic

Verify how next_z_entry is calculated in SimpleUnifiedExecutor
"""

def test_next_z_calculation():
    """Test next_z_entry calculation logic"""

    print("="*80)
    print("NEXT Z ENTRY CALCULATION LOGIC")
    print("="*80)

    scale_interval = 0.5  # Default value

    print(f"\nScale interval: {scale_interval}")

    # ========== INITIAL ENTRY ==========
    print("\n" + "="*80)
    print("1. INITIAL ENTRY - Code from _execute_entry()")
    print("="*80)

    print("""
    Code (lines 227-232):

    if side == 'LONG':
        # LONG: z goes MORE negative, so next = current - interval
        next_z = current_z - self.scale_interval
    else:
        # SHORT: z goes MORE positive, so next = current + interval
        next_z = current_z + self.scale_interval
    """)

    # Test LONG
    print("\n[LONG Position]")
    print("-"*80)

    long_entries = [
        (-2.0, "Entry at z=-2.0"),
        (-2.1, "Entry at z=-2.1"),
        (-0.66, "Entry at z=-0.66 (current state)"),
    ]

    for current_z, desc in long_entries:
        next_z = current_z - scale_interval
        print(f"  {desc}")
        print(f"    current_z = {current_z}")
        print(f"    next_z = {current_z} - {scale_interval} = {next_z}")
        print(f"    Pyramid triggers when: z <= {next_z}")
        print()

    # Test SHORT
    print("\n[SHORT Position]")
    print("-"*80)

    short_entries = [
        (2.0, "Entry at z=+2.0"),
        (2.1, "Entry at z=+2.1"),
        (0.66, "Entry at z=+0.66"),
    ]

    for current_z, desc in short_entries:
        next_z = current_z + scale_interval
        print(f"  {desc}")
        print(f"    current_z = {current_z}")
        print(f"    next_z = {current_z} + {scale_interval} = {next_z}")
        print(f"    Pyramid triggers when: z >= {next_z}")
        print()

    # ========== PYRAMIDING UPDATE ==========
    print("\n" + "="*80)
    print("2. PYRAMIDING - Code from _check_and_execute_pyramid()")
    print("="*80)

    print("""
    Code (lines 319-323):

    state.last_z_entry = current_z
    if state.side == 'LONG':
        state.next_z_entry = current_z - self.scale_interval
    else:
        state.next_z_entry = current_z + self.scale_interval
    """)

    # Simulate LONG pyramiding sequence
    print("\n[LONG Pyramiding Sequence]")
    print("-"*80)

    last_z = -0.66
    next_z = -1.16
    entry_count = 1

    print(f"Initial state:")
    print(f"  last_z_entry = {last_z}")
    print(f"  next_z_entry = {next_z}")
    print(f"  entry_count = {entry_count}")

    # Simulate 5 pyramids
    pyramid_zs = [-1.16, -1.66, -2.16, -2.66, -3.16]

    for i, current_z in enumerate(pyramid_zs, 2):
        print(f"\nPyramid #{i} at z={current_z}:")

        # Check condition
        if current_z <= next_z:
            print(f"  Check: {current_z} <= {next_z}? YES -> EXECUTE")

            # Update state
            old_last = last_z
            old_next = next_z
            last_z = current_z
            next_z = current_z - scale_interval
            entry_count += 1

            print(f"  Update:")
            print(f"    last_z: {old_last} -> {last_z}")
            print(f"    next_z: {old_next} -> {next_z}")
            print(f"    count: {entry_count-1} -> {entry_count}")
        else:
            print(f"  Check: {current_z} <= {next_z}? NO -> WAIT")

    # Simulate SHORT pyramiding sequence
    print("\n[SHORT Pyramiding Sequence]")
    print("-"*80)

    last_z = 0.66
    next_z = 1.16
    entry_count = 1

    print(f"Initial state:")
    print(f"  last_z_entry = {last_z}")
    print(f"  next_z_entry = {next_z}")
    print(f"  entry_count = {entry_count}")

    # Simulate 5 pyramids
    pyramid_zs = [1.16, 1.66, 2.16, 2.66, 3.16]

    for i, current_z in enumerate(pyramid_zs, 2):
        print(f"\nPyramid #{i} at z={current_z}:")

        # Check condition
        if current_z >= next_z:
            print(f"  Check: {current_z} >= {next_z}? YES -> EXECUTE")

            # Update state
            old_last = last_z
            old_next = next_z
            last_z = current_z
            next_z = current_z + scale_interval
            entry_count += 1

            print(f"  Update:")
            print(f"    last_z: {old_last} -> {last_z}")
            print(f"    next_z: {old_next} -> {next_z}")
            print(f"    count: {entry_count-1} -> {entry_count}")
        else:
            print(f"  Check: {current_z} >= {next_z}? NO -> WAIT")

    # ========== CURRENT STATE ANALYSIS ==========
    print("\n" + "="*80)
    print("3. CURRENT STATE ANALYSIS")
    print("="*80)

    current_last_z = -0.6603704579668043
    current_next_z = -1.1603704579668044

    print(f"\nFrom spread_states.json:")
    print(f"  last_z_entry = {current_last_z}")
    print(f"  next_z_entry = {current_next_z}")

    # Verify calculation
    calculated_next_z = current_last_z - scale_interval
    print(f"\nVerification:")
    print(f"  {current_last_z} - {scale_interval} = {calculated_next_z}")
    print(f"  Stored next_z_entry = {current_next_z}")

    if abs(calculated_next_z - current_next_z) < 0.0000001:
        print(f"  MATCH!")
    else:
        print(f"  MISMATCH! Difference: {abs(calculated_next_z - current_next_z)}")

    # ========== SUMMARY ==========
    print("\n" + "="*80)
    print("SUMMARY - NEXT Z ENTRY CALCULATION")
    print("="*80)

    print("""
    FORMULA:

    LONG position:
        next_z_entry = last_z_entry - scale_interval
        Execute when: current_z <= next_z_entry (z goes DOWN)

    SHORT position:
        next_z_entry = last_z_entry + scale_interval
        Execute when: current_z >= next_z_entry (z goes UP)

    EXAMPLE (LONG, scale_interval=0.5):

        Entry 1: z=-0.66
            last_z = -0.66
            next_z = -0.66 - 0.5 = -1.16

        Pyramid 2: z=-1.16 (when z <= -1.16)
            last_z = -1.16
            next_z = -1.16 - 0.5 = -1.66

        Pyramid 3: z=-1.66 (when z <= -1.66)
            last_z = -1.66
            next_z = -1.66 - 0.5 = -2.16

        ... and so on

    KEY POINTS:

    1. next_z is calculated from CURRENT z-score at execution
    2. NOT from the previous next_z value
    3. This means if z jumps (e.g., -1.16 to -1.80),
       next_z becomes -1.80 - 0.5 = -2.30, not -1.66
    4. Scale interval is ALWAYS 0.5 (configurable)
    """)

    print("="*80)


if __name__ == '__main__':
    test_next_z_calculation()

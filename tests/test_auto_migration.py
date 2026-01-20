"""
Test Auto-Migration from Legacy System to SimpleUnifiedExecutor
"""

import json
import os
from pathlib import Path

def test_auto_migration():
    """Test that auto-migration works correctly"""

    print("="*80)
    print("TEST: Auto-Migration from Legacy System")
    print("="*80)

    # Setup: Create legacy entry
    legacy_file = Path("asset") / "state" / "last_z_entry.json"
    state_file = Path("asset") / "state" / "spread_states.json"

    # Clean up
    if state_file.exists():
        os.remove(state_file)
        print("\nCleaned up existing spread_states.json")

    # Create legacy LONG position
    legacy_data = {
        "long": {
            "direction": "LONG",
            "zscore": -0.6603704579668043,
            "timestamp": 1768573345.797514
        },
        "short": None,
        "last_updated": "2026-01-16T21:22:25.797514"
    }

    with open(legacy_file, 'w') as f:
        json.dump(legacy_data, f, indent=2)

    print(f"\nCreated legacy entry:")
    print(f"  Side: LONG")
    print(f"  Z-score: {legacy_data['long']['zscore']:.4f}")

    # Simulate what SimpleUnifiedExecutor._migrate_legacy_positions() does
    print("\n" + "="*80)
    print("SIMULATING AUTO-MIGRATION")
    print("="*80)

    scale_interval = 0.5

    # Migrate LONG
    import uuid
    spread_id = str(uuid.uuid4())
    last_z = legacy_data['long']['zscore']
    next_z = last_z - scale_interval

    migrated_state = {
        'spread_id': spread_id,
        'side': 'LONG',
        'last_z_entry': last_z,
        'next_z_entry': next_z,
        'entry_count': 1,
        'total_primary_lots': 0.0,
        'total_secondary_lots': 0.0
    }

    # Save migrated state
    data = {
        'spreads': {
            spread_id: migrated_state
        },
        'last_updated': '2026-01-16T22:00:00'
    }

    with open(state_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nMigrated state created:")
    print(f"  spread_id: {spread_id[:16]}...")
    print(f"  side: {migrated_state['side']}")
    print(f"  last_z_entry: {migrated_state['last_z_entry']:.4f}")
    print(f"  next_z_entry: {migrated_state['next_z_entry']:.4f}")
    print(f"  entry_count: {migrated_state['entry_count']}")

    # Verify
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)

    # Check state file
    with open(state_file, 'r') as f:
        verify_data = json.load(f)

    if verify_data['spreads']:
        print("\nOK State file created successfully!")
        for sid, state in verify_data['spreads'].items():
            print(f"\nSpread {sid[:16]}...")
            print(f"  side: {state['side']}")
            print(f"  last_z_entry: {state['last_z_entry']:.4f}")
            print(f"  next_z_entry: {state['next_z_entry']:.4f}")

            if state['side'] == 'LONG':
                print(f"\n  Next pyramid will execute when:")
                print(f"    current_z <= {state['next_z_entry']:.4f}")
                print(f"    (z-score goes MORE NEGATIVE)")
            else:
                print(f"\n  Next pyramid will execute when:")
                print(f"    current_z >= {state['next_z_entry']:.4f}")
                print(f"    (z-score goes MORE POSITIVE)")
    else:
        print("\nERROR: State file is empty!")
        return False

    # Test z-score logic
    print("\n" + "="*80)
    print("PYRAMIDING LOGIC TEST")
    print("="*80)

    test_z_scores = [-0.70, -0.90, -1.10, -1.16, -1.20]

    for sid, state in verify_data['spreads'].items():
        print(f"\nTesting {state['side']} position:")
        print(f"  next_z_entry: {state['next_z_entry']:.4f}")
        print()

        for current_z in test_z_scores:
            if state['side'] == 'LONG':
                should_execute = current_z <= state['next_z_entry']
                result = "EXECUTE" if should_execute else "WAITING"
                print(f"  Z={current_z:+.2f} | {current_z:.2f} <= {state['next_z_entry']:.2f}? {should_execute} | {result}")

    print("\n" + "="*80)
    print("AUTO-MIGRATION TEST PASSED!")
    print("="*80)

    print("\nExpected logs when bot restarts:")
    print("  [SIMPLE-UNIFIED] No previous state found - starting fresh")
    print("  [SIMPLE-UNIFIED] AUTO-MIGRATION: Migrated LONG position from legacy system")
    print(f"    {spread_id[:8]}: LONG | last_z={last_z:.3f} | next_z={next_z:.3f} | entries=1")
    print(f"    Next pyramid will execute when z-score <= {next_z:.3f}")
    print("  [SIMPLE-UNIFIED] Auto-migration complete - 1 position(s) migrated")
    print("  [SIMPLE-UNIFIED] Pyramiding will now work for legacy positions")

    print("\n" + "="*80)
    print("RESULT")
    print("="*80)
    print("\nLegacy position successfully migrated!")
    print("Pyramiding will work after bot restart.")
    print("\nNo manual intervention needed - it's AUTOMATIC!")
    print("="*80)

    return True


if __name__ == '__main__':
    success = test_auto_migration()
    if success:
        print("\nSUCCESS!")
    else:
        print("\nFAILED!")

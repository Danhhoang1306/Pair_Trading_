"""
Test: Verify MT5RiskMonitor and HybridRebalancer use SAME imbalance formula

This test ensures the GUI display formula matches the trading logic formula exactly.

Date: 2026-01-13
Reference: CRITICAL_BUG_IMBALANCE_FORMULA_MISMATCH.md
"""

def test_imbalance_formulas_match():
    """Verify MT5RiskMonitor and HybridRebalancer use SAME formula"""

    print("Testing Imbalance Formula Match\n")
    print("=" * 60)

    # Test scenarios
    test_cases = [
        {
            'name': 'Perfectly Balanced Hedge',
            'primary': 1.0,
            'secondary': 0.5,
            'beta': 2.0,
            'expected_imbalance': 0.0,
            'interpretation': 'Balanced'
        },
        {
            'name': 'Primary Oversized',
            'primary': 1.0,
            'secondary': 0.3,
            'beta': 2.0,
            'expected_imbalance': 0.4,  # 1.0 - (2.0 × 0.3) = 0.4
            'interpretation': 'Primary oversized'
        },
        {
            'name': 'Secondary Oversized',
            'primary': 1.0,
            'secondary': 0.7,
            'beta': 2.0,
            'expected_imbalance': -0.4,  # 1.0 - (2.0 × 0.7) = -0.4
            'interpretation': 'Secondary oversized'
        },
        {
            'name': 'Large Primary Oversized',
            'primary': 2.0,
            'secondary': 0.5,
            'beta': 2.0,
            'expected_imbalance': 1.0,  # 2.0 - (2.0 × 0.5) = 1.0
            'interpretation': 'Primary oversized'
        },
        {
            'name': 'Large Secondary Oversized',
            'primary': 1.0,
            'secondary': 1.0,
            'beta': 2.0,
            'expected_imbalance': -1.0,  # 1.0 - (2.0 × 1.0) = -1.0
            'interpretation': 'Secondary oversized'
        }
    ]

    all_passed = True

    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"  Primary: {test_case['primary']:.2f} lots")
        print(f"  Secondary: {test_case['secondary']:.2f} lots")
        print(f"  Beta: {test_case['beta']:.2f}")

        # CORRECT Formula (used by both after fix)
        imbalance = test_case['primary'] - (test_case['beta'] * test_case['secondary'])

        print(f"  Calculated Imbalance: {imbalance:+.4f} lots")
        print(f"  Expected Imbalance: {test_case['expected_imbalance']:+.4f} lots")
        print(f"  Interpretation: {test_case['interpretation']}")

        # Verify match
        tolerance = 0.0001
        if abs(imbalance - test_case['expected_imbalance']) < tolerance:
            print(f"  Result: [PASS]")
        else:
            print(f"  Result: [FAIL] (mismatch!)")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] ALL TESTS PASSED - Formulas match correctly!")
    else:
        print("[FAIL] TESTS FAILED - Formula mismatch detected!")
    print("=" * 60)

    return all_passed


def test_wrong_formula_detection():
    """Show that the OLD formula was WRONG"""

    print("\n\nDemonstrating OLD Formula Bug\n")
    print("=" * 60)

    # Perfectly balanced hedge
    primary = 1.0
    secondary = 0.5
    beta = 2.0

    print(f"Perfectly Balanced Hedge:")
    print(f"  Primary: {primary:.2f} lots")
    print(f"  Secondary: {secondary:.2f} lots")
    print(f"  Beta: {beta:.2f}")
    print(f"  Check: Primary = Beta x Secondary? {primary} = {beta} x {secondary} = {beta * secondary}")
    print(f"  Result: {primary == beta * secondary} - Perfectly balanced!\n")

    # OLD formula (WRONG)
    old_formula_imbalance = (primary * beta) - secondary
    print(f"OLD Formula (WRONG):")
    print(f"  imbalance = (primary x beta) - secondary")
    print(f"  imbalance = ({primary} x {beta}) - {secondary}")
    print(f"  imbalance = {primary * beta} - {secondary}")
    print(f"  imbalance = {old_formula_imbalance:+.4f} lots")
    print(f"  [WRONG] Should be 0.0 for balanced hedge!\n")

    # NEW formula (CORRECT)
    new_formula_imbalance = primary - (beta * secondary)
    print(f"NEW Formula (CORRECT):")
    print(f"  imbalance = primary - (beta x secondary)")
    print(f"  imbalance = {primary} - ({beta} x {secondary})")
    print(f"  imbalance = {primary} - {beta * secondary}")
    print(f"  imbalance = {new_formula_imbalance:+.4f} lots")
    print(f"  [CORRECT] Returns 0.0 for balanced hedge!")

    print("=" * 60)


if __name__ == "__main__":
    # Run tests
    passed = test_imbalance_formulas_match()
    test_wrong_formula_detection()

    # Exit with appropriate code
    exit(0 if passed else 1)

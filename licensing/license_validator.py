"""
License Validator

For development: Returns True (all features unlocked)
For production: Implement proper validation logic
"""

from typing import Tuple


def validate_license() -> Tuple[bool, str]:
    """
    Validate license

    Returns:
        (is_valid, message)

    For development: Always returns (True, "Development Mode")
    For production: Implement actual validation
    """
    # Development mode - all features unlocked
    return True, "Development Mode - All Features Unlocked"


def require_license():
    """
    Require valid license (decorator/function)

    For development: Does nothing
    For production: Exits if invalid
    """
    is_valid, message = validate_license()
    if not is_valid:
        print(f"❌ License validation failed: {message}")
        import sys
        sys.exit(1)

    print(f"✅ License OK: {message}")

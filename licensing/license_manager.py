"""
License Manager

For development: Mock license manager
For production: Implement actual license management
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Tuple


class LicenseType(Enum):
    """License types"""
    TRIAL = "trial"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    DEVELOPMENT = "development"


@dataclass
class LicenseInfo:
    """License information"""
    license_type: LicenseType
    customer_name: str
    email: str
    issue_date: datetime
    expiry_date: datetime
    max_pairs: int = 999
    max_accounts: int = 999

    def is_valid(self) -> bool:
        """Check if license is still valid"""
        return datetime.now() < self.expiry_date

    def days_remaining(self) -> int:
        """Days until expiration"""
        delta = self.expiry_date - datetime.now()
        return max(0, delta.days)


class LicenseManager:
    """
    License Manager

    For development: Returns mock license
    For production: Implement actual license management
    """

    def __init__(self):
        """Initialize license manager"""
        pass

    def get_license_info(self) -> Optional[LicenseInfo]:
        """
        Get current license information

        For development: Returns development license
        For production: Load from secure storage
        """
        return LicenseInfo(
            license_type=LicenseType.DEVELOPMENT,
            customer_name="Developer",
            email="dev@pairtradingpro.com",
            issue_date=datetime.now(),
            expiry_date=datetime.now() + timedelta(days=365),
            max_pairs=999,
            max_accounts=999
        )

    def activate_license(
        self,
        license_key: str,
        customer_name: str,
        email: str
    ) -> Tuple[bool, str]:
        """
        Activate license

        For development: Always succeeds
        For production: Implement actual activation

        Args:
            license_key: License key from customer
            customer_name: Customer name
            email: Customer email

        Returns:
            (success, message)
        """
        # Development mode - accept any key
        if license_key.startswith("PTP20-"):
            return True, "License activated successfully (Development Mode)"
        else:
            return False, "Invalid license key format"

    def deactivate_license(self) -> bool:
        """
        Deactivate current license

        For development: Does nothing
        For production: Implement deactivation

        Returns:
            Success status
        """
        return True

    def validate_license(self) -> Tuple[bool, str]:
        """
        Validate current license

        For development: Always valid
        For production: Check expiry, signature, etc.

        Returns:
            (is_valid, message)
        """
        info = self.get_license_info()
        if info is None:
            return False, "No license found"

        if not info.is_valid():
            return False, f"License expired on {info.expiry_date.strftime('%Y-%m-%d')}"

        return True, f"License valid ({info.license_type.value.upper()})"


# Global instance
_license_manager: Optional[LicenseManager] = None


def get_license_manager() -> LicenseManager:
    """Get global license manager instance"""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager()
    return _license_manager

"""Lake County Illinois Public Works."""

from .base import MunicipalityBase


class LCPW(MunicipalityBase):
    """Lake County Illinois Public Works."""

    @staticmethod
    def name() -> str:
        """Distinct recognizable name of the municipality."""
        return "Lake County Illinois Public Works"

    @staticmethod
    def timezone() -> str:
        """Return the timezone."""
        return "America/Chicago"

    @staticmethod
    def muni_code() -> str:
        """Return the short hand for this municipality."""
        return "lcpw"

    @staticmethod
    def base_url() -> str:
        """Base URL for itron hosting which differs between municipalities."""
        return "lcpw-p-ia-wb1.itron-hosting.com/AnalyticsCustomerPortal_LCPW_PROD"

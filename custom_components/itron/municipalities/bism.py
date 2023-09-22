"""City Of Bismarck Public Works."""

from .base import MunicipalityBase


class BISM(MunicipalityBase):
    """City Of Bismarck Public Works."""

    @staticmethod
    def name() -> str:
        """Distinct recognizable name of the municipality."""
        return "City Of Bismarck Public Works"

    @staticmethod
    def timezone() -> str:
        """Return the timezone."""
        return "America/Chicago"

    @staticmethod
    def muni_code() -> str:
        """Return the short hand for this municipality."""
        return "bism"

    @staticmethod
    def base_url() -> str:
        """Base URL for itron hosting which differs between municipalities."""
        return "bism-p-ia-wb.itron-hosting.com/AnalyticsCustomerPortal_BISM_PROD"

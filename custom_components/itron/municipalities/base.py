"""Base class that each municipality needs to extend."""


from typing import Any


class MunicipalityBase:
    """Base class that each municipality needs to extend."""

    subclasses: list[type["MunicipalityBase"]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Keep track of all subclass implementations."""
        super().__init_subclass__(**kwargs)
        cls.subclasses.append(cls)

    @staticmethod
    def name() -> str:
        """Distinct recognizable name of the municipality."""
        raise NotImplementedError

    @staticmethod
    def muni_code() -> str:
        """Return the short hand for this municipality."""
        raise NotImplementedError

    @staticmethod
    def timezone() -> str:
        """Return the timezone."""
        raise NotImplementedError

    @staticmethod
    def base_url() -> str:
        """Base URL for itron hosting which differs between municipalities."""
        raise NotImplementedError

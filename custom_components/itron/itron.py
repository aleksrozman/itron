"""Implementation of reverse engineered Itron JSON API."""

# While this integration is present for water, it is inspired by opower and the
# likelihood that gas would be eventually supported and maybe even electricity
# in some municipalties


import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

import aiohttp
import pytz
from aiohttp.client_exceptions import ClientResponseError

from .exceptions import CannotConnect, InvalidAuth
from .municipalities import MunicipalityBase

_LOGGER = logging.getLogger(__file__)
DEBUG_LOG_RESPONSE = False


class MeterType(Enum):
    """Meter type. Electric, gas, or water."""

    ELEC = "ELEC"
    GAS = "GAS"
    WATER = "WATER"
    UNSUPPORTED = "UNSUPPORTED"

    def __str__(self) -> str:
        """Return the value of the enum."""
        return self.value


class UnitOfMeasure(Enum):
    """Unit of measure for the associated meter type. kWh for
    electricity, Therm/CCF for gas, or gallon for water.
    """

    KWH = "KWH"
    THERM = "THERM"
    CCF = "CCF"
    GALLON = "GALLON"
    UNSUPPORTED = "UNSUPPORTED"

    def __str__(self) -> str:
        """Return the value of the enum."""
        return self.value


@dataclass
class ItronCustomer:
    """An itron customer, rarely used."""
    first_name: str
    last_name: str


@dataclass
class ItronCommodity:
    """The commodity to track, storing the type, unit, and flow."""
    type: str
    unit: UnitOfMeasure
    demand: str


@dataclass
class ItronLocation:
    """Meter location."""
    address: str
    city: str
    zip: str


@dataclass
class ItronStatisticsDetailEntry:
    """Raw statistics entry."""
    value: float
    timestamp: datetime


@dataclass
class ItronStatisticsDetail:
    """Aggregate of statistics."""
    weekday: ItronStatisticsDetailEntry
    weekend: ItronStatisticsDetailEntry
    allday: ItronStatisticsDetailEntry


@dataclass
class ItronStatistics:
    """Types of statistics stored."""
    lowest_usage: ItronStatisticsDetail
    highest_usage: ItronStatisticsDetail
    average_usage: ItronStatisticsDetail
    lowest_flow: ItronStatisticsDetail
    highest_flow: ItronStatisticsDetail


@dataclass
class ItronMeter:
    """Information about a particular meter."""
    id_: str
    type: MeterType
    reading: float
    timestamp: datetime
    statistics: ItronStatistics


@dataclass
class ItronUserAccount:
    """Information about the customers account."""
    key: int
    id_: str


@dataclass
class ItronUsageDetail:
    """The lowest level information about usage."""
    timestamp: datetime
    usage: float


@dataclass
class ItronServicePoint:
    """All encompassing information about a meter."""

    # pylint: disable=too-many-instance-attributes
    # Eight is reasonable in this case.

    start_date: datetime  # used for backfills
    id_: str
    timezone: str
    meter: ItronMeter
    location: ItronLocation
    commodity: ItronCommodity
    customer: ItronCustomer
    account: ItronUserAccount


def daterange(start_date, end_date):
    """Iterate between start and end date inclusive."""
    for num in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(num)


def get_supported_utilities() -> list[type["MunicipalityBase"]]:
    """Return a list of all supported utilities."""
    return MunicipalityBase.subclasses


def get_supported_municipality_names() -> list[str]:
    """Return a sorted list of names of all supported utilities."""
    return sorted([municipality.name() for municipality in MunicipalityBase.subclasses])


def select_municipality(name: str) -> type[MunicipalityBase]:
    """Return the municipality with the given name."""
    for municipality in MunicipalityBase.subclasses:
        if name.lower() in [municipality.name().lower(), municipality.__name__.lower()]:
            return municipality
    raise ValueError(f"Municipality {name} not found")


class Itron:
    """Class that can get historical and statistical usage from itron hosting."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        municipality: str,
        username: str,
        password: str,
    ) -> None:
        """Initialize."""
        # Note: Do not modify default headers since Home Assistant that uses this library needs to
        # use a default session for all integrations. Instead specify the headers for each request.
        self.session: aiohttp.ClientSession = session
        self.municipality: type[MunicipalityBase] = select_municipality(
            municipality)
        self.username: str = username
        self.password: str = password
        self.servicepoints: list[ItronServicePoint] = []

    def adjust_timezone(self, timestamp: datetime) -> datetime:
        """Force the timestamp into the timezone of the municipality."""
        return timestamp.replace(tzinfo=pytz.timezone(self.municipality.timezone()))

    def convert_date(self, timestamp: str) -> datetime:
        """Take an ISO string and make a municipality timezone aware datetime object.

        If no string provided, returns the current time as if it was in the timezone
        """
        return self.adjust_timezone(
            datetime.fromisoformat(timestamp) if timestamp else datetime.now()
        )

    def convert_statistics(self, raw_value) -> ItronStatisticsDetail:
        """Helper function to parse statistics."""
        return ItronStatisticsDetail(
            weekday=ItronStatisticsDetailEntry(
                value=raw_value["WeekdayStatistic"]["Value"],
                timestamp=self.convert_date(
                    raw_value["WeekdayStatistic"]["Date"]),
            ),
            weekend=ItronStatisticsDetailEntry(
                value=raw_value["WeekendStatistic"]["Value"],
                timestamp=self.convert_date(
                    raw_value["WeekendStatistic"]["Date"]),
            ),
            allday=ItronStatisticsDetailEntry(
                value=raw_value["AlldayStatistic"]["Value"],
                timestamp=self.convert_date(
                    raw_value["AlldayStatistic"]["Date"]),
            ),
        )

    async def async_login(self) -> None:
        """Login to the website for access.

        :raises InvalidAuth: if login information is incorrect
        :raises CannotConnect: if we receive any HTTP error
        """
        try:
            login = await self.session.post(
                f"https://{self.municipality.base_url()}/PortalServices/api/User/Login",
                json={"username": self.username, "password": self.password},
            )
            if login.status in (401, 403):
                raise InvalidAuth()
            await self._async_get_service_points()

        except ClientResponseError as err:
            if err.status in (401, 403):
                raise InvalidAuth from err
            raise CannotConnect from err

    async def _async_get_service_points(self):
        """Populate service point data that the signed user has access to.

        Effectively the guts of this class, it obtains and converts the JSON data
        into python data classes which can be absorbed by the rest of the system.

        :raises InvalidAuth: if login information is incorrect
        :raises CannotConnect: if we receive any HTTP error
        """
        try:
            current_date = datetime.now().strftime("%m/%d/%y %I:%M:%S %p")
            user_accounts = await self.session.get(
                f"https://{self.municipality.base_url()}/PortalServices/api/Account/UserAccounts"
            )
            for user_account in await user_accounts.json():
                account = ItronUserAccount(
                    key=user_account["AccountKey"], id_=user_account["AccountID"]
                )
                customer = ItronCustomer(
                    first_name=user_account["Customer"]["CustomerFirstName"],
                    last_name=user_account["Customer"]["CustomerLastName"],
                )
                for servicepoint in user_account["ServicePointAccountLinks"]:
                    point = servicepoint["ServicePoint"]
                    assert point["ServicePointMeterLinks"]
                    commodity = ItronCommodity(
                        type=point["CommodityType"],
                        unit=UnitOfMeasure.GALLON
                        if point["CommodityType1"]["UsageUnitID"] == "GAL"
                        else UnitOfMeasure.UNSUPPORTED,
                        demand=point["CommodityType1"]["DemandUnitID"],
                    )
                    location = ItronLocation(
                        address=f"{point['Location']['AddressLine1']} "
                        f"{point['Location']['AddressLine2']}",
                        city=point["Location"]["City"],
                        zip=point["Location"]["PostalCode"],
                    )

                    details = await self.session.request(
                        "get",
                        f"https://{self.municipality.base_url()}/PortalServices/api"
                        f"/UsageData/Bundle/?accountId={account.id_}&"
                        f"servicepointid={point['ServicePointID']}&"
                        f"endDate={current_date}",
                    )
                    bundles = await details.json()
                    for bundle in bundles:
                        assert bundle["ServicePointID"] == point["ServicePointID"]
                        meter = ItronMeter(
                            id_=point["ServicePointMeterLinks"][0]["Meter"][
                                "MeterNumber"
                            ],
                            type=MeterType.WATER
                            if point["CommodityType"] == "Water"
                            else MeterType.UNSUPPORTED,
                            reading=float(
                                bundle["DailyData"]["RecentRegisterRead"][
                                    "DialReadingValue"
                                ]
                            )
                            / pow(
                                10,
                                float(
                                    bundle["DailyData"]["RecentRegisterRead"][
                                        "NumberOfBlackDials"
                                    ]
                                ),
                            ),
                            timestamp=self.convert_date(
                                bundle["DailyData"]["RecentRegisterRead"]["ReadingTime"]),
                            statistics=ItronStatistics(
                                lowest_usage=self.convert_statistics(
                                    raw_value=bundle["DailyData"]["Statistics"]["LowestUsage"]
                                ),
                                highest_usage=self.convert_statistics(
                                    raw_value=bundle["DailyData"]["Statistics"]["HighestUsage"]
                                ),
                                average_usage=self.convert_statistics(
                                    raw_value=bundle["DailyData"]["Statistics"]["AverageUsage"]
                                ),
                                lowest_flow=self.convert_statistics(
                                    raw_value=bundle["DailyData"]["Statistics"]["LowestFlow"]
                                ),
                                highest_flow=self.convert_statistics(
                                    raw_value=bundle["DailyData"]["Statistics"]["HighestFlow"]
                                ),
                            ),
                        )
                        self.servicepoints.append(
                            ItronServicePoint(
                                start_date=self.convert_date(
                                    servicepoint["StartDate"]),
                                id_=point["ServicePointID"],
                                timezone=point["TimeZoneID"],
                                meter=meter,
                                location=location,
                                commodity=commodity,
                                customer=customer,
                                account=account,
                            )
                        )

        except ClientResponseError as err:
            if err.status in (401, 403):
                raise InvalidAuth from err
            raise CannotConnect from err

        assert self.servicepoints

    async def async_get_usage_since(
        self, servicepoint_id: str, timestamp: datetime
    ) -> list[ItronUsageDetail]:
        """Gets all the hourly data from the Usage API since the date provide until now."""
        usages: list[ItronUsageDetail] = []
        try:
            for servicepoint in self.servicepoints:
                for date in daterange(
                    servicepoint.start_date if timestamp is None else timestamp,
                    self.convert_date(None),
                ):
                    usage_request = await self.session.request(
                        "get",
                        f"https://{self.municipality.base_url()}/PortalServices/api"
                        f"/UsageData/Interval?servicePointId={servicepoint_id}&"
                        f"accountId={servicepoint.account.id_}&"
                        f"skipHours=0&takeHours=24&endDate={date.strftime('%Y-%m-%d')}",
                    )
                    usage_details = await usage_request.json()
                    for usage_detail in usage_details:
                        usages.append(
                            ItronUsageDetail(
                                timestamp=self.convert_date(
                                    usage_detail["Date"]),
                                usage=(usage_detail["Usage"] or 0),
                            )
                        )

        except ClientResponseError as err:
            if err.status in (401, 403):
                raise InvalidAuth from err
            raise CannotConnect from err

        return usages

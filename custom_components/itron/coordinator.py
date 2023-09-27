"""Coordinator to handle itron connections."""

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_MUNICIPALITY, DOMAIN, CONF_COST_OPTION
from .exceptions import InvalidAuth
from .itron import Itron, ItronServicePoint, ItronUsageDetail, UnitOfMeasure

_LOGGER = logging.getLogger(__name__)


class ItronCoordinator(DataUpdateCoordinator[dict[str, ItronServicePoint]]):
    """Handle fetching itron data, updating sensors and inserting statistics."""

    cost: float

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the data handler."""
        super().__init__(
            hass,
            _LOGGER,
            name="itron",
            # Data is updated daily on itron.
            # Refresh every 12h to be at most 12h behind.
            update_interval=timedelta(hours=12),
        )

        self.cost = entry.options.get(CONF_COST_OPTION, 1.0) / 1000  # per gallons

        self.api = Itron(
            aiohttp_client.async_get_clientsession(hass),
            entry.data[CONF_MUNICIPALITY],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
        )

    async def _async_update_data(
        self,
    ) -> dict[str, ItronServicePoint]:
        """Fetch data from API endpoint."""

        # pylint: disable=too-many-locals
        # There are multiple statistics connected to each other

        try:
            # Login expires after a few minutes.
            # Given the infrequent updating (every 12h)
            # assume previous session has expired and re-login.
            await self.api.async_login()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err

        for servicepoint in self.api.servicepoints:
            id_prefix = "_".join(
                (
                    self.api.municipality.muni_code(),
                    servicepoint.id_,
                    servicepoint.meter.type.name,
                )
            )
            meter_statistic_id = f"{DOMAIN}:{id_prefix.lower()}_hourly_usage"
            cost_statistic_id = f"{DOMAIN}:{id_prefix.lower()}_hourly_cost"
            _LOGGER.debug(
                "Updating Statistics for %s",
                meter_statistic_id,
            )

            last_stat = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, meter_statistic_id, True, set()
            )
            consumption = 0
            consumption_statistics = []
            cost_statistics = []
            details: list[ItronUsageDetail] = []
            existing_stats = []

            if not last_stat:
                _LOGGER.debug("Updating statistic for the first time")
                details = await self.api.async_get_usage_since(servicepoint.id_, None)

            else:
                _LOGGER.debug("Calculating new consumption")
                # Data is provided sometimes a day ahead but empty, so going back
                # 2 days and grab some extra and we will backfill from 3 days prior
                last_stat_timestamp = self.api.adjust_timezone(
                    datetime.fromtimestamp(last_stat[meter_statistic_id][0]["start"])
                )
                details = await self.api.async_get_usage_since(
                    servicepoint.id_, last_stat_timestamp - timedelta(2)
                )

                existing_stats = await get_instance(self.hass).async_add_executor_job(
                    statistics_during_period,
                    self.hass,
                    last_stat_timestamp - timedelta(3),
                    None,  # from last_stat till now
                    {meter_statistic_id},
                    "hour",
                    None,
                    {"state", "sum"},
                )
                if not existing_stats or not existing_stats[meter_statistic_id]:
                    # This should never happen, we got the timestamp before the stats
                    _LOGGER.error("No old statistics found but time exists")

            sorted_details = sorted(details, key=lambda d: d.timestamp)

            if existing_stats and existing_stats[meter_statistic_id]:
                # Time to synchronize to the old consumption sum so
                # we can take over as they don't always align per hour (upto 12)
                # since the API will return the whole day
                for stat in sorted(
                    existing_stats[meter_statistic_id], key=lambda d: int(d["start"])
                ):
                    if int(stat["start"]) < sorted_details[0].timestamp.timestamp():
                        consumption = float(stat["sum"])
                    else:
                        break

                if consumption == 0:
                    # Also should not happen since we go 1 extra day back
                    _LOGGER.error("Failed to synchronize consumption statistics")

            for detail in sorted_details:
                consumption += detail.usage or 0
                consumption_statistics.append(
                    StatisticData(
                        start=detail.timestamp, state=detail.usage, sum=consumption
                    )
                )
                cost_statistics.append(
                    StatisticData(
                        start=detail.timestamp,
                        state=detail.usage * self.cost,
                        sum=consumption * self.cost,
                    )
                )

            name_prefix = " ".join(
                (
                    "itron",
                    self.api.municipality.muni_code(),
                    servicepoint.id_,
                    servicepoint.meter.type.name,
                )
            )

            if consumption_statistics:
                consumption_metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=f"{name_prefix.lower()} consumption",
                    source=DOMAIN,
                    statistic_id=meter_statistic_id,
                    unit_of_measurement=UnitOfVolume.GALLONS
                    if servicepoint.commodity.unit == UnitOfMeasure.GALLON
                    else UnitOfEnergy.KILO_WATT_HOUR,
                )
                cost_metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=f"{name_prefix.lower()} cost",
                    source=DOMAIN,
                    statistic_id=cost_statistic_id,
                    unit_of_measurement=None,
                )

                async_add_external_statistics(
                    self.hass, consumption_metadata, consumption_statistics
                )
                async_add_external_statistics(self.hass, cost_metadata, cost_statistics)

        return {
            servicepoint.id_: servicepoint for servicepoint in self.api.servicepoints
        }

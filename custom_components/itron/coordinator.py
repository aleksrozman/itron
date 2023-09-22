"""Coordinator to handle itron connections."""

import logging
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, cast

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_MUNICIPALITY, DOMAIN
from .exceptions import InvalidAuth
from .itron import Itron, ItronServicePoint, ItronUsageDetail, UnitOfMeasure

_LOGGER = logging.getLogger(__name__)


class ItronCoordinator(DataUpdateCoordinator[dict[str, ItronServicePoint]]):
    """Handle fetching itron data, updating sensors and inserting statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_data: MappingProxyType[str, Any],
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
        self.api = Itron(
            aiohttp_client.async_get_clientsession(hass),
            entry_data[CONF_MUNICIPALITY],
            entry_data[CONF_USERNAME],
            entry_data[CONF_PASSWORD],
        )

    async def _async_update_data(
        self,
    ) -> dict[str, ItronServicePoint]:
        """Fetch data from API endpoint."""
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
            _LOGGER.debug(
                "Updating Statistics for %s",
                meter_statistic_id,
            )

            last_stat = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, meter_statistic_id, True, set()
            )
            consumption = 0
            consumption_statistics = []
            details: list[ItronUsageDetail] = []

            if not last_stat:
                _LOGGER.debug("Updating statistic for the first time")
                details = await self.api.async_get_usage_since(servicepoint.id_, None)

                for detail in sorted(details, key=lambda d: d.timestamp):
                    consumption += detail.usage or 0
                    consumption_statistics.append(
                        StatisticData(
                            start=detail.timestamp.replace(
                                minute=0, second=0, microsecond=0),  # to be sure
                            state=detail.usage, sum=consumption
                        )
                    )
            else:
                _LOGGER.debug("Calculating consumption")
                # Data is provided sometimes a day ahead but empty, so going back
                # 2 days and grab some extra since we can backfill easily
                last_stat_timestamp = self.api.adjust_timezone(
                    datetime.fromtimestamp(
                        last_stat[meter_statistic_id][0]["start"])
                ) - timedelta(2)
                details = await self.api.async_get_usage_since(
                    servicepoint.id_, last_stat_timestamp
                )

                stats = await get_instance(self.hass).async_add_executor_job(
                    statistics_during_period,
                    self.hass,
                    last_stat_timestamp,
                    None,
                    {meter_statistic_id},
                    "hour",
                    None,
                    {"sum", "state"},
                )
                if stats:  # Fresh
                    consumption = cast(
                        float, stats[meter_statistic_id][0]["sum"])
                    for detail in sorted(details, key=lambda d: d.timestamp):
                        consumption += detail.usage  # count the usage
                        consumption_statistics.append(
                            StatisticData(
                                start=detail.timestamp.replace(
                                    minute=0, second=0, microsecond=0),
                                state=detail.usage,
                                sum=consumption,
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
                    name=f"{name_prefix.lower()} hourly consumption",
                    source=DOMAIN,
                    statistic_id=meter_statistic_id,
                    unit_of_measurement=UnitOfVolume.GALLONS
                    if servicepoint.commodity.unit == UnitOfMeasure.GALLON
                    else UnitOfEnergy.KILO_WATT_HOUR,
                )

            async_add_external_statistics(
                self.hass, consumption_metadata, consumption_statistics
            )

        return {
            servicepoint.id_: servicepoint for servicepoint in self.api.servicepoints
        }

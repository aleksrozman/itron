"""Support for itron sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import pytz
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ItronCoordinator
from .itron import ItronServicePoint, MeterType, UnitOfMeasure


@dataclass
class ItronEntityDescriptionMixin:
    """Mixin values for required keys."""

    value_fn: Callable[[ItronServicePoint], str | float]


@dataclass
class ItronEntityDescription(SensorEntityDescription, ItronEntityDescriptionMixin):
    """Class describing itron sensors entities."""


# suggested_display_precision=0 for all sensors since
# itron provides 0 decimal points for all these.
# (for the statistics in the energy dashboard Opower does provide decimal points)

ELEC_SENSORS: tuple[ItronEntityDescription, ...] = ()
GAS_SENSORS: tuple[ItronEntityDescription, ...] = ()

WATER_SENSORS: tuple[ItronEntityDescription, ...] = (
    ItronEntityDescription(
        key="water_meter_reading",
        name="Last Water Meter Reading",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        suggested_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda data: data.meter.reading,
    ),
    ItronEntityDescription(
        key="average_usage_weekday",
        name="Average Usage Weekdays Over Last 30 Days",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        suggested_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.meter.statistics.average_usage.weekday.value,
    ),
    ItronEntityDescription(
        key="average_usage_weekend",
        name="Average Usage Weekends Over Last 30 Days",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        suggested_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.meter.statistics.average_usage.weekend.value,
    ),
    ItronEntityDescription(
        key="average_usage_all",
        name="Average Usage Over Last 30 Days",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        suggested_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.meter.statistics.average_usage.allday.value,
    ),
    ItronEntityDescription(
        key="highest_usage_all",
        name="Highest Usage Over Last 30 Days",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        suggested_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.meter.statistics.highest_usage.allday.value,
    ),
    ItronEntityDescription(
        key="highest_usage_all_time",
        name="Date Of Highest Usage Over Last 30 Days",
        device_class=SensorDeviceClass.DATE,
        # Timestamps are midnight, so we need to grab the UTC again to get the right date
        value_fn=lambda data: data.meter.statistics.highest_usage.allday.timestamp.astimezone(
            pytz.utc
        ).date(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the itron sensor."""

    coordinator: ItronCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ItronSensor] = []
    servicepoints = coordinator.data.values()
    for servicepoint in servicepoints:
        device_id = f"{coordinator.api.municipality.muni_code()}_{servicepoint.id_}"
        device = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"{servicepoint.meter.type.name} account {servicepoint.account.id_}",
            manufacturer="itron",
            model=coordinator.api.municipality.name(),
            entry_type=DeviceEntryType.SERVICE,
        )
        sensors: tuple[ItronEntityDescription, ...] = ()
        if (
            servicepoint.meter.type == MeterType.WATER
            and servicepoint.commodity.unit == UnitOfMeasure.GALLON
        ):
            sensors = WATER_SENSORS
        elif (
            servicepoint.meter.type == MeterType.GAS
            and servicepoint.commodity.unit in [UnitOfMeasure.THERM, UnitOfMeasure.CCF]
        ):
            sensors = GAS_SENSORS
        elif (
            servicepoint.meter.type == MeterType.ELEC
            and servicepoint.commodity.unit == UnitOfMeasure.KWH
        ):
            sensors = ELEC_SENSORS
        for sensor in sensors:
            entities.append(
                ItronSensor(
                    coordinator,
                    sensor,
                    servicepoint.id_,
                    device,
                    device_id,
                )
            )

    async_add_entities(entities)


class ItronSensor(CoordinatorEntity[ItronCoordinator], SensorEntity):
    """Representation of an itron sensor."""

    entity_description: ItronEntityDescription

    def __init__(
        self,
        coordinator: ItronCoordinator,
        description: ItronEntityDescription,
        municipality_account_id: str,
        device: DeviceInfo,
        device_id: str,
    ) -> None:
        """Initialize the sensor."""

        # pylint: disable=too-many-arguments
        # Contains enough information to describe

        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = device
        self.municipality_account_id = municipality_account_id

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        if self.coordinator.data is not None:
            return self.entity_description.value_fn(
                self.coordinator.data[self.municipality_account_id]
            )
        return None

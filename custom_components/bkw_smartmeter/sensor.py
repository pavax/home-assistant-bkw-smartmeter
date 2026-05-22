"""Sensors for BKW Smart Meter."""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import p1d_window_for_swiss_day
from .const import CONF_METERING_POINT_CODE, DOMAIN, SUGGESTED_DISPLAY_PRECISION
from .coordinator import BkwSmartMeterCoordinator


def _latest_day_period_attributes(data_date: str | None) -> dict[str, str]:
    """Attributes describing which Swiss portal day the latest-day kWh refers to."""
    if not data_date:
        return {}
    try:
        swiss_day = date.fromisoformat(data_date)
    except ValueError:
        return {"data_date": data_date}
    start_utc, stop_utc, start_swiss, stop_swiss = p1d_window_for_swiss_day(
        swiss_day
    )
    return {
        "data_date": data_date,
        "period_start": start_swiss.isoformat(),
        "period_end": stop_swiss.isoformat(),
        "period_start_utc": start_utc.isoformat(),
        "period_end_utc": stop_utc.isoformat(),
    }

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="latest_day",
        translation_key="consumption_latest_day",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=SUGGESTED_DISPLAY_PRECISION,
    ),
    SensorEntityDescription(
        key="total",
        translation_key="consumption_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=SUGGESTED_DISPLAY_PRECISION,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up BKW sensors from a config entry."""
    coordinator: BkwSmartMeterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        BkwConsumptionSensor(coordinator, entry, description)
        for description in SENSOR_TYPES
    )


class BkwConsumptionSensor(CoordinatorEntity[BkwSmartMeterCoordinator], SensorEntity):
    """Representation of a BKW consumption sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BkwSmartMeterCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="BKW Smart Meter",
            manufacturer="BKW",
            model="Energy Monitoring",
            configuration_url="https://my.bkw.ch/energy",
        )
        metering = entry.data.get(CONF_METERING_POINT_CODE, "")
        if metering:
            self._attr_device_info["serial_number"] = metering

    @property
    def available(self) -> bool:
        """Return True if coordinator has data."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        data = self.coordinator.data
        if data is None:
            return None

        key = self.entity_description.key
        if key == "latest_day":
            return data.get("latest_day_kwh")
        if key == "total":
            return data.get("total_kwh")
        return None

    @property
    def last_reset(self) -> datetime | None:
        """Start of the portal day this reading refers to (not “now”)."""
        if self.entity_description.key != "latest_day":
            return None
        data = self.coordinator.data
        if data is None:
            return None
        attrs = _latest_day_period_attributes(data.get("data_date"))
        period_start = attrs.get("period_start")
        if not period_start:
            return None
        return datetime.fromisoformat(period_start)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra state attributes."""
        if self.entity_description.key != "latest_day":
            return {}
        data = self.coordinator.data
        if data is None:
            return {}
        return _latest_day_period_attributes(data.get("data_date"))

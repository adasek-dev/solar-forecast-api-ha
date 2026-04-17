"""Sensor platform for Solar Forecast API."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_NAME, DEFAULT_NAME
from .coordinator import SolarForecastCoordinator, SolarForecastData

_LOGGER = logging.getLogger(__name__)


SENSOR_TYPES: dict[str, dict[str, Any]] = {
    "power_production_now": {
        "name": "Estimated power production - now",
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "enabled": True,
    },
    "energy_production_today": {
        "name": "Estimated energy production - today",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
    },
    "energy_production_tomorrow": {
        "name": "Estimated energy production - tomorrow",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
    },
    "energy_production_today_remaining": {
        "name": "Estimated energy production - remaining today",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
    },
    "energy_next_hour": {
        "name": "Estimated energy production - next hour",
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
    },
    "peak_power_today": {
        "name": "Highest power - today",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": None,
        "unit": UnitOfPower.WATT,
        "enabled": True,
    },
    "peak_time_today": {
        "name": "Peak time - today",
        "icon": "mdi:clock-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled": True,
    },
    "peak_power_tomorrow": {
        "name": "Highest power - tomorrow",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": None,
        "unit": UnitOfPower.WATT,
        "enabled": False,
    },
    "peak_time_tomorrow": {
        "name": "Peak time - tomorrow",
        "icon": "mdi:clock-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled": False,
    },
    "correction_factor": {
        "name": "Correction factor",
        "icon": "mdi:tune",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled": False,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Forecast sensors."""
    coordinator: SolarForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    entities = []
    for sensor_type, config in SENSOR_TYPES.items():
        entities.append(
            SolarForecastSensor(
                coordinator=coordinator,
                entry=entry,
                sensor_type=sensor_type,
                sensor_config=config,
                name_prefix=name,
            )
        )

    async_add_entities(entities)


class SolarForecastSensor(CoordinatorEntity[SolarForecastCoordinator], SensorEntity):
    """Representation of a Solar Forecast sensor."""

    def __init__(
        self,
        coordinator: SolarForecastCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
        sensor_config: dict[str, Any],
        name_prefix: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._sensor_config = sensor_config
        self._entry = entry

        self._attr_name = f"{name_prefix} {sensor_config['name']}"
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_entity_registry_enabled_default = sensor_config["enabled"]

        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Solar Forecast - {name_prefix}",
            "manufacturer": "Solar Forecast API",
            "model": "Custom API",
            "sw_version": "2.2",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        data: SolarForecastData | None = self.coordinator.data
        if data is None:
            return None

        if self._sensor_type == "power_production_now":
            return data.power_now
        elif self._sensor_type == "energy_production_today":
            return data.energy_today
        elif self._sensor_type == "energy_production_tomorrow":
            return data.energy_tomorrow
        elif self._sensor_type == "energy_production_today_remaining":
            return data.energy_remaining_today
        elif self._sensor_type == "energy_next_hour":
            return data.energy_next_hour
        elif self._sensor_type == "peak_power_today":
            return data.peak_power_today
        elif self._sensor_type == "peak_time_today":
            return data.peak_time_today
        elif self._sensor_type == "peak_power_tomorrow":
            return data.peak_power_tomorrow
        elif self._sensor_type == "peak_time_tomorrow":
            return data.peak_time_tomorrow
        elif self._sensor_type == "correction_factor":
            return data.correction

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        data: SolarForecastData | None = self.coordinator.data
        if data is None:
            return None

        # Add hourly forecast as attribute on energy_production_today
        if self._sensor_type == "energy_production_today":
            return {
                "forecast": data.hourly_forecast,
                "watt_hours_day": data.watt_hours_day,
            }

        # Add daily summary on tomorrow sensor
        if self._sensor_type == "energy_production_tomorrow":
            return {
                "watt_hours_day": data.watt_hours_day,
            }

        return None

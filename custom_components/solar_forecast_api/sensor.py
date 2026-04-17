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
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfSpeed,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_STRING_COUNT,
    DEFAULT_NAME,
    conf_string_name,
)
from .coordinator import (
    SolarForecastCoordinator,
    SolarForecastData,
    StringForecastData,
)

_LOGGER = logging.getLogger(__name__)

# ─── Senzory pro výrobu ─────────────────────────────────────────────────────

PRODUCTION_SENSORS: dict[str, dict[str, Any]] = {
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
    # Extra dny (D+2 až D+6)
    "energy_production_d2": {
        "name": "Estimated energy production - day +2",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "day_offset": 2,
    },
    "energy_production_d3": {
        "name": "Estimated energy production - day +3",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "day_offset": 3,
    },
    "energy_production_d4": {
        "name": "Estimated energy production - day +4",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "day_offset": 4,
    },
    "energy_production_d5": {
        "name": "Estimated energy production - day +5",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "day_offset": 5,
    },
    "energy_production_d6": {
        "name": "Estimated energy production - day +6",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "day_offset": 6,
    },
}

# ─── Senzory počasí (jen s API klíčem + feature weather) ─────────────────────

WEATHER_SENSORS: dict[str, dict[str, Any]] = {
    "weather_temperature": {
        "name": "Weather - Temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "enabled": True,
    },
    "weather_sky": {
        "name": "Weather - Sky clarity",
        "icon": "mdi:weather-sunny",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "enabled": True,
    },
    "weather_condition": {
        "name": "Weather - Condition",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled": True,
    },
    "weather_wind_speed": {
        "name": "Weather - Wind speed",
        "icon": "mdi:weather-windy",
        "device_class": SensorDeviceClass.WIND_SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "enabled": True,
    },
    "weather_wind_direction": {
        "name": "Weather - Wind direction",
        "icon": "mdi:compass",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled": True,
    },
}

# ─── Pomocné funkce ──────────────────────────────────────────────────────────

def _get_total_value(data: SolarForecastData, sensor_type: str) -> Any:
    if sensor_type.startswith("energy_production_d"):
        day_offset = PRODUCTION_SENSORS.get(sensor_type, {}).get("day_offset")
        if day_offset is not None:
            return data.energy_for_day(day_offset)
    mapping = {
        "power_production_now": lambda: data.power_now,
        "energy_production_today": lambda: data.energy_today,
        "energy_production_tomorrow": lambda: data.energy_tomorrow,
        "energy_production_today_remaining": lambda: data.energy_remaining_today,
        "energy_next_hour": lambda: data.energy_next_hour,
        "peak_power_today": lambda: data.peak_power_today,
        "peak_time_today": lambda: data.peak_time_today,
        "peak_power_tomorrow": lambda: data.peak_power_tomorrow,
        "peak_time_tomorrow": lambda: data.peak_time_tomorrow,
    }
    getter = mapping.get(sensor_type)
    return getter() if getter else None


def _get_string_value(string_data: StringForecastData, sensor_type: str) -> Any:
    if sensor_type.startswith("energy_production_d"):
        day_offset = PRODUCTION_SENSORS.get(sensor_type, {}).get("day_offset")
        if day_offset is not None:
            return string_data.energy_for_day(day_offset)
    mapping = {
        "power_production_now": lambda: string_data.power_now,
        "energy_production_today": lambda: string_data.energy_today,
        "energy_production_tomorrow": lambda: string_data.energy_tomorrow,
        "energy_production_today_remaining": lambda: string_data.energy_remaining_today,
        "energy_next_hour": lambda: string_data.energy_next_hour,
        "peak_power_today": lambda: string_data.peak_power_today,
        "peak_time_today": lambda: string_data.peak_time_today,
        "peak_power_tomorrow": lambda: string_data.peak_power_tomorrow,
        "peak_time_tomorrow": lambda: string_data.peak_time_tomorrow,
    }
    getter = mapping.get(sensor_type)
    return getter() if getter else None


def _get_weather_value(data: SolarForecastData, sensor_type: str) -> Any:
    if data.weather is None:
        return None
    w = data.weather
    mapping = {
        "weather_temperature": lambda: w.temperature_now,
        "weather_sky": lambda: round(w.sky_now * 100) if w.sky_now is not None else None,
        "weather_condition": lambda: w.condition_now,
        "weather_wind_speed": lambda: w.wind_speed_now,
        "weather_wind_direction": lambda: w.wind_direction_now,
    }
    getter = mapping.get(sensor_type)
    return getter() if getter else None


# ─── Setup ──────────────────────────────────────────────────────────────────

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Forecast sensors."""
    coordinator: SolarForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    string_count = entry.data.get(CONF_STRING_COUNT, 0)

    entities: list[SensorEntity] = []

    # ── Celkové (součtové) senzory ──
    for sensor_type, config in PRODUCTION_SENSORS.items():
        entities.append(
            SolarForecastTotalSensor(coordinator, entry, sensor_type, config, name)
        )

    # ── Per-string senzory ──
    if string_count >= 1:
        for i in range(1, string_count + 1):
            string_label = entry.data.get(conf_string_name(i), f"String {i}")
            for sensor_type, config in PRODUCTION_SENSORS.items():
                entities.append(
                    SolarForecastStringSensor(
                        coordinator, entry, sensor_type, config, name, string_label, i - 1
                    )
                )
    elif not string_count:
        legacy_strings = coordinator._get_strings()
        if len(legacy_strings) > 1:
            for idx, s_cfg in enumerate(legacy_strings):
                for sensor_type, config in PRODUCTION_SENSORS.items():
                    entities.append(
                        SolarForecastStringSensor(
                            coordinator, entry, sensor_type, config, name, s_cfg["name"], idx
                        )
                    )

    # ── Počasí senzory ──
    for sensor_type, config in WEATHER_SENSORS.items():
        entities.append(
            SolarForecastWeatherSensor(coordinator, entry, sensor_type, config, name)
        )

    # ── Horizont senzor ──
    entities.append(SolarForecastHorizonSensor(coordinator, entry, name))

    async_add_entities(entities)


# ─── Base class ─────────────────────────────────────────────────────────────

class _SolarForecastBase(CoordinatorEntity[SolarForecastCoordinator], SensorEntity):
    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix):
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._entry = entry
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_entity_registry_enabled_default = sensor_config["enabled"]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Solar Forecast - {name_prefix}",
            "manufacturer": "Solar Forecast API",
            "model": "forecast.xnas.cz",
            "sw_version": "1.3.0",
        }


# ─── Celkové senzory ────────────────────────────────────────────────────────

class SolarForecastTotalSensor(_SolarForecastBase):
    """Total (sum of all strings) production sensor."""

    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix):
        super().__init__(coordinator, entry, sensor_type, sensor_config, name_prefix)
        self._attr_name = f"{name_prefix} {sensor_config['name']}"
        self._attr_unique_id = f"{entry.entry_id}_total_{sensor_type}"

    @property
    def native_value(self) -> Any:
        data: SolarForecastData | None = self.coordinator.data
        if data is None:
            return None
        return _get_total_value(data, self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data: SolarForecastData | None = self.coordinator.data
        if data is None:
            return None
        if self._sensor_type == "energy_production_today":
            return {
                "forecast": data.hourly_forecast,
                "watt_hours_day": data.watt_hours_day,
                "correction": data.correction,
            }
        if self._sensor_type == "energy_production_tomorrow":
            return {"watt_hours_day": data.watt_hours_day}
        return None


# ─── Per-string senzory ─────────────────────────────────────────────────────

class SolarForecastStringSensor(_SolarForecastBase):
    """Sensor for a single string."""

    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix, string_label, string_index):
        super().__init__(coordinator, entry, sensor_type, sensor_config, name_prefix)
        self._string_index = string_index
        self._attr_name = f"{name_prefix} {string_label} {sensor_config['name']}"
        self._attr_unique_id = f"{entry.entry_id}_str{string_index}_{sensor_type}"

    @property
    def native_value(self) -> Any:
        data: SolarForecastData | None = self.coordinator.data
        if data is None or self._string_index >= len(data.strings):
            return None
        return _get_string_value(data.strings[self._string_index], self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data: SolarForecastData | None = self.coordinator.data
        if data is None or self._string_index >= len(data.strings):
            return None
        sd = data.strings[self._string_index]
        if self._sensor_type == "energy_production_today":
            return {
                "forecast": sd.hourly_forecast,
                "watt_hours_day": sd.watt_hours_day,
                "correction": sd.correction,
                "actual_calibration": sd.actual_info,
            }
        if self._sensor_type == "energy_production_tomorrow":
            return {"watt_hours_day": sd.watt_hours_day}
        return None


# ─── Počasí senzory ─────────────────────────────────────────────────────────

class SolarForecastWeatherSensor(_SolarForecastBase):
    """Weather forecast sensor (requires API key with weather feature)."""

    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix):
        super().__init__(coordinator, entry, sensor_type, sensor_config, name_prefix)
        self._attr_name = f"{name_prefix} {sensor_config['name']}"
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"

    @property
    def available(self) -> bool:
        data: SolarForecastData | None = self.coordinator.data
        return data is not None and data.weather is not None

    @property
    def native_value(self) -> Any:
        data: SolarForecastData | None = self.coordinator.data
        if data is None:
            return None
        return _get_weather_value(data, self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data: SolarForecastData | None = self.coordinator.data
        if data is None or data.weather is None:
            return None
        if self._sensor_type == "weather_condition":
            # Vrátit celou předpověď jako atribut
            return {"forecast": data.weather.entries}
        return None


# ─── Horizont senzor ────────────────────────────────────────────────────────

class SolarForecastHorizonSensor(CoordinatorEntity[SolarForecastCoordinator], SensorEntity):
    """Sensor showing horizon obstruction data."""

    def __init__(self, coordinator, entry, name_prefix):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = f"{name_prefix} Horizon - Max elevation"
        self._attr_unique_id = f"{entry.entry_id}_horizon"
        self._attr_icon = "mdi:image-filter-hdr"
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_unit_of_measurement = "°"
        self._attr_entity_registry_enabled_default = False  # defaultně skrytý
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Solar Forecast - {name_prefix}",
            "manufacturer": "Solar Forecast API",
            "model": "forecast.xnas.cz",
            "sw_version": "1.3.0",
        }

    @property
    def available(self) -> bool:
        data: SolarForecastData | None = self.coordinator.data
        return data is not None and data.horizon is not None

    @property
    def native_value(self) -> Any:
        data: SolarForecastData | None = self.coordinator.data
        if data is None or data.horizon is None:
            return None
        return data.horizon.get("max_elevation")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data: SolarForecastData | None = self.coordinator.data
        if data is None or data.horizon is None:
            return None
        h = data.horizon
        return {
            "mean_elevation": h.get("mean_elevation"),
            "azimuth": h.get("horizon", {}).get("azimuth"),
            "elevation": h.get("horizon", {}).get("elevation"),
        }

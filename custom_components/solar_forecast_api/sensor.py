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
    CONF_DAYS,
    CONF_API_FEATURES,
    DEFAULT_NAME,
    FEATURE_WEATHER,
    CONF_FEATURE_WEATHER,
    CONF_FEATURE_ACTUAL,
    CONF_FEATURE_CALIBRATION,
    CONF_FEATURE_TIMEWINDOWS,
    conf_string_name,
)
from .coordinator import (
    SolarForecastCoordinator,
    SolarForecastData,
    StringForecastData,
)

_LOGGER = logging.getLogger(__name__)

# ─── Sensor definitions ─────────────────────────────────────────────────────

PRODUCTION_SENSORS: dict[str, dict[str, Any]] = {
    "power_production_now": {
        "name": "Estimated power production - now",
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "enabled": True,
        "min_days": 1,
    },
    "energy_production_today": {
        "name": "Estimated energy production - today",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
        "min_days": 1,
    },
    "energy_production_today_remaining": {
        "name": "Estimated energy production - remaining today",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
        "min_days": 1,
    },
    "energy_next_hour": {
        "name": "Estimated energy production - next hour",
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
        "min_days": 1,
    },
    "peak_power_today": {
        "name": "Highest power - today",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": None,
        "unit": UnitOfPower.WATT,
        "enabled": True,
        "min_days": 1,
    },
    "peak_time_today": {
        "name": "Peak time - today",
        "icon": "mdi:clock-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled": True,
        "min_days": 1,
    },
    # ── Requires days >= 2 ──
    "energy_production_tomorrow": {
        "name": "Estimated energy production - tomorrow",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": True,
        "min_days": 2,
    },
    "peak_power_tomorrow": {
        "name": "Highest power - tomorrow",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": None,
        "unit": UnitOfPower.WATT,
        "enabled": False,
        "min_days": 2,
    },
    "peak_time_tomorrow": {
        "name": "Peak time - tomorrow",
        "icon": "mdi:clock-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled": False,
        "min_days": 2,
    },
    # ── Extra days ──
    "energy_production_d2": {
        "name": "Estimated energy production - day +2",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "min_days": 3,
        "day_offset": 2,
    },
    "energy_production_d3": {
        "name": "Estimated energy production - day +3",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "min_days": 4,
        "day_offset": 3,
    },
    "energy_production_d4": {
        "name": "Estimated energy production - day +4",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "min_days": 5,
        "day_offset": 4,
    },
    "energy_production_d5": {
        "name": "Estimated energy production - day +5",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "min_days": 6,
        "day_offset": 5,
    },
    "energy_production_d6": {
        "name": "Estimated energy production - day +6",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled": False,
        "min_days": 7,
        "day_offset": 6,
    },
}

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


# ─── Value getters ────────────────────────────────────────────────────────────

def _total_value(data: SolarForecastData, sensor_type: str) -> Any:
    day_offset = PRODUCTION_SENSORS.get(sensor_type, {}).get("day_offset")
    if day_offset is not None:
        return data.energy_for_day(day_offset)
    return {
        "power_production_now": lambda: data.power_now,
        "energy_production_today": lambda: data.energy_today,
        "energy_production_tomorrow": lambda: data.energy_tomorrow,
        "energy_production_today_remaining": lambda: data.energy_remaining_today,
        "energy_next_hour": lambda: data.energy_next_hour,
        "peak_power_today": lambda: data.peak_power_today,
        "peak_time_today": lambda: data.peak_time_today,
        "peak_power_tomorrow": lambda: data.peak_power_tomorrow,
        "peak_time_tomorrow": lambda: data.peak_time_tomorrow,
    }.get(sensor_type, lambda: None)()


def _string_value(sd: StringForecastData, sensor_type: str) -> Any:
    day_offset = PRODUCTION_SENSORS.get(sensor_type, {}).get("day_offset")
    if day_offset is not None:
        return sd.energy_for_day(day_offset)
    return {
        "power_production_now": lambda: sd.power_now,
        "energy_production_today": lambda: sd.energy_today,
        "energy_production_tomorrow": lambda: sd.energy_tomorrow,
        "energy_production_today_remaining": lambda: sd.energy_remaining_today,
        "energy_next_hour": lambda: sd.energy_next_hour,
        "peak_power_today": lambda: sd.peak_power_today,
        "peak_time_today": lambda: sd.peak_time_today,
        "peak_power_tomorrow": lambda: sd.peak_power_tomorrow,
        "peak_time_tomorrow": lambda: sd.peak_time_tomorrow,
    }.get(sensor_type, lambda: None)()


def _weather_value(data: SolarForecastData, sensor_type: str) -> Any:
    if data.weather is None:
        return None
    w = data.weather
    return {
        "weather_temperature": lambda: w.temperature_now,
        "weather_sky": lambda: round(w.sky_now * 100) if w.sky_now is not None else None,
        "weather_condition": lambda: w.condition_now,
        "weather_wind_speed": lambda: w.wind_speed_now,
        "weather_wind_direction": lambda: w.wind_direction_now,
    }.get(sensor_type, lambda: None)()


def _device_info(entry: ConfigEntry, name_prefix: str) -> dict:
    """Build device info with feature list as model info."""
    ecfg = {**entry.data, **entry.options}
    features = ecfg.get(CONF_API_FEATURES, [])
    days = ecfg.get(CONF_DAYS, 1)
    has_key = bool(ecfg.get("api_key", ""))

    if has_key and features:
        model_info = f"forecast.xnas.cz | {days}d | {', '.join(features)}"
    elif has_key:
        model_info = f"forecast.xnas.cz | {days}d | klíč bez funkcí"
    else:
        model_info = "forecast.xnas.cz | 1d | bez API klíče"

    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": f"Solar Forecast - {name_prefix}",
        "manufacturer": "Solar Forecast API",
        "model": model_info,
        "sw_version": "1.5.0",
        "configuration_url": "https://forecast.xnas.cz",
    }


# ─── Setup ──────────────────────────────────────────────────────────────────

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SolarForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Always merge data + options – options flow stores everything in entry.options
    cfg = {**entry.data, **entry.options}
    name = cfg.get(CONF_NAME, DEFAULT_NAME)
    string_count = cfg.get(CONF_STRING_COUNT, 1)
    configured_days = cfg.get(CONF_DAYS, 1)
    api_features = cfg.get(CONF_API_FEATURES, [])
    # Respect per-feature toggles (user can disable even available features)
    has_weather = (FEATURE_WEATHER in api_features and
                   cfg.get(CONF_FEATURE_WEATHER, True))

    entities: list[SensorEntity] = []

    # ── Total sensors (always created, filtered by min_days) ──
    for sensor_type, cfg in PRODUCTION_SENSORS.items():
        if configured_days >= cfg.get("min_days", 1):
            entities.append(SolarForecastTotalSensor(
                coordinator, entry, sensor_type, cfg, name
            ))

    # ── Per-string sensors (only if more than 1 string) ──
    if string_count > 1:
        for i in range(1, string_count + 1):
            string_label = cfg.get(conf_string_name(i), f"String {i}")
            for sensor_type, cfg in PRODUCTION_SENSORS.items():
                if configured_days >= cfg.get("min_days", 1):
                    entities.append(SolarForecastStringSensor(
                        coordinator, entry, sensor_type, cfg, name, string_label, i - 1
                    ))

    # ── Weather sensors (only if API key has weather feature) ──
    if has_weather:
        for sensor_type, cfg in WEATHER_SENSORS.items():
            entities.append(SolarForecastWeatherSensor(
                coordinator, entry, sensor_type, cfg, name
            ))

    # ── Horizon sensor (always, but disabled by default) ──
    entities.append(SolarForecastHorizonSensor(coordinator, entry, name))

    async_add_entities(entities)


# ─── Base ────────────────────────────────────────────────────────────────────

class _Base(CoordinatorEntity[SolarForecastCoordinator], SensorEntity):
    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix):
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._entry = entry
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_entity_registry_enabled_default = sensor_config["enabled"]
        self._attr_device_info = _device_info(entry, name_prefix)


# ─── Total sensors ───────────────────────────────────────────────────────────

class SolarForecastTotalSensor(_Base):
    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix):
        super().__init__(coordinator, entry, sensor_type, sensor_config, name_prefix)
        self._attr_has_entity_name = True
        self._attr_name = sensor_config['name']
        self._attr_unique_id = f"{entry.entry_id}_total_{sensor_type}"

    @property
    def native_value(self) -> Any:
        data: SolarForecastData | None = self.coordinator.data
        return None if data is None else _total_value(data, self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict | None:
        data: SolarForecastData | None = self.coordinator.data
        if data is None:
            return None
        if self._sensor_type == "energy_production_today":
            return {"forecast": data.hourly_forecast, "watt_hours_day": data.watt_hours_day, "correction": data.correction}
        if self._sensor_type == "energy_production_tomorrow":
            return {"watt_hours_day": data.watt_hours_day}
        return None


# ─── Per-string sensors ──────────────────────────────────────────────────────

class SolarForecastStringSensor(_Base):
    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix, string_label, idx):
        super().__init__(coordinator, entry, sensor_type, sensor_config, name_prefix)
        self._idx = idx
        self._attr_has_entity_name = True
        self._attr_name = f"{string_label} {sensor_config['name']}"
        self._attr_unique_id = f"{entry.entry_id}_str{idx}_{sensor_type}"

    @property
    def native_value(self) -> Any:
        data: SolarForecastData | None = self.coordinator.data
        if data is None or self._idx >= len(data.strings):
            return None
        return _string_value(data.strings[self._idx], self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict | None:
        data: SolarForecastData | None = self.coordinator.data
        if data is None or self._idx >= len(data.strings):
            return None
        sd = data.strings[self._idx]
        if self._sensor_type == "energy_production_today":
            return {"forecast": sd.hourly_forecast, "watt_hours_day": sd.watt_hours_day,
                    "correction": sd.correction, "actual_calibration": sd.actual_info}
        if self._sensor_type == "energy_production_tomorrow":
            return {"watt_hours_day": sd.watt_hours_day}
        return None


# ─── Weather sensors ─────────────────────────────────────────────────────────

class SolarForecastWeatherSensor(_Base):
    def __init__(self, coordinator, entry, sensor_type, sensor_config, name_prefix):
        super().__init__(coordinator, entry, sensor_type, sensor_config, name_prefix)
        self._attr_has_entity_name = True
        self._attr_name = sensor_config['name']
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"

    @property
    def available(self) -> bool:
        d = self.coordinator.data
        return d is not None and d.weather is not None

    @property
    def native_value(self) -> Any:
        d = self.coordinator.data
        return None if d is None else _weather_value(d, self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self.coordinator.data
        if d is None or d.weather is None:
            return None
        if self._sensor_type == "weather_condition":
            return {"forecast": d.weather.entries}
        return None


# ─── Horizon sensor ───────────────────────────────────────────────────────────

class SolarForecastHorizonSensor(CoordinatorEntity[SolarForecastCoordinator], SensorEntity):
    def __init__(self, coordinator, entry, name_prefix):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Horizon - Max elevation"
        self._attr_unique_id = f"{entry.entry_id}_horizon"
        self._attr_icon = "mdi:image-filter-hdr"
        self._attr_native_unit_of_measurement = "°"
        self._attr_entity_registry_enabled_default = False
        self._attr_device_info = _device_info(entry, name_prefix)

    @property
    def available(self) -> bool:
        d = self.coordinator.data
        return d is not None and d.horizon is not None

    @property
    def native_value(self) -> Any:
        d = self.coordinator.data
        return None if (d is None or d.horizon is None) else d.horizon.get("max_elevation")

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self.coordinator.data
        if d is None or d.horizon is None:
            return None
        return {
            "mean_elevation": d.horizon.get("mean_elevation"),
            "azimuth": d.horizon.get("horizon", {}).get("azimuth"),
            "elevation": d.horizon.get("horizon", {}).get("elevation"),
        }

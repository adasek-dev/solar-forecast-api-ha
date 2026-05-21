"""Config flow for Solar Forecast API integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    DEFAULT_API_URL,
    DEFAULT_NAME,
    MAX_STRINGS,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_STRING_COUNT,
    CONF_UPDATE_INTERVAL,
    CONF_DAYS,
    CONF_DAMPING,
    CONF_NO_HORIZON,
    CONF_RESOLUTION,
    CONF_API_FEATURES,
    INTERVAL_OPTIONS_WITH_KEY,
    FEATURE_ACTUAL,
    FEATURE_WEATHER,
    FEATURE_TIMEWINDOWS,
    CONF_FEATURE_WEATHER,
    CONF_FEATURE_ACTUAL,
    CONF_FEATURE_CALIBRATION,
    CONF_FEATURE_TIMEWINDOWS,
    CONF_STR_NAME,
    CONF_STR_DECLINATION,
    CONF_STR_AZIMUTH,
    CONF_STR_WP,
    CONF_STR_ACTUAL_ENTITY,
    CONF_STR_CORRECTION,
    conf_string_name,
    conf_declination,
    conf_azimuth,
    conf_wp,
    conf_actual_entity,
    conf_correction,
)

_LOGGER = logging.getLogger(__name__)


# ─── API helpers ─────────────────────────────────────────────────────────────

async def validate_api(url: str) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}/health", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return (await resp.json(content_type=None)).get("status") == "ok"
    except Exception:
        pass
    return False


async def fetch_key_info(url: str, api_key: str) -> dict | None:
    """Fetch API key features via /info/:apikey. Returns None if key invalid."""
    base = url.rstrip("/")
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base}/info/{api_key}", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if "features" in data:
                        return data

            # Fallback: probe via estimate
            async with session.get(
                f"{base}/estimate/{api_key}/50.0/16.0/35/0/1.0?days=1", timeout=timeout
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status == 403:
                    if "Neplatný" in body.get("message", "") or "nvalid" in body.get("message", ""):
                        return None
                elif resp.status == 429:
                    return {"features": ["actual", "calibration"], "name": "", "rate_limit": 12}
                elif resp.status != 200:
                    return {"features": ["actual", "calibration"], "name": "", "rate_limit": 12}

            features = ["actual", "calibration"]
            async with session.get(f"{base}/weather/{api_key}/50.0/16.0?days=1", timeout=timeout) as resp:
                if resp.status == 200:
                    features.append(FEATURE_WEATHER)
            async with session.get(
                f"{base}/timewindows/{api_key}/50.0/16.0/35/0/1.0?days=1", timeout=timeout
            ) as resp:
                if resp.status == 200:
                    features.append(FEATURE_TIMEWINDOWS)
            return {"features": features, "name": "", "rate_limit": 100}
    except Exception as err:
        _LOGGER.warning("Feature detection error: %s", err)
        return {"features": ["actual", "calibration"], "name": "", "rate_limit": 12}


# ─── Schema helpers ───────────────────────────────────────────────────────────

def _interval_options() -> list[selector.SelectOptionDict]:
    return [selector.SelectOptionDict(value=str(m), label=f"{m} minut")
            for m in INTERVAL_OPTIONS_WITH_KEY]


def _days_options() -> list[selector.SelectOptionDict]:
    labels = {1:"1 den",2:"2 dny",3:"3 dny",4:"4 dny",5:"5 dní",6:"6 dní",7:"7 dní"}
    return [selector.SelectOptionDict(value=str(d), label=labels[d]) for d in range(1, 8)]


def _resolution_options() -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value="60", label="60 minut (standardní)"),
        selector.SelectOptionDict(value="15", label="15 minut (vyžaduje API klíč)"),
    ]


def _string_count_options() -> list[selector.SelectOptionDict]:
    return [selector.SelectOptionDict(value=str(i), label=str(i)) for i in range(1, MAX_STRINGS + 1)]


def _num(min_v, max_v, step=1, mode=selector.NumberSelectorMode.BOX) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(min=min_v, max=max_v, step=step, mode=mode))


def _save_string(data: dict, i: int, user_input: dict, has_actual: bool) -> None:
    data[conf_string_name(i)] = user_input.get(CONF_STR_NAME, f"String {i}")
    # NumberSelector returns float – convert to correct types
    data[conf_declination(i)] = int(float(user_input[CONF_STR_DECLINATION]))
    data[conf_azimuth(i)] = float(user_input[CONF_STR_AZIMUTH])
    data[conf_wp(i)] = int(float(user_input[CONF_STR_WP]))
    if has_actual:
        entity = user_input.get(CONF_STR_ACTUAL_ENTITY) or ""
        if entity:
            data[conf_actual_entity(i)] = entity
        else:
            data.pop(conf_actual_entity(i), None)
        try:
            val = float(user_input.get(CONF_STR_CORRECTION) or 0)
        except (ValueError, TypeError):
            val = 0.0
        if val > 0:
            data[conf_correction(i)] = val
        else:
            data.pop(conf_correction(i), None)


def _string_schema(i: int, defaults: dict, has_actual: bool) -> vol.Schema:
    fields: dict = {
        vol.Optional(CONF_STR_NAME, default=defaults.get(conf_string_name(i), f"String {i}")): str,
        vol.Required(CONF_STR_DECLINATION, default=int(float(defaults.get(conf_declination(i), 35)))): _num(0, 90, 1),
        vol.Required(CONF_STR_AZIMUTH, default=float(defaults.get(conf_azimuth(i), 0))): _num(-180, 180, 0.01),
        vol.Required(CONF_STR_WP, default=int(float(defaults.get(conf_wp(i), 5000)))): _num(1, 100000, 1),
    }
    if has_actual:
        # EntitySelector: use vol.Optional WITHOUT default to avoid "Unknown error"
        # If there's a saved entity, pre-populate via description_placeholders instead
        saved_entity = defaults.get(conf_actual_entity(i))
        if saved_entity:
            fields[vol.Optional(CONF_STR_ACTUAL_ENTITY, default=saved_entity)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy", multiple=False)
            )
        else:
            fields[vol.Optional(CONF_STR_ACTUAL_ENTITY)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy", multiple=False)
            )
        saved_correction = defaults.get(conf_correction(i), 0.0)
        fields[vol.Optional(CONF_STR_CORRECTION, default=float(saved_correction))] = _num(0.0, 2.0, 0.01)
    return vol.Schema(fields)


def _advanced_schema(defaults: dict, available_features: list[str]) -> vol.Schema:
    fields: dict = {
        vol.Required(CONF_DAYS, default=str(defaults.get(CONF_DAYS, 4))): selector.SelectSelector(
            selector.SelectSelectorConfig(options=_days_options(), mode=selector.SelectSelectorMode.LIST)
        ),
        vol.Required(CONF_RESOLUTION, default=str(defaults.get(CONF_RESOLUTION, 60))): selector.SelectSelector(
            selector.SelectSelectorConfig(options=_resolution_options(), mode=selector.SelectSelectorMode.LIST)
        ),
        vol.Optional(CONF_DAMPING, default=float(defaults.get(CONF_DAMPING, 0.0))): _num(0.0, 1.0, 0.01),
        vol.Optional(CONF_NO_HORIZON, default=bool(defaults.get(CONF_NO_HORIZON, False))): bool,
    }
    if FEATURE_WEATHER in available_features:
        fields[vol.Optional(CONF_FEATURE_WEATHER, default=bool(defaults.get(CONF_FEATURE_WEATHER, True)))] = bool
    if FEATURE_ACTUAL in available_features:
        fields[vol.Optional(CONF_FEATURE_ACTUAL, default=bool(defaults.get(CONF_FEATURE_ACTUAL, True)))] = bool
    if "calibration" in available_features:
        fields[vol.Optional(CONF_FEATURE_CALIBRATION, default=bool(defaults.get(CONF_FEATURE_CALIBRATION, True)))] = bool
    if FEATURE_TIMEWINDOWS in available_features:
        fields[vol.Optional(CONF_FEATURE_TIMEWINDOWS, default=bool(defaults.get(CONF_FEATURE_TIMEWINDOWS, False)))] = bool
    return vol.Schema(fields)


def _save_advanced(data: dict, user_input: dict) -> None:
    data.update({
        CONF_DAYS: int(user_input.get(CONF_DAYS, 4)),
        CONF_DAMPING: float(user_input.get(CONF_DAMPING, 0.0)),
        CONF_NO_HORIZON: bool(user_input.get(CONF_NO_HORIZON, False)),
        CONF_RESOLUTION: int(user_input.get(CONF_RESOLUTION, 60)),
        CONF_FEATURE_WEATHER: bool(user_input.get(CONF_FEATURE_WEATHER, True)),
        CONF_FEATURE_ACTUAL: bool(user_input.get(CONF_FEATURE_ACTUAL, True)),
        CONF_FEATURE_CALIBRATION: bool(user_input.get(CONF_FEATURE_CALIBRATION, True)),
        CONF_FEATURE_TIMEWINDOWS: bool(user_input.get(CONF_FEATURE_TIMEWINDOWS, False)),
    })


def _basic_schema(defaults: dict) -> vol.Schema:
    current_min = defaults.get(CONF_UPDATE_INTERVAL, 3600) // 60
    return vol.Schema({
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
        vol.Optional(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
        vol.Required(CONF_LATITUDE, default=float(defaults.get(CONF_LATITUDE, 50.0))): cv.latitude,
        vol.Required(CONF_LONGITUDE, default=float(defaults.get(CONF_LONGITUDE, 16.0))): cv.longitude,
        vol.Required(CONF_STRING_COUNT, default=str(defaults.get(CONF_STRING_COUNT, 1))): selector.SelectSelector(
            selector.SelectSelectorConfig(options=_string_count_options(), mode=selector.SelectSelectorMode.LIST)
        ),
        vol.Required(CONF_UPDATE_INTERVAL, default=str(current_min)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=_interval_options(), mode=selector.SelectSelectorMode.LIST)
        ),
    })


# ─── Config Flow ──────────────────────────────────────────────────────────────

class SolarForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Forecast API."""

    VERSION = 2

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "SolarForecastOptionsFlow":
        return SolarForecastOptionsFlow(config_entry)

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._current_string: int = 1
        self._string_count: int = 1
        self._has_api_key: bool = False
        self._api_features: list[str] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            interval_min = int(user_input.get(CONF_UPDATE_INTERVAL, 60))

            if not api_key and interval_min != 60:
                errors[CONF_UPDATE_INTERVAL] = "interval_requires_key"
            elif not await validate_api(DEFAULT_API_URL):
                errors["base"] = "cannot_connect"
            else:
                if api_key:
                    key_info = await fetch_key_info(DEFAULT_API_URL, api_key)
                    if key_info is None:
                        errors[CONF_API_KEY] = "invalid_api_key"
                    else:
                        self._api_features = key_info.get("features", [])
                        self._has_api_key = True
                else:
                    self._api_features = []
                    self._has_api_key = False

                if not errors:
                    string_count = int(user_input.get(CONF_STRING_COUNT, 1))
                    if not self._has_api_key:
                        string_count = 1
                    self._string_count = string_count
                    self._data = {
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_API_KEY: api_key,
                        CONF_LATITUDE: user_input[CONF_LATITUDE],
                        CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                        CONF_STRING_COUNT: string_count,
                        CONF_UPDATE_INTERVAL: interval_min * 60,
                        CONF_API_FEATURES: self._api_features,
                    }
                    self._current_string = 1
                    return await self.async_step_string()

        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Required(CONF_LATITUDE, default=default_lat): cv.latitude,
                vol.Required(CONF_LONGITUDE, default=default_lon): cv.longitude,
                vol.Required(CONF_STRING_COUNT, default="1"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_string_count_options(), mode=selector.SelectSelectorMode.LIST)
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default="60"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_interval_options(), mode=selector.SelectSelectorMode.LIST)
                ),
            }),
            errors=errors,
        )

    async def async_step_string(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        i = self._current_string
        has_actual = self._has_api_key and FEATURE_ACTUAL in self._api_features

        if user_input is not None:
            _save_string(self._data, i, user_input, has_actual)
            if self._current_string < self._string_count:
                self._current_string += 1
                return await self.async_step_string()
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="string",
            description_placeholders={"index": str(i), "total": str(self._string_count)},
            data_schema=_string_schema(i, self._data, has_actual),
        )

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._has_api_key:
            self._data.update({CONF_DAYS: 1, CONF_RESOLUTION: 60, CONF_DAMPING: 0.0, CONF_NO_HORIZON: False})
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        if user_input is not None:
            _save_advanced(self._data, user_input)
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        features_text = ", ".join(self._api_features) if self._api_features else "žádné"
        return self.async_show_form(
            step_id="advanced",
            description_placeholders={"features": features_text},
            data_schema=_advanced_schema(self._data, self._api_features),
        )


# ─── Options Flow ─────────────────────────────────────────────────────────────

class SolarForecastOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._data: dict[str, Any] = {**config_entry.data, **config_entry.options}
        self._current_string: int = 1
        self._string_count: int = self._data.get(CONF_STRING_COUNT, 1)
        self._has_api_key: bool = bool(self._data.get(CONF_API_KEY, ""))
        self._old_api_key: str = self._data.get(CONF_API_KEY, "")
        self._api_features: list[str] = self._data.get(CONF_API_FEATURES, [])
        self._needs_feature_fetch: bool = self._has_api_key and not self._api_features

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        # Auto-fetch features on first open if missing
        if self._needs_feature_fetch and user_input is None:
            self._needs_feature_fetch = False
            key_info = await fetch_key_info(DEFAULT_API_URL, self._old_api_key)
            if key_info:
                self._api_features = key_info.get("features", [])
                self._data[CONF_API_FEATURES] = self._api_features

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            interval_min = int(user_input.get(CONF_UPDATE_INTERVAL, 60))

            if not api_key and interval_min != 60:
                errors[CONF_UPDATE_INTERVAL] = "interval_requires_key"
            else:
                if api_key and api_key != self._old_api_key:
                    key_info = await fetch_key_info(DEFAULT_API_URL, api_key)
                    if key_info is None:
                        errors[CONF_API_KEY] = "invalid_api_key"
                    else:
                        self._api_features = key_info.get("features", [])
                        self._has_api_key = True
                elif api_key:
                    self._has_api_key = True
                else:
                    self._api_features = []
                    self._has_api_key = False

                if not errors:
                    string_count = int(user_input.get(CONF_STRING_COUNT, 1))
                    if not self._has_api_key:
                        string_count = 1
                    self._string_count = string_count
                    self._data.update({
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_API_KEY: api_key,
                        CONF_LATITUDE: user_input[CONF_LATITUDE],
                        CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                        CONF_STRING_COUNT: string_count,
                        CONF_UPDATE_INTERVAL: interval_min * 60,
                        CONF_API_FEATURES: self._api_features,
                    })
                    self._current_string = 1
                    return await self.async_step_string()

        return self.async_show_form(
            step_id="init",
            data_schema=_basic_schema(self._data),
            errors=errors,
            description_placeholders={
                "features": ", ".join(self._api_features) if self._api_features else "žádné"
            },
        )

    async def async_step_string(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        i = self._current_string
        has_actual = self._has_api_key and FEATURE_ACTUAL in self._api_features

        if user_input is not None:
            _save_string(self._data, i, user_input, has_actual)
            if self._current_string < self._string_count:
                self._current_string += 1
                return await self.async_step_string()
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="string",
            description_placeholders={"index": str(i), "total": str(self._string_count)},
            data_schema=_string_schema(i, self._data, has_actual),
        )

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._has_api_key:
            self._data.update({CONF_DAYS: 1, CONF_RESOLUTION: 60, CONF_DAMPING: 0.0, CONF_NO_HORIZON: False})
            return self.async_create_entry(title="", data=self._data)

        if user_input is not None:
            _save_advanced(self._data, user_input)
            return self.async_create_entry(title="", data=self._data)

        features_text = ", ".join(self._api_features) if self._api_features else "žádné"
        return self.async_show_form(
            step_id="advanced",
            description_placeholders={"features": features_text},
            data_schema=_advanced_schema(self._data, self._api_features),
        )

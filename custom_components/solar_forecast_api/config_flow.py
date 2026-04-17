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


# ─── API helpers ────────────────────────────────────────────────────────────

async def validate_api(url: str) -> bool:
    """Check that the API server is reachable."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}/health", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return (await resp.json()).get("status") == "ok"
    except Exception:
        pass
    return False


async def fetch_key_features(url: str, api_key: str) -> list[str] | None:
    """
    Return list of features for the given API key, or None if the key is invalid.
    Uses a single estimate call to verify the key, then tests weather + timewindows.
    Deliberately minimal – only 1 rate-limit slot consumed for estimate.
    """
    base = url.rstrip("/")
    # Minimal valid params: lat=50, lon=16, dec=35, az=0, kwp=1
    est_url = f"{base}/estimate/{api_key}/50.0/16.0/35/0/1.0?days=1"
    wx_url  = f"{base}/weather/{api_key}/50.0/16.0?days=1"
    tw_url  = f"{base}/timewindows/{api_key}/50.0/16.0/35/0/1.0?days=1"

    features: list[str] = []
    timeout = aiohttp.ClientTimeout(total=15)

    try:
        async with aiohttp.ClientSession() as session:
            # ── 1. Verify key via estimate ──────────────────────────────
            async with session.get(est_url, timeout=timeout) as resp:
                body = await resp.json(content_type=None)
                if resp.status == 403:
                    msg = body.get("message", "")
                    if "Neplatný" in msg or "nvalid" in msg or "neplatný" in msg.lower():
                        _LOGGER.debug("API key rejected: %s", msg)
                        return None   # genuinely invalid key
                    # Other 403 = some other restriction, key may still be valid
                elif resp.status == 429:
                    # Rate-limited but key is valid – assume basic features
                    _LOGGER.debug("Rate limited during feature detection, assuming basic features")
                    return ["actual", "calibration"]
                elif resp.status == 200:
                    features += ["actual", "calibration"]
                else:
                    _LOGGER.warning("Unexpected status %s from estimate", resp.status)
                    return ["actual", "calibration"]   # be optimistic

            # ── 2. Test weather feature ─────────────────────────────────
            try:
                async with session.get(wx_url, timeout=timeout) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status == 200:
                        features.append(FEATURE_WEATHER)
                    elif resp.status == 403:
                        msg = body.get("message", "")
                        # "nemá povolen" = key valid but no weather
                        # "Neplatný" = would have been caught above already
                        _LOGGER.debug("Weather feature not available: %s", msg)
            except Exception as e:
                _LOGGER.debug("Weather feature check failed: %s", e)

            # ── 3. Test timewindows feature ─────────────────────────────
            try:
                async with session.get(tw_url, timeout=timeout) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status == 200:
                        features.append(FEATURE_TIMEWINDOWS)
                    elif resp.status == 403:
                        _LOGGER.debug("Timewindows feature not available: %s",
                                      body.get("message", ""))
            except Exception as e:
                _LOGGER.debug("Timewindows feature check failed: %s", e)

    except aiohttp.ClientError as err:
        _LOGGER.warning("Feature detection network error: %s", err)
        # Network error – don't block setup, return basic features
        return ["actual", "calibration"]
    except Exception as err:
        _LOGGER.warning("Feature detection unexpected error: %s", err)
        return ["actual", "calibration"]

    _LOGGER.debug("Detected features for key: %s", features)
    return features



def _interval_options() -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=str(m), label=f"{m} minut")
        for m in INTERVAL_OPTIONS_WITH_KEY
    ]


def _days_options() -> list[selector.SelectOptionDict]:
    labels = {1: "1 den", 2: "2 dny", 3: "3 dny", 4: "4 dny",
              5: "5 dní", 6: "6 dní", 7: "7 dní"}
    return [selector.SelectOptionDict(value=str(d), label=labels[d]) for d in range(1, 8)]


def _resolution_options() -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value="60", label="60 minut (standardní)"),
        selector.SelectOptionDict(value="15", label="15 minut (vyžaduje API klíč)"),
    ]


def _save_string(data: dict, i: int, user_input: dict, has_actual: bool) -> None:
    """Save one string's form values into data dict."""
    data[conf_string_name(i)] = user_input.get(CONF_STR_NAME, f"String {i}")
    data[conf_declination(i)] = user_input[CONF_STR_DECLINATION]
    data[conf_azimuth(i)] = user_input[CONF_STR_AZIMUTH]
    data[conf_wp(i)] = user_input[CONF_STR_WP]

    if has_actual:
        entity = user_input.get(CONF_STR_ACTUAL_ENTITY) or ""
        if entity:
            data[conf_actual_entity(i)] = entity
        else:
            data.pop(conf_actual_entity(i), None)

        raw = user_input.get(CONF_STR_CORRECTION)
        try:
            val = float(raw) if raw is not None else 0.0
        except (ValueError, TypeError):
            val = 0.0
        if val > 0:
            data[conf_correction(i)] = val
        else:
            data.pop(conf_correction(i), None)


def _string_schema(i: int, defaults: dict, has_actual: bool) -> vol.Schema:
    """Build the voluptuous schema for one string step."""
    fields: dict = {
        vol.Optional(CONF_STR_NAME, default=defaults.get(conf_string_name(i), f"String {i}")): str,
        vol.Required(CONF_STR_DECLINATION, default=defaults.get(conf_declination(i), 35)): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=90)
        ),
        vol.Required(CONF_STR_AZIMUTH, default=defaults.get(conf_azimuth(i), 0)): vol.All(
            vol.Coerce(float), vol.Range(min=-180, max=180)
        ),
        vol.Required(CONF_STR_WP, default=defaults.get(conf_wp(i), 5000)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100000)
        ),
    }
    if has_actual:
        fields[vol.Optional(CONF_STR_ACTUAL_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy", multiple=False)
        )
        fields[vol.Optional(CONF_STR_CORRECTION)] = vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0))
        )
    return vol.Schema(fields)


def _advanced_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_DAYS, default=defaults.get(CONF_DAYS, 4)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=_days_options(), mode=selector.SelectSelectorMode.LIST)
        ),
        vol.Required(CONF_RESOLUTION, default=str(defaults.get(CONF_RESOLUTION, 60))): selector.SelectSelector(
            selector.SelectSelectorConfig(options=_resolution_options(), mode=selector.SelectSelectorMode.LIST)
        ),
        vol.Optional(CONF_DAMPING, default=defaults.get(CONF_DAMPING, 0.0)): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=1.0)
        ),
        vol.Optional(CONF_NO_HORIZON, default=defaults.get(CONF_NO_HORIZON, False)): bool,
    })


# ─── Config Flow ────────────────────────────────────────────────────────────

class SolarForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Forecast API."""

    VERSION = 2

    # ── Required: expose options flow ──────────────────────────────────────
    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "SolarForecastOptionsFlow":
        """Return the options flow handler."""
        return SolarForecastOptionsFlow(config_entry)

    # ── Internal state ──────────────────────────────────────────────────────
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._current_string: int = 1
        self._string_count: int = 1
        self._has_api_key: bool = False
        self._api_features: list[str] = []

    # ── Step 1: basic ───────────────────────────────────────────────────────
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
                    features = await fetch_key_features(DEFAULT_API_URL, api_key)
                    if features is None:
                        errors[CONF_API_KEY] = "invalid_api_key"
                    else:
                        self._api_features = features
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
                vol.Required(CONF_STRING_COUNT, default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=MAX_STRINGS)
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default=60): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_interval_options(),
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            errors=errors,
        )

    # ── Step 2: string(s) ───────────────────────────────────────────────────
    async def async_step_string(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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

    # ── Step 3: advanced ────────────────────────────────────────────────────
    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        # Without API key → skip with safe defaults
        if not self._has_api_key:
            self._data.update({
                CONF_DAYS: 1,
                CONF_RESOLUTION: 60,
                CONF_DAMPING: 0.0,
                CONF_NO_HORIZON: False,
            })
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        if user_input is not None:
            self._data.update({
                CONF_DAYS: int(user_input.get(CONF_DAYS, 4)),
                CONF_DAMPING: float(user_input.get(CONF_DAMPING, 0.0)),
                CONF_NO_HORIZON: bool(user_input.get(CONF_NO_HORIZON, False)),
                CONF_RESOLUTION: int(user_input.get(CONF_RESOLUTION, 60)),
            })
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        features_text = ", ".join(self._api_features) if self._api_features else "žádné"
        return self.async_show_form(
            step_id="advanced",
            description_placeholders={"features": features_text},
            data_schema=_advanced_schema(self._data),
        )


# ─── Options Flow ────────────────────────────────────────────────────────────

class SolarForecastOptionsFlow(config_entries.OptionsFlow):
    """Allow reconfiguring an existing entry without deleting it."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # Work on a mutable copy of the current full config
        self._data: dict[str, Any] = {**config_entry.data, **config_entry.options}
        self._current_string: int = 1
        self._string_count: int = self._data.get(CONF_STRING_COUNT, 1)
        self._has_api_key: bool = bool(self._data.get(CONF_API_KEY, ""))
        self._api_features: list[str] = self._data.get(CONF_API_FEATURES, [])
        self._old_api_key: str = self._data.get(CONF_API_KEY, "")

    # ── Options step 1: basic ───────────────────────────────────────────────
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            interval_min = int(user_input.get(CONF_UPDATE_INTERVAL, 60))

            if not api_key and interval_min != 60:
                errors[CONF_UPDATE_INTERVAL] = "interval_requires_key"
            else:
                # Re-fetch features only if key changed
                if api_key and api_key != self._old_api_key:
                    features = await fetch_key_features(DEFAULT_API_URL, api_key)
                    if features is None:
                        errors[CONF_API_KEY] = "invalid_api_key"
                    else:
                        self._api_features = features
                        self._has_api_key = True
                elif not api_key:
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
                        CONF_STRING_COUNT: string_count,
                        CONF_UPDATE_INTERVAL: interval_min * 60,
                        CONF_API_FEATURES: self._api_features,
                    })
                    self._current_string = 1
                    return await self.async_step_string()

        current_min = self._data.get(CONF_UPDATE_INTERVAL, 3600) // 60

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=self._data.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Optional(CONF_API_KEY, default=self._data.get(CONF_API_KEY, "")): str,
                vol.Required(CONF_STRING_COUNT, default=self._string_count): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=MAX_STRINGS)
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default=current_min): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_interval_options(),
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            errors=errors,
        )

    # ── Options step 2: string(s) ───────────────────────────────────────────
    async def async_step_string(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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

    # ── Options step 3: advanced ────────────────────────────────────────────
    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._has_api_key:
            self._data.update({
                CONF_DAYS: 1,
                CONF_RESOLUTION: 60,
                CONF_DAMPING: 0.0,
                CONF_NO_HORIZON: False,
            })
            return self.async_create_entry(title="", data=self._data)

        if user_input is not None:
            self._data.update({
                CONF_DAYS: int(user_input.get(CONF_DAYS, 4)),
                CONF_DAMPING: float(user_input.get(CONF_DAMPING, 0.0)),
                CONF_NO_HORIZON: bool(user_input.get(CONF_NO_HORIZON, False)),
                CONF_RESOLUTION: int(user_input.get(CONF_RESOLUTION, 60)),
            })
            return self.async_create_entry(title="", data=self._data)

        features_text = ", ".join(self._api_features) if self._api_features else "žádné"
        return self.async_show_form(
            step_id="advanced",
            description_placeholders={"features": features_text},
            data_schema=_advanced_schema(self._data),
        )

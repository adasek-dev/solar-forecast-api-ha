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
    INTERVAL_OPTIONS_NO_KEY,
    DAYS_OPTIONS_WITH_KEY,
    DAYS_OPTIONS_NO_KEY,
    FEATURE_WEATHER,
    FEATURE_ACTUAL,
    FEATURE_CALIBRATION,
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


async def validate_api(url: str) -> bool:
    """Validate API connection."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}/health",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("status") == "ok"
    except Exception:
        pass
    return False


async def fetch_key_features(url: str, api_key: str) -> list[str]:
    """Fetch features for an API key from /health endpoint."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}/health",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Try to get per-key features
                    # The health endpoint lists api_keys_features (all possible features)
                    # We verify by making a test estimate call with the key
                    # For now return all features if key is valid, subset if not
                    # Validate key by trying to call estimate with it
                    pass
        # Try a minimal estimate call to verify key is valid and check what works
        # Use a dummy call to /estimate/:apikey/health-check style
        # Actually: fetch_key_features by calling /weather endpoint
        # If 403 with "nemá povolen" → feature not available
        # If 403 with "Neplatný" → key invalid
        features = []
        test_lat = "50.0"
        test_lon = "16.0"

        async with aiohttp.ClientSession() as session:
            # Test weather feature
            async with session.get(
                f"{url}/weather/{api_key}/{test_lat}/{test_lon}?days=1",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    features.append(FEATURE_WEATHER)
                elif resp.status == 403:
                    msg = data.get("message", "")
                    if "Neplatný" in msg or "Invalid" in msg.lower():
                        return []  # Invalid key

            # Test timewindows feature
            async with session.get(
                f"{url}/timewindows/{api_key}/{test_lat}/{test_lon}/35/0/5.0?days=1",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    features.append(FEATURE_TIMEWINDOWS)

            # Test estimate (actual + calibration) – if key works for estimate, has actual
            async with session.get(
                f"{url}/estimate/{api_key}/{test_lat}/{test_lon}/35/0/1.0?days=1",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    features.append(FEATURE_ACTUAL)
                    features.append(FEATURE_CALIBRATION)

        return features
    except Exception as e:
        _LOGGER.warning("Could not fetch API key features: %s", e)
        return [FEATURE_ACTUAL, FEATURE_CALIBRATION]  # default: assume basic features


def _interval_options(has_key: bool) -> list[selector.SelectOptionDict]:
    opts = INTERVAL_OPTIONS_WITH_KEY if has_key else INTERVAL_OPTIONS_NO_KEY
    return [selector.SelectOptionDict(value=str(m), label=f"{m} minut") for m in opts]


def _days_options(has_key: bool) -> list[selector.SelectOptionDict]:
    opts = DAYS_OPTIONS_WITH_KEY if has_key else DAYS_OPTIONS_NO_KEY
    labels = {1: "1 den", 2: "2 dny", 3: "3 dny", 4: "4 dny",
              5: "5 dní", 6: "6 dní", 7: "7 dní"}
    return [selector.SelectOptionDict(value=str(d), label=labels[d]) for d in opts]


def _resolution_options(has_key: bool) -> list[selector.SelectOptionDict]:
    opts = [selector.SelectOptionDict(value="60", label="60 minut (standardní)")]
    if has_key:
        opts.append(selector.SelectOptionDict(value="15", label="15 minut (vyžaduje API klíč)"))
    return opts


# ─── Config Flow ────────────────────────────────────────────────────────────

class SolarForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Forecast API."""

    VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._current_string: int = 1
        self._string_count: int = 1
        self._has_api_key: bool = False
        self._api_features: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Basic config."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            interval_min = int(user_input.get(CONF_UPDATE_INTERVAL, 60))

            if not api_key and interval_min != 60:
                errors[CONF_UPDATE_INTERVAL] = "interval_requires_key"
            elif not await validate_api(DEFAULT_API_URL):
                errors["base"] = "cannot_connect"
            else:
                self._has_api_key = bool(api_key)

                # Fetch features for API key
                if api_key:
                    self._api_features = await fetch_key_features(DEFAULT_API_URL, api_key)
                    if not self._api_features and not await validate_api(DEFAULT_API_URL):
                        errors[CONF_API_KEY] = "invalid_api_key"
                    elif not self._api_features:
                        errors[CONF_API_KEY] = "invalid_api_key"
                else:
                    self._api_features = []

                if not errors:
                    string_count = user_input.get(CONF_STRING_COUNT, 1)
                    if not api_key:
                        string_count = 1  # bez klíče jen 1 string
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

        schema_fields: dict = {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Optional(CONF_API_KEY, default=""): str,
            vol.Required(CONF_LATITUDE, default=default_lat): cv.latitude,
            vol.Required(CONF_LONGITUDE, default=default_lon): cv.longitude,
        }
        # String count – jen pokud má klíč (bez klíče vždy 1)
        schema_fields[vol.Required(CONF_STRING_COUNT, default=1)] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_STRINGS)
        )
        schema_fields[vol.Required(CONF_UPDATE_INTERVAL, default=60)] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=_interval_options(True),  # zobrazíme všechny, validace proběhne
                mode=selector.SelectSelectorMode.LIST,
            )
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    async def async_step_string(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step per string."""
        i = self._current_string

        if user_input is not None:
            self._data[conf_string_name(i)] = user_input.get(CONF_STR_NAME, f"String {i}")
            self._data[conf_declination(i)] = user_input[CONF_STR_DECLINATION]
            self._data[conf_azimuth(i)] = user_input[CONF_STR_AZIMUTH]
            self._data[conf_wp(i)] = user_input[CONF_STR_WP]

            # actual entity – jen pokud má klíč s actual feature
            if self._has_api_key and FEATURE_ACTUAL in self._api_features:
                entity = user_input.get(CONF_STR_ACTUAL_ENTITY, "")
                if entity:
                    self._data[conf_actual_entity(i)] = entity

            correction_raw = user_input.get(CONF_STR_CORRECTION)
            if correction_raw is not None and str(correction_raw).strip() not in ("", "0", "0.0"):
                try:
                    self._data[conf_correction(i)] = float(correction_raw)
                except (ValueError, TypeError):
                    pass

            if self._current_string < self._string_count:
                self._current_string += 1
                return await self.async_step_string()
            else:
                return await self.async_step_advanced()

        # Build schema based on available features
        schema_fields: dict = {
            vol.Optional(CONF_STR_NAME, default=f"String {i}"): str,
            vol.Required(CONF_STR_DECLINATION, default=35): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=90)
            ),
            vol.Required(CONF_STR_AZIMUTH, default=0): vol.All(
                vol.Coerce(float), vol.Range(min=-180, max=180)
            ),
            vol.Required(CONF_STR_WP, default=5000): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=100000)
            ),
        }

        # Actual entity – jen s API klíčem + actual feature
        if self._has_api_key and FEATURE_ACTUAL in self._api_features:
            schema_fields[vol.Optional(CONF_STR_ACTUAL_ENTITY)] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class="energy",
                    multiple=False,
                )
            )
            schema_fields[vol.Optional(CONF_STR_CORRECTION)] = vol.Any(
                None,
                vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0)),
            )

        return self.async_show_form(
            step_id="string",
            description_placeholders={
                "index": str(i),
                "total": str(self._string_count),
            },
            data_schema=vol.Schema(schema_fields),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Advanced options (only with API key)."""
        # Without API key – skip advanced, use defaults
        if not self._has_api_key:
            self._data[CONF_DAYS] = 1
            self._data[CONF_RESOLUTION] = 60
            self._data[CONF_DAMPING] = 0.0
            self._data[CONF_NO_HORIZON] = False
            return self.async_create_entry(
                title=self._data.get(CONF_NAME, DEFAULT_NAME),
                data=self._data,
            )

        if user_input is not None:
            self._data[CONF_DAYS] = int(user_input.get(CONF_DAYS, 4))
            self._data[CONF_DAMPING] = float(user_input.get(CONF_DAMPING, 0.0))
            self._data[CONF_NO_HORIZON] = bool(user_input.get(CONF_NO_HORIZON, False))
            resolution = int(user_input.get(CONF_RESOLUTION, 60))
            if not self._has_api_key:
                resolution = 60
            self._data[CONF_RESOLUTION] = resolution
            return self.async_create_entry(
                title=self._data.get(CONF_NAME, DEFAULT_NAME),
                data=self._data,
            )

        features_text = ", ".join(self._api_features) if self._api_features else "žádné"

        return self.async_show_form(
            step_id="advanced",
            description_placeholders={"features": features_text},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DAYS, default=4): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_days_options(True),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(CONF_RESOLUTION, default=60): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_resolution_options(True),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(CONF_DAMPING, default=0.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0.0, max=1.0)
                    ),
                    vol.Optional(CONF_NO_HORIZON, default=False): bool,
                }
            ),
        )


# ─── Options Flow (úprava bez mazání) ───────────────────────────────────────

class SolarForecastOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Solar Forecast API."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data)
        self._current_string: int = 1
        self._string_count: int = config_entry.data.get(CONF_STRING_COUNT, 1)
        self._has_api_key: bool = bool(config_entry.data.get(CONF_API_KEY, ""))
        self._api_features: list[str] = config_entry.data.get(CONF_API_FEATURES, [])

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Options: step 1 – basic params."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            interval_min = int(user_input.get(CONF_UPDATE_INTERVAL, 60))

            if not api_key and interval_min != 60:
                errors[CONF_UPDATE_INTERVAL] = "interval_requires_key"
            else:
                self._has_api_key = bool(api_key)

                # Re-fetch features if key changed
                old_key = self._entry.data.get(CONF_API_KEY, "")
                if api_key and api_key != old_key:
                    self._api_features = await fetch_key_features(DEFAULT_API_URL, api_key)
                    if not self._api_features:
                        errors[CONF_API_KEY] = "invalid_api_key"
                elif not api_key:
                    self._api_features = []

                if not errors:
                    string_count = user_input.get(CONF_STRING_COUNT, 1)
                    if not api_key:
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

        current_interval_sec = self._entry.data.get(CONF_UPDATE_INTERVAL, 3600)
        current_interval_min = current_interval_sec // 60

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=self._data.get(CONF_NAME, DEFAULT_NAME)): str,
                    vol.Optional(CONF_API_KEY, default=self._data.get(CONF_API_KEY, "")): str,
                    vol.Required(CONF_STRING_COUNT, default=self._string_count): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=MAX_STRINGS)
                    ),
                    vol.Required(CONF_UPDATE_INTERVAL, default=current_interval_min): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_interval_options(True),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_string(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Options: string configuration."""
        i = self._current_string

        if user_input is not None:
            self._data[conf_string_name(i)] = user_input.get(CONF_STR_NAME, f"String {i}")
            self._data[conf_declination(i)] = user_input[CONF_STR_DECLINATION]
            self._data[conf_azimuth(i)] = user_input[CONF_STR_AZIMUTH]
            self._data[conf_wp(i)] = user_input[CONF_STR_WP]

            if self._has_api_key and FEATURE_ACTUAL in self._api_features:
                entity = user_input.get(CONF_STR_ACTUAL_ENTITY, "")
                if entity:
                    self._data[conf_actual_entity(i)] = entity
                else:
                    self._data.pop(conf_actual_entity(i), None)

                correction_raw = user_input.get(CONF_STR_CORRECTION)
                if correction_raw is not None and str(correction_raw).strip() not in ("", "0", "0.0"):
                    try:
                        self._data[conf_correction(i)] = float(correction_raw)
                    except (ValueError, TypeError):
                        self._data.pop(conf_correction(i), None)
                else:
                    self._data.pop(conf_correction(i), None)

            if self._current_string < self._string_count:
                self._current_string += 1
                return await self.async_step_string()
            else:
                return await self.async_step_advanced()

        schema_fields: dict = {
            vol.Optional(CONF_STR_NAME, default=self._data.get(conf_string_name(i), f"String {i}")): str,
            vol.Required(CONF_STR_DECLINATION, default=self._data.get(conf_declination(i), 35)): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=90)
            ),
            vol.Required(CONF_STR_AZIMUTH, default=self._data.get(conf_azimuth(i), 0)): vol.All(
                vol.Coerce(float), vol.Range(min=-180, max=180)
            ),
            vol.Required(CONF_STR_WP, default=self._data.get(conf_wp(i), 5000)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=100000)
            ),
        }

        if self._has_api_key and FEATURE_ACTUAL in self._api_features:
            schema_fields[vol.Optional(CONF_STR_ACTUAL_ENTITY, default=self._data.get(conf_actual_entity(i), ""))] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy", multiple=False)
            )
            schema_fields[vol.Optional(CONF_STR_CORRECTION, default=self._data.get(conf_correction(i), 0.0))] = vol.Any(
                None, vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0))
            )

        return self.async_show_form(
            step_id="string",
            description_placeholders={"index": str(i), "total": str(self._string_count)},
            data_schema=vol.Schema(schema_fields),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Options: advanced settings."""
        if not self._has_api_key:
            self._data[CONF_DAYS] = 1
            self._data[CONF_RESOLUTION] = 60
            self._data[CONF_DAMPING] = 0.0
            self._data[CONF_NO_HORIZON] = False
            return self.async_create_entry(title="", data=self._data)

        if user_input is not None:
            self._data[CONF_DAYS] = int(user_input.get(CONF_DAYS, 4))
            self._data[CONF_DAMPING] = float(user_input.get(CONF_DAMPING, 0.0))
            self._data[CONF_NO_HORIZON] = bool(user_input.get(CONF_NO_HORIZON, False))
            self._data[CONF_RESOLUTION] = int(user_input.get(CONF_RESOLUTION, 60))
            return self.async_create_entry(title="", data=self._data)

        features_text = ", ".join(self._api_features) if self._api_features else "žádné"

        return self.async_show_form(
            step_id="advanced",
            description_placeholders={"features": features_text},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DAYS, default=self._data.get(CONF_DAYS, 4)): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_days_options(True),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(CONF_RESOLUTION, default=self._data.get(CONF_RESOLUTION, 60)): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_resolution_options(True),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(CONF_DAMPING, default=self._data.get(CONF_DAMPING, 0.0)): vol.All(
                        vol.Coerce(float), vol.Range(min=0.0, max=1.0)
                    ),
                    vol.Optional(CONF_NO_HORIZON, default=self._data.get(CONF_NO_HORIZON, False)): bool,
                }
            ),
        )


    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SolarForecastOptionsFlow:
        """Get the options flow for this handler."""
        return SolarForecastOptionsFlow(config_entry)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

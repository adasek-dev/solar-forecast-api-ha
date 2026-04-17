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
    INTERVAL_OPTIONS,
    # Static form field keys
    CONF_STR_NAME,
    CONF_STR_DECLINATION,
    CONF_STR_AZIMUTH,
    CONF_STR_WP,
    CONF_STR_ACTUAL_ENTITY,
    CONF_STR_CORRECTION,
    # Storage key builders
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


class SolarForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Forecast API."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize."""
        self._data: dict[str, Any] = {}
        self._current_string: int = 1
        self._string_count: int = 1
        self._has_api_key: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Basic config + number of strings + update interval."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            interval_min = user_input.get(CONF_UPDATE_INTERVAL, 60)

            # Without API key only 60 min is allowed
            if not api_key and interval_min != 60:
                errors[CONF_UPDATE_INTERVAL] = "interval_requires_key"
            elif not await validate_api(DEFAULT_API_URL):
                errors["base"] = "cannot_connect"
            else:
                self._has_api_key = bool(api_key)
                self._string_count = user_input.get(CONF_STRING_COUNT, 1)
                self._data = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_API_KEY: api_key,
                    CONF_LATITUDE: user_input[CONF_LATITUDE],
                    CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                    CONF_STRING_COUNT: self._string_count,
                    CONF_UPDATE_INTERVAL: interval_min * 60,  # store as seconds
                }
                self._current_string = 1
                return await self.async_step_string()

        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        # Interval selector options
        interval_options = [
            selector.SelectOptionDict(value=str(m), label=f"{m} minut")
            for m in INTERVAL_OPTIONS
        ]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Optional(CONF_API_KEY, default=""): str,
                    vol.Required(CONF_LATITUDE, default=default_lat): cv.latitude,
                    vol.Required(CONF_LONGITUDE, default=default_lon): cv.longitude,
                    vol.Required(CONF_STRING_COUNT, default=1): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=MAX_STRINGS)
                    ),
                    vol.Required(CONF_UPDATE_INTERVAL, default=60): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=interval_options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key=CONF_UPDATE_INTERVAL,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_string(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step per string: declination, azimuth, Wp, optional entity+correction."""
        i = self._current_string

        if user_input is not None:
            # Map static form keys -> storage keys with index
            self._data[conf_string_name(i)] = user_input.get(CONF_STR_NAME, f"String {i}")
            self._data[conf_declination(i)] = user_input[CONF_STR_DECLINATION]
            self._data[conf_azimuth(i)] = user_input[CONF_STR_AZIMUTH]
            self._data[conf_wp(i)] = user_input[CONF_STR_WP]

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
                return self.async_create_entry(
                    title=self._data.get(CONF_NAME, DEFAULT_NAME),
                    data=self._data,
                )

        return self.async_show_form(
            step_id="string",
            description_placeholders={
                "index": str(i),
                "total": str(self._string_count),
            },
            data_schema=vol.Schema(
                {
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
                    vol.Optional(CONF_STR_ACTUAL_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="energy",
                            multiple=False,
                        )
                    ),
                    vol.Optional(CONF_STR_CORRECTION): vol.Any(
                        None,
                        vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0)),
                    ),
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

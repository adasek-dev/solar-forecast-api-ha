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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Basic config + number of strings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not await validate_api(DEFAULT_API_URL):
                errors["base"] = "cannot_connect"
            else:
                self._string_count = user_input.get(CONF_STRING_COUNT, 1)
                self._data = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_API_KEY: user_input.get(CONF_API_KEY, ""),
                    CONF_LATITUDE: user_input[CONF_LATITUDE],
                    CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                    CONF_STRING_COUNT: self._string_count,
                }
                self._current_string = 1
                return await self.async_step_string()

        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

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
            # Save string data
            self._data[conf_string_name(i)] = user_input.get(conf_string_name(i), f"String {i}")
            self._data[conf_declination(i)] = user_input[conf_declination(i)]
            self._data[conf_azimuth(i)] = user_input[conf_azimuth(i)]
            self._data[conf_wp(i)] = user_input[conf_wp(i)]

            # Optional entity
            entity = user_input.get(conf_actual_entity(i), "")
            if entity:
                self._data[conf_actual_entity(i)] = entity

            # Optional correction - only save if provided
            correction_raw = user_input.get(conf_correction(i))
            if correction_raw is not None and correction_raw != 0.0:
                self._data[conf_correction(i)] = float(correction_raw)

            # Next string or finish
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
            description_placeholders={"index": str(i), "total": str(self._string_count)},
            data_schema=vol.Schema(
                {
                    vol.Optional(conf_string_name(i), default=f"String {i}"): str,
                    vol.Required(conf_declination(i), default=35): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=90)
                    ),
                    vol.Required(conf_azimuth(i), default=0): vol.All(
                        vol.Coerce(float), vol.Range(min=-180, max=180)
                    ),
                    vol.Required(conf_wp(i), default=5000): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=100000)
                    ),
                    vol.Optional(conf_actual_entity(i)): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="energy",
                            multiple=False,
                        )
                    ),
                    vol.Optional(conf_correction(i)): vol.Any(
                        None,
                        vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0)),
                    ),
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

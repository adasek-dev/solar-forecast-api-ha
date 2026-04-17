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
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_DECLINATION,
    CONF_AZIMUTH,
    CONF_KWP,
    CONF_DECLINATION_2,
    CONF_AZIMUTH_2,
    CONF_KWP_2,
    CONF_NAME,
    CONF_SECOND_PLANE,
    CONF_ACTUAL_ENTITY,
    CONF_CORRECTION,
    DEFAULT_NAME,
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

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Basic config."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Test API connection
            if not await validate_api(DEFAULT_API_URL):
                errors["base"] = "cannot_connect"
            else:
                self._data = user_input
                return await self.async_step_plane2()

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
                    vol.Required(CONF_DECLINATION, default=35): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=90)
                    ),
                    vol.Required(CONF_AZIMUTH, default=0): vol.All(
                        vol.Coerce(float), vol.Range(min=-180, max=180)
                    ),
                    vol.Required(CONF_KWP, default=5.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0.1, max=1000000)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_plane2(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Second plane + options."""
        if user_input is not None:
            if user_input.get(CONF_SECOND_PLANE, False):
                self._data[CONF_DECLINATION_2] = user_input.get(CONF_DECLINATION_2, 0)
                self._data[CONF_AZIMUTH_2] = user_input.get(CONF_AZIMUTH_2, 0)
                self._data[CONF_KWP_2] = user_input.get(CONF_KWP_2, 0)

            # Actual entity & correction
            actual = user_input.get(CONF_ACTUAL_ENTITY, "")
            if actual:
                self._data[CONF_ACTUAL_ENTITY] = actual

            correction = user_input.get(CONF_CORRECTION, 0)
            if correction and correction > 0:
                self._data[CONF_CORRECTION] = correction

            return self.async_create_entry(
                title=self._data.get(CONF_NAME, DEFAULT_NAME),
                data=self._data,
            )

        return self.async_show_form(
            step_id="plane2",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SECOND_PLANE, default=False): bool,
                    vol.Optional(CONF_DECLINATION_2, default=35): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=90)
                    ),
                    vol.Optional(CONF_AZIMUTH_2, default=0): vol.All(
                        vol.Coerce(float), vol.Range(min=-180, max=180)
                    ),
                    vol.Optional(CONF_KWP_2, default=5.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0.1, max=1000000)
                    ),
                    vol.Optional(CONF_ACTUAL_ENTITY, default=""): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="energy",
                            multiple=False,
                        )
                    ),
                    vol.Optional(CONF_CORRECTION, default=0): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=1.5)
                    ),
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

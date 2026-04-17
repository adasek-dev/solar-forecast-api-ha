"""DataUpdateCoordinator for Solar Forecast API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_API_URL,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_DECLINATION,
    CONF_AZIMUTH,
    CONF_KWP,
    CONF_DECLINATION_2,
    CONF_AZIMUTH_2,
    CONF_KWP_2,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SolarForecastData:
    """Parsed solar forecast data."""

    def __init__(self, raw: dict[str, Any]) -> None:
        """Initialize from API response."""
        self.raw = raw
        result = raw.get("result", {})

        # watts: {"2026-04-15 07:00:00": 129, ...}
        self.watts = result.get("watts", {})
        # watt_hours: cumulative per day
        self.watt_hours = result.get("watt_hours", {})
        # watt_hours_period: per period
        self.watt_hours_period = result.get("watt_hours_period", {})
        # watt_hours_day: {"2026-04-15": 17234, ...}
        self.watt_hours_day = result.get("watt_hours_day", {})

        # Parse correction factor
        msg = raw.get("message", {})
        info = msg.get("info", {})
        self.correction = info.get("correction")

    @property
    def sorted_days(self) -> list[str]:
        """Get sorted list of forecast days."""
        return sorted(self.watt_hours_day.keys())

    @property
    def today(self) -> str | None:
        """Get today's date string."""
        days = self.sorted_days
        return days[0] if days else None

    @property
    def tomorrow(self) -> str | None:
        """Get tomorrow's date string."""
        days = self.sorted_days
        return days[1] if len(days) > 1 else None

    @property
    def energy_today(self) -> float | None:
        """Total energy forecast today in kWh."""
        if self.today:
            return round(self.watt_hours_day.get(self.today, 0) / 1000, 2)
        return None

    @property
    def energy_tomorrow(self) -> float | None:
        """Total energy forecast tomorrow in kWh."""
        if self.tomorrow:
            return round(self.watt_hours_day.get(self.tomorrow, 0) / 1000, 2)
        return None

    @property
    def power_now(self) -> int:
        """Current estimated power in W."""
        now = datetime.now()
        current_key = now.strftime("%Y-%m-%d %H:00:00")
        return self.watts.get(current_key, 0)

    @property
    def peak_power_today(self) -> int:
        """Peak power today in W."""
        if not self.today:
            return 0
        return max(
            (w for k, w in self.watts.items() if k.startswith(self.today)),
            default=0,
        )

    @property
    def peak_time_today(self) -> str | None:
        """Time of peak power today."""
        if not self.today:
            return None
        today_watts = {k: w for k, w in self.watts.items() if k.startswith(self.today)}
        if not today_watts:
            return None
        peak_key = max(today_watts, key=today_watts.get)
        return peak_key

    @property
    def peak_power_tomorrow(self) -> int:
        """Peak power tomorrow in W."""
        if not self.tomorrow:
            return 0
        return max(
            (w for k, w in self.watts.items() if k.startswith(self.tomorrow)),
            default=0,
        )

    @property
    def peak_time_tomorrow(self) -> str | None:
        """Time of peak power tomorrow."""
        if not self.tomorrow:
            return None
        tmrw_watts = {k: w for k, w in self.watts.items() if k.startswith(self.tomorrow)}
        if not tmrw_watts:
            return None
        peak_key = max(tmrw_watts, key=tmrw_watts.get)
        return peak_key

    @property
    def energy_remaining_today(self) -> float | None:
        """Remaining energy today in kWh."""
        if not self.today:
            return None
        now = datetime.now()
        current_key = now.strftime("%Y-%m-%d %H:00:00")
        remaining = sum(
            w for k, w in self.watts.items()
            if k.startswith(self.today) and k >= current_key
        )
        return round(remaining / 1000, 2)

    @property
    def energy_next_hour(self) -> float | None:
        """Energy forecast for next hour in kWh."""
        now = datetime.now()
        next_key = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")
        w = self.watts.get(next_key, 0)
        return round(w / 1000, 2)

    @property
    def hourly_forecast(self) -> list[dict]:
        """Hourly forecast as list of dicts for graph attributes."""
        result = []
        for k in sorted(self.watts.keys()):
            result.append({
                "datetime": k,
                "power": self.watts[k],
            })
        return result


class SolarForecastCoordinator(DataUpdateCoordinator[SolarForecastData]):
    """Coordinator to fetch data from Solar Forecast API."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.config = config
        self._build_url()

    def _build_url(self) -> None:
        """Build the API URL from config."""
        base = self.config[CONF_API_URL].rstrip("/")
        api_key = self.config.get(CONF_API_KEY, "")
        lat = self.config[CONF_LATITUDE]
        lon = self.config[CONF_LONGITUDE]
        dec = self.config[CONF_DECLINATION]
        az = self.config[CONF_AZIMUTH]
        kwp = self.config[CONF_KWP]

        # Build path
        if api_key:
            path = f"/estimate/{api_key}"
        else:
            path = "/estimate"

        path += f"/{lat}/{lon}/{dec}/{az}/{kwp}"

        # Second plane
        dec2 = self.config.get(CONF_DECLINATION_2)
        az2 = self.config.get(CONF_AZIMUTH_2)
        kwp2 = self.config.get(CONF_KWP_2)
        if dec2 and kwp2 and kwp2 > 0:
            path += f"/{dec2}/{az2}/{kwp2}"

        self.api_url = f"{base}{path}?days=7"
        _LOGGER.info("Solar Forecast API URL: %s", self.api_url)

    async def _async_update_data(self) -> SolarForecastData:
        """Fetch data from API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.api_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        raise UpdateFailed(f"HTTP {resp.status}")
                    data = await resp.json()

            if "error" in data and data.get("error"):
                raise UpdateFailed(data.get("message", "Unknown error"))

            return SolarForecastData(data)

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error: {err}") from err

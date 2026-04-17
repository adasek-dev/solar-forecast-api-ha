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
    DEFAULT_API_URL,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STRING_COUNT,
    UPDATE_INTERVAL,
    conf_string_name,
    conf_declination,
    conf_azimuth,
    conf_wp,
    conf_actual_entity,
    conf_correction,
)

_LOGGER = logging.getLogger(__name__)


class StringForecastData:
    """Parsed solar forecast data for one string."""

    def __init__(self, raw: dict[str, Any], string_name: str) -> None:
        """Initialize from API response."""
        self.raw = raw
        self.string_name = string_name
        result = raw.get("result", {})

        self.watts = result.get("watts", {})
        self.watt_hours = result.get("watt_hours", {})
        self.watt_hours_period = result.get("watt_hours_period", {})
        self.watt_hours_day = result.get("watt_hours_day", {})

        msg = raw.get("message", {})
        info = msg.get("info", {})
        self.correction = info.get("correction")

    @property
    def sorted_days(self) -> list[str]:
        return sorted(self.watt_hours_day.keys())

    @property
    def today(self) -> str | None:
        days = self.sorted_days
        return days[0] if days else None

    @property
    def tomorrow(self) -> str | None:
        days = self.sorted_days
        return days[1] if len(days) > 1 else None

    @property
    def energy_today(self) -> float | None:
        if self.today:
            return round(self.watt_hours_day.get(self.today, 0) / 1000, 2)
        return None

    @property
    def energy_tomorrow(self) -> float | None:
        if self.tomorrow:
            return round(self.watt_hours_day.get(self.tomorrow, 0) / 1000, 2)
        return None

    @property
    def power_now(self) -> int:
        now = datetime.now()
        current_key = now.strftime("%Y-%m-%d %H:00:00")
        return self.watts.get(current_key, 0)

    @property
    def peak_power_today(self) -> int:
        if not self.today:
            return 0
        return max(
            (w for k, w in self.watts.items() if k.startswith(self.today)),
            default=0,
        )

    @property
    def peak_time_today(self) -> str | None:
        if not self.today:
            return None
        today_watts = {k: w for k, w in self.watts.items() if k.startswith(self.today)}
        if not today_watts:
            return None
        return max(today_watts, key=today_watts.get)

    @property
    def peak_power_tomorrow(self) -> int:
        if not self.tomorrow:
            return 0
        return max(
            (w for k, w in self.watts.items() if k.startswith(self.tomorrow)),
            default=0,
        )

    @property
    def peak_time_tomorrow(self) -> str | None:
        if not self.tomorrow:
            return None
        tmrw_watts = {k: w for k, w in self.watts.items() if k.startswith(self.tomorrow)}
        if not tmrw_watts:
            return None
        return max(tmrw_watts, key=tmrw_watts.get)

    @property
    def energy_remaining_today(self) -> float | None:
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
        now = datetime.now()
        next_key = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")
        return round(self.watts.get(next_key, 0) / 1000, 2)

    @property
    def hourly_forecast(self) -> list[dict]:
        return [{"datetime": k, "power": self.watts[k]} for k in sorted(self.watts.keys())]


class SolarForecastData:
    """Combined data for all strings."""

    def __init__(self, strings: list[StringForecastData]) -> None:
        self.strings = strings

    def _sum_float(self, getter) -> float:
        total = 0.0
        for s in self.strings:
            val = getter(s)
            if val is not None:
                total += val
        return round(total, 2)

    @property
    def power_now(self) -> int:
        return sum(s.power_now for s in self.strings)

    @property
    def energy_today(self) -> float:
        return self._sum_float(lambda s: s.energy_today)

    @property
    def energy_tomorrow(self) -> float:
        return self._sum_float(lambda s: s.energy_tomorrow)

    @property
    def energy_remaining_today(self) -> float:
        return self._sum_float(lambda s: s.energy_remaining_today)

    @property
    def energy_next_hour(self) -> float:
        return self._sum_float(lambda s: s.energy_next_hour)

    @property
    def peak_power_today(self) -> int:
        # Peak of combined watts per hour
        all_keys = set()
        for s in self.strings:
            all_keys.update(s.watts.keys())
        if not all_keys or not self.strings[0].today:
            return 0
        today = self.strings[0].today
        return max(
            (sum(s.watts.get(k, 0) for s in self.strings) for k in all_keys if k.startswith(today)),
            default=0,
        )

    @property
    def peak_time_today(self) -> str | None:
        all_keys = set()
        for s in self.strings:
            all_keys.update(s.watts.keys())
        if not all_keys or not self.strings[0].today:
            return None
        today = self.strings[0].today
        today_keys = [k for k in all_keys if k.startswith(today)]
        if not today_keys:
            return None
        return max(today_keys, key=lambda k: sum(s.watts.get(k, 0) for s in self.strings))

    @property
    def peak_power_tomorrow(self) -> int:
        all_keys = set()
        for s in self.strings:
            all_keys.update(s.watts.keys())
        if not all_keys or not self.strings[0].tomorrow:
            return 0
        tomorrow = self.strings[0].tomorrow
        return max(
            (sum(s.watts.get(k, 0) for s in self.strings) for k in all_keys if k.startswith(tomorrow)),
            default=0,
        )

    @property
    def peak_time_tomorrow(self) -> str | None:
        all_keys = set()
        for s in self.strings:
            all_keys.update(s.watts.keys())
        if not all_keys or not self.strings[0].tomorrow:
            return None
        tomorrow = self.strings[0].tomorrow
        tmrw_keys = [k for k in all_keys if k.startswith(tomorrow)]
        if not tmrw_keys:
            return None
        return max(tmrw_keys, key=lambda k: sum(s.watts.get(k, 0) for s in self.strings))

    @property
    def hourly_forecast(self) -> list[dict]:
        all_keys = set()
        for s in self.strings:
            all_keys.update(s.watts.keys())
        return [
            {"datetime": k, "power": sum(s.watts.get(k, 0) for s in self.strings)}
            for k in sorted(all_keys)
        ]

    @property
    def watt_hours_day(self) -> dict:
        combined: dict[str, float] = {}
        for s in self.strings:
            for day, val in s.watt_hours_day.items():
                combined[day] = combined.get(day, 0) + val
        return combined

    @property
    def correction(self):
        # Return correction from first string that has one
        for s in self.strings:
            if s.correction is not None:
                return s.correction
        return None


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
        self.hass = hass

    def _get_strings(self) -> list[dict]:
        """Get list of string configs, supporting both new and legacy format."""
        string_count = self.config.get(CONF_STRING_COUNT)

        if string_count:
            # New multi-string format
            strings = []
            for i in range(1, string_count + 1):
                wp = self.config.get(conf_wp(i), 5000)
                strings.append({
                    "name": self.config.get(conf_string_name(i), f"String {i}"),
                    "declination": self.config.get(conf_declination(i), 35),
                    "azimuth": self.config.get(conf_azimuth(i), 0),
                    "kwp": wp / 1000.0,  # convert Wp to kWp for API
                    "actual_entity": self.config.get(conf_actual_entity(i), ""),
                    "correction": self.config.get(conf_correction(i)),
                })
            return strings
        else:
            # Legacy format (old 2-plane config)
            strings = [{
                "name": "String 1",
                "declination": self.config.get("declination", 35),
                "azimuth": self.config.get("azimuth", 0),
                "kwp": self.config.get("kwp", 5.0),
                "actual_entity": self.config.get("actual_entity", ""),
                "correction": self.config.get("correction"),
            }]
            if self.config.get("second_plane") and self.config.get("kwp_2", 0) > 0:
                strings.append({
                    "name": "String 2",
                    "declination": self.config.get("declination_2", 35),
                    "azimuth": self.config.get("azimuth_2", 0),
                    "kwp": self.config.get("kwp_2", 5.0),
                    "actual_entity": "",
                    "correction": self.config.get("correction"),
                })
            return strings

    def _build_url(self, string_cfg: dict) -> str:
        """Build API URL for a single string."""
        base = DEFAULT_API_URL.rstrip("/")
        api_key = self.config.get(CONF_API_KEY, "")
        lat = self.config[CONF_LATITUDE]
        lon = self.config[CONF_LONGITUDE]
        dec = string_cfg["declination"]
        az = string_cfg["azimuth"]
        kwp = string_cfg["kwp"]

        if api_key:
            path = f"/estimate/{api_key}"
        else:
            path = "/estimate"

        path += f"/{lat}/{lon}/{dec}/{az}/{kwp}"

        params = ["days=7"]

        correction = string_cfg.get("correction")
        if correction is not None and correction > 0:
            params.append(f"correction={correction}")

        actual_entity = string_cfg.get("actual_entity", "")
        if actual_entity:
            state = self.hass.states.get(actual_entity)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    actual_kwh = float(state.state)
                    if actual_kwh > 0:
                        params.append(f"actual={actual_kwh}")
                except (ValueError, TypeError):
                    pass

        url = f"{base}{path}?{'&'.join(params)}"
        return url

    async def _fetch_string(self, session: aiohttp.ClientSession, string_cfg: dict) -> StringForecastData:
        """Fetch data for one string."""
        url = self._build_url(string_cfg)
        _LOGGER.debug("Fetching solar forecast for %s: %s", string_cfg["name"], url)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise UpdateFailed(f"HTTP {resp.status} for string {string_cfg['name']}")
            data = await resp.json()
        if "error" in data and data.get("error"):
            raise UpdateFailed(data.get("message", "Unknown error"))
        return StringForecastData(data, string_cfg["name"])

    async def _async_update_data(self) -> SolarForecastData:
        """Fetch data from API for all strings."""
        strings_cfg = self._get_strings()
        try:
            async with aiohttp.ClientSession() as session:
                string_data = []
                for cfg in strings_cfg:
                    data = await self._fetch_string(session, cfg)
                    string_data.append(data)
            return SolarForecastData(string_data)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error: {err}") from err

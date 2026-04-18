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
    CONF_FEATURE_ACTUAL,
    CONF_FEATURE_CALIBRATION,
    CONF_FEATURE_TIMEWINDOWS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STRING_COUNT,
    CONF_UPDATE_INTERVAL,
    CONF_DAYS,
    CONF_DAMPING,
    CONF_NO_HORIZON,
    CONF_RESOLUTION,
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
        self.actual_info = info.get("actual")

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

    def energy_for_day(self, day_offset: int) -> float | None:
        days = self.sorted_days
        if len(days) > day_offset:
            return round(self.watt_hours_day.get(days[day_offset], 0) / 1000, 2)
        return None


class WeatherData:
    """Weather forecast data from /weather endpoint."""

    def __init__(self, raw: list[dict]) -> None:
        self.entries = raw

    @property
    def current(self) -> dict | None:
        now = datetime.now()
        current_key = now.strftime("%Y-%m-%d %H:00:00")
        for e in self.entries:
            if e.get("datetime") == current_key:
                return e
        return self.entries[0] if self.entries else None

    @property
    def temperature_now(self) -> float | None:
        c = self.current
        return c.get("temperature") if c else None

    @property
    def sky_now(self) -> float | None:
        c = self.current
        return c.get("sky") if c else None

    @property
    def condition_now(self) -> str | None:
        c = self.current
        return c.get("condition") if c else None

    @property
    def wind_speed_now(self) -> float | None:
        c = self.current
        return c.get("wind_speed") if c else None

    @property
    def wind_direction_now(self) -> str | None:
        c = self.current
        return c.get("wind_direction") if c else None


class SolarForecastData:
    """Combined data for all strings + weather + timewindows."""

    def __init__(
        self,
        strings: list[StringForecastData],
        weather: WeatherData | None = None,
        timewindows: list[dict] | None = None,
        horizon: dict | None = None,
    ) -> None:
        self.strings = strings
        self.weather = weather
        self.timewindows = timewindows or []
        self.horizon = horizon

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

    def energy_for_day(self, day_offset: int) -> float:
        return self._sum_float(lambda s: s.energy_for_day(day_offset))

    @property
    def peak_power_today(self) -> int:
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
        for s in self.strings:
            if s.correction is not None:
                return s.correction
        return None


class SolarForecastCoordinator(DataUpdateCoordinator[SolarForecastData]):
    """Coordinator to fetch data from Solar Forecast API."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=config.get(CONF_UPDATE_INTERVAL, UPDATE_INTERVAL)),
        )
        self.config = config
        self.hass = hass

    def _get_strings(self) -> list[dict]:
        string_count = self.config.get(CONF_STRING_COUNT)
        if string_count:
            strings = []
            for i in range(1, string_count + 1):
                wp = self.config.get(conf_wp(i), 5000)
                strings.append({
                    "name": self.config.get(conf_string_name(i), f"String {i}"),
                    "declination": self.config.get(conf_declination(i), 35),
                    "azimuth": self.config.get(conf_azimuth(i), 0),
                    "kwp": wp / 1000.0,
                    "actual_entity": self.config.get(conf_actual_entity(i), ""),
                    "correction": self.config.get(conf_correction(i)),
                })
            return strings
        else:
            # Legacy
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

    def _build_combined_url(self, strings_cfg: list[dict]) -> str:
        """Build a single URL with ALL strings – same as node-red convention.
        This ensures the server uses one calibration hash for the whole installation.
        """
        base = DEFAULT_API_URL.rstrip("/")
        api_key = self.config.get(CONF_API_KEY, "")
        lat = self.config[CONF_LATITUDE]
        lon = self.config[CONF_LONGITUDE]
        days = self.config.get(CONF_DAYS, 4)
        resolution = self.config.get(CONF_RESOLUTION, 60)
        damping = self.config.get(CONF_DAMPING, 0.0)
        no_horizon = self.config.get(CONF_NO_HORIZON, False)
        feature_actual_on = self.config.get(CONF_FEATURE_ACTUAL, True)

        path = f"/estimate/{api_key}" if api_key else "/estimate"
        path += f"/{lat}/{lon}"

        # Append all strings: /dec1/az1/kwp1/dec2/az2/kwp2/...
        for s in strings_cfg:
            path += f"/{s['declination']}/{s['azimuth']}/{s['kwp']}"

        params = [f"days={days}"]
        if resolution == 15 and api_key:
            params.append("resolution=15")
        if damping and damping > 0:
            params.append(f"damping={damping}")
        if no_horizon:
            params.append("no_horizon=1")

        # Use correction from first string that has one
        for s in strings_cfg:
            correction = s.get("correction")
            if correction is not None and correction > 0:
                params.append(f"correction={correction}")
                break

        # Use actual from first string that has an entity
        if feature_actual_on:
            for s in strings_cfg:
                actual_entity = s.get("actual_entity", "")
                if actual_entity:
                    state = self.hass.states.get(actual_entity)
                    if state and state.state not in ("unknown", "unavailable"):
                        try:
                            actual_kwh = float(state.state)
                            if actual_kwh > 0:
                                params.append(f"actual={actual_kwh}")
                        except (ValueError, TypeError):
                            pass
                    break

        return f"{base}{path}?{'&'.join(params)}"

    def _build_weather_url(self) -> str | None:
        api_key = self.config.get(CONF_API_KEY, "")
        if not api_key:
            return None
        base = DEFAULT_API_URL.rstrip("/")
        lat = self.config[CONF_LATITUDE]
        lon = self.config[CONF_LONGITUDE]
        days = self.config.get(CONF_DAYS, 4)
        return f"{base}/weather/{api_key}/{lat}/{lon}?days={days}"

    def _build_horizon_url(self) -> str:
        base = DEFAULT_API_URL.rstrip("/")
        lat = self.config[CONF_LATITUDE]
        lon = self.config[CONF_LONGITUDE]
        return f"{base}/horizon/{lat}/{lon}"

    async def _fetch_combined(
        self, session: aiohttp.ClientSession, strings_cfg: list[dict]
    ) -> "SolarForecastData":
        """Fetch all strings in a single API request (same calibration hash as node-red)."""
        url = self._build_combined_url(strings_cfg)
        _LOGGER.debug("Fetching solar forecast (combined %d strings): %s", len(strings_cfg), url)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise UpdateFailed(f"HTTP {resp.status}")
            data = await resp.json(content_type=None)
        if "error" in data and data.get("error"):
            raise UpdateFailed(data.get("message", "Unknown error"))

        # The server returns combined watts for all strings together.
        # Wrap as a single StringForecastData; per-string breakdown is not available
        # when using combined URL (server sums internally). We create one entry
        # representing the whole installation and mark it as combined.
        combined_name = " + ".join(s["name"] for s in strings_cfg)
        return StringForecastData(data, combined_name)

    async def _fetch_weather(self, session: aiohttp.ClientSession) -> WeatherData | None:
        url = self._build_weather_url()
        if not url:
            return None
        try:
            _LOGGER.debug("Fetching weather: %s", url)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 403:
                    _LOGGER.debug("Weather endpoint not available for this API key")
                    return None
                if resp.status != 200:
                    _LOGGER.warning("Weather fetch HTTP %s", resp.status)
                    return None
                data = await resp.json()
                if "error" in data and data.get("error"):
                    _LOGGER.debug("Weather error: %s", data.get("message"))
                    return None
                return WeatherData(data.get("result", []))
        except Exception as err:
            _LOGGER.warning("Weather fetch failed: %s", err)
            return None

    async def _fetch_horizon(self, session: aiohttp.ClientSession) -> dict | None:
        url = self._build_horizon_url()
        try:
            _LOGGER.debug("Fetching horizon: %s", url)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if "error" in data and data.get("error"):
                    return None
                return data
        except Exception as err:
            _LOGGER.warning("Horizon fetch failed: %s", err)
            return None

    async def _async_update_data(self) -> SolarForecastData:
        strings_cfg = self._get_strings()
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch ALL strings in ONE combined request (same as node-red)
                # This ensures the same calibration hash as manual API calls
                combined = await self._fetch_combined(session, strings_cfg)

                # Fetch weather (optional, needs API key with feature)
                weather = await self._fetch_weather(session)

                # Fetch horizon (always available)
                horizon = await self._fetch_horizon(session)

            # Wrap combined result as single-string list for SolarForecastData
            return SolarForecastData([combined], weather, horizon=horizon)

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error: {err}") from err

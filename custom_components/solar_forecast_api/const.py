"""Constants for Solar Forecast API integration."""

DOMAIN = "solar_forecast_api"
DEFAULT_API_URL = "https://forecast.xnas.cz"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_NAME = "name"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_DAYS = "days"
CONF_DAMPING = "damping"
CONF_NO_HORIZON = "no_horizon"
CONF_RESOLUTION = "resolution"

# Per-string config keys (up to 10 strings)
MAX_STRINGS = 10
CONF_STRING_COUNT = "string_count"

# Static form field keys (displayed in UI, translated)
CONF_STR_NAME = "str_name"
CONF_STR_DECLINATION = "str_declination"
CONF_STR_AZIMUTH = "str_azimuth"
CONF_STR_WP = "str_wp"
CONF_STR_ACTUAL_ENTITY = "str_actual_entity"
CONF_STR_CORRECTION = "str_correction"


def conf_string_name(i: int) -> str:
    return f"string_{i}_name"


def conf_declination(i: int) -> str:
    return f"string_{i}_declination"


def conf_azimuth(i: int) -> str:
    return f"string_{i}_azimuth"


def conf_wp(i: int) -> str:
    return f"string_{i}_wp"


def conf_actual_entity(i: int) -> str:
    return f"string_{i}_actual_entity"


def conf_correction(i: int) -> str:
    return f"string_{i}_correction"


# Legacy keys (kept for backward compatibility)
CONF_DECLINATION = "declination"
CONF_AZIMUTH = "azimuth"
CONF_KWP = "kwp"
CONF_DECLINATION_2 = "declination_2"
CONF_AZIMUTH_2 = "azimuth_2"
CONF_KWP_2 = "kwp_2"
CONF_SECOND_PLANE = "second_plane"
CONF_ACTUAL_ENTITY = "actual_entity"
CONF_CORRECTION = "correction"

DEFAULT_NAME = "Solar Forecast"
UPDATE_INTERVAL = 3600       # default 60 minut v sekundách

INTERVAL_OPTIONS = [5, 15, 30, 45, 60]   # minuty
DAYS_OPTIONS = [1, 2, 3, 4, 5, 6, 7]

"""Constants for Solar Forecast API integration."""

DOMAIN = "solar_forecast_api"
DEFAULT_API_URL = "https://forecast.xnas.cz"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_NAME = "name"

# Per-string config keys (up to 10 strings)
MAX_STRINGS = 10
CONF_STRING_COUNT = "string_count"


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
UPDATE_INTERVAL = 1800  # 30 minut

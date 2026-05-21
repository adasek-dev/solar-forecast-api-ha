# Solar Forecast API - Home Assistant Integration

Custom Home Assistant integration for [Solar Forecast API](https://github.com/YOUR-USERNAME/solar-forecast-api) - self-hosted solar production forecast.

Uses Open-Meteo (weather) + pvlib (solar model) + PVGIS (horizon) as a free, unlimited replacement for forecast.solar.

## Features

- Solar production forecast (today + 6 days)
- Multiple panel planes in one config (east/west roof etc.)
- PVGIS horizon (automatic terrain shading)
- Auto-calibration via actual production data
- Weather forecast endpoint
- Time windows for controllable loads
- API keys with per-user rate limiting
- forecast.solar compatible API format

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right → **Custom repositories**
3. Add URL: `https://github.com/YOUR-USERNAME/solar-forecast-api-ha`
4. Category: **Integration**
5. Click **Add**
6. Search for "Solar Forecast API" and install
7. Restart Home Assistant

### Manual

1. Download the latest release
2. Copy `custom_components/solar_forecast_api/` to your HA `custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Solar Forecast API**
3. Enter:
   - **Name**: e.g. "East+West"
   - **API URL**: `http://YOUR-SERVER-IP:5001`
   - **API Key**: your key (optional)
   - **Latitude/Longitude**: your location
   - **Declination**: panel tilt (0-90°)
   - **Azimuth**: panel orientation, forecast.solar convention (0=south, -90=east, 90=west)
   - **kWp**: installed power
4. Optionally add a second panel plane

You can add the integration multiple times for different configurations.

## Sensors

| Sensor | Description | Unit |
|--------|-------------|------|
| Estimated power production - now | Current estimated power | W |
| Estimated energy production - today | Total forecast today | kWh |
| Estimated energy production - tomorrow | Total forecast tomorrow | kWh |
| Estimated energy production - remaining today | Remaining energy today | kWh |
| Estimated energy production - next hour | Next hour forecast | kWh |
| Highest power - today | Peak power today | W |
| Peak time - today | Time of peak power | datetime |
| Highest power - tomorrow | Peak power tomorrow | W |
| Peak time - tomorrow | Time of peak power | datetime |

## Azimuth Convention

This integration uses the **forecast.solar** azimuth convention:

| Direction | Azimuth |
|-----------|---------|
| North | ±180° |
| East | -90° |
| South | 0° |
| West | 90° |

**Conversion from pvlib/HA (0=North):** `azimuth_fs = azimuth_pvlib - 180`

## Requirements

You need a running Solar Forecast API server. See the [server repository](https://github.com/YOUR-USERNAME/solar-forecast-api) for setup instructions.

## License

MIT

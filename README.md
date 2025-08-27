# PubliBike Stations — Home Assistant Custom Integration

This custom integration adds availability sensors for a single PubliBike station in Switzerland.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

## Features

- Interactive setup flow:
  - Type part of the station name, city, or address to search.
  - If multiple stations match (e.g., “Bahnhof”), pick the right one from a dropdown.
- Sensors provided:
  - Bikes available
  - E-bikes available
  - Station state (e.g., Active, Active (empty), Inactive)
- Rich attributes on all sensors: station ID, name, city, address, ZIP, coordinates, and capacity.
- Options flow to change the selected station later without re-adding the integration.
- Cloud polling of the PubliBike public API every 5 minutes.
- Unique IDs for all entities.

See below for examples, troubleshooting, and notes.

## Installation

You can install manually or as a custom repository in HACS.

### Manual installation

1. Copy the `custom_components/publibike_stations` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

### HACS (Custom repository)

1. Open HACS → Integrations.
2. Click the three-dots menu → Custom repositories.
3. Add your repository URL and select category “Integration”.
4. Install the integration.
5. Restart Home Assistant.

Now you are ready to add one or more instances of the integration.

## Setup

- Open Home Assistant Settings → Devices & Services.
- Click “Add Integration”.
- Search for “PubliBike Stations” and proceed.
- Enter a search term for your station (you can type part of the name, city, or address).
  - If more than one station matches, you will get a dropdown to select the exact station.
- Finish the setup. Your sensors are created immediately.

Tip: You can later change the station via the integration’s “Configure” option (Options Flow).

## Configuration and data sources

- Search API:
  - GET https://rest.publibike.ch/v1/public/all/stations
  - Used during setup/options to find your station by name.
- Station detail API (polled every 5 minutes):
  - GET https://rest.publibike.ch/v1/public/stations/[STATIONID]
  - Used to determine:
    - Bikes available
    - E-bikes available
    - Station state

E-bikes are detected from the vehicle type information provided by the API.

## Entities created

You will get three sensors (the exact entity IDs depend on your chosen station name):

- Bikes available
  - Example: `sensor.piazza_molino_nuovo_bikes_available`
- E-bikes available
  - Example: `sensor.piazza_molino_nuovo_e_bikes_available`
- Station state
  - Example: `sensor.piazza_molino_nuovo_station_state`

All sensors include attributes such as station ID, city, address, ZIP, latitude/longitude, and capacity.

## Examples

### Notify when an e-bike becomes available

```yaml
alias: Notify when e-bike available
trigger:
  - platform: numeric_state
    entity_id: sensor.publibike_station_e_bikes_available
    above: 0
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "An e-bike is now available at your PubliBike station."
      title: "PubliBike"
mode: single
```

Replace `sensor.publibike_station_e_bikes_available` with your actual entity ID.

### Create a helper sensor for total vehicles

```yaml
template:
  - sensor:
      - name: "PubliBike total vehicles"
        unique_id: publibike_total_vehicles_example
        state: >-
          {{
            (states('sensor.publibike_station_bikes_available')|int(0)) +
            (states('sensor.publibike_station_e_bikes_available')|int(0))
          }}
```

Replace the entity IDs to match your station’s sensors.

## Branding (Logo and Icon)

This integration ships with local brand assets so the integration tile shows a proper logo/icon:

- `custom_components/publibike_stations/icon.svg` (square icon)
- `custom_components/publibike_stations/logo.svg` (horizontal logo)

If distributing publicly (e.g., via HACS default), consider contributing the same assets to the official brands repository so users get consistent branding without local files:
- https://github.com/home-assistant/brands
- Path: `custom_integrations/publibike_stations/` (include `icon.svg`/`icon.png`, `logo.svg`/`logo.png`).

## Troubleshooting

- “Unknown error occurred” during station selection:
  - Make sure you’re on version 0.1.2 or newer. The selection step uses a simple, widely compatible dropdown (no special UI selectors required).
- API/network issues:
  - The PubliBike API is polled every 5 minutes. If the service is down or unreachable, sensors may briefly show unavailable.
- Enable debug logging:

```yaml
logger:
  default: warning
  logs:
    aiohttp.client: debug
    custom_components.publibike_stations: debug
```

Then restart Home Assistant and check your logs.

## Upgrade notes

- Switching stations:
  - Use the integration’s “Configure” → search and pick a new station. No need to remove or re-add the integration.
- Entities and unique IDs:
  - Entities come with stable unique IDs. If you rename entities, the names will persist across updates.

## Privacy

This integration calls the public PubliBike API:
- https://rest.publibike.ch
- No credentials or personal information are sent.
- Only the selected station ID is used during polling.

## Support

- Issues and feature requests: open an issue in your repository (e.g., GitHub issues for this integration).

---
© Your Name or Organization. Not affiliated with PubliBike.

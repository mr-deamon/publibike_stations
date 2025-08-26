from __future__ import annotations

DOMAIN = "publibike_stations"

API_BASE = "https://rest.publibike.ch/v1/public"
API_ALL_STATIONS = f"{API_BASE}/all/stations"
API_STATION_DETAIL = f"{API_BASE}/stations/{{station_id}}"

DEFAULT_UPDATE_INTERVAL_SECONDS = 300  # 5 minutes

CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_STATION_CITY = "station_city"
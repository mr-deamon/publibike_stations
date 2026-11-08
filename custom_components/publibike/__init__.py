from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import async_get_station_payload
from .const import (
    CONF_STATION_CITY,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_STATION_SOURCE,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
    STATION_SOURCE_PUBLIBIKE,
    STATION_SOURCE_VELOSPOT,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class PublibikeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        station_id: str,
        station_name: str,
        station_city: str,
        station_source: str,
    ) -> None:
        self._station_id = station_id
        self.station_name = station_name
        self.station_city = station_city
        self.station_source = station_source
        super().__init__(
            hass,
            _LOGGER,
            name=f"PubliBike Station {station_name} ({station_city})",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            payload = await async_get_station_payload(self.hass)
        except (asyncio.TimeoutError, ClientError) as err:
            raise UpdateFailed(f"Error communicating with PubliBike API: {err}") from err

        station: dict[str, Any] | None = None
        if self.station_source == STATION_SOURCE_VELOSPOT:
            for item in (payload.get("velospot") or {}).get("responseData") or []:
                if str(item.get("station_id") or "").strip() == self._station_id:
                    station = item
                    break
        else:
            for item in (payload.get("publibike") or {}).get("stations") or []:
                if str(item.get("id") or "").strip() == self._station_id:
                    station = item
                    break

        if station is None:
            raise UpdateFailed(f"Station not found in API response: {self.station_source}:{self._station_id}")

        if self.station_source == STATION_SOURCE_VELOSPOT:
            bikes = _to_int(station.get("totalNonElectricalBike"))
            ebikes = _to_int(station.get("totalElectricalBike"))
            total_bikes = _to_int(station.get("totalBike"))
            state_name = "Active" if total_bikes > 0 else "Empty"
            normalized_station = {
                "id": self._station_id,
                "name": station.get("station_name") or self.station_name,
                "city": self.station_city,
                "address": station.get("station_address"),
                "zip": None,
                "latitude": station.get("lat"),
                "longitude": station.get("lng"),
                "capacity": None,
                "state": state_name,
            }
        else:
            vehicles = station.get("vehicles", []) or []

            def is_ebike(vehicle: dict[str, Any]) -> bool:
                type_data = vehicle.get("type") or {}
                name = str(type_data.get("name") or "").strip().lower()
                type_id = type_data.get("id")
                return type_id == 2 or "e-bike" in name or name == "ebike" or name == "e_bike"

            ebikes = sum(1 for vehicle in vehicles if is_ebike(vehicle))
            bikes = len(vehicles) - ebikes

            state_name = ((station.get("state") or {}).get("name") or "").strip() or "Unknown"
            normalized_station = {
                "id": station.get("id") or self._station_id,
                "name": station.get("name") or self.station_name,
                "city": station.get("city") or self.station_city,
                "address": station.get("address"),
                "zip": station.get("zip"),
                "latitude": station.get("latitude"),
                "longitude": station.get("longitude"),
                "capacity": station.get("capacity"),
                "state": state_name,
            }

        normalized = {
            "raw": station,
            "counts": {
                "bikes": bikes,
                "ebikes": ebikes,
            },
            "station": normalized_station,
        }
        return normalized


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = {**entry.data, **entry.options}
    station_id = str(entry_data[CONF_STATION_ID])
    station_name = entry_data.get(CONF_STATION_NAME, station_id)
    station_city = entry_data.get(CONF_STATION_CITY, "")
    station_source = entry_data.get(CONF_STATION_SOURCE, STATION_SOURCE_PUBLIBIKE)

    coordinator = PublibikeCoordinator(hass, station_id, station_name, station_city, station_source)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
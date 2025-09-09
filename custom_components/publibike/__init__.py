from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    API_STATION_DETAIL,
    CONF_STATION_CITY,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class PublibikeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, station_id: int, station_name: str, station_city: str) -> None:
        self._station_id = station_id
        self.station_name = station_name
        self.station_city = station_city
        self.session = async_get_clientsession(hass)
        super().__init__(
            hass,
            _LOGGER,
            name=f"PubliBike Station {station_name} ({station_city})",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        url = API_STATION_DETAIL.format(station_id=self._station_id)
        try:
            async with self.session.get(url, headers={"Accept": "application/json"}) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise UpdateFailed(f"HTTP {resp.status} from PubliBike API: {text}")
                data = await resp.json()
        except (asyncio.TimeoutError, ClientError) as err:
            raise UpdateFailed(f"Error communicating with PubliBike API: {err}") from err

        # Normalize data for sensors
        vehicles = data.get("vehicles", []) or []

        def is_ebike(v: dict[str, Any]) -> bool:
            t = (v.get("type") or {})
            name = str(t.get("name") or "").strip().lower()
            type_id = t.get("id")
            # Heuristics: id 2 is typically E-Bike; name could be "E-Bike", "Ebike", etc.
            return type_id == 2 or "e-bike" in name or name == "ebike" or name == "e_bike"

        ebikes = sum(1 for v in vehicles if is_ebike(v))
        bikes = len(vehicles) - ebikes

        state_name = ((data.get("state") or {}).get("name") or "").strip() or "Unknown"

        normalized = {
            "raw": data,
            "counts": {
                "bikes": bikes,
                "ebikes": ebikes,
            },
            "station": {
                "id": data.get("id"),
                "name": data.get("name") or self.station_name,
                "city": data.get("city") or self.station_city,
                "address": data.get("address"),
                "zip": data.get("zip"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "capacity": data.get("capacity"),
                "state": state_name,
            },
        }
        return normalized


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    station_id = int(entry.data[CONF_STATION_ID])
    station_name = entry.data.get(CONF_STATION_NAME, str(station_id))
    station_city = entry.data.get(CONF_STATION_CITY, "")

    coordinator = PublibikeCoordinator(hass, station_id, station_name, station_city)
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
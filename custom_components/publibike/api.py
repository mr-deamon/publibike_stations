from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_ALL_STATIONS, DOMAIN

_CACHE_TTL_SECONDS = 30
_CACHE_KEY = "_station_payload_cache"
_LOCK_KEY = "_station_payload_lock"


async def async_get_station_payload(hass: HomeAssistant) -> dict[str, Any]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    cache = domain_data.get(_CACHE_KEY)
    if cache and monotonic() < cache["expires"]:
        return cache["data"]

    lock = domain_data.setdefault(_LOCK_KEY, asyncio.Lock())
    async with lock:
        cache = domain_data.get(_CACHE_KEY)
        if cache and monotonic() < cache["expires"]:
            return cache["data"]

        session = async_get_clientsession(hass)
        async with session.get(
            API_ALL_STATIONS, headers={"Accept": "application/json"}
        ) as response:
            response.raise_for_status()
            payload = await response.json()

        payload = payload or {}
        domain_data[_CACHE_KEY] = {
            "data": payload,
            "expires": monotonic() + _CACHE_TTL_SECONDS,
        }
        return payload
from __future__ import annotations

from typing import Any, Dict, List, Optional

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_ALL_STATIONS,
    CONF_STATION_CITY,
    CONF_STATION_DETAILS_URL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_STATION_SOURCE,
    DOMAIN,
    STATION_SOURCE_PUBLIBIKE,
    STATION_SOURCE_VELOSPOT,
)


async def _fetch_all_stations(hass: HomeAssistant) -> List[Dict[str, Any]]:
    session = async_get_clientsession(hass)
    async with session.get(API_ALL_STATIONS, headers={"Accept": "application/json"}) as resp:
        resp.raise_for_status()
        data = await resp.json()
        payload = data or {}
        legacy = (payload.get("publibike") or {}).get("stations") or []
        velospot = (payload.get("velospot") or {}).get("responseData") or []

        stations: List[Dict[str, Any]] = []
        for item in legacy:
            station_id = str(item.get("id") or "").strip()
            if not station_id:
                continue
            stations.append(
                {
                    "id": station_id,
                    "name": (item.get("name") or "").strip() or station_id,
                    "address": (item.get("address") or "").strip(),
                    "city": (item.get("city") or "").strip(),
                    "source": STATION_SOURCE_PUBLIBIKE,
                    "details_url": None,
                }
            )

        for item in velospot:
            station_id = str(item.get("station_id") or "").strip()
            if not station_id:
                continue
            stations.append(
                {
                    "id": station_id,
                    "name": (item.get("station_name") or "").strip() or station_id,
                    "address": (item.get("station_address") or "").strip(),
                    "city": "",
                    "source": STATION_SOURCE_VELOSPOT,
                    "details_url": (item.get("detailsRoute") or "").strip() or None,
                }
            )

        return stations


def _display_name(station: Dict[str, Any]) -> str:
    name = (station.get("name") or "").strip() or str(station.get("id") or "")
    if station.get("source") == STATION_SOURCE_PUBLIBIKE:
        return f"{name} (legacy)"
    return name


def _entry_title(station: Dict[str, Any]) -> str:
    name = (station.get("name") or "").strip() or str(station.get("id") or "")
    city = (station.get("city") or "").strip()
    if city:
        return f"{name} ({city})"
    return name


def _search_matches(stations: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    q = query.strip().casefold()
    if not q:
        return []
    # Prioritize exact name match, then substring in name/address/city
    exact = [s for s in stations if (s.get("name") or "").strip().casefold() == q]
    if exact:
        return exact
    return [
        s
        for s in stations
        if q in (s.get("name") or "").casefold()
        or q in (s.get("address") or "").casefold()
        or q in (s.get("city") or "").casefold()
    ]


class PublibikeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._matches: List[Dict[str, Any]] = []
        self._last_query: str | None = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            query = user_input["station_name"]
            self._last_query = query
            try:
                stations = await _fetch_all_stations(self.hass)
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            else:
                matches = _search_matches(stations, query)
                if not matches:
                    errors["base"] = "no_stations_found"
                elif len(matches) == 1:
                    station = matches[0]
                    unique_id = f'{station.get("source") or STATION_SOURCE_PUBLIBIKE}:{station["id"]}'
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    title = _entry_title(station)
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_STATION_ID: station["id"],
                            CONF_STATION_NAME: station.get("name") or str(station["id"]),
                            CONF_STATION_CITY: station.get("city") or "",
                            CONF_STATION_SOURCE: station.get("source") or STATION_SOURCE_PUBLIBIKE,
                            CONF_STATION_DETAILS_URL: station.get("details_url"),
                        },
                    )
                else:
                    # Multiple matches, go to selection step
                    self._matches = matches
                    return await self.async_step_select_station()

        schema = vol.Schema(
            {
                vol.Required(
                    "station_name",
                    default=self._last_query or "",
                ): str
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={},
        )

    async def async_step_select_station(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        # Build user-friendly option labels mapped to IDs
        options_map: Dict[str, str] = {}
        for s in self._matches:
            sid = str(s.get("id"))
            source = str(s.get("source") or STATION_SOURCE_PUBLIBIKE)
            city = (s.get("city") or "").strip()
            label = f'{_display_name(s)} — {city} (#{sid})' if city else f'{_display_name(s)} (#{sid})'
            options_map[label] = f"{source}:{sid}"

        if user_input is not None:
            chosen_label = user_input["station_id"]
            chosen_key = options_map.get(chosen_label)
            station = next(
                (
                    s
                    for s in self._matches
                    if f'{s.get("source") or STATION_SOURCE_PUBLIBIKE}:{str(s.get("id"))}' == chosen_key
                ),
                None,
            )
            if station is None:
                # go back to search if something went wrong
                return await self.async_step_user()
            unique_id = f'{station.get("source") or STATION_SOURCE_PUBLIBIKE}:{station["id"]}'
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            title = _entry_title(station)
            return self.async_create_entry(
                title=title,
                data={
                    CONF_STATION_ID: station["id"],
                    CONF_STATION_NAME: station.get("name") or str(station["id"]),
                    CONF_STATION_CITY: station.get("city") or "",
                    CONF_STATION_SOURCE: station.get("source") or STATION_SOURCE_PUBLIBIKE,
                    CONF_STATION_DETAILS_URL: station.get("details_url"),
                },
            )

        data_schema = vol.Schema(
            {
                # Use vol.In for a widely-supported dropdown
                vol.Required("station_id"): vol.In(list(options_map.keys()))
            }
        )
        return self.async_show_form(step_id="select_station", data_schema=data_schema)

    async def async_step_import(self, user_input: Dict[str, Any]) -> FlowResult:
        # Not used; no YAML import
        return await self.async_step_user()


class PublibikeOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._matches: List[Dict[str, Any]] = []
        self._last_query: str | None = None

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        return await self.async_step_search()

    async def async_step_search(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        errors: Dict[str, str] = {}
        if user_input is not None:
            query = user_input["station_name"]
            self._last_query = query
            try:
                stations = await _fetch_all_stations(self.hass)
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            else:
                matches = _search_matches(stations, query)
                if not matches:
                    errors["base"] = "no_stations_found"
                elif len(matches) == 1:
                    return await self._finish_with_station(matches[0])
                else:
                    self._matches = matches
                    return await self.async_step_pick()

        schema = vol.Schema(
            {vol.Required("station_name", default=self._last_query or ""): str}
        )
        return self.async_show_form(step_id="search", data_schema=schema, errors=errors)

    async def async_step_pick(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        # Build user-friendly option labels mapped to IDs
        options_map: Dict[str, str] = {}
        for s in self._matches:
            sid = str(s.get("id"))
            source = str(s.get("source") or STATION_SOURCE_PUBLIBIKE)
            city = (s.get("city") or "").strip()
            label = f'{_display_name(s)} — {city} (#{sid})' if city else f'{_display_name(s)} (#{sid})'
            options_map[label] = f"{source}:{sid}"

        if user_input is not None:
            label = user_input["station_id"]
            station_key = options_map.get(label)
            station = next(
                (
                    s
                    for s in self._matches
                    if f'{s.get("source") or STATION_SOURCE_PUBLIBIKE}:{str(s.get("id"))}' == station_key
                ),
                None,
            )
            if station:
                return await self._finish_with_station(station)
            return await self.async_step_search()

        schema = vol.Schema(
            {
                vol.Required("station_id"): vol.In(list(options_map.keys()))
            }
        )
        return self.async_show_form(step_id="pick", data_schema=schema)

    async def _finish_with_station(self, station: Dict[str, Any]) -> FlowResult:
        data = {
            **self.config_entry.data,
            CONF_STATION_ID: station["id"],
            CONF_STATION_NAME: station.get("name") or str(station["id"]),
            CONF_STATION_CITY: station.get("city") or "",
            CONF_STATION_SOURCE: station.get("source") or STATION_SOURCE_PUBLIBIKE,
            CONF_STATION_DETAILS_URL: station.get("details_url"),
        }
        return self.async_create_entry(title="", data=data)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> PublibikeOptionsFlowHandler:
    return PublibikeOptionsFlowHandler(config_entry)

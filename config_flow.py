from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector as sel
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_ALL_STATIONS,
    CONF_STATION_CITY,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
)


async def _fetch_all_stations(hass: HomeAssistant) -> List[Dict[str, Any]]:
    session = async_get_clientsession(hass)
    async with session.get(API_ALL_STATIONS, headers={"Accept": "application/json"}) as resp:
        resp.raise_for_status()
        data = await resp.json()
        # Expected top-level under "publibike" -> "stations"
        stations = (data or {}).get("publibike", {}).get("stations", [])
        return stations or []


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
                    unique_id = str(station["id"])
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    title = f'{station.get("name") or unique_id} ({station.get("city","")})'.strip()
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_STATION_ID: station["id"],
                            CONF_STATION_NAME: station.get("name") or str(station["id"]),
                            CONF_STATION_CITY: station.get("city") or "",
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
        if user_input is not None:
            chosen_id = int(user_input["station_id"])
            station = next((s for s in self._matches if int(s.get("id")) == chosen_id), None)
            if station is None:
                return await self.async_step_user()
            unique_id = str(station["id"])
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            title = f'{station.get("name") or unique_id} ({station.get("city","")})'.strip()
            return self.async_create_entry(
                title=title,
                data={
                    CONF_STATION_ID: station["id"],
                    CONF_STATION_NAME: station.get("name") or str(station["id"]),
                    CONF_STATION_CITY: station.get("city") or "",
                },
            )

        # Build selector options
        options = []
        for s in self._matches:
            sid = int(s.get("id"))
            label = f'{s.get("name","")} — {s.get("city","")} (#{sid})'
            options.append({"value": sid, "label": label})

        data_schema = vol.Schema(
            {
                vol.Required("station_id"): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=options,
                        mode=sel.SelectSelectorMode.DROPDOWN,
                    )
                )
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
        if user_input is not None:
            station_id = int(user_input["station_id"])
            station = next((s for s in self._matches if int(s.get("id")) == station_id), None)
            if station:
                return await self._finish_with_station(station)
            return await self.async_step_search()

        options = []
        for s in self._matches:
            sid = int(s.get("id"))
            label = f'{s.get("name","")} — {s.get("city","")} (#{sid})'
            options.append({"value": sid, "label": label})
        schema = vol.Schema(
            {
                vol.Required("station_id"): sel.SelectSelector(
                    sel.SelectSelectorConfig(options=options, mode=sel.SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="pick", data_schema=schema)

    async def _finish_with_station(self, station: Dict[str, Any]) -> FlowResult:
        # Update entry data
        data = {
            **self.config_entry.data,
            CONF_STATION_ID: station["id"],
            CONF_STATION_NAME: station.get("name") or str(station["id"]),
            CONF_STATION_CITY: station.get("city") or "",
        }
        return self.async_create_entry(title="", data=data)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> PublibikeOptionsFlowHandler:
    return PublibikeOptionsFlowHandler(config_entry)
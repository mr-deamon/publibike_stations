from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PublibikeCoordinator
from .const import (
    CONF_STATION_CITY,
    CONF_STATION_DETAILS_URL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_STATION_SOURCE,
    DOMAIN,
    STATION_SOURCE_PUBLIBIKE,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: PublibikeCoordinator = hass.data[DOMAIN][entry.entry_id]

    station_id = str(entry.data[CONF_STATION_ID])
    station_name = entry.data.get(CONF_STATION_NAME, station_id)
    station_city = entry.data.get(CONF_STATION_CITY, "")
    station_source = entry.data.get(CONF_STATION_SOURCE, STATION_SOURCE_PUBLIBIKE)
    station_details_url = entry.data.get(CONF_STATION_DETAILS_URL)

    configuration_url = station_details_url
    if not configuration_url and station_source == STATION_SOURCE_PUBLIBIKE:
        configuration_url = f"https://rest.publibike.ch/v1/public/stations/{station_id}"

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"station_{station_id}")},
        name=(
            f"{station_name} ({station_city})"
            if station_city
            else station_name
        )
        + (" (legacy)" if station_source == STATION_SOURCE_PUBLIBIKE else ""),
        manufacturer="PubliBike",
        model="Station",
        configuration_url=configuration_url,
    )

    entities: list[SensorEntity] = [
        PublibikeCountSensor(coordinator, "bikes", "Bikes available", "bikes", device_info, station_id),
        PublibikeCountSensor(coordinator, "ebikes", "E-bikes available", "ebikes", device_info, station_id),
        PublibikeStateSensor(coordinator, "state", "Station state", device_info, station_id),
    ]
    async_add_entities(entities)


class PublibikeBaseEntity(CoordinatorEntity[PublibikeCoordinator], SensorEntity):
    def __init__(self, coordinator: PublibikeCoordinator, key: str, name: str, device_info: DeviceInfo, station_id: str) -> None:
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"publibike_{station_id}_{key}"
        self._attr_device_info = device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.coordinator.data.get("station", {}) if self.coordinator.data else {}
        return {
            "station_id": st.get("id"),
            "station_name": st.get("name"),
            "station_city": st.get("city"),
            "address": st.get("address"),
            "zip": st.get("zip"),
            "latitude": st.get("latitude"),
            "longitude": st.get("longitude"),
            "capacity": st.get("capacity"),
        }


class PublibikeCountSensor(PublibikeBaseEntity):
    def __init__(self, coordinator: PublibikeCoordinator, key: str, name: str, count_key: str, device_info: DeviceInfo, station_id: str) -> None:
        super().__init__(coordinator, key, name, device_info, station_id)
        self._count_key = count_key
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return int(self.coordinator.data.get("counts", {}).get(self._count_key, 0))


class PublibikeStateSensor(PublibikeBaseEntity):
    def __init__(self, coordinator: PublibikeCoordinator, key: str, name: str, device_info: DeviceInfo, station_id: str) -> None:
        super().__init__(coordinator, key, name, device_info, station_id)
        # No device_class; keep plain text

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("station", {}).get("state") or "Unknown"

    @property
    def entity_category(self) -> EntityCategory | None:
        # Keep as diagnostic? If you prefer it as primary, return None
        return None
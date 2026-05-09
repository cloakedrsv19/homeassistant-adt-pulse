"""ADT Pulse binary sensor entities."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SensorStatus
from .const import (
    DOMAIN,
    MANUFACTURER,
    SENSOR_TYPE_CO,
    SENSOR_TYPE_DOOR_WINDOW,
    SENSOR_TYPE_FIRE,
    SENSOR_TYPE_FLOOD,
    SENSOR_TYPE_GLASS,
    SENSOR_TYPE_HEAT,
    SENSOR_TYPE_MOTION,
    SENSOR_TYPE_SHOCK,
    SENSOR_TYPE_TEMPERATURE,
)
from .coordinator import ADTPulseCoordinator

_LOGGER = logging.getLogger(__name__)

_SENSOR_DEVICE_CLASS: dict[str, BinarySensorDeviceClass] = {
    SENSOR_TYPE_CO: BinarySensorDeviceClass.CO,
    SENSOR_TYPE_DOOR_WINDOW: BinarySensorDeviceClass.DOOR,
    SENSOR_TYPE_FIRE: BinarySensorDeviceClass.SMOKE,
    SENSOR_TYPE_FLOOD: BinarySensorDeviceClass.MOISTURE,
    SENSOR_TYPE_GLASS: BinarySensorDeviceClass.VIBRATION,
    SENSOR_TYPE_HEAT: BinarySensorDeviceClass.HEAT,
    SENSOR_TYPE_MOTION: BinarySensorDeviceClass.MOTION,
    SENSOR_TYPE_SHOCK: BinarySensorDeviceClass.VIBRATION,
    SENSOR_TYPE_TEMPERATURE: BinarySensorDeviceClass.HEAT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from config entry."""
    coordinator: ADTPulseCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which zones we have already added
    known_zones: set[str] = set()

    @callback
    def _add_new_sensors() -> None:
        new_entities: list[ADTPulseBinarySensor] = []
        for sensor in coordinator.data.sensors if coordinator.data else []:
            uid = _sensor_uid(entry.entry_id, sensor)
            if uid not in known_zones:
                known_zones.add(uid)
                new_entities.append(ADTPulseBinarySensor(coordinator, entry, sensor))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_sensors))

    if coordinator.data:
        _add_new_sensors()


def _sensor_uid(entry_id: str, sensor: SensorStatus) -> str:
    return f"{entry_id}_zone_{sensor.zone}_{sensor.name}"


class ADTPulseBinarySensor(
    CoordinatorEntity[ADTPulseCoordinator], BinarySensorEntity
):
    """Represents a single ADT Pulse sensor zone."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ADTPulseCoordinator,
        entry: ConfigEntry,
        sensor: SensorStatus,
    ) -> None:
        super().__init__(coordinator)
        self._zone = sensor.zone
        self._sensor_name = sensor.name
        self._attr_name = sensor.name
        self._attr_unique_id = _sensor_uid(entry.entry_id, sensor)
        self._attr_device_class = _SENSOR_DEVICE_CLASS.get(sensor.sensor_type)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="ADT Pulse",
            manufacturer=MANUFACTURER,
        )

    def _current_sensor(self) -> SensorStatus | None:
        if not self.coordinator.data:
            return None
        for s in self.coordinator.data.sensors:
            if s.zone == self._zone and s.name == self._sensor_name:
                return s
        return None

    @property
    def is_on(self) -> bool | None:
        sensor = self._current_sensor()
        if sensor is None:
            return None
        return sensor.is_open

    @property
    def extra_state_attributes(self) -> dict:
        sensor = self._current_sensor()
        if sensor is None:
            return {}
        return {
            "zone": sensor.zone,
            "sensor_type": sensor.sensor_type,
            "status": sensor.status,
            "tampered": sensor.is_tampered,
            "low_battery": sensor.low_battery,
            "trouble": sensor.is_trouble,
        }

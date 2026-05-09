"""ADT Pulse alarm control panel entity."""
from __future__ import annotations

import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ARM_STATE_AWAY,
    ARM_STATE_NIGHT,
    ARM_STATE_OFF,
    ARM_STATE_STAY,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import ADTPulseCoordinator

_LOGGER = logging.getLogger(__name__)

_ARM_STATE_TO_HA: dict[str, AlarmControlPanelState] = {
    ARM_STATE_OFF: AlarmControlPanelState.DISARMED,
    ARM_STATE_STAY: AlarmControlPanelState.ARMED_HOME,
    ARM_STATE_AWAY: AlarmControlPanelState.ARMED_AWAY,
    ARM_STATE_NIGHT: AlarmControlPanelState.ARMED_NIGHT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the alarm control panel from a config entry."""
    coordinator: ADTPulseCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ADTPulseAlarmPanel(coordinator, entry)])


class ADTPulseAlarmPanel(
    CoordinatorEntity[ADTPulseCoordinator], AlarmControlPanelEntity
):
    """Represents the ADT Pulse security panel in Home Assistant."""

    _attr_has_entity_name = True
    _attr_name = "Security Panel"
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )
    _attr_code_arm_required = False

    def __init__(
        self,
        coordinator: ADTPulseCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_panel"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="ADT Pulse",
            manufacturer=MANUFACTURER,
            model="Security Panel",
        )

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        if self.coordinator.data is None:
            return None
        panel = self.coordinator.data.panel
        if panel.is_alarm:
            return AlarmControlPanelState.TRIGGERED
        return _ARM_STATE_TO_HA.get(panel.arm_state, AlarmControlPanelState.DISARMED)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        await self._set_arm(ARM_STATE_OFF)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm-stay command."""
        await self._set_arm(ARM_STATE_STAY)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm-away command."""
        await self._set_arm(ARM_STATE_AWAY)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send arm-night command."""
        await self._set_arm(ARM_STATE_NIGHT)

    async def _set_arm(self, target: str) -> None:
        current = (
            self.coordinator.data.panel.arm_state
            if self.coordinator.data
            else ARM_STATE_OFF
        )
        await self.coordinator.api.async_set_arm_state(target, current)
        await self.coordinator.async_request_refresh()

"""Alarm control panel platform for Elk-M1."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ARMED_AWAY,
    STATE_ARMED_HOME,
    STATE_DISARMED,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData
from .entity import ElkEntity

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up alarm control panel platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    
    async_add_entities([
        ElkAlarmControlPanel(
            hass=hass,
            coordinator=runtime_data.coordinator,
            config_entry=config_entry,
        )
    ])


class ElkAlarmControlPanel(ElkEntity, AlarmControlPanelEntity):
    """Elk-M1 alarm control panel."""

    _attr_name = "Alarm Panel"
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.DISARM
    )

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry, "alarm_panel")
        self._hass = hass
        self._coordinator = coordinator

    @property
    def state(self) -> str | None:
        """Return state."""
        if not self.coordinator.data:
            return None

        if self.coordinator.data["armed"]:
            if self.coordinator.data["armed_mode"] == "stay":
                return STATE_ARMED_HOME
            else:
                return STATE_ARMED_AWAY
        return STATE_DISARMED

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arm away."""
        # Use serial queue for write
        await self._coordinator._serial_queue.async_send_command(
            "arm_stay",
            user=0,
        )
        # Refresh state
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarm."""
        await self._coordinator._serial_queue.async_send_command(
            "disarm",
            user=0,
        )
        await self.coordinator.async_request_refresh()

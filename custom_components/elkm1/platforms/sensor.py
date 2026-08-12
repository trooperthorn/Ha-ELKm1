"""Sensor platform for Elk-M1 system info."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    """Set up sensor platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities = [
        ElkPanelTemperatureSensor(coordinator, config_entry),
        ElkPanelCommunicationStatusSensor(coordinator, config_entry),
        ElkLastUserSensor(coordinator, config_entry),
        ElkFaultedZonesSensor(coordinator, config_entry),
    ]

    async_add_entities(entities)


class ElkPanelTemperatureSensor(ElkEntity, SensorEntity):
    """Sensor for panel temperature."""
    
    _attr_name = "Panel Temperature"
    _attr_native_unit_of_measurement = "°C"
    _attr_has_entity_name = True

    @property
    def native_value(self) -> float | None:
        """Return panel temperature."""
        if not self.coordinator._elk:
            return None
        return getattr(self.coordinator._elk.panel, "temperature", None)


class ElkPanelCommunicationStatusSensor(ElkEntity, SensorEntity):
    """Sensor for panel communication status."""
    
    _attr_name = "Panel Status"
    _attr_has_entity_name = True

    @property
    def native_value(self) -> str:
        """Return panel communication status."""
        if not self.coordinator.last_update_success:
            return "Disconnected"
        return "Connected"


class ElkLastUserSensor(ElkEntity, SensorEntity):
    """Sensor for last user to arm/disarm."""
    
    _attr_name = "Last User"
    _attr_has_entity_name = True

    @property
    def native_value(self) -> str | None:
        """Return last user name."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("last_user_name")


class ElkFaultedZonesSensor(ElkEntity, SensorEntity):
    """Sensor listing faulted zones."""
    
    _attr_name = "Faulted Zones"
    _attr_has_entity_name = True

    @property
    def native_value(self) -> str:
        """Return comma-separated list of faulted zone numbers."""
        if not self.coordinator.data:
            return "None"
        
        zones = self.coordinator.data.get("zones_faulted", [])
        if not zones:
            return "None"
        
        return ", ".join(str(z + 1) for z in zones)

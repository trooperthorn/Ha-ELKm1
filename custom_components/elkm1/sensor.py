"""Sensor platform for Elk-M1 system info."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .data import ElkRuntimeData
from .entity import ElkEntity
from .helpers.troublestatus import get_trouble_status_string

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
        ElkPanelTemperatureSensor(coordinator, config_entry, "panel_temperature"),
        ElkPanelCommunicationStatusSensor(coordinator, config_entry, "panel_comm_status"),
        ElkLastUserSensor(coordinator, config_entry, "last_user"),
        
        # The new Window Group (Replace 1, 2, 3, 4 with your window zone numbers)
        ElkZoneGroupSensor(
            coordinator, config_entry, "windows_count", "Open Windows", 
            "mdi:window-closed", [1, 2, 3, 4, 5, 6, 7, 8]
        ),
        
        # The new Door Group (Replace 9, 10, 11 with your door zone numbers)
        ElkZoneGroupSensor(
            coordinator, config_entry, "doors_count", "Open Doors", 
            "mdi:door-closed", [9, 10, 11]
        ),
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


class ElkZoneGroupSensor(ElkEntity, SensorEntity):
    """Sensor that counts faulted zones for a specific group and lists them."""

    def __init__(self, coordinator, config_entry, sensor_type, name, icon, zone_list):
        super().__init__(coordinator, config_entry, sensor_type)
        self._attr_name = name
        self._attr_icon = icon
        self._zone_list = zone_list
        self._attr_has_entity_name = True
        
        # Bind this sensor to the main Elk-M1 device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "elk_m1_main_panel")},
            name="Elk-M1 Control Panel",
            manufacturer="Elk Products",
            model="M1 Gold",
        )

    @property
    def native_value(self) -> int:
        """Return the count of faulted zones in this group."""
        if not self.coordinator.data:
            return 0
        
        faulted_zones = self.coordinator.data.get("zones_faulted", [])
        
        # Count how many faulted zones (adjusted for 0-indexing) are in our filter list
        count = sum(1 for z in faulted_zones if (z + 1) in self._zone_list)
        
        # Optionally toggle icon dynamically
        if self._attr_name == "Open Windows":
            self._attr_icon = "mdi:window-open" if count > 0 else "mdi:window-closed"
        elif self._attr_name == "Open Doors":
            self._attr_icon = "mdi:door-open" if count > 0 else "mdi:door-closed"
            
        return count

    @property
    def extra_state_attributes(self):
        """Return attributes including a readable list of open zones."""
        if not self.coordinator.data:
            return {"open_entities": "None"}

        faulted_zones = self.coordinator.data.get("zones_faulted", [])
        
        # Get the actual zone numbers that are currently open and in this group
        active_zones = [z + 1 for z in faulted_zones if (z + 1) in self._zone_list]
        
        if not active_zones:
            return {"open_entities": "None"}
            
        # Format them nicely. If your coordinator has a dictionary of names, 
        # you could map them here. Otherwise, it defaults to "Zone 1, Zone 3"
        zone_strings = [f"Zone {z}" for z in active_zones]
        
        return {
            "open_entities": ", ".join(zone_strings)
        }



class ElkPanelSensor(CoordinatorEntity, SensorEntity):
    """Sensor for ELK panel information."""
    
    @property
    def state(self) -> str | None:
        """Return panel state (armed/disarmed status)."""
        panel = self.coordinator.data.get("panel")
        if panel is None:
            return None
        return str(panel.state)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        panel = self.coordinator.data.get("panel")
        if panel is None:
            return {}
        
        return {
            "armed": panel.armed,
            "mode": panel.mode,
            "system_trouble_status": get_trouble_status_string(panel),
            "temperature": getattr(panel, 'temperature', None),
            "battery": getattr(panel, 'battery_voltage', None),
        }

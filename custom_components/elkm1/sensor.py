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
        
        # Replace with your ACTUAL window zone IDs
        ElkZoneGroupSensor(
            coordinator, config_entry, "windows_count", "Open Windows", 
            "mdi:window-closed", [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14] 
        ),
        
        # Replace with your ACTUAL door zone IDs
        ElkZoneGroupSensor(
            coordinator, config_entry, "doors_count", "Open Doors", 
            "mdi:door-closed", [1, 2, 3, 15, 16] 
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
    """Sensor that counts open zones for a specific group using live physical/logical status."""

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

    def _is_zone_open(self, zone) -> bool:
        """Helper to match the exact logic used by ElkZoneBinarySensor."""
        if not zone:
            return False
            
        logical_val = getattr(getattr(zone, "logical_status", None), "value", 0)
        physical_val = getattr(getattr(zone, "physical_status", None), "value", 0)
        
        # 2 = Violated (Logical), 1 = Open, 3 = Short (Physical)
        return logical_val == 2 or physical_val in (1, 3)

    @property
    def native_value(self) -> int:
        """Return the live count of open zones in this group."""
        if not self.coordinator._elk or not hasattr(self.coordinator._elk, "zones"):
            return 0
        
        count = 0
        # Iterate through all zones provided by the Elk-M1 panel
        for i, zone in enumerate(self.coordinator._elk.zones):
            # i is 0-indexed, so the actual zone number is i + 1
            if (i + 1) in self._zone_list:
                if self._is_zone_open(zone):
                    count += 1
        
        # Dynamically change the icon based on the count
        if self._attr_name == "Open Windows":
            self._attr_icon = "mdi:window-open" if count > 0 else "mdi:window-closed"
        elif self._attr_name == "Open Doors":
            self._attr_icon = "mdi:door-open" if count > 0 else "mdi:door-closed"
            
        return count

    @property
    def extra_state_attributes(self):
        """Return attributes including a readable list of open zones."""
        if not self.coordinator._elk or not hasattr(self.coordinator._elk, "zones"):
            return {"open_entities": "None"}

        open_zones = []
        for i, zone in enumerate(self.coordinator._elk.zones):
            if (i + 1) in self._zone_list:
                if self._is_zone_open(zone):
                    # Get the friendly name of the zone, fallback to "Zone X" if name is missing
                    name = getattr(zone, "name", f"Zone {i + 1}")
                    open_zones.append(name)
        
        return {
            "open_entities": ", ".join(open_zones) if open_zones else "None"
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

"""Sensor platform for Elk-M1 system info."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData
from .entity import ElkEntity

_LOGGER = logging.getLogger(__name__)


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
        
        # Window Group (Dynamically counts ANY binary sensor shown as a "window")
        ElkZoneGroupSensor(
            coordinator, config_entry, "windows_count", "Open Windows", 
            "mdi:window-closed", "window"
        ),
        
        # Door Group (Dynamically counts ANY binary sensor shown as a "door")
        ElkZoneGroupSensor(
            coordinator, config_entry, "doors_count", "Open Doors", 
            "mdi:door-closed", "door"
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
    """Sensor that counts open zones dynamically by looking at the Home Assistant Entity Registry."""

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        name: str,
        icon: str,
        target_device_class: str,
    ) -> None:
        """Initialize the zone group sensor."""
        super().__init__(coordinator, config_entry, sensor_type)
        self.config_entry = config_entry
        self._attr_name = name
        self._attr_icon = icon
        self._target_device_class = target_device_class
        self._attr_has_entity_name = True


    def _is_zone_open(self, zone) -> bool:
        """Helper to match the exact physical/logical logic."""
        if not zone:
            return False
        logical_val = getattr(getattr(zone, "logical_status", None), "value", 0)
        physical_val = getattr(getattr(zone, "physical_status", None), "value", 0)
        return logical_val == 2 or physical_val in (1, 3)

    def _get_matching_open_zones(self):
        """Cross-references the UI Entity Registry with the live hardware state."""
        open_zones = []
        
        if not self.coordinator._elk or not hasattr(self.coordinator._elk, "zones"):
            return open_zones
            
        # NEW GUARD: Ensure the entity is fully attached to HA before checking the registry
        if not self.hass:
            return open_zones
            
        # Tap into the Home Assistant Entity Registry
        entity_reg = er.async_get(self.hass)
        entries = er.async_entries_for_config_entry(entity_reg, self.config_entry.entry_id)
                
        for entry in entries:
            # We only care about the binary_sensors (the actual zones)
            if entry.domain != "binary_sensor":
                continue
                
            # Check the effective device class.
            # entry.device_class is what the user sets in the UI ("Show as").
            # entry.original_device_class is the default we assigned in code.
            device_class = entry.device_class or entry.original_device_class
            if device_class != self._target_device_class:
                continue
                
            # Extract the actual hardware zone number from the unique_id (e.g., "elk_123_zone_14")
            try:
                if "zone_" in entry.unique_id:
                    zone_index = int(entry.unique_id.split("zone_")[-1])
                else:
                    continue
            except (ValueError, TypeError):
                continue
                
            # Instantly check the hardware without waiting for HA state machines to catch up
            try:
                zone = self.coordinator._elk.zones[zone_index]
            except IndexError:
                continue
                
            if self._is_zone_open(zone):
                # Major Bonus: If you rename the entity in HA, it uses that name! 
                # Otherwise it falls back to the Elk name, then generic "Zone X"
                name = entry.name or entry.original_name or getattr(zone, "name", f"Zone {zone_index + 1}")
                open_zones.append(name)
                
        return open_zones

    @property
    def native_value(self) -> int:
        """Return the live count of open zones."""
        open_zones = self._get_matching_open_zones()
        count = len(open_zones)
        
        if self._target_device_class == "window":
            self._attr_icon = "mdi:window-open" if count > 0 else "mdi:window-closed"
        elif self._target_device_class == "door":
            self._attr_icon = "mdi:door-open" if count > 0 else "mdi:door-closed"
            
        return count

    @property
    def extra_state_attributes(self):
        """Return attributes including a readable list of open zones."""
        open_zones = self._get_matching_open_zones()
        return {
            "open_entities": ", ".join(open_zones) if open_zones else "None"
        }


def get_trouble_status_string(panel: Any) -> str:
    """Parse the Elk panel trouble status into a readable string."""
    if not panel:
        return "Unknown"
    
    # elkm1_lib exposes trouble status, which we safely extract
    status = getattr(panel, "system_trouble_status", "")
    
    if not status:
        return "Normal"
        
    return str(status)

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

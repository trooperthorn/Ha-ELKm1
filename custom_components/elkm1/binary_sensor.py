"""Support for control of ElkM1 binary sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ElkDataUpdateCoordinator
from .entity import ElkEntity
from .helpers.troublestatus import TROUBLE_INDEX_NAMES
from .models import ElkRuntimeData

_LOGGER = logging.getLogger(__name__)

# Map raw ELK integer definitions to Home Assistant Device Classes
# 1-2: Entry/Exit, 3: Window, 4-7: Motion, 10-11: Fire, 17: CO, 19: Freeze, 20: Gas, 21: Heat, 25: Water
_DEVICE_CLASS_MAP: dict[int, BinarySensorDeviceClass] = {
    1: BinarySensorDeviceClass.DOOR,
    2: BinarySensorDeviceClass.MOTION,
    3: BinarySensorDeviceClass.WINDOW,
    4: BinarySensorDeviceClass.MOTION,
    5: BinarySensorDeviceClass.MOTION,
    6: BinarySensorDeviceClass.MOTION,
    7: BinarySensorDeviceClass.MOTION,
    10: BinarySensorDeviceClass.SMOKE,
    11: BinarySensorDeviceClass.SMOKE,
    17: BinarySensorDeviceClass.CO,
    19: BinarySensorDeviceClass.COLD,
    20: BinarySensorDeviceClass.GAS,
    21: BinarySensorDeviceClass.HEAT,
    25: BinarySensorDeviceClass.MOISTURE,
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the Elk-M1 binary sensor platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities = []
    zones = coordinator.data.zones if coordinator.data else []

    for zone in zones:
        # elkm1_lib always allocates Max.ZONES.value (208) Zone objects
        # regardless of how many the panel actually has configured.
        if not zone.configured:
            continue

        # Safely extract the zone definition (integer representation)
        def_val = 0
        if hasattr(zone, "definition"):
            def_obj = zone.definition
            def_val = int(def_obj.value) if hasattr(def_obj, "value") else int(def_obj)

        # Skip 33 (TEMPERATURE) and 34 (ANALOG_ZONE) - these are handled natively in sensor.py
        if def_val in (33, 34):
            continue

        # Create the Binary Sensor entity
        entities.append(
            ElkBinarySensor(
                coordinator=coordinator,
                config_entry=config_entry,
                zone_index=zone.index,
            )
        )

    entities.extend(
        ElkTroubleBinarySensor(coordinator, config_entry, name, label)
        for _index, (name, label) in TROUBLE_INDEX_NAMES.items()
    )

    async_add_entities(entities)


class ElkBinarySensor(ElkEntity, BinarySensorEntity):
    """Representation of ElkM1 binary sensor."""

    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        zone_index: int,
    ) -> None:
        """Initialize the binary sensor."""
        zone_num = zone_index + 1
        super().__init__(coordinator, config_entry, f"binary_sensor_zone_{zone_num}")
        self._zone_index = zone_index
        self._attr_unique_id = f"{config_entry.entry_id}_zone_{zone_num}"
        
        # Initial name setup
        zone_obj = self.zone_data
        self._attr_name = getattr(zone_obj, "name", f"Zone {zone_num}") if zone_obj else f"Zone {zone_num}"

    @property
    def zone_data(self) -> Any:
        """Helper to get the specific zone object from the coordinator data."""
        if self.coordinator.data and self._zone_index < len(self.coordinator.data.zones):
            return self.coordinator.data.zones[self._zone_index]
        return None

    def _get_enum_value(self, obj: Any, default: int = 0) -> int:
        """Safely extract the raw integer value from elkm1_lib Enum objects or raw dicts."""
        if hasattr(obj, "value"):
            return int(obj.value)
        if isinstance(obj, str):
            return int(obj) if obj.isdigit() else default
        return int(obj) if isinstance(obj, (int, float)) else default

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on (violated)."""
        zone = self.zone_data
        if not zone:
            return False
            
        logical_status = self._get_enum_value(getattr(zone, "logical_status", 0))
        # ZoneLogicalStatus: 0=normal, 1=trouble, 2=violated, 3=bypassed.
        return logical_status == 2

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the device class of this sensor based on its Elk definition."""
        zone = self.zone_data
        if not zone:
            return None
            
        def_val = self._get_enum_value(getattr(zone, "definition", 0))
        return _DEVICE_CLASS_MAP.get(def_val)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for the zone."""
        zone = self.zone_data
        if not zone:
            return {}

        logical_status = self._get_enum_value(getattr(zone, "logical_status", 0))
        return {
            "physical_status": self._get_enum_value(getattr(zone, "physical_status", 0)),
            "logical_status": logical_status,
            "definition": self._get_enum_value(getattr(zone, "definition", 0)),
            # ZoneLogicalStatus.BYPASSED == 3; Zone has no separate
            # "bypassed" attribute of its own (bypass is its own logical
            # status value, not a flag layered on top of another one).
            "bypassed": logical_status == 3,
            "triggered_alarm": getattr(zone, "triggered_alarm", False),
            "voltage": getattr(zone, "voltage", 0.0),
        }


class ElkTroubleBinarySensor(ElkEntity, BinarySensorEntity):
    """Representation of a single Elk-M1 system trouble condition."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        trouble_name: str,
        trouble_label: str,
    ) -> None:
        """Initialize the trouble sensor."""
        super().__init__(coordinator, config_entry, f"trouble_{trouble_name}")
        self._trouble_name = trouble_name
        self._attr_unique_id = f"{config_entry.entry_id}_trouble_{trouble_name}"
        self._attr_name = trouble_label

    @property
    def is_on(self) -> bool:
        """Return true if this trouble condition is currently active."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.troubles.get(self._trouble_name, False)

"""Binary sensor platform for Elk-M1 zones and sensors."""
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .data import ElkRuntimeData
from .coordinator import ElkDataUpdateCoordinator
from .entity import ElkEntity

_LOGGER = logging.getLogger(__name__)


class ElkZoneBinarySensor(ElkEntity, BinarySensorEntity):
    """Binary sensor for ELK zone."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False  # Users can enable as needed

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        zone_index: int,
        zone: Any,
    ) -> None:
        """Initialize zone binary sensor."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            entity_key=f"zone_{zone_index}",
        )
        self._zone_index = zone_index
        self._zone = zone
        
        # Map ELK zone type to HA device class
        # Safely extract the zone definition as an integer
        definition_val = getattr(getattr(zone, "definition", None), "value", 0)
        self._attr_device_class = self._get_device_class(definition_val)
        self._attr_name = zone.name

    @property
    def is_on(self) -> bool | None:
        """Return true if zone is open/triggered.
        
        Zone is "on" (open) when:
        - Faulted: sensor is triggered (door open, motion detected, etc.)
        - Open: zone status indicates violation
        """
        if not self.coordinator.data:
            _LOGGER.debug(f"Zone {self._zone_index}: No coordinator data")
            return None
        
        # Check both conditions
        is_faulted = bool(self._zone.faulted)
        is_open = bool(self._zone.open)
        
        result = is_faulted or is_open
        
        _LOGGER.debug(
            f"Zone {self._zone_index} ({self._zone.name}): "
            f"faulted={is_faulted}, open={is_open}, result={result}"
        )
        
        return result

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes.
        
        Updates with every coordinator refresh so data is current.
        """
        # We use getattr with string conversions so Enums render safely in HA
        return {
            "zone_number": self._zone_index + 1,
            "zone_definition": str(getattr(self._zone, "definition", "Unknown")),
            "logical_status": str(getattr(self._zone, "logical_status", "Unknown")),
            "physical_status": str(getattr(self._zone, "physical_status", "Unknown")),
            "zone_open": getattr(self._zone, "open", False),
            "zone_faulted": getattr(self._zone, "faulted", False),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        is_available = (
            self.coordinator.last_update_success
            and self._zone is not None
        )
        
        if not is_available:
            _LOGGER.debug(
                f"Zone {self._zone_index} unavailable: "
                f"coordinator_success={self.coordinator.last_update_success}, "
                f"zone_exists={self._zone is not None}"
            )
        
        return is_available

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator.
        
        Called whenever coordinator updates.
        Refreshes zone reference and notifies HA of state change.
        """
        try:
            if self.coordinator._elk and self.coordinator._elk.zones:
                old_zone = self._zone
                self._zone = self.coordinator._elk.zones[self._zone_index]
            
                _LOGGER.debug(
                    f"Zone {self._zone_index}: Updated from coordinator. "
                    f"State changed from {old_zone.status if old_zone else 'N/A'} "
                    f"to {self._zone.status}"
                )
        except (IndexError, AttributeError):
            _LOGGER.exception(f"Failed to update zone {self._zone_index}")
    
        # Notify Home Assistant of state change
        self.async_write_ha_state()

    @staticmethod
    def _get_device_class(zone_definition: int) -> BinarySensorDeviceClass | None:
        """Map ELK zone definition integer to HA device class.
        
        Args:
            zone_definition: ELK zone definition integer (from ElkRP)
            
        Returns:
            Home Assistant BinarySensorDeviceClass or None
        """
        # Map official Elk-M1 Zone Definition integers to HA Device Classes
        zone_type_map = {
            1: BinarySensorDeviceClass.DOOR,       # Burglar Entry/Exit 1
            2: BinarySensorDeviceClass.DOOR,       # Burglar Entry/Exit 2
            3: BinarySensorDeviceClass.WINDOW,     # Burglar Perimeter Instant
            4: BinarySensorDeviceClass.MOTION,     # Burglar Interior
            5: BinarySensorDeviceClass.MOTION,     # Burglar Interior Follower
            6: BinarySensorDeviceClass.MOTION,     # Burglar Interior Night
            7: BinarySensorDeviceClass.MOTION,     # Burglar Interior Night Delay
            9: BinarySensorDeviceClass.SMOKE,      # Fire Alarm
            10: BinarySensorDeviceClass.SMOKE,     # Fire Verified
            17: BinarySensorDeviceClass.CO,        # Carbon Monoxide
            19: BinarySensorDeviceClass.COLD,      # Freeze
            20: BinarySensorDeviceClass.GAS,       # Gas
            21: BinarySensorDeviceClass.HEAT,      # Heat
            22: BinarySensorDeviceClass.MOISTURE,  # Water
            25: BinarySensorDeviceClass.TAMPER,    # Tamper
        }
        
        device_class = zone_type_map.get(zone_definition)
        
        if device_class is None:
            # We return None instead of DOOR so that unmapped or generic automation 
            # zones just show up as a generic sensor (Clear/Detected) in Home Assistant.
            _LOGGER.debug(f"Unmapped zone definition: {zone_definition}, defaulting to generic sensor")
            return None
            
        return device_class

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elk-M1 binary sensor platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities = [] 
    
    if coordinator._elk:
        # Use enumerate() to get BOTH the index number and the zone object
        for index, zone in enumerate(coordinator._elk.zones):
            
            # Safely get the definition value, defaulting to 0 if it's missing or not an Enum
            definition_val = getattr(getattr(zone, "definition", None), "value", 0)
            
            if zone and definition_val > 0 and getattr(zone, "name", None):
                entities.append(
                    ElkZoneBinarySensor(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        zone_index=index,  # <--- We are now passing the missing index!
                        zone=zone,
                    )
                )
                
    async_add_entities(entities)

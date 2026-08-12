"""Binary sensor platform for Elk-M1 zones and sensors."""
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback

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
        self._attr_device_class = self._get_device_class(zone.zone_type)
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
        return {
            "zone_number": self._zone_index + 1,
            "zone_type": self._zone.zone_type,
            "zone_status": self._zone.status,
            "zone_open": self._zone.open,
            "zone_faulted": self._zone.faulted,
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
        except (IndexError, AttributeError) as e:
            _LOGGER.exception(f"Failed to update zone {self._zone_index}")

        
        # Notify Home Assistant of state change
        self.async_write_ha_state()

    @staticmethod
    def _get_device_class(zone_type: str) -> BinarySensorDeviceClass | None:
        """Map ELK zone type to HA device class.
        
        Args:
            zone_type: ELK zone type string
            
        Returns:
            Home Assistant BinarySensorDeviceClass or None
        """
        zone_type_map = {
            "burglar": BinarySensorDeviceClass.DOOR,
            "fire": BinarySensorDeviceClass.SMOKE,
            "gas": BinarySensorDeviceClass.GAS,
            "water": BinarySensorDeviceClass.MOISTURE,
            "temp": BinarySensorDeviceClass.TEMPERATURE,
            "motion": BinarySensorDeviceClass.MOTION,
            "door": BinarySensorDeviceClass.DOOR,
            "window": BinarySensorDeviceClass.WINDOW,
            "glass": BinarySensorDeviceClass.WINDOW,
            "tamper": BinarySensorDeviceClass.TAMPER,
        }
        
        device_class = zone_type_map.get(zone_type.lower())
        
        if device_class is None:
            _LOGGER.warning(f"Unknown zone type: {zone_type}, defaulting to DOOR")
            return BinarySensorDeviceClass.DOOR
        
        return device_class

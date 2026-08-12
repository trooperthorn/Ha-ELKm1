"""Binary sensor platform for Elk-M1 zones and sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up binary sensor platform from a config entry."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities: list[ElkZoneBinarySensor] = []

    # Create a binary sensor for each zone (max 208 zones on ELK-M1)
    if coordinator._elk:
        for zone_index in range(len(coordinator._elk.zones)):
            zone = coordinator._elk.zones[zone_index]
            if zone and zone.name:  # Only add if zone has a name
                entities.append(
                    ElkZoneBinarySensor(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        zone_index=zone_index,
                        zone=zone,
                    )
                )

    async_add_entities(entities)


class ElkZoneBinarySensor(ElkEntity, BinarySensorEntity):
    """Binary sensor for ELK zone."""

    _attr_has_entity_name = True
    _attr_should_poll = False

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
        
        # Store zone number for reference (1-based for Elk protocol)
        self._attr_extra_state_attributes = {
            "zone_number": zone_index + 1,
            "zone_type": zone.zone_type,
            "zone_status": zone.status,
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if zone is open/triggered."""
        if not self.coordinator.data:
            return None
        
        # Zone is "on" (open) if:
        # - Faulted: sensor triggered (open door, motion detected, etc.)
        # - Status indicates violation
        return self._zone.faulted or self._zone.open

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._zone is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        # Refresh zone reference
        if self.coordinator._elk:
            self._zone = self.coordinator._elk.zones[self._zone_index]
        self.async_write_ha_state()

    def _get_device_class(self, zone_type: str) -> BinarySensorDeviceClass | None:
        """Map ELK zone type to HA device class."""
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
        return zone_type_map.get(zone_type.lower())


# Optional: Add a battery sensor for wireless zones
class ElkZoneBatterySensor(ElkEntity, BinarySensorEntity):
    """Binary sensor for zone low battery."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        zone_index: int,
        zone: Any,
    ) -> None:
        """Initialize battery sensor."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            entity_key=f"zone_{zone_index}_battery",
        )
        self._zone_index = zone_index
        self._zone = zone
        self._attr_name = f"{zone.name} Battery"

    @property
    def is_on(self) -> bool | None:
        """Return true if battery is low."""
        if not self._zone:
            return None
        return getattr(self._zone, "battery_low", False)

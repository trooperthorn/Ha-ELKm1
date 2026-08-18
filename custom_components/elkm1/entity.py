"""Base entity for Elk-M1 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import ElkDataUpdateCoordinator


def create_elk_system_device_info(config_entry: ConfigEntry) -> DeviceInfo:
    """Create standard device info for Elk-M1 system components."""
    return DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name="Elk-M1",
        manufacturer=MANUFACTURER,
        model=MODEL,
    )


class ElkEntity(CoordinatorEntity[ElkDataUpdateCoordinator], Entity):
    """Base entity for Elk-M1."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        entity_key: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_key = entity_key
        self._config_entry = config_entry

        # EVERY entity that inherits ElkEntity will now share this exact device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},  # Uses the integration ID as the glue
            name="Elk-M1",                    # The cleaner name you wanted
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

        # Unique ID
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_key}"

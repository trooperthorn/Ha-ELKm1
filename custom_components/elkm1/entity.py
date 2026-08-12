"""Base entity for Elk-M1 integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import ElkDataUpdateCoordinator


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

        # Set device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": MODEL,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

        # Unique ID
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_key}"

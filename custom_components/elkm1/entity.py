"""Base entity for Elk-M1 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import ElkDataUpdateCoordinator


def create_elk_system_device_info(
    config_entry: ConfigEntry, sw_version: str | None = None
) -> DeviceInfo:
    """Create standard device info for Elk-M1 system components.

    `sw_version` is the panel firmware version (coordinator.data.panel_version,
    parsed from the panel's own `vn` reply) once known; entities created
    before the first successful sync simply omit it.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name="Elk-M1",
        manufacturer=MANUFACTURER,
        model=MODEL,
        sw_version=sw_version,
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

        # Every entity currently shares this one panel-wide device; splitting
        # into per-area/per-keypad devices is tracked as follow-up work once
        # those become first-class (keypad platform, area-aware naming).
        self._attr_device_info = create_elk_system_device_info(
            config_entry, sw_version=getattr(coordinator.data, "panel_version", None)
        )

        # Unique ID
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_key}"

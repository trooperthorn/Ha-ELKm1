"""Support for Elk-M1 PLC (X10-style) lighting."""

from __future__ import annotations

import logging
from typing import Any, ClassVar, override

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ElkDataUpdateCoordinator
from .entity import ElkEntity
from .models import ElkRuntimeData

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Elk light levels are 0-100; HA brightness is 0-255.
_ELK_MAX_LEVEL = 100
_HA_MAX_BRIGHTNESS = 255


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the Elk-M1 PLC light platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    lights = coordinator.data.lights if coordinator.data else []
    async_add_entities(
        ElkPlcLight(coordinator, config_entry, light.index)
        for light in lights
        if light.configured
    )


class ElkPlcLight(ElkEntity, LightEntity):
    """Representation of an Elk-M1 PLC lighting device."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.BRIGHTNESS}

    def __init__(
        self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry, index: int
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator, config_entry, f"light_{index + 1}")
        self._index = index
        self._attr_unique_id = f"{config_entry.entry_id}_light_{index + 1}"
        obj = self._get_obj()
        self._attr_name = getattr(obj, "name", f"Light {index + 1}") if obj else None

    def _get_obj(self) -> Any:
        if self.coordinator.data and self._index < len(self.coordinator.data.lights):
            return self.coordinator.data.lights[self._index]
        return None

    @property
    @override
    def is_on(self) -> bool:
        obj = self._get_obj()
        return bool(obj and obj.status > 0)

    @property
    @override
    def brightness(self) -> int | None:
        obj = self._get_obj()
        if not obj:
            return None
        return round(obj.status * _HA_MAX_BRIGHTNESS / _ELK_MAX_LEVEL)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (optionally to a specific brightness)."""
        obj = self._get_obj()
        if not obj:
            return
        if (brightness := kwargs.get("brightness")) is not None:
            level = round(brightness * _ELK_MAX_LEVEL / _HA_MAX_BRIGHTNESS)
            obj.level(max(level, 1))
        else:
            obj.level(_ELK_MAX_LEVEL)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        if obj := self._get_obj():
            obj.level(0)

"""Discovery helpers for Elk-M1 integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _short_mac(mac: str) -> str:
    """Format a MAC address to a short, colon-less string."""
    return mac.replace(":", "").replace("-", "").lower()


async def async_discover_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    element_type: str,
    element_id: int,
) -> Any | None:
    """Discover a specific Elk-M1 device element."""
    return None


async def async_discover_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> list[Any]:
    """Discover all Elk-M1 device elements."""
    return []


async def async_trigger_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Trigger a rediscovery scan for Elk-M1 devices."""
    _LOGGER.debug("Triggering Elk-M1 device discovery scan")


async def async_update_entry_from_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
    discovery_info: dict[str, Any],
) -> None:
    """Update configuration entry from discovery data payload."""
    _LOGGER.debug(f"Updating entry from discovery info: {discovery_info}")

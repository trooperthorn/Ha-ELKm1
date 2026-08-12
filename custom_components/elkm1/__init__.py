"""Elk-M1 Control integration."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData

_LOGGER: logging.getLogger = logging.getLogger(__name__)

PLATFORMS: Final = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    _LOGGER.debug("Setting up Elk-M1 integration")
    
    # Create coordinator
    coordinator = ElkDataUpdateCoordinator(
        hass=hass,
        serial_port=entry.data["serial_port"],
        username=entry.data.get("username"),
        password=entry.data.get("password"),
    )

    # Do initial sync (connect, get panel state)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to connect to Elk panel: {err}") from err

    # Store coordinator in runtime_data
    entry.runtime_data = ElkRuntimeData(
        coordinator=coordinator,
        serial_port=entry.data["serial_port"],
    )

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for unload
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: ElkDataUpdateCoordinator = entry.runtime_data.coordinator
        await coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)

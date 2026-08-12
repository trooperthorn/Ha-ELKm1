"""Elk-M1 Control integration."""
# At the top with other imports
from .alarmo_integration import async_setup_alarmo_service
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

    # Setup Alarmo integration service
    await async_setup_alarmo_service(hass)
    
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

async def async_setup_services(hass: HomeAssistant) -> None:
    """Register custom services."""
    
    async def handle_bypass_zone(call: ServiceCall) -> None:
        """Handle bypass zone service."""
        entry_id = call.data.get("entry_id")
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry:
            return
        
        coordinator: ElkDataUpdateCoordinator = entry.runtime_data.coordinator
        zone = call.data.get("zone")
        
        try:
            await coordinator._serial_queue.async_send_command(
                "bypass_zone",
                zone=zone - 1,  # Convert to 0-based
            )
            await coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Error bypassing zone: {err}")
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        "bypass_zone",
        handle_bypass_zone,
    )

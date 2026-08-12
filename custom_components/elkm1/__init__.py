"""Elk-M1 Control integration."""

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SCENE,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elk-M1 Control from a config entry."""
    
    _LOGGER.info(f"Setting up Elk-M1 at {entry.data.get('serial_port', entry.data.get('host'))}")
    
    # Create coordinator with config data
    coordinator = ElkDataUpdateCoordinator(
        hass=hass,
        config_entry_data=entry.data,  # ← Pass the entire config entry data
    )
    
    try:
        # Connect and do first refresh
        await coordinator.async_first_refresh()
    except Exception as err:
        _LOGGER.error(f"Failed to set up coordinator: {err}")
        await coordinator.async_disconnect()
        raise ConfigEntryNotReady(f"Failed to connect: {err}")
    
    # Store coordinator in hass.data
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    hass.data[DOMAIN][entry.entry_id] = ElkRuntimeData(coordinator=coordinator)
    
    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Listen for unload
    entry.async_on_unload(coordinator.async_shutdown)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    _LOGGER.info(f"Unloading Elk-M1 entry: {entry.entry_id}")
    
    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Disconnect coordinator
        coordinator = hass.data[DOMAIN][entry.entry_id].coordinator
        await coordinator.async_disconnect()
        
        # Remove from hass.data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
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

"""Elk-M1 Control integration."""

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntryNotReady
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.const import Platform
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
    coordinator = ElkDataUpdateCoordinator(hass=hass, config_entry_data=entry.data)

    try:
        await coordinator.async_first_refresh()
    except UpdateFailed as err:
        _LOGGER.error(f"Failed to set up coordinator: {err}")
        await coordinator.async_disconnect()
        raise ConfigEntryNotReady(f"Failed to connect: {err}") from err

    # Store coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = ElkRuntimeData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_shutdown)

    await async_register_services(hass)

    return True


async def async_register_services(hass: HomeAssistant) -> None:
    """Register custom services."""

    async def handle_bypass_zone(call: ServiceCall) -> None:
        """Handle bypass zone service."""
        entry_id = call.data.get("entry_id")
        zone_number = call.data.get("zone")

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.bypass_zone(zone_number)
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error bypassing zone: {err}")

    hass.services.async_register(DOMAIN, "bypass_zone", handle_bypass_zone)


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
        try:
            # ...
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error bypassing zone: {err}")
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        "bypass_zone",
        handle_bypass_zone,
    )

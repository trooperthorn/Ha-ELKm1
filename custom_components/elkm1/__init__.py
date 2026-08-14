"""Elk-M1 Control integration."""
import logging
from typing import Final

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import CONF_SERIAL_PORT, CONF_PIN, DOMAIN
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elk-M1 Control from a config entry."""
    _LOGGER.info(f"Setting up Elk-M1 at {entry.data.get(CONF_SERIAL_PORT, entry.data.get('host'))}")

    coordinator = ElkDataUpdateCoordinator(
        hass=hass,
        config_entry_data=entry.data,
    )

    try:
        await coordinator.async_first_refresh()
    except UpdateFailed as err:
        _LOGGER.error(f"Failed to set up coordinator: {err}")
        await coordinator.async_disconnect()
        raise ConfigEntryNotReady(f"Failed to connect: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    
    serial_port_value = entry.data.get(CONF_SERIAL_PORT)
    
    runtime_data = ElkRuntimeData(
        coordinator=coordinator,
        serial_port=serial_port_value
    )

    hass.data[DOMAIN][entry.entry_id] = runtime_data
    entry.runtime_data = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass, entry)

    entry.async_on_unload(coordinator.async_shutdown)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading Elk-M1 entry: {entry.entry_id}")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN][entry.entry_id].coordinator
        await coordinator.async_disconnect()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_setup_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register custom services."""
    default_pin = entry.data.get(CONF_PIN)
    coordinator = entry.runtime_data.coordinator

    async def handle_bypass_zone(call: ServiceCall) -> None:
        """Handle bypass zone service."""
        # Check both "zone" and "zone_number" just in case
        zone_number = call.data.get("zone_number") or call.data.get("zone")
        code = call.data.get("code") or default_pin

        if not code:
            _LOGGER.warning("Cannot bypass zone %s: No PIN provided.", zone_number)
            return

        if coordinator._elk and zone_number:
            zone_index = int(zone_number) - 1
            _LOGGER.debug("Bypassing zone %s using PIN", zone_number)
            coordinator._elk.zones[zone_index].bypass(code)

    async def handle_unbypass_zone(call: ServiceCall) -> None:
        """Handle unbypass zone service."""
        zone_number = call.data.get("zone_number") or call.data.get("zone")
        code = call.data.get("code") or default_pin
        
        if coordinator._elk and zone_number:
            zone_index = int(zone_number) - 1
            coordinator._elk.zones[zone_index].bypass(code) # In Elk, bypass toggles or clears depending on panel setting, but passing the code is identical

    async def handle_disarm(call: ServiceCall) -> None:
        try:
            await coordinator.send_disarm()
        except Exception as err:
            _LOGGER.error(f"Error disarming: {err}")

    async def handle_arm_stay(call: ServiceCall) -> None:
        try:
            await coordinator.send_arm_stay()
        except Exception as err:
            _LOGGER.error(f"Error arming stay: {err}")

    async def handle_arm_away(call: ServiceCall) -> None:
        try:
            await coordinator.send_arm_away()
        except Exception as err:
            _LOGGER.error(f"Error arming away: {err}")

    async def handle_arm_night(call: ServiceCall) -> None:
        try:
            await coordinator.send_arm_night()
        except Exception as err:
            _LOGGER.error(f"Error arming night: {err}")

    async def handle_panic(call: ServiceCall) -> None:
        try:
            await coordinator.panic_alarm()
        except Exception as err:
            _LOGGER.error(f"Error triggering panic: {err}")

    # Register all services
    hass.services.async_register(DOMAIN, "bypass_zone", handle_bypass_zone)
    hass.services.async_register(DOMAIN, "unbypass_zone", handle_unbypass_zone)
    hass.services.async_register(DOMAIN, "disarm", handle_disarm)
    hass.services.async_register(DOMAIN, "arm_stay", handle_arm_stay)
    hass.services.async_register(DOMAIN, "arm_away", handle_arm_away)
    hass.services.async_register(DOMAIN, "arm_night", handle_arm_night)
    hass.services.async_register(DOMAIN, "panic_alarm", handle_panic)

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
    coordinator = entry.runtime_data.coordinator

    # --- STRICT SECURITY SERVICES (PIN REQUIRED) ---

    async def handle_bypass_zone(call: ServiceCall) -> None:
        zone_number = call.data.get("zone_number") or call.data.get("zone")
        code = call.data.get("code") or call.data.get("pin_code")

        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to bypass zone %s.", zone_number)
            return

        if coordinator._elk and zone_number:
            zone_index = int(zone_number) - 1
            _LOGGER.debug("Bypassing zone %s using user PIN", zone_number)
            coordinator._elk.zones[zone_index].bypass(code)

    async def handle_unbypass_zone(call: ServiceCall) -> None:
        zone_number = call.data.get("zone_number") or call.data.get("zone")
        code = call.data.get("code") or call.data.get("pin_code")
        
        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to unbypass zone %s.", zone_number)
            return

        if coordinator._elk and zone_number:
            zone_index = int(zone_number) - 1
            coordinator._elk.zones[zone_index].bypass(code)

    async def handle_disarm(call: ServiceCall) -> None:
        code = call.data.get("code") or call.data.get("pin_code")
        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to disarm.")
            return
        await coordinator.send_disarm(code)

    async def handle_arm_stay(call: ServiceCall) -> None:
        code = call.data.get("code") or call.data.get("pin_code")
        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to arm stay.")
            return
        await coordinator.send_arm_stay(code)

    async def handle_arm_away(call: ServiceCall) -> None:
        code = call.data.get("code") or call.data.get("pin_code")
        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to arm away.")
            return
        await coordinator.send_arm_away(code)

    async def handle_arm_night(call: ServiceCall) -> None:
        code = call.data.get("code") or call.data.get("pin_code")
        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to arm night.")
            return
        await coordinator.send_arm_night(code)

    async def handle_panic(call: ServiceCall) -> None:
        code = call.data.get("code") or call.data.get("pin_code")
        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to trigger panic.")
            return
        await coordinator.panic_alarm(code)

    async def handle_force_arm_away(call: ServiceCall) -> None:
        area = call.data.get("area", 1)
        code = call.data.get("code") or call.data.get("pin_code")
        if not code:
            _LOGGER.warning("Action Rejected: User PIN code is required to force arm.")
            return
        await coordinator.force_arm_away(int(area), code)

    # --- NON-SECURITY SERVICES (NO PIN REQUIRED) ---

    async def handle_trigger_zone(call: ServiceCall) -> None:
        zone_number = call.data.get("zone_number") or call.data.get("zone")
        if zone_number:
            await coordinator.trigger_zone(int(zone_number))

    async def handle_display_message(call: ServiceCall) -> None:
        area = call.data.get("area", 1)
        line1 = call.data.get("line1", "")
        line2 = call.data.get("line2", "^")
        beep = 1 if call.data.get("beep") else 0
        timeout = call.data.get("timeout", 0)
        # Clear option: 2 = Display until timeout
        await coordinator.display_message(area, 2, beep, timeout, line1, line2)

    async def handle_speak_phrase(call: ServiceCall) -> None:
        phrase_number = call.data.get("phrase_number")
        if phrase_number:
            await coordinator.speak_phrase(int(phrase_number))

    async def handle_activate_task(call: ServiceCall) -> None:
        task_number = call.data.get("task_number")
        if task_number:
            await coordinator.activate_task(int(task_number))

    # Register all services
    hass.services.async_register(DOMAIN, "bypass_zone", handle_bypass_zone)
    hass.services.async_register(DOMAIN, "unbypass_zone", handle_unbypass_zone)
    hass.services.async_register(DOMAIN, "disarm", handle_disarm)
    hass.services.async_register(DOMAIN, "arm_stay", handle_arm_stay)
    hass.services.async_register(DOMAIN, "arm_away", handle_arm_away)
    hass.services.async_register(DOMAIN, "arm_night", handle_arm_night)
    hass.services.async_register(DOMAIN, "panic_alarm", handle_panic)
    hass.services.async_register(DOMAIN, "trigger_zone", handle_trigger_zone)
    hass.services.async_register(DOMAIN, "force_arm_away", handle_force_arm_away)
    hass.services.async_register(DOMAIN, "display_message", handle_display_message)
    hass.services.async_register(DOMAIN, "speak_phrase", handle_speak_phrase)
    hass.services.async_register(DOMAIN, "activate_task", handle_activate_task)

"""Elk-M1 Control integration."""
import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import UpdateFailed

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

    # Store coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = ElkRuntimeData(coordinator=coordinator)

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once, even if multiple entries)
    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)

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
        zone_number = call.data.get("zone")
        entry_id = call.data.get("entry_id")

        if not zone_number or not entry_id:
            _LOGGER.error("Missing zone or entry_id in bypass_zone service call")
            return

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.bypass_zone(zone_number)
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error bypassing zone {zone_number}: {err}")

    async def handle_unbypass_zone(call: ServiceCall) -> None:
        """Handle unbypass zone service."""
        zone_number = call.data.get("zone")
        entry_id = call.data.get("entry_id")

        if not zone_number or not entry_id:
            _LOGGER.error("Missing zone or entry_id in unbypass_zone service call")
            return

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.unbypass_zone(zone_number)
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error unbypassing zone {zone_number}: {err}")

    async def handle_disarm(call: ServiceCall) -> None:
        """Handle disarm service."""
        entry_id = call.data.get("entry_id")

        if not entry_id:
            _LOGGER.error("Missing entry_id in disarm service call")
            return

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.send_disarm()
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error disarming: {err}")

    async def handle_arm_stay(call: ServiceCall) -> None:
        """Handle arm stay service."""
        entry_id = call.data.get("entry_id")

        if not entry_id:
            _LOGGER.error("Missing entry_id in arm_stay service call")
            return

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.send_arm_stay()
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error arming stay: {err}")

    async def handle_arm_away(call: ServiceCall) -> None:
        """Handle arm away service."""
        entry_id = call.data.get("entry_id")

        if not entry_id:
            _LOGGER.error("Missing entry_id in arm_away service call")
            return

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.send_arm_away()
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error arming away: {err}")

    async def handle_arm_night(call: ServiceCall) -> None:
        """Handle arm night service."""
        entry_id = call.data.get("entry_id")

        if not entry_id:
            _LOGGER.error("Missing entry_id in arm_night service call")
            return

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.send_arm_night()
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error arming night: {err}")

    async def handle_panic(call: ServiceCall) -> None:
        """Handle panic alarm service."""
        entry_id = call.data.get("entry_id")

        if not entry_id:
            _LOGGER.error("Missing entry_id in panic_alarm service call")
            return

        runtime_data = hass.data[DOMAIN].get(entry_id)
        if runtime_data is None:
            _LOGGER.error(f"No config entry found for entry_id {entry_id}")
            return

        try:
            await runtime_data.coordinator.panic_alarm()
            await runtime_data.coordinator.async_request_refresh()
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.error(f"Error triggering panic: {err}")

    # Register all services
    hass.services.async_register(DOMAIN, "bypass_zone", handle_bypass_zone)
    hass.services.async_register(DOMAIN, "unbypass_zone", handle_unbypass_zone)
    hass.services.async_register(DOMAIN, "disarm", handle_disarm)
    hass.services.async_register(DOMAIN, "arm_stay", handle_arm_stay)
    hass.services.async_register(DOMAIN, "arm_away", handle_arm_away)
    hass.services.async_register(DOMAIN, "arm_night", handle_arm_night)
    hass.services.async_register(DOMAIN, "panic_alarm", handle_panic)

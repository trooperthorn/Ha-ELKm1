"""Elk-M1 Control integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.util.network import is_ip_address

from .alarmo_integration import async_setup_alarmo_auto_config
from .const import (
    CONF_AUTO_CONFIGURE,
    CONF_BAUD_RATE,
    CONF_CONNECTION_TYPE,
    CONF_PREFIX,
    CONNECTION_NETWORK,
    CONNECTION_SERIAL,
    DOMAIN,
)
from .coordinator import ElkDataUpdateCoordinator
from .discovery import (
    async_discover_device,
    async_update_entry_from_discovery,
)
from .entity import create_elk_system_device_info
from .helpers.panel_settings import verify_panel_configuration
from .models import ElkRuntimeData
from .services import async_setup_services

if TYPE_CHECKING:
    ElkM1ConfigEntry = ConfigEntry[ElkRuntimeData]
else:
    ElkM1ConfigEntry = ConfigEntry

_LOGGER = logging.getLogger(__name__)

# Only platforms that actually exist today; climate/light/number/scene/time
# are added back to this list as each lands (tracked in the rework plan).
PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]


def hostname_from_url(url: str) -> str:
    """Return the hostname from a url."""
    parsed = urlparse(url)
    return parsed.hostname or url.replace("serial://", "")


async def async_setup(hass: HomeAssistant, _hass_config: dict[str, Any]) -> bool:
    """Set up the Elk-M1 integration (services only; no YAML config import)."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ElkM1ConfigEntry) -> bool:
    """Set up Elk-M1 Control from a config entry."""
    conf = dict(entry.data)

    serial_port = conf.get("serial_port")
    if serial_port:
        connection_url = f"serial://{serial_port}"
        conf[CONF_CONNECTION_TYPE] = CONNECTION_SERIAL
    else:
        connection_url = conf.get("host", "")
        conf[CONF_CONNECTION_TYPE] = (
            CONNECTION_SERIAL
            if connection_url.startswith("serial://")
            else CONNECTION_NETWORK
        )

    host = hostname_from_url(connection_url)
    _LOGGER.info("Setting up elkm1 at %s", connection_url)

    if (
        (not entry.unique_id or ":" not in entry.unique_id)
        and is_ip_address(host)
        and (device := await async_discover_device(hass, entry, "network", 0))
    ):
        await async_update_entry_from_discovery(hass, entry, device)

    def _on_baud_detected(baud: int) -> None:
        """Persist a newly detected baud rate so reconnects try it first."""
        if entry.data.get(CONF_BAUD_RATE) != baud:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_BAUD_RATE: baud}
            )

    coordinator = ElkDataUpdateCoordinator(
        hass, conf, on_baud_detected=_on_baud_detected
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Timed out or failed connecting to {connection_url}"
        ) from err

    # Verify panel version and log required global settings reminders;
    # non-fatal, setup should still succeed if this check itself errors.
    try:
        await verify_panel_configuration(coordinator)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Panel verification encountered non-fatal error: %s", err)

    prefix: str = conf.get(CONF_PREFIX, "")
    auto_configure: bool = conf.get(CONF_AUTO_CONFIGURE, False)

    entry.runtime_data = ElkRuntimeData(
        prefix=prefix,
        mac=entry.unique_id,
        auto_configure=auto_configure,
        config=dict(conf),
        coordinator=coordinator,
    )

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **create_elk_system_device_info(entry, sw_version=coordinator.data.panel_version),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if async_setup_alarmo_auto_config is not None:
        await async_setup_alarmo_auto_config(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ElkM1ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator = entry.runtime_data.coordinator
    if coordinator:
        await coordinator.async_disconnect()

    return unload_ok

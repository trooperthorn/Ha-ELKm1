"""Elk-M1 Control integration."""

from __future__ import annotations

# 1. CLEAN UP IMPORTS (Remove asyncio, UnitOfTemperature, DISCOVERY constants, etc.)
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_ENABLED,
    CONF_EXCLUDE,
    CONF_HOST,
    CONF_INCLUDE,
    CONF_PASSWORD,
    CONF_PREFIX,
    CONF_USERNAME,
    CONF_ZONE,
    Platform,
    CONF_TEMPERATURE_UNIT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.network import is_ip_address

from .alarmo_integration import async_setup_alarmo_auto_config
from .const import (
    CONF_AREA,
    CONF_AUTO_CONFIGURE,
    CONF_COUNTER,
    CONF_KEYPAD,
    CONF_OUTPUT,
    CONF_PLC,
    CONF_SETTING,
    CONF_TASK,
    CONF_THERMOSTAT,
    DOMAIN,
    ELK_ELEMENTS,
)
from .coordinator import ElkDataUpdateCoordinator
from .discovery import (
    async_discover_device,
    async_update_entry_from_discovery,
)
from .entity import create_elk_system_device_info
from .models import ElkRuntimeData
from .helpers.panel_settings import verify_panel_configuration
from .services import async_setup_services

if TYPE_CHECKING:
    ElkM1ConfigEntry = ConfigEntry[ElkRuntimeData]
else:
    ElkM1ConfigEntry = ConfigEntry

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
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


def hostname_from_url(url: str) -> str:
    """Return the hostname from a url."""
    parsed = urlparse(url)
    return parsed.hostname or url.replace("serial://", "")


def _host_validator(config: dict[str, str]) -> dict[str, str]:
    """Validate that a host is properly configured."""
    if config[CONF_HOST].startswith(("elks://", "elksv1_2://")):
        if CONF_USERNAME not in config or CONF_PASSWORD not in config:
            raise vol.Invalid(
                "Specify username and password for elks:// or elksv1_2://"
            )
    elif not config[CONF_HOST].startswith("elk://") and not config[
        CONF_HOST
    ].startswith("serial://"):
        raise vol.Invalid("Invalid host URL")
    return config


def _elk_range_validator(rng: str) -> tuple[int, int]:
    def _housecode_to_int(val: str) -> int:
        match = re.search(r"^([a-p])(0[1-9]|1[0-6]|[1-9])$", val.lower())
        if match:
            return (ord(match.group(1)) - ord("a")) * 16 + int(match.group(2))
        raise vol.Invalid("Invalid range")

    def _elk_value(val: str) -> int:
        return int(val) if val.isdigit() else _housecode_to_int(val)

    vals = [s.strip() for s in str(rng).split("-")]
    start = _elk_value(vals[0])
    end = start if len(vals) == 1 else _elk_value(vals[1])
    return (start, end)


def _has_all_unique_prefixes(value: list[dict[str, str]]) -> list[dict[str, str]]:
    """Validate that each m1 configured has a unique prefix."""
    prefixes = [device[CONF_PREFIX] for device in value]
    schema = vol.Schema(vol.Unique())
    schema(prefixes)
    return value


DEVICE_SCHEMA_SUBDOMAIN = vol.Schema(
    {
        vol.Optional(CONF_ENABLED, default=True): cv.boolean,
        vol.Optional(CONF_INCLUDE, default=[]): [_elk_range_validator],
        vol.Optional(CONF_EXCLUDE, default=[]): [_elk_range_validator],
    }
)

DEVICE_SCHEMA = vol.All(
    cv.deprecated(CONF_TEMPERATURE_UNIT),
    vol.Schema(
        {
            vol.Required(CONF_HOST): cv.string,
            vol.Optional(CONF_PREFIX, default=""): vol.All(cv.string, vol.Lower),
            vol.Optional(CONF_USERNAME, default=""): cv.string,
            vol.Optional(CONF_PASSWORD, default=""): cv.string,
            vol.Optional(CONF_AUTO_CONFIGURE, default=False): cv.boolean,
            vol.Optional(CONF_TEMPERATURE_UNIT, default="F"): cv.temperature_unit,
            vol.Optional(CONF_AREA, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_COUNTER, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_KEYPAD, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_OUTPUT, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_PLC, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_SETTING, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_TASK, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_THERMOSTAT, default={}): DEVICE_SCHEMA_SUBDOMAIN,
            vol.Optional(CONF_ZONE, default={}): DEVICE_SCHEMA_SUBDOMAIN,
        },
    ),
    _host_validator,
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [DEVICE_SCHEMA], _has_all_unique_prefixes)},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, hass_config: ConfigType) -> bool:
    """Set up the Elk M1 platform."""
    async_setup_services(hass)

    if DOMAIN not in hass_config:
        return True

    for index, conf in enumerate(hass_config[DOMAIN]):
        _LOGGER.debug("Importing elkm1 #%d - %s", index, conf[CONF_HOST])
        current_config_entry = _async_find_matching_config_entry(
            hass, conf[CONF_PREFIX]
        )
        if current_config_entry:
            hass.config_entries.async_update_entry(current_config_entry, data=conf)
            continue

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=conf,
            )
        )
    return True


@callback
def _async_find_matching_config_entry(
    hass: HomeAssistant, prefix: str
) -> ConfigEntry | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.unique_id == prefix:
            return entry
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ElkM1ConfigEntry) -> bool:
    """Set up Elk-M1 Control from a config entry."""
    conf = entry.data

    serial_port = conf.get("serial_port")
    if serial_port:
        connection_url = f"serial://{serial_port}"
        connection_type = "serial"
    else:
        connection_url = conf.get(CONF_HOST, "")
        conf[CONF_CONNECTION_TYPE] = (
            CONNECTION_SERIAL
            if connection_url.startswith("serial://")
            else CONNECTION_NETWORK
        )

    host = hostname_from_url(connection_url)
        
    host = hostname_from_url(connection_url)
    _LOGGER.info(f"Setting up elkm1 at {connection_url}")

    if (not entry.unique_id or ":" not in entry.unique_id) and is_ip_address(host) and (device := await async_discover_device(hass, entry, "network", 0)):
        await async_update_entry_from_discovery(hass, entry, device)

    # Initialize the new Coordinator
    coordinator = ElkDataUpdateCoordinator(hass, dict(conf))

    try:
        # This will natively connect to the Elk panel, start the background tasks, and fetch state
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        raise ConfigEntryNotReady(f"Timed out or failed connecting to {connection_url}") from exc

    # Run the setup wizard to verify panel version and configure global settings if serial
    # Verify panel version and log required global settings reminders
    try:
        await verify_panel_configuration(coordinator)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(f"Panel verification encountered non-fatal error: {err}")

    # Build the runtime data matching our new models.py
    prefix: str = conf.get(CONF_PREFIX, "")
    auto_configure: bool = conf.get(CONF_AUTO_CONFIGURE, False)

    entry.runtime_data = ElkRuntimeData(
        prefix=prefix,
        mac=entry.unique_id,
        auto_configure=auto_configure,
        config=dict(conf),
        coordinator=coordinator,
        connection=getattr(coordinator, "_connection", None),
    )

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **create_elk_system_device_info(entry),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if async_setup_alarmo_auto_config is not None:
        await async_setup_alarmo_auto_config(hass)

    return True


def _included(ranges: list[tuple[int, int]], set_to: bool, values: list[bool]) -> None:
    for rng in ranges:
        if not rng[0] <= rng[1] <= len(values):
            raise vol.Invalid(f"Invalid range {rng}")
        values[rng[0] - 1 : rng[1]] = [set_to] * (rng[1] - rng[0] + 1)


async def async_unload_entry(hass: HomeAssistant, entry: ElkM1ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Safely disconnect using the coordinator
    coordinator = entry.runtime_data.coordinator
    if coordinator:
        await coordinator.async_disconnect()
        
    return unload_ok

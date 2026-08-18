"""Config flow for Elk-M1 Control integration."""

from __future__ import annotations

import glob
import logging
import os
from typing import Any, Self

try:
    from typing import override
except ImportError:
    from typing_extensions import override

import serial.tools.list_ports
import voluptuous as vol

from elkm1_lib.discovery import ElkSystem
from elkm1_lib.elk import Elk

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_DEVICE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PREFIX,
    CONF_PROTOCOL,
    CONF_USERNAME,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, selector
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.typing import DiscoveryInfoType, VolDictType
from homeassistant.util import slugify

from . import ElkSyncWaiter, hostname_from_url
from .const import CONF_AUTO_CONFIGURE, DISCOVER_SCAN_TIMEOUT, DOMAIN, LOGIN_TIMEOUT
from .discovery import (
    _short_mac,
    async_discover_device,
    async_discover_devices,
    async_update_entry_from_discovery,
)

NON_SECURE_PORT = 2101
SECURE_PORT = 2601
STANDARD_PORTS = {NON_SECURE_PORT, SECURE_PORT}

_LOGGER = logging.getLogger(__name__)

PROTOCOL_MAP = {
    "secure": "elks://",
    "TLS 1.2": "elksv1_2://",
    "non-secure": "elk://",
    "serial": "serial://",
}

VALIDATE_TIMEOUT = 35

BASE_SCHEMA: VolDictType = {
    vol.Optional(CONF_USERNAME, default=""): str,
    vol.Optional(CONF_PASSWORD, default=""): str,
}

SECURE_PROTOCOLS = ["secure", "TLS 1.2"]
ALL_PROTOCOLS = [*SECURE_PROTOCOLS, "non-secure", "serial"]

DEFAULT_SECURE_PROTOCOL = "secure"
DEFAULT_NON_SECURE_PROTOCOL = "non-secure"

PORT_PROTOCOL_MAP = {
    NON_SECURE_PORT: DEFAULT_NON_SECURE_PROTOCOL,
    SECURE_PORT: DEFAULT_SECURE_PROTOCOL,
}


def get_persistent_port_path(device_path: str) -> str:
    """Map a raw /dev/ttyUSBx path to its persistent /dev/serial/by-id/ symlink."""
    try:
        resolved_target = os.path.realpath(device_path)
    except OSError:
        return device_path
    
    for symlink in glob.glob("/dev/serial/by-id/*"):
        try:
            if os.path.realpath(symlink) == resolved_target:
                return symlink
        except OSError:
            continue

    for symlink in glob.glob("/dev/serial/by-path/*"):
        try:
            if os.path.realpath(symlink) == resolved_target:
                return symlink
        except OSError:
            continue

    return device_path


async def validate_input(data: dict[str, str], mac: str | None) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    userid = data.get(CONF_USERNAME)
    password = data.get(CONF_PASSWORD)
    prefix = data.get(CONF_PREFIX, "")
    url = _make_url_from_data(data)

    requires_password = url.startswith(("elks://", "elksv1_2"))
    if requires_password and (not userid or not password):
        raise InvalidAuth

    elk = Elk(
        {"url": url, "userid": userid, "password": password, "element_list": ["panel"]}
    )
    elk.connect()

    try:
        await ElkSyncWaiter(elk, LOGIN_TIMEOUT, VALIDATE_TIMEOUT).async_wait()
    except LoginFailed as exc:
        raise InvalidAuth from exc
    finally:
        elk.disconnect()

    short_mac = _short_mac(mac) if mac else None

    if prefix and prefix != short_mac:
        device_name = prefix
    elif mac:
        device_name = f"ElkM1 {short_mac}"
    else:
        device_name = "ElkM1"

    return {"title": device_name, CONF_HOST: url, CONF_PREFIX: slugify(prefix)}


def _address_from_discovery(device: ElkSystem) -> str:
    """Append the port only if its non-standard."""
    if device.port in STANDARD_PORTS:
        return device.ip_address
    return f"{device.ip_address}:{device.port}"


def _make_url_from_data(data: dict[str, str]) -> str:
    if host := data.get(CONF_HOST):
        return host
    
    protocol = PROTOCOL_MAP.get(data.get(CONF_PROTOCOL, "serial"), "serial://")
    address = data.get(CONF_ADDRESS, data.get("serial_port", ""))
    return f"{protocol}{address}"


def _get_protocol_from_url(url: str) -> str:
    """Get protocol from URL."""
    return next(
        (k for k, v in PROTOCOL_MAP.items() if url.startswith(v)),
        DEFAULT_SECURE_PROTOCOL,
    )


def _placeholders_from_device(device: ElkSystem) -> dict[str, str]:
    return {
        "mac_address": _short_mac(device.mac_address),
        "host": _address_from_discovery(device),
    }


class Elkm1ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elk-M1 Control."""

    VERSION = 1
    host: str | None = None

    def __init__(self) -> None:
        """Initialize the elkm1 config flow."""
        self._discovered_device: ElkSystem | None = None
        self._discovered_devices: dict[str, ElkSystem] = {}

    @override
    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle discovery via dhcp."""
        self._discovered_device = ElkSystem(
            discovery_info.macaddress, discovery_info.ip, 0
        )
        return await self._async_handle_discovery()

    @override
    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        self._discovered_device = ElkSystem(
            discovery_info["mac_address"],
            discovery_info["ip_address"],
            discovery_info["port"],
        )
        return await self._async_handle_discovery()

    async def _async_handle_discovery(self) -> ConfigFlowResult:
        """Handle any discovery."""
        device = self._discovered_device
        assert device is not None
        mac = dr.format_mac(device.mac_address)
        host = device.ip_address
        await self.async_set_unique_id(mac)

        for entry in self._async_current_entries(include_ignore=False):
            if (
                entry.unique_id == mac
                or hostname_from_url(entry.data[CONF_HOST]) == host
            ):
                if async_update_entry_from_discovery(self.hass, entry, device):
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(reason="already_configured")

        self.host = host

        if self.hass.config_entries.flow.async_has_matching_flow(self):
            return self.async_abort(reason="already_in_progress")

        self._abort_if_unique_id_configured()

        if not device.port:
            if discovered_device := await async_discover_device(self.hass, host):
                self._discovered_device = discovered_device
            else:
                return self.async_abort(reason="cannot_connect")

        return await self.async_step_discovery_confirm()

    @override
    def is_matching(self, other_flow: Self) -> bool:
        """Return True if other_flow is matching this flow."""
        return other_flow.host == self.host

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovered_device is not None
        self.context["title_placeholders"] = _placeholders_from_device(
            self._discovered_device
        )
        return await self.async_step_discovered_connection()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            if mac := user_input[CONF_DEVICE]:
                if mac == "serial_port_flow":
                    return await self.async_step_manual_serial()
                elif mac == "manual_network_flow":
                    return await self.async_step_manual_connection()
                else:
                    await self.async_set_unique_id(mac, raise_on_progress=False)
                    self._discovered_device = self._discovered_devices[mac]
                    return await self.async_step_discovered_connection()
            return await self.async_step_manual_connection()

        current_unique_ids = self._async_current_ids(include_ignore=False)
        current_hosts = {
            hostname_from_url(entry.data[CONF_HOST])
            for entry in self._async_current_entries(include_ignore=False)
        }
        
        discovered_devices = await async_discover_devices(
            self.hass, DISCOVER_SCAN_TIMEOUT
        )
        self._discovered_devices = {
            dr.format_mac(device.mac_address): device for device in discovered_devices
        }

        devices_name: dict[str | None, str] = {
            mac: f"{_short_mac(device.mac_address)} ({device.ip_address})"
            for mac, device in self._discovered_devices.items()
            if mac not in current_unique_ids and device.ip_address not in current_hosts
        }

        # Inject UI options for Manual and Serial
        devices_name["manual_network_flow"] = "Manual Network Entry"
        devices_name["serial_port_flow"] = "USB / Serial Port Discovery"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE): vol.In(devices_name)}),
        )

    async def _async_create_or_error(
        self, user_input: dict[str, Any], importing: bool
    ) -> tuple[dict[str, str] | None, ConfigFlowResult | None]:
        """Try to connect and create the entry or error."""
        if self._url_already_configured(_make_url_from_data(user_input)):
            return None, self.async_abort(reason="address_already_configured")

        try:
            info = await validate_input(user_input, self.unique_id)
        except TimeoutError as ex:
            _LOGGER.debug("Connection timed out: %s", ex)
            return {"base": "cannot_connect"}, None
        except InvalidAuth as ex:
            _LOGGER.debug("Invalid auth for %s: %s", user_input.get(CONF_HOST), ex)
            return {CONF_PASSWORD: "invalid_auth"}, None
        except Exception:
            _LOGGER.exception("Unexpected error validating input")
            return {"base": "unknown"}, None

        data_payload = {
            CONF_HOST: info[CONF_HOST],
            CONF_USERNAME: user_input.get(CONF_USERNAME, ""),
            CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
            CONF_AUTO_CONFIGURE: True,
            CONF_PREFIX: info[CONF_PREFIX],
        }

        if "serial_port" in user_input:
            data_payload["serial_port"] = user_input["serial_port"]

        if importing:
            return None, self.async_create_entry(title=info["title"], data=user_input)

        return None, self.async_create_entry(title=info["title"], data=data_payload)

    async def async_step_discovered_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle connecting the device when we have a discovery."""
        errors: dict[str, str] | None = {}
        device = self._discovered_device
        assert device is not None

        if user_input is not None:
            user_input[CONF_ADDRESS] = _address_from_discovery(device)
            if self._async_current_entries():
                user_input[CONF_PREFIX] = _short_mac(device.mac_address)
            else:
                user_input[CONF_PREFIX] = ""
            errors, result = await self._async_create_or_error(user_input, False)
            if result is not None:
                return result

        default_proto = PORT_PROTOCOL_MAP.get(device.port, DEFAULT_SECURE_PROTOCOL)

        return self.async_show_form(
            step_id="discovered_connection",
            data_schema=vol.Schema(
                {
                    **BASE_SCHEMA,
                    vol.Required(CONF_PROTOCOL, default=default_proto): vol.In(
                        ALL_PROTOCOLS
                    ),
                }
            ),
            errors=errors,
            description_placeholders=_placeholders_from_device(device),
        )

    async def async_step_manual_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle connecting the device when we need manual network entry."""
        errors: dict[str, str] | None = {}
        if user_input is not None:
            if device := await async_discover_device(
                self.hass, user_input[CONF_ADDRESS]
            ):
                await self.async_set_unique_id(
                    dr.format_mac(device.mac_address), raise_on_progress=False
                )
                self._abort_if_unique_id_configured()
                user_input[CONF_ADDRESS] = device.ip_address

            errors, result = await self._async_create_or_error(user_input, False)
            if result is not None:
                return result

        return self.async_show_form(
            step_id="manual_connection",
            data_schema=vol.Schema(
                {
                    **BASE_SCHEMA,
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_PREFIX, default=""): str,
                    vol.Required(
                        CONF_PROTOCOL, default=DEFAULT_SECURE_PROTOCOL
                    ): vol.In(ALL_PROTOCOLS),
                }
            ),
            errors=errors,
        )

    async def async_step_manual_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle connecting the device via a dynamically probed USB/Serial port."""
        errors: dict[str, str] | None = {}

        if user_input is not None:
            raw_port = user_input["serial_port"]
            
            # Map dynamic ttyUSB to persistent by-id path
            persistent_port = await self.hass.async_add_executor_job(
                get_persistent_port_path, raw_port
            )
            
            user_input["serial_port"] = persistent_port
            
            # Route through the core sync validation
            errors, result = await self._async_create_or_error(user_input, False)
            if result is not None:
                return result

        # Probe the OS for active ports
        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        port_options = [
            {"value": p.device, "label": f"{p.device} - {p.description}"}
            for p in ports
        ]
        
        if not port_options:
            port_options = [{"value": "", "label": "No serial ports discovered on system"}]

        data_schema = vol.Schema(
            {
                vol.Required("serial_port"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=port_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(CONF_PREFIX, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="manual_serial",
            data_schema=data_schema,
            errors=errors,
        )

    def _url_already_configured(self, url: str) -> bool:
        """See if we already have a elkm1 matching user input configured."""
        existing_hosts = {
            hostname_from_url(entry.data[CONF_HOST])
            for entry in self._async_current_entries()
        }
        return hostname_from_url(url) in existing_hosts


class LoginFailed(Exception):
    """Raised when login to ElkM1 fails."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

"""Config flow for Elk-M1 Control integration."""

from __future__ import annotations

import asyncio
import glob
import logging
import os
from typing import Any, Self

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from urllib.parse import urlparse
import voluptuous as vol

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

from .const import (
    CONF_AUTO_CONFIGURE,
    CONF_CONNECTION_TYPE,
    CONF_PIN,
    CONF_SERIAL_PORT,
    CONNECTION_SERIAL,
    DOMAIN,
)
from .discovery import (
    _short_mac,
    async_discover_devices,
)
from .helpers.connection import ElkConnectionManager
from .helpers.usb_discovery import probe_serial_port

NON_SECURE_PORT = 2101
SECURE_PORT = 2601
STANDARD_PORTS = {NON_SECURE_PORT, SECURE_PORT}
CONF_VERIFY_DEVICE = "verify_device"

_LOGGER = logging.getLogger(__name__)

PROTOCOL_MAP = {
    "secure": "elks://",
    "TLS 1.2": "elksv1_2://",
    "non-secure": "elk://",
    "serial": "serial://",
}

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

def hostname_from_url(url: str) -> str:
    """Return the hostname from a url."""
    parsed = urlparse(url)
    return parsed.hostname or url.replace("serial://", "")

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
    """Validate the user input allows us to connect natively without elkm1_lib."""
    userid = data.get(CONF_USERNAME)
    password = data.get(CONF_PASSWORD)
    prefix = data.get(CONF_PREFIX, "")
    url = _make_url_from_data(data)

    requires_password = url.startswith(("elks://", "elksv1_2"))
    if requires_password and (not userid or not password):
        raise InvalidAuth

    connected_event = asyncio.Event()

    def _on_message(msg: str) -> None:
        """Callback to prove the connection is receiving live Elk data."""
        if len(msg) >= 4:
            connected_event.set()

    conn = ElkConnectionManager(
        connection_url=url,
        on_message_callback=_on_message,
        is_serial=url.startswith("serial://")
    )

    try:
        await conn.connect()
        # Request panel version to force a response
        await conn.write("vn")
        
        # Wait up to 10 seconds for the panel to respond
        await asyncio.wait_for(connected_event.wait(), timeout=10.0)
    except asyncio.TimeoutError as exc:
        raise CannotConnect from exc
    except Exception as exc:
        raise CannotConnect from exc
    finally:
        await conn.disconnect()

    short_mac = _short_mac(mac) if mac else None

    if prefix and prefix != short_mac:
        device_name = prefix
    elif mac:
        device_name = f"ElkM1 {short_mac}"
    else:
        device_name = "ElkM1"

    return {"title": device_name, CONF_HOST: url, CONF_PREFIX: slugify(prefix)}


def _address_from_discovery(device: dict[str, Any]) -> str:
    """Append the port only if its non-standard."""
    port = device.get("port", NON_SECURE_PORT)
    ip_addr = device.get("ip_address", "")
    if port in STANDARD_PORTS:
        return ip_addr
    return f"{ip_addr}:{port}"


def _make_url_from_data(data: dict[str, str]) -> str:
    if host := data.get(CONF_HOST):
        return host
    
    protocol = PROTOCOL_MAP.get(data.get(CONF_PROTOCOL, "serial"), "serial://")
    address = data.get(CONF_ADDRESS, data.get("serial_port", ""))
    return f"{protocol}{address}"


def _placeholders_from_device(device: dict[str, Any]) -> dict[str, str]:
    return {
        "mac_address": _short_mac(device.get("mac_address", "")),
        "host": _address_from_discovery(device),
    }


class Elkm1ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elk-M1 Control."""

    VERSION = 1
    host: str | None = None

    def __init__(self) -> None:
        """Initialize the elkm1 config flow."""
        self._discovered_device: dict[str, Any] | None = None
        self._discovered_devices: dict[str, dict[str, Any]] = {}

    @override
    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle discovery via dhcp."""
        self._discovered_device = {
            "mac_address": discovery_info.macaddress,
            "ip_address": discovery_info.ip,
            "port": 0
        }
        return await self._async_handle_discovery()

    @override
    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        self._discovered_device = {
            "mac_address": discovery_info["mac_address"],
            "ip_address": discovery_info["ip_address"],
            "port": discovery_info.get("port", NON_SECURE_PORT),
        }
        return await self._async_handle_discovery()

    async def _async_handle_discovery(self) -> ConfigFlowResult:
        """Handle any discovery."""
        device = self._discovered_device
        assert device is not None
        mac = dr.format_mac(device["mac_address"])
        host = device["ip_address"]
        await self.async_set_unique_id(mac)

        for entry in self._async_current_entries(include_ignore=False):
            if (
                entry.unique_id == mac
                or hostname_from_url(entry.data.get(CONF_HOST, "")) == host
            ):
                return self.async_abort(reason="already_configured")

        self.host = host

        if self.hass.config_entries.flow.async_has_matching_flow(self):
            return self.async_abort(reason="already_in_progress")

        self._abort_if_unique_id_configured()

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
                    return await self.async_step_serial()
                elif mac == "manual_network_flow":
                    return await self.async_step_manual_connection()
                else:
                    await self.async_set_unique_id(mac, raise_on_progress=False)
                    self._discovered_device = self._discovered_devices[mac]
                    return await self.async_step_discovered_connection()
            return await self.async_step_manual_connection()

        current_unique_ids = self._async_current_ids(include_ignore=False)
        
        discovered_devices = await async_discover_devices(self.hass)
        self._discovered_devices = {
            dr.format_mac(device["mac_address"]): device for device in discovered_devices
        }

        devices_name: dict[str | None, str] = {
            mac: f"{_short_mac(device['mac_address'])} ({device['ip_address']})"
            for mac, device in self._discovered_devices.items()
            if mac not in current_unique_ids
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
        except CannotConnect:
            return {"base": "cannot_connect"}, None
        except InvalidAuth:
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
                user_input[CONF_PREFIX] = _short_mac(device.get("mac_address", ""))
            else:
                user_input[CONF_PREFIX] = ""
            errors, result = await self._async_create_or_error(user_input, False)
            if result is not None:
                return result

        default_proto = PORT_PROTOCOL_MAP.get(device.get("port", NON_SECURE_PORT), DEFAULT_SECURE_PROTOCOL)

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

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2a: Serial/USB configuration with PIN & Smart Probing."""
        import serial.tools.list_ports
        errors = {}

        if user_input is not None:
            raw_port = user_input[CONF_SERIAL_PORT]
            
            # Map dynamic ttyUSB to persistent by-id path
            port = await self.hass.async_add_executor_job(
                get_persistent_port_path, raw_port
            )
            
            # Check if already configured using the persistent path
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            
            # Verify device exists on this port
            if user_input.get(CONF_VERIFY_DEVICE, True):
                try:
                    if not await probe_serial_port(port, timeout=5.0):
                        errors["base"] = "no_elk_device"
                except (OSError, TimeoutError, ValueError) as e:
                    _LOGGER.error(f"Error probing port: {e}")
                    errors["base"] = "cannot_connect"
            
            if not errors:
                # Normalize PIN: ignore if empty, None, 0, or "0"
                raw_pin = user_input.get(CONF_PIN)
                pin = str(raw_pin).strip() if raw_pin not in (None, "", 0, "0") else ""

                return self.async_create_entry(
                    title=f"Elk-M1 Serial @ {port}",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_SERIAL,
                        CONF_SERIAL_PORT: port,
                        CONF_PIN: pin,  # Saves as empty string if ignored
                    },
                )

        # 1. Map all active HA integration entries to device paths they consume
        ha_configured_ports: dict[str, str] = {}
        for entry in self.hass.config_entries.async_entries():
            # Check if an entry is utilizing a serial port
            if CONF_SERIAL_PORT in entry.data:
                ha_configured_ports[entry.data[CONF_SERIAL_PORT]] = entry.domain
            elif "device" in entry.data: # ZHA / Z-Wave JS standard
                ha_configured_ports[entry.data["device"]] = entry.domain

        # 2. Get list of ports from the OS
        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)

        # 3. Smart Hardware Probe (Async Concurrent Execution)
        async def _probe_and_format(port_info: Any) -> dict[str, str]:
            device_path = port_info.device
            
            # Get the reboot-safe persistent path
            persistent_path = await self.hass.async_add_executor_job(
                get_persistent_port_path, device_path
            )
            
            status_label = "(Available)"

            # Check raw and persistent paths against HA configured ports
            if device_path in ha_configured_ports or persistent_path in ha_configured_ports:
                using_domain = ha_configured_ports.get(device_path) or ha_configured_ports.get(persistent_path)
                status_label = f"(In Use by {using_domain})"
            else:
                try:
                    # Probe the hardware directly using our ElkConnectionManager probe
                    is_elk = await probe_serial_port(persistent_path, timeout=2.0)
                    if is_elk:
                        status_label = "(ELK-M1 Panel Detected) 🎯"
                except Exception:  # noqa: BLE001
                    status_label = "(Available)"

            # Build a clean label for the UI
            label = f"{persistent_path} - {port_info.description}" if port_info.description and port_info.description != "n/a" else persistent_path
            
            return {
                "value": persistent_path, 
                "label": f"{status_label} {label}",
            }

        # 4. Run all port probes CONCURRENTLY
        port_options = await asyncio.gather(*[_probe_and_format(p) for p in ports])
        
        # Fallback if the system literally has 0 serial ports available
        if not port_options:
            port_options = [{"value": "", "label": "No serial ports discovered on system"}]

        # Serial configuration schema using flexible dynamic dropdown
        data_schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=port_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(CONF_PIN, default=""): str,
                vol.Optional(CONF_VERIFY_DEVICE, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"discovered": str(len(ports))}
        )

    def _url_already_configured(self, url: str) -> bool:
        """See if we already have a elkm1 matching user input configured."""
        existing_hosts = {
            hostname_from_url(entry.data.get(CONF_HOST, ""))
            for entry in self._async_current_entries()
        }
        return hostname_from_url(url) in existing_hosts


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

"""Config flow for Elk-M1 Control integration."""

import asyncio
import glob
import logging
import os
import serial.tools.list_ports
from typing import Any

import voluptuous as vol  # type: ignore[import-untyped]

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_PIN,
    CONF_SERIAL_PORT,
    CONF_VERIFY_DEVICE,
    CONNECTION_NETWORK,
    CONNECTION_SERIAL,
    DOMAIN,
)
from .helpers.usb_discovery import probe_serial_port

_LOGGER = logging.getLogger(__name__)

def get_persistent_port_path(device_path: str) -> str:
    """Map a raw /dev/ttyUSBx path to its persistent /dev/serial/by-id/ symlink."""
    try:
        resolved_target = os.path.realpath(device_path)
    except OSError:
        return device_path
    
    # 1. First choice: Check /dev/serial/by-id/ (Unique by hardware serial number)
    for symlink in glob.glob("/dev/serial/by-id/*"):
        try:
            if os.path.realpath(symlink) == resolved_target:
                return symlink
        except OSError as err:
            _LOGGER.debug("Could not resolve symlink %s: %s", symlink, err)
            continue

    # 2. Second choice: Check /dev/serial/by-path/ (Unique by physical USB socket)
    for symlink in glob.glob("/dev/serial/by-path/*"):
        try:
            if os.path.realpath(symlink) == resolved_target:
                return symlink
        except OSError as err:
            _LOGGER.debug("Could not resolve symlink %s: %s", symlink, err)
            continue

    # Fallback to provided path if no persistent symlinks exist
    return device_path


class ElkM1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Elk-M1 Control."""

    VERSION = 1
    
    _connection_type: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Ask user how to connect (Serial or Network)."""
        
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            
            if self._connection_type == CONNECTION_SERIAL:
                return await self.async_step_serial()
            else:
                return await self.async_step_network()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE): vol.In(
                    {
                        CONNECTION_SERIAL: "Serial/USB (Direct connection)",
                        CONNECTION_NETWORK: "Network (Elk M1XEP or remote)",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            description_placeholders={},
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2a: Serial/USB configuration with PIN."""
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
        async def _probe_and_format(port_info) -> dict[str, str]:
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
                    # Probe the hardware directly
                    is_elk = await probe_serial_port(persistent_path, timeout=2.0)
                    if is_elk:
                        status_label = "(ELK-M1 Panel Detected) 🎯"
                except Exception:
                    status_label = "(Available)"

            # Build a clean label for the UI
            label = f"{persistent_path} - {port_info.description}" if port_info.description and port_info.description != "n/a" else persistent_path
            
            return {
                "value": persistent_path, 
                "label": f"{label} {status_label}",
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

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2b: Network (Elk M1XEP) configuration with username/password."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, 2101)
            
            unique_id = f"{host}:{port}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            
            # Test network connection
            try:
                if not await probe_network_device(
                    host, 
                    port,
                    user_input.get(CONF_USERNAME, ""),
                    user_input.get(CONF_PASSWORD, ""),
                    timeout=5.0
                ):
                    errors["base"] = "cannot_connect"
            except (OSError, TimeoutError, ValueError) as e:
                _LOGGER.error(f"Error probing port: {e}")
                errors["base"] = "cannot_connect"
            
            if not errors:
                return self.async_create_entry(
                    title=f"Elk-M1 Network @ {host}",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_NETWORK,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_USERNAME: user_input.get(CONF_USERNAME, ""),
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                        CONF_PIN: user_input.get(CONF_PIN, ""),  # Optional PIN
                    },
                )

        # Network configuration schema - username/password
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=2101): int,
                vol.Required(CONF_USERNAME): str,  # M1XEP requires username
                vol.Required(CONF_PASSWORD): str,  # M1XEP requires password
                vol.Optional(CONF_PIN, default=""): str,  # Optional PIN override
            }
        )

        return self.async_show_form(
            step_id="network",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration."""
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        
        connection_type = config_entry.data.get(CONF_CONNECTION_TYPE)

        if user_input is not None:
            # Map dynamic ttyUSB to persistent by-id path during reconfiguration
            if connection_type == CONNECTION_SERIAL and CONF_SERIAL_PORT in user_input:
                raw_port = user_input[CONF_SERIAL_PORT]
                persistent_port = await self.hass.async_add_executor_job(
                    get_persistent_port_path, raw_port
                )
                user_input[CONF_SERIAL_PORT] = persistent_port

            # Normalize PIN if it was modified during reconfiguration
            if CONF_PIN in user_input:
                raw_pin = user_input[CONF_PIN]
                user_input[CONF_PIN] = str(raw_pin).strip() if raw_pin not in (None, "", 0, "0") else ""

            self.hass.config_entries.async_update_entry(
                config_entry,
                data={**config_entry.data, **user_input},
            )
            await self.hass.config_entries.async_reload(config_entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")

        # Show appropriate form based on connection type
        if connection_type == CONNECTION_SERIAL:
            data_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_SERIAL_PORT,
                        default=config_entry.data.get(CONF_SERIAL_PORT),
                    ): selector.SerialPortSelector(),
                    vol.Optional(
                        CONF_PIN,
                        default=config_entry.data.get(CONF_PIN, ""),
                    ): str,
                }
            )
        else:
            # Network reconfiguration
            data_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=config_entry.data.get(CONF_HOST),
                    ): str,
                    vol.Optional(
                        CONF_PORT,
                        default=int(config_entry.data.get(CONF_PORT, 2101)),
                    ): int,
                    vol.Required(
                        CONF_USERNAME,
                        default=config_entry.data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(
                        CONF_PASSWORD,
                        default=config_entry.data.get(CONF_PASSWORD, ""),
                    ): str,
                }
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
        )

async def probe_network_device(
    host: str,
    port: int = 2101,
    username: str = "",
    password: str = "",
    timeout: float = 5.0,
) -> bool:
    """Test network connection to Elk M1XEP."""
    
    from elkm1_lib import Elk
    
    try:
        url = f"elk://{host}:{port}"
        _LOGGER.debug(f"Testing connection to {url}")
        
        config = {"url": url}
        if username:
            config["userid"] = username
        if password:
            config["password"] = password
            
        connection = Elk(config)
        connected_event = asyncio.Event()
        
        def on_connected(*args, **kwargs):
            connected_event.set()
            
        connection.add_handler("connected", on_connected)
        
        # Connect is synchronous, do not await it
        connection.connect()
        
        try:
            # Wait for the connected event
            await asyncio.wait_for(connected_event.wait(), timeout=timeout)
            _LOGGER.info(f"Network device {url}: Connected ✓")
            return True
        except asyncio.TimeoutError:
            _LOGGER.debug(f"Network device {host}: Connection timeout")
            return False
        finally:
            # Safely release the connection block to prevent task leaking
            connection.disconnect() 
            
    except Exception as e:  # noqa: BLE001
        _LOGGER.debug(f"Network device {host}: Error - {e}")
        return False

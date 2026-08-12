"""Config flow for Elk-M1 Control integration."""

import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_SERIAL_PORT,
    CONF_CONNECTION_TYPE,
    CONF_VERIFY_DEVICE,
    CONNECTION_SERIAL,
    CONNECTION_NETWORK,
)
from .helpers.usb_discovery import discover_elk_ports, probe_serial_port

_LOGGER = logging.getLogger(__name__)


class ElkM1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elk-M1 Control."""

    VERSION = 1
    
    # Store connection type for use in next step
    _connection_type: str = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Step 1: Ask user how to connect (Serial or Network)."""
        
        if user_input is not None:
            # Save connection type for next step
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            
            # Go to appropriate next step
            if self._connection_type == CONNECTION_SERIAL:
                return await self.async_step_serial()
            else:
                return await self.async_step_network()

        # Show connection type selection
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
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Step 2a: Serial/USB configuration."""
        errors = {}

        if user_input is not None:
            # Validate and save
            port = user_input[CONF_SERIAL_PORT]
            
            # Check if already configured
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            
            # Optional: verify device exists
            if user_input.get(CONF_VERIFY_DEVICE, True):
                try:
                    if not await probe_serial_port(port, timeout=5):
                        errors["base"] = "no_elk_device"
                except Exception as e:
                    _LOGGER.error(f"Error probing port: {e}")
                    errors["base"] = "cannot_connect"
            
            if not errors:
                return self.async_create_entry(
                    title=f"Elk-M1 Serial @ {port}",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_SERIAL,
                        CONF_SERIAL_PORT: port,
                        CONF_USERNAME: user_input.get(CONF_USERNAME, ""),
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                    },
                )

        # Discover available ports
        try:
            ports = await discover_elk_ports()
            description_placeholders = {"discovered": str(len(ports))}
        except Exception as e:
            _LOGGER.error(f"Error discovering ports: {e}")
            ports = {}
            description_placeholders = {"discovered": "0"}

        # If no ports found, allow manual entry
        if not ports:
            ports = {"manual": "Enter port manually"}

        # Serial configuration schema
        data_schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): vol.In(ports),
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_VERIFY_DEVICE, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_network(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Step 2b: Network (Elk M1XEP) configuration."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, 2101)
            
            # Create unique ID from host:port
            unique_id = f"{host}:{port}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            
            # Optional: test connection
            try:
                if not await probe_network_device(host, port, timeout=5):
                    errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.error(f"Error testing network connection: {e}")
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
                    },
                )

        # Network configuration schema
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,  # e.g., "192.168.1.100"
                vol.Optional(CONF_PORT, default=2101): int,
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="network",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={},
        )

    async def async_step_reconfigure(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle reconfiguration of existing entry."""
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        
        connection_type = config_entry.data.get(CONF_CONNECTION_TYPE)

        if user_input is not None:
            # Update the config entry
            self.hass.config_entries.async_update_entry(
                config_entry,
                data={**config_entry.data, **user_input},
            )
            await self.hass.config_entries.async_reload(config_entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")

        # Show appropriate form based on connection type
        if connection_type == CONNECTION_SERIAL:
            try:
                ports = await discover_elk_ports()
            except Exception as e:
                _LOGGER.error(f"Error discovering ports: {e}")
                ports = {}

            if not ports:
                ports = {"manual": "Enter port manually"}

            data_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_SERIAL_PORT,
                        default=config_entry.data.get(CONF_SERIAL_PORT),
                    ): vol.In(ports),
                }
            )

            return self.async_show_form(
                step_id="reconfigure",
                data_schema=data_schema,
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
                        default=config_entry.data.get(CONF_PORT, 2101),
                    ): int,
                }
            )

            return self.async_show_form(
                step_id="reconfigure",
                data_schema=data_schema,
            )


async def probe_network_device(
    host: str, port: int = 2101, timeout: float = 5.0
) -> bool:
    """
    Test if a network device is an ELK-M1 panel.
    
    Args:
        host: IP address or hostname
        port: TCP port (default 2101 for Elk M1XEP)
        timeout: Connection timeout
        
    Returns:
        True if device responds, False otherwise
    """
    from elkm1_lib.connection import ElkM1Connection
    import asyncio
    
    try:
        url = f"elk://{host}:{port}"
        _LOGGER.debug(f"Testing connection to {url}")
        
        connection = ElkM1Connection(url=url, timeout=timeout)
        
        async def _connect():
            await asyncio.wait_for(connection.connect(), timeout=timeout)
            await connection.disconnect()
            return True
        
        result = await _connect()
        _LOGGER.info(f"Network device {url}: ELK-M1 detected ✓")
        return result
        
    except asyncio.TimeoutError:
        _LOGGER.debug(f"Network device {host}: Connection timeout")
        return False
    except Exception as e:
        _LOGGER.debug(f"Network device {host}: No response - {e}")
        return False

"""Config flow for Elk-M1 Control integration."""

import logging
from typing import Any

import voluptuous as vol  # type: ignore[import-untyped]
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult


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
            port = user_input[CONF_SERIAL_PORT]
            
            # Check if already configured
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            
            # Verify device exists on this port
            if user_input.get(CONF_VERIFY_DEVICE, True):
                try:
                    if not await probe_serial_port(port, timeout=5):
                        errors["base"] = "no_elk_device"
                except (OSError, TimeoutError, ValueError) as e:
                    _LOGGER.error(f"Error probing port: {e}")
                    errors["base"] = "cannot_connect"
            
            if not errors:
                return self.async_create_entry(
                    title=f"Elk-M1 Serial @ {port}",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_SERIAL,
                        CONF_SERIAL_PORT: port,
                        CONF_PIN: user_input.get(CONF_PIN, ""),  # PIN for commands
                        # Note: No username/password for serial
                    },
                )

        # Serial configuration schema using the native UI Selector
        data_schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): selector.SerialPortSelector(),
                vol.Optional(CONF_PIN, default=""): str,  # PIN for commands
                vol.Optional(CONF_VERIFY_DEVICE, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={},
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
                    timeout=5
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
                        default=config_entry.data.get(CONF_PORT, 2101),
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
    import asyncio
    
    # FIX 1: Import the correct Elk class
    from elkm1_lib import Elk
    
    try:
        url = f"elk://{host}:{port}"
        _LOGGER.debug(f"Testing connection to {url}")
        
        # FIX 2: elkm1_lib expects a config dictionary, not kwargs
        config = {"url": url}
        if username:
            config["userid"] = username
        if password:
            config["password"] = password
            
        # Initialize with the config dict
        connection = Elk(config)
        
        async def _connect():
            # Attempt to connect within the timeout period
            await asyncio.wait_for(connection.connect(), timeout=timeout)
            
            # FIX 3: In elkm1_lib, disconnect is usually synchronous (no 'await' needed)
            connection.disconnect() 
            return True
        
        result = await _connect()
        _LOGGER.info(f"Network device {url}: Connected ✓")
        return result
        
    except asyncio.TimeoutError:
        _LOGGER.debug(f"Network device {host}: Connection timeout")
        return False
    except Exception as e:  # Broadened to catch elkm1_lib specific exceptions
        _LOGGER.debug(f"Network device {host}: Error - {e}")
        return False

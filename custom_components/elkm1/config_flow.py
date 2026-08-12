"""Config flow for Elk-M1 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_USERNAME, CONF_PASSWORD
from .helpers.usb_discovery import discover_elk_ports, probe_serial_port

_LOGGER: logging.Logger = logging.getLogger(__name__)


class ElkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Elk-M1."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user config step with port auto-detection."""
        errors = {}

        if user_input is not None:
            # User selected or entered a port
            try:
                # Test the port before saving
                await probe_serial_port(user_input[CONF_SERIAL_PORT])
            except Exception as err:
                _LOGGER.error(f"Failed to connect to port: {err}")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Elk-M1 @ {user_input[CONF_SERIAL_PORT]}",
                    data=user_input,
                )

        # Auto-discover available ports
        discovered_ports: dict[str, str] = {}
        try:
            discovered_ports = await discover_elk_ports()
        except Exception as err:
            _LOGGER.warning(f"Auto-discovery failed: {err}")

        # Build schema with discovered ports + manual entry
        port_options = {**discovered_ports, "manual": "Enter port manually..."}
        
        schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): vol.In(port_options),
                vol.Optional(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "discovered_count": str(len(discovered_ports)),
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration (changing port, credentials)."""
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if not config_entry:
            return self.async_abort(reason="reconfigure_failed")

        return await self.async_step_user()

"""Diagnostics for Elk-M1 integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .models import ELKM1Data

# Ensure all security credentials and network locators are wiped from the diagnostic output
TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "pin", "code", "userid", "host", "serial_port"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for config entry."""
    elk_data: ELKM1Data = entry.runtime_data
    coordinator = elk_data.coordinator

    # Our coordinator already normalizes everything into a safe, serializable dictionary!
    data = coordinator.data if coordinator and coordinator.data else {}

    return {
        "config_entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
            "prefix": elk_data.prefix,
            "mac": elk_data.mac,
            "auto_configure": elk_data.auto_configure,
            "config_filters": async_redact_data(elk_data.config, TO_REDACT),
        },
        "panel": {
            "connected": coordinator.connected if coordinator else False,
            "elkm1_version": data.get("panel_version", "Unknown"),
            "system_trouble_status": data.get("trouble_status", False),
            "ac_power": data.get("ac_power", True),
            "battery_status": data.get("battery_status", "Good"),
        },
        "areas": data.get("areas", {}),
        "zones": data.get("zones", []),
        "keypads": data.get("keypads", []),
        "outputs": data.get("outputs", []),
        "thermostats": data.get("thermostats", []),
        "tasks": data.get("tasks", []),
        "counters": data.get("counters", []),
        "settings": data.get("settings", []),
    }

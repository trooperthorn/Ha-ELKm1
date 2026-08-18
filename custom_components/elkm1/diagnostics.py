"""Diagnostics for Elk-M1 integration."""
from __future__ import annotations

from enum import Enum
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .models import ELKM1Data

# Ensure all security credentials are wiped from the diagnostic output
TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "pin", "code", "userid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for config entry."""
    elk_data: ELKM1Data = entry.runtime_data
    elk = elk_data.elk

    def serialize_elements(elements: Any) -> dict[int, dict[str, Any]]:
        """Safely serialize Elk elements and unpack strict Enums for JSON formatting."""
        if not elements:
            return {}
        
        result = {}
        for element in elements:
            elem_dict = {}
            for k, v in element.as_dict().items():
                if isinstance(v, Enum):
                    elem_dict[k] = v.name
                else:
                    elem_dict[k] = v
            result[element.index] = elem_dict
            
        return result

    return {
        "config_entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
            "prefix": elk_data.prefix,
            "mac": elk_data.mac,
            "auto_configure": elk_data.auto_configure,
            "config_filters": elk_data.config,
        },
        "panel": {
            "connected": elk.is_connected() if elk else False,
            "paused": elk.is_paused() if elk else False,
            "elkm1_version": getattr(elk.panel, "elkm1_version", "Unknown") if elk and hasattr(elk, "panel") else "Unknown",
            "system_trouble_status": str(getattr(elk.panel, "system_trouble_status", "")) if elk and hasattr(elk, "panel") else "",
        },
        "areas": serialize_elements(getattr(elk, "areas", [])),
        "zones": serialize_elements(getattr(elk, "zones", [])),
        "keypads": serialize_elements(getattr(elk, "keypads", [])),
        "outputs": serialize_elements(getattr(elk, "outputs", [])),
        "thermostats": serialize_elements(getattr(elk, "thermostats", [])),
        "tasks": serialize_elements(getattr(elk, "tasks", [])),
        "counters": serialize_elements(getattr(elk, "counters", [])),
        "settings": serialize_elements(getattr(elk, "settings", [])),
    }

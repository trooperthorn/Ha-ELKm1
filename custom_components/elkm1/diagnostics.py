"""Diagnostics for Elk-M1 integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_PASSWORD
from .data import ElkRuntimeData

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for config entry."""
    runtime_data: ElkRuntimeData = entry.runtime_data

    diag_data = {
        "config": async_redact_data(entry.data, TO_REDACT),
        "serial_port": runtime_data.serial_port,
        "panel_state": {
            "armed": runtime_data.coordinator.data.get("armed"),
            "zones_faulted": runtime_data.coordinator.data.get("zones_faulted"),
            "outputs_active": runtime_data.coordinator.data.get("outputs_active"),
        },
        "coordinator_data": runtime_data.coordinator.last_update_success,
    }

    return diag_data

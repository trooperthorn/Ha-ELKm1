"""Diagnostics for Elk-M1 integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .data import ElkRuntimeData


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for config entry."""
    runtime_data: ElkRuntimeData = entry.runtime_data
    coordinator = runtime_data.coordinator

    # Zone diagnostics
    zones_diag = {}
    if coordinator._elk:
        for i, zone in enumerate(coordinator._elk.zones):
            zones_diag[i] = {
                "name": zone.name if zone else None,
                "faulted": zone.faulted if zone else None,
                "open": zone.open if zone else None,
                "zone_type": zone.zone_type if zone else None,
            }

    # Output diagnostics
    outputs_diag = {}
    if coordinator._elk:
        for i, output in enumerate(coordinator._elk.outputs):
            outputs_diag[i] = {
                "name": output.name if output else None,
                "status": output.status if output else None,
            }

    return {
        "config": {
            "serial_port": runtime_data.serial_port,
        },
        "panel_state": {
            "armed": coordinator.data.get("armed") if coordinator.data else None,
            "armed_mode": coordinator.data.get("armed_mode") if coordinator.data else None,
            "zones_faulted": coordinator.data.get("zones_faulted") if coordinator.data else [],
            "outputs_active": coordinator.data.get("outputs_active") if coordinator.data else [],
        },
        "zones": zones_diag,
        "outputs": outputs_diag,
        "coordinator_health": {
            "last_update_success": coordinator.last_update_success,
            "last_update_error": str(coordinator.last_update_error) if coordinator.last_update_error else None,
        },
    }

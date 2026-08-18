"""Support the ElkM1 Gold and ElkM1 EZ8 alarm/integration panels."""

from __future__ import annotations

import voluptuous as vol

from elkm1_lib.elk import Elk, Panel

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .models import ELKM1Data

SPEAK_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("number"): vol.All(vol.Coerce(int), vol.Range(min=0, max=999)),
        vol.Optional("prefix", default=""): cv.string,
    }
)

SET_TIME_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("prefix", default=""): cv.string,
    }
)

SECURITY_SUMMARY_SCHEMA = vol.Schema(
    {
        vol.Optional("prefix", default=""): cv.string,
    }
)

def _find_elk_by_prefix(hass: HomeAssistant, prefix: str) -> Elk | None:
    """Search all config entries for a given prefix."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not entry.runtime_data:
            continue
        elk_data: ELKM1Data = entry.runtime_data
        if elk_data.prefix == prefix:
            return elk_data.elk
    return None

@callback
def _async_get_elk_panel(service: ServiceCall) -> Panel:
    """Get the ElkM1 panel from a service call."""
    prefix = service.data.get("prefix", "")
    elk = _find_elk_by_prefix(service.hass, prefix)
    if elk is None:
        raise HomeAssistantError(f"No ElkM1 with prefix '{prefix}' found")
    return elk.panel

@callback
def _speak_word_service(service: ServiceCall) -> None:
    _async_get_elk_panel(service).speak_word(service.data["number"])

@callback
def _speak_phrase_service(service: ServiceCall) -> None:
    _async_get_elk_panel(service).speak_phrase(service.data["number"])

@callback
def _set_time_service(service: ServiceCall) -> None:
    _async_get_elk_panel(service).set_time(dt_util.now())

@callback
def _get_security_summary(service: ServiceCall) -> ServiceResponse:
    """Return live security data to an automation or script."""
    prefix = service.data.get("prefix", "")
    elk = _find_elk_by_prefix(service.hass, prefix)
    if elk is None:
        raise HomeAssistantError(f"No ElkM1 with prefix '{prefix}' found")
    
    faulted_zones = []
    # Definition 2 corresponds to Burglar/Perimeter, 1 corresponds to Burglar/Entry
    # Logical status 2 is Violated/Open
    for zone in elk.zones:
        if zone and hasattr(zone, "logical_status") and zone.logical_status.value == 2:
            faulted_zones.append(zone.index + 1)

    return {
        "total_faulted": len(faulted_zones),
        "is_ready_to_arm": len(faulted_zones) == 0,
        "faulted_zone_numbers": faulted_zones,
    }

@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Create ElkM1 services."""
    hass.services.async_register(
        DOMAIN, "speak_word", _speak_word_service, SPEAK_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "speak_phrase", _speak_phrase_service, SPEAK_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "set_time", _set_time_service, SET_TIME_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, 
        "get_security_summary", 
        _get_security_summary, 
        SECURITY_SUMMARY_SCHEMA,
        supports_response=SupportsResponse.ONLY
    )

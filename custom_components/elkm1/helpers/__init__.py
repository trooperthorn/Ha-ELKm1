"""Helpers for Elk-M1 integration."""

from __future__ import annotations

from .panel_settings import (
    check_panel_version,
    check_required_settings,
    enable_required_settings,
    verify_panel_configuration,
)
from .troublestatus import (
    get_critical_troubles,
    get_trouble_status_string,
    has_troubles,
    parse_trouble_status,
)
from .usb_discovery import discover_elk_ports, probe_serial_port

__all__ = [
    "check_panel_version",
    "check_required_settings",
    "discover_elk_ports",
    "enable_required_settings",
    "get_critical_troubles",
    "get_trouble_status_string",
    "has_troubles",
    "parse_trouble_status",
    "probe_serial_port",
    "verify_panel_configuration",
]

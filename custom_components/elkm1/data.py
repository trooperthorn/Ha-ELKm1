"""Data models for Elk-M1 integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from homeassistant.config_entries import ConfigEntry

from .coordinator import ElkDataUpdateCoordinator


class ElkConfigEntry(ConfigEntry):
    """Typed ConfigEntry for Elk integration."""

    runtime_data: ElkRuntimeData


@dataclass
class ElkRuntimeData:
    """Runtime data for Elk integration."""

    coordinator: ElkDataUpdateCoordinator
    serial_port: str


class ElkPanelStatus(TypedDict):
    """Panel status data."""

    armed: bool
    armed_mode: str
    last_user: int
    last_user_name: str
    zones_faulted: list[int]
    outputs_active: list[int]

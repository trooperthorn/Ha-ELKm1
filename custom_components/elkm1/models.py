"""Models for Elk-M1 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .coordinator import ElkDataUpdateCoordinator


@dataclass
class ElkRuntimeData:
    """Data class for Elk-M1 runtime data storage in Home Assistant config entries."""

    prefix: str
    mac: str | None
    auto_configure: bool
    config: dict[str, Any]
    coordinator: ElkDataUpdateCoordinator
    connection: Any | None = None


# Alias to prevent import crashes during migration
ELKM1Data = ElkRuntimeData

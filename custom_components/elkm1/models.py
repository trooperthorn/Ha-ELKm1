"""Models for Elk-M1 integration."""

from __future__ import annotations

from dataclasses import dataclass

from .coordinator import ElkDataUpdateCoordinator
from .helpers import ElkSerialQueue


@dataclass
class ELKM1Data:
    """Data class for Elk-M1 runtime data storage in Home Assistant config entries."""

    coordinator: ElkDataUpdateCoordinator
    serial_queue: ElkSerialQueue | None = None

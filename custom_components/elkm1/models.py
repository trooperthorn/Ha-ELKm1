"""Models for Elk-M1 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elkm1_lib.elk import Elk

from .coordinator import ElkDataUpdateCoordinator
from .helpers import ElkSerialQueue


@dataclass
class ELKM1Data:
    """Data class for Elk-M1 runtime data storage in Home Assistant config entries."""

    elk: Elk
    prefix: str
    mac: str | None
    auto_configure: bool
    config: dict[str, Any]
    keypads: dict[int, Any]
    coordinator: ElkDataUpdateCoordinator | None = None
    serial_queue: ElkSerialQueue | None = None

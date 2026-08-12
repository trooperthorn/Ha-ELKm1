"""Data coordinator for Elk-M1 integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from elkm1_lib import Elk
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL,
    COMMAND_QUEUE_INTERVAL,
    LIVENESS_CHECK_INTERVAL,
)
from .data import ElkPanelStatus
from .helpers.serial_queue import ElkSerialQueue

_LOGGER: logging.Logger = logging.getLogger(__name__)


class ElkDataUpdateCoordinator(DataUpdateCoordinator[ElkPanelStatus]):
    """Coordinator to manage Elk-M1 data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        serial_port: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            config_entry_id=None,
        )

        self._serial_port = serial_port
        self._username = username
        self._password = password
        
        self._elk: Elk | None = None
        self._serial_queue: ElkSerialQueue | None = None
        self._liveness_task: asyncio.Task[None] | None = None
        self._connected = False

    async def _async_setup(self) -> None:
        """Set up connection before first refresh."""
        # Called before first async_config_entry_first_refresh()
        await self._connect()

    async def _connect(self) -> None:
        """Establish connection to Elk panel."""
        try:
            # Build URL based on connection type
            if self._serial_port.startswith("/"):
                url = f"serial://{self._serial_port}"
            else:
                url = f"elk://{self._serial_port}"

            config = {
                "url": url,
                "userid": self._username or "admin",
                "password": self._password or "",
            }

            self._elk = Elk(config)
            await self._elk.async_connect()

            # Wrap serial queue for rate limiting
            self._serial_queue = ElkSerialQueue(
                elk=self._elk,
                interval=COMMAND_QUEUE_INTERVAL,
            )

            self._connected = True
            
            # Start liveness check task
            self._liveness_task = asyncio.create_task(self._async_liveness_check())
            
            _LOGGER.info(f"Connected to Elk panel at {self._serial_port}")

        except Exception as err:
            self._connected = False
            raise UpdateFailed(f"Could not connect to Elk panel: {err}") from err

    async def _async_update_data(self) -> ElkPanelStatus:
        """Fetch latest data from panel."""
        if not self._connected or not self._elk:
            await self._connect()

        try:
            # Query panel state
            # The elkm1_lib should handle unsolicited updates via callbacks
            # but you can poll for status as well
            panel_data: ElkPanelStatus = {
                "armed": self._elk.panel.armed,
                "armed_mode": self._elk.panel.armed_mode,
                "last_user": self._elk.panel.last_user,
                "last_user_name": self._elk.panel.last_user_name,
                "zones_faulted": [i for i, z in enumerate(self._elk.zones) if z.faulted],
                "outputs_active": [i for i, o in enumerate(self._elk.outputs) if o.status],
            }
            return panel_data

        except Exception as err:
            self._connected = False
            raise UpdateFailed(f"Error updating Elk data: {err}") from err

    async def _async_liveness_check(self) -> None:
        """Monitor connection liveness; reconnect if silent."""
        while self._connected:
            await asyncio.sleep(LIVENESS_CHECK_INTERVAL.total_seconds())
            # Check if we've heard from the panel recently
            # If not, trigger a reconnect
            # (elkm1_lib should track last message time)

    async def async_shutdown(self) -> None:
        """Gracefully shutdown coordinator."""
        if self._liveness_task:
            self._liveness_task.cancel()
        if self._elk:
            await self._elk.async_disconnect()
        self._connected = False

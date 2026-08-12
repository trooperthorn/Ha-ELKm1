"""Data coordinator for Elk-M1 integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from elkm1_lib import Elk
from homeassistant.core import HomeAssistant, callback
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

        # PART 4: Track previous zone states to fire events on changes
        self._previous_zone_states: dict[int, bool] = {}
        self._previous_output_states: dict[int, bool] = {}
        self._previous_armed_state: bool | None = None
        self._previous_armed_mode: str | None = None

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
            panel_data: ElkPanelStatus = {
                "armed": self._elk.panel.armed,
                "armed_mode": self._elk.panel.armed_mode,
                "last_user": self._elk.panel.last_user,
                "last_user_name": self._elk.panel.last_user_name,
                "zones_faulted": [i for i, z in enumerate(self._elk.zones) if z.faulted],
                "outputs_active": [i for i, o in enumerate(self._elk.outputs) if o.status],
            }

            # PART 4: Fire events for zone state changes
            await self._async_check_zone_changes()
            
            # PART 4: Fire events for output state changes
            await self._async_check_output_changes()
            
            # PART 4: Fire events for armed state changes
            await self._async_check_armed_changes(panel_data)

            return panel_data

        except Exception as err:
            self._connected = False
            raise UpdateFailed(f"Error updating Elk data: {err}") from err

    # ============================================================================
    # PART 4: Event Firing Methods - Fire Zone Events for Automations
    # ============================================================================

    @callback
    async def _async_check_zone_changes(self) -> None:
        """Check for zone state changes and fire events."""
        if not self._elk:
            return

        for zone_index, zone in enumerate(self._elk.zones):
            if not zone:
                continue

            zone_number = zone_index + 1
            is_open = zone.faulted or zone.open
            
            # Get previous state
            prev_state = self._previous_zone_states.get(zone_index)
            
            # Fire event if state changed
            if prev_state != is_open:
                event_type = "open" if is_open else "closed"
                
                self.hass.bus.async_fire(
                    f"{DOMAIN}_zone_{event_type}",
                    {
                        "zone_number": zone_number,
                        "zone_name": zone.name,
                        "zone_index": zone_index,
                        "zone_type": zone.zone_type,
                        "is_open": is_open,
                        "timestamp": self.hass.loop.time(),
                    },
                )
                
                _LOGGER.debug(
                    f"Zone {zone_number} ({zone.name}) {event_type}: {is_open}"
                )
                
                self._previous_zone_states[zone_index] = is_open

    @callback
    async def _async_check_output_changes(self) -> None:
        """Check for output state changes and fire events."""
        if not self._elk:
            return

        for output_index, output in enumerate(self._elk.outputs):
            if not output:
                continue

            output_number = output_index + 1
            is_active = output.status
            
            # Get previous state
            prev_state = self._previous_output_states.get(output_index)
            
            # Fire event if state changed
            if prev_state != is_active:
                event_type = "activated" if is_active else "deactivated"
                
                self.hass.bus.async_fire(
                    f"{DOMAIN}_output_{event_type}",
                    {
                        "output_number": output_number,
                        "output_name": output.name,
                        "output_index": output_index,
                        "is_active": is_active,
                        "timestamp": self.hass.loop.time(),
                    },
                )
                
                _LOGGER.debug(
                    f"Output {output_number} ({output.name}) {event_type}: {is_active}"
                )
                
                self._previous_output_states[output_index] = is_active

    @callback
    async def _async_check_armed_changes(self, panel_data: ElkPanelStatus) -> None:
        """Check for armed/disarmed state changes and fire events."""
        is_armed = panel_data.get("armed", False)
        armed_mode = panel_data.get("armed_mode", "disarmed")
        
        # Fire event if armed state changed
        if self._previous_armed_state != is_armed:
            event_type = "armed" if is_armed else "disarmed"
            
            self.hass.bus.async_fire(
                f"{DOMAIN}_panel_{event_type}",
                {
                    "armed": is_armed,
                    "armed_mode": armed_mode,
                    "last_user": panel_data.get("last_user"),
                    "last_user_name": panel_data.get("last_user_name"),
                    "timestamp": self.hass.loop.time(),
                },
            )
            
            _LOGGER.info(f"Panel {event_type}: mode={armed_mode}")
            self._previous_armed_state = is_armed

        # Fire event if armed mode changed
        if self._previous_armed_mode != armed_mode and is_armed:
            self.hass.bus.async_fire(
                f"{DOMAIN}_panel_mode_changed",
                {
                    "armed_mode": armed_mode,
                    "last_user": panel_data.get("last_user"),
                    "last_user_name": panel_data.get("last_user_name"),
                    "timestamp": self.hass.loop.time(),
                },
            )
            
            _LOGGER.info(f"Panel armed mode changed to: {armed_mode}")
            self._previous_armed_mode = armed_mode

    # ============================================================================
    # End of Part 4 Event Firing
    # ============================================================================

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

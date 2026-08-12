"""Switch platform for Elk-M1 outputs/relays."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..coordinator import ElkDataUpdateCoordinator
from ..data import ElkRuntimeData
from ..entity import ElkEntity

_LOGGER: logging.Logger = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch platform from a config entry."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities: list[ElkOutputSwitch] = []

    # Create a switch for each output (up to 208 on ELK-M1)
    if coordinator._elk:
        for output_index in range(len(coordinator._elk.outputs)):
            output = coordinator._elk.outputs[output_index]
            if output and output.name:  # Only add if output has a name
                entities.append(
                    ElkOutputSwitch(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        output_index=output_index,
                        output=output,
                    )
                )

    async_add_entities(entities)


class ElkOutputSwitch(ElkEntity, SwitchEntity):
    """Switch for ELK output/relay."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        output_index: int,
        output: Any,
    ) -> None:
        """Initialize output switch."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            entity_key=f"output_{output_index}",
        )
        self._output_index = output_index
        self._output = output
        
        self._attr_name = output.name
        
        # Determine device class based on output name
        if any(keyword in output.name.lower() for keyword in ("siren", "strobe", "light")):
            self._attr_device_class = SwitchDeviceClass.OUTLET

    @property
    def is_on(self) -> bool:
        """Return true if output is active."""
        return self._output.status if self._output else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on output."""
        try:
            await self.coordinator._serial_queue.async_send_command(
                "output_on",
                output=self._output_index,
            )
            await self.coordinator.async_request_refresh()
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error turning on output {self._output_index}: {err}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off output."""
        try:
            await self.coordinator._serial_queue.async_send_command(
                "output_off",
                output=self._output_index,
            )
            await self.coordinator.async_request_refresh()
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error turning on output {self._output_index}: {err}")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        if self.coordinator._elk:
            self._output = self.coordinator._elk.outputs[self._output_index]
        self.async_write_ha_state()

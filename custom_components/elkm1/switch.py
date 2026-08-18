"""Switch platform for Elk-M1 outputs/relays and proxy switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData
from .entity import ElkEntity

_LOGGER: logging.Logger = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch platform from a config entry."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    # Type as a generic list of SwitchEntity so it accepts both output switches and our proxy switch
    entities: list[SwitchEntity] = []

    # 1. Add the native proxy switch for the Atmospheric Pre-Arm Check blueprint
    entities.append(ElkArmRequestSwitch(coordinator, config_entry))

    # 2. Create a switch for each physical Elk-M1 output safely
    if coordinator._elk:
        # Iterate directly since elkm1_lib collections don't support len()
        for output in coordinator._elk.outputs:
            name = getattr(output, "name", "")
            # Only add the switch if it has a custom name in ElkRP
            if name and not name.startswith("Output "):
                entities.append(
                    ElkOutputSwitch(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        output_index=getattr(output, "index", 0),
                        output=output,
                    )
                )

    async_add_entities(entities)


class ElkArmRequestSwitch(ElkEntity, SwitchEntity):
    """Native proxy switch for triggering pre-arm validation automations."""

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the arm request proxy switch."""
        # Passes "arm_system_request" as the unique_id suffix to the base ElkEntity
        super().__init__(coordinator, config_entry, "arm_system_request")
        
        self._attr_name = "Arm System Request"
        self._attr_icon = "mdi:shield-sync"
        self._attr_is_on = False
        self._attr_has_entity_name = True
        

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        return self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (Triggers the HA Pre-Arm Blueprint)."""
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (Reset by the Blueprint or manually)."""
        self._attr_is_on = False
        self.async_write_ha_state()


class ElkOutputSwitch(ElkEntity, SwitchEntity):
    """Switch for ELK output/relay."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # This disables all outputs by default:
    _attr_entity_registry_enabled_default = False

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
        """Return true if output is on."""
        if not self._output:
            return False
        # elkm1_lib typically uses output_on for the boolean state
        return getattr(self._output, "output_on", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the output."""
        try:
            if self._output:
                # '0' tells the Elk-M1 to turn the output on indefinitely
                self._output.turn_on(0)
                
                # Tell HA to update the UI immediately
                self.async_write_ha_state()
        except Exception as err: # noqa: BLE001
            _LOGGER.error(f"Error turning on output: {err}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the output."""
        try:
            if self._output:
                self._output.turn_off()
                
                # Tell HA to update the UI immediately
                self.async_write_ha_state()
        except Exception as err: # noqa: BLE001
            _LOGGER.error(f"Error turning off output: {err}")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        if self.coordinator._elk:
            self._output = self.coordinator._elk.outputs[self._output_index]
        self.async_write_ha_state()

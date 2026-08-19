"""Support for control of ElkM1 outputs (relays) and proxy switches."""

from __future__ import annotations

import logging
from datetime import timedelta
from math import ceil
from typing import Any, override

import voluptuous as vol

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import VolDictType

from .const import ATTR_DURATION, DOMAIN
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData
from .entity import ElkEntity, create_elk_system_device_info

_LOGGER = logging.getLogger(__name__)

SERVICE_SWITCH_OUTPUT_TURN_ON_FOR = "switch_output_turn_on_for"

ELK_OUTPUT_TURN_ON_FOR_SERVICE_SCHEMA: VolDictType = {
    vol.Required(ATTR_DURATION): vol.All(
        cv.time_period,
        vol.Range(min=timedelta(seconds=1), max=timedelta(seconds=65535)),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the Elk-M1 switch platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities: list[SwitchEntity] = []

    # 1. Native Proxy Switch for Atmospheric Pre-Arm Blueprint
    entities.append(ElkArmRequestSwitch(coordinator, config_entry))

    # 2. Native Physical Outputs
    outputs = coordinator.data.get("outputs", []) if coordinator.data else []
    for i, output in enumerate(outputs):
        if output:
            entities.append(ElkOutput(coordinator, config_entry, i))

    # 3. Thermostat Emergency Heat Switches
    thermostats = coordinator.data.get("thermostats", []) if coordinator.data else []
    for i, tstat in enumerate(thermostats):
        if tstat:
            entities.append(ElkThermostatEMHeat(coordinator, config_entry, i))

    async_add_entities(entities)

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SWITCH_OUTPUT_TURN_ON_FOR,
        entity_domain=SWITCH_DOMAIN,
        schema=ELK_OUTPUT_TURN_ON_FOR_SERVICE_SCHEMA,
        func="async_switch_output_turn_on_for",
    )


class ElkArmRequestSwitch(ElkEntity, SwitchEntity):
    """Native proxy switch for triggering pre-arm validation automations."""

    _attr_icon = "mdi:shield-sync"
    _attr_should_poll = False

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the arm request proxy switch."""
        super().__init__(coordinator, config_entry, "arm_request")
        self._prefix = config_entry.data.get("prefix", "")
        self._mac = config_entry.unique_id
        
        self._attr_name = "Arm System Request"
        self._attr_unique_id = f"elkm1_{self._prefix}_arm_request".lower()
        self._attr_is_on = False

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Device info connecting via the ElkM1 system."""
        # Note: requires the Elk instance or similar device reference upstream
        return create_elk_system_device_info(self.coordinator._elk, self._prefix, self._mac)

    @property
    @override
    def is_on(self) -> bool:
        """Return the state of the switch."""
        return self._attr_is_on

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (Triggers the HA Pre-Arm Blueprint)."""
        self._attr_is_on = True
        self.async_write_ha_state()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (Reset by the Blueprint or manually)."""
        self._attr_is_on = False
        self.async_write_ha_state()


class ElkOutput(ElkEntity, SwitchEntity):
    """Elk output as switch."""

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry, index: int) -> None:
        """Initialize the Elk physical output."""
        super().__init__(coordinator, config_entry, f"output_{index+1}")
        self._index = index
        self._attr_unique_id = f"{config_entry.entry_id}_output_{index+1}"
        
        output_obj = self._get_obj()
        self._attr_name = getattr(output_obj, "name", f"Output {index+1}") if output_obj else f"Output {index+1}"

    def _get_obj(self) -> Any:
        if self.coordinator.data and "outputs" in self.coordinator.data:
            outputs = self.coordinator.data["outputs"]
            if self._index < len(outputs):
                return outputs[self._index]
        return None

    @property
    @override
    def is_on(self) -> bool:
        """Get the current output status."""
        if not self.coordinator.data:
            return False
        # Check if this index exists in the active outputs array cached by the coordinator
        return self._index in self.coordinator.data.get("outputs_active", [])

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the output indefinitely (Timer = 00000)."""
        # Elk ASCII 'cn' command: cn + Output(3) + Timer(5)
        await self.coordinator.send_raw_elk_command(f"cn{self._index + 1:03d}00000")

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the output."""
        # Elk ASCII 'cf' command: cf + Output(3)
        await self.coordinator.send_raw_elk_command(f"cf{self._index + 1:03d}")

    async def async_switch_output_turn_on_for(self, duration: timedelta) -> None:
        """Turn on an output for specified length of time."""
        seconds = ceil(duration.total_seconds())
        await self.coordinator.send_raw_elk_command(f"cn{self._index + 1:03d}{seconds:05d}")


class ElkThermostatEMHeat(ElkEntity, SwitchEntity):
    """Elk Thermostat emergency heat as switch."""

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry, index: int) -> None:
        """Initialize the emergency heat switch."""
        super().__init__(coordinator, config_entry, f"thermostat_{index+1}_emheat")
        self._index = index
        self._attr_unique_id = f"{config_entry.entry_id}_thermostat_{index+1}_emheat"
        
        tstat_obj = self._get_obj()
        base_name = getattr(tstat_obj, "name", f"Thermostat {index+1}") if tstat_obj else f"Thermostat {index+1}"
        self._attr_name = f"{base_name} Emergency Heat"

    def _get_obj(self) -> Any:
        if self.coordinator.data and "thermostats" in self.coordinator.data:
            thermostats = self.coordinator.data["thermostats"]
            if self._index < len(thermostats):
                return thermostats[self._index]
        return None

    @property
    @override
    def is_on(self) -> bool:
        """Get the current emergency heat status."""
        obj = self._get_obj()
        if not obj:
            return False
        # Assuming Elk mode 4 is EM HEAT
        mode = getattr(obj, "mode", 0)
        return mode == 4

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on Emergency Heat."""
        # Elk ASCII 'ts' command: ts + Tstat(2) + ValueType(1) + Value(2)
        # ValueType 0 = Mode. Value 04 = EmHeat
        await self.coordinator.send_raw_elk_command(f"ts{self._index + 1:02d}004")

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off Emergency Heat by reverting to Auto."""
        # ValueType 0 = Mode. Value 03 = Auto
        await self.coordinator.send_raw_elk_command(f"ts{self._index + 1:02d}003")

    async def async_switch_output_turn_on_for(self, duration: timedelta) -> None:
        """Not supported for thermostat."""
        raise HomeAssistantError("supported only on ElkM1 output switch entities")

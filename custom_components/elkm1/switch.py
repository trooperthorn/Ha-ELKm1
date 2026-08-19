"""Support for control of ElkM1 outputs (relays) and proxy switches."""

from __future__ import annotations

from datetime import timedelta
import logging
from math import ceil
from typing import Any, override

import voluptuous as vol
from elkm1_lib.const import ThermostatMode, ThermostatSetting

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN, SwitchEntity
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
from .entity import ElkEntity, create_elk_system_device_info
from .models import ElkRuntimeData

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
    # elkm1_lib always allocates Max.OUTPUTS.value (208) Output objects
    # regardless of how many the panel actually has - only create switches
    # for ones that received real sync data, not the library's ceiling.
    outputs = coordinator.data.outputs if coordinator.data else []
    for output in outputs:
        if output.configured:
            entities.append(ElkOutput(coordinator, config_entry, output.index))

    # 3. Thermostat Emergency Heat Switches
    thermostats = coordinator.data.thermostats if coordinator.data else []
    for tstat in thermostats:
        if tstat.configured:
            entities.append(ElkThermostatEMHeat(coordinator, config_entry, tstat.index))

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
        return create_elk_system_device_info(
            self._config_entry, sw_version=self.coordinator.data.panel_version
        )

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
        if self.coordinator.data and self._index < len(self.coordinator.data.outputs):
            return self.coordinator.data.outputs[self._index]
        return None

    @property
    @override
    def is_on(self) -> bool:
        """Get the current output status."""
        obj = self._get_obj()
        return bool(obj and obj.output_on)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the output indefinitely."""
        if obj := self._get_obj():
            obj.turn_on(0)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the output."""
        if obj := self._get_obj():
            obj.turn_off()

    async def async_switch_output_turn_on_for(self, duration: timedelta) -> None:
        """Turn on an output for specified length of time."""
        if obj := self._get_obj():
            obj.turn_on(ceil(duration.total_seconds()))


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
        if self.coordinator.data and self._index < len(self.coordinator.data.thermostats):
            return self.coordinator.data.thermostats[self._index]
        return None

    @property
    @override
    def is_on(self) -> bool:
        """Get the current emergency heat status."""
        obj = self._get_obj()
        if not obj:
            return False
        mode = self._get_enum_value(getattr(obj, "mode", 0))
        return mode == ThermostatMode.EMERGENCY_HEAT.value

    def _get_enum_value(self, obj: Any, default: int = 0) -> int:
        if hasattr(obj, "value"):
            return int(obj.value)
        return int(obj) if isinstance(obj, (int, float)) else default

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on Emergency Heat."""
        if obj := self._get_obj():
            obj.set(ThermostatSetting.MODE, ThermostatMode.EMERGENCY_HEAT)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off Emergency Heat by reverting to Auto."""
        if obj := self._get_obj():
            obj.set(ThermostatSetting.MODE, ThermostatMode.AUTO)

    async def async_switch_output_turn_on_for(self, duration: timedelta) -> None:
        """Not supported for thermostat."""
        raise HomeAssistantError("supported only on ElkM1 output switch entities")

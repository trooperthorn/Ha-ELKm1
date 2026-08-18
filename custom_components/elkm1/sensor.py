"""Support for control of ElkM1 sensors."""

from __future__ import annotations

from typing import Any, cast, override

import voluptuous as vol

from elkm1_lib.const import SettingFormat, ZoneType
from elkm1_lib.counters import Counter
from elkm1_lib.elements import Element
from elkm1_lib.elk import Elk
from elkm1_lib.keypads import Keypad
from elkm1_lib.panel import Panel
from elkm1_lib.settings import Setting
from elkm1_lib.util import pretty_const
from elkm1_lib.zones import Zone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import VolDictType

from . import ElkM1ConfigEntry
from .const import ATTR_VALUE, ELK_USER_CODE_SERVICE_SCHEMA
from .entity import (
    ElkAttachedEntity,
    ElkEntity,
    create_elk_entities,
    create_elk_system_device_info,
    generate_unique_id,
)
from .models import ELKM1Data
from .util import deprecate_entity

SERVICE_SENSOR_COUNTER_REFRESH = "sensor_counter_refresh"
SERVICE_SENSOR_COUNTER_SET = "sensor_counter_set"
SERVICE_SENSOR_ZONE_BYPASS = "sensor_zone_bypass"
SERVICE_SENSOR_ZONE_TRIGGER = "sensor_zone_trigger"

UNDEFINED_TEMPERATURE = -40

_DEVICE_CLASS_MAP: dict[ZoneType, SensorDeviceClass] = {
    ZoneType.TEMPERATURE: SensorDeviceClass.TEMPERATURE,
    ZoneType.ANALOG_ZONE: SensorDeviceClass.VOLTAGE,
}

_STATE_CLASS_MAP: dict[ZoneType, SensorStateClass] = {
    ZoneType.TEMPERATURE: SensorStateClass.MEASUREMENT,
    ZoneType.ANALOG_ZONE: SensorStateClass.MEASUREMENT,
}

ELK_SET_COUNTER_SERVICE_SCHEMA: VolDictType = {
    vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(0, 65535))
}


def get_trouble_status_string(status: str) -> str:
    """Parse Elk panel trouble status into a readable string based on the Elk ASCII protocol."""
    if not status or not isinstance(status, str):
        return "Normal"

    troubles = []
    # ElkM1 SS Command (System Trouble Status) bit map
    if len(status) >= 1 and status[0] != "0": troubles.append("AC Fail")
    if len(status) >= 2 and status[1] != "0": troubles.append("Box Tamper")
    if len(status) >= 3 and status[2] != "0": troubles.append("Fail To Communicate")
    if len(status) >= 4 and status[3] != "0": troubles.append("EEPROM Error")
    if len(status) >= 5 and status[4] != "0": troubles.append("Low Battery")
    if len(status) >= 6 and status[5] != "0": troubles.append("Transmitter Low Battery")
    if len(status) >= 7 and status[6] != "0": troubles.append("Over Current")
    if len(status) >= 8 and status[7] != "0": troubles.append("Telephone Fault")

    if not troubles and any(char != "0" and char != " " for char in status):
        return f"Unknown Trouble ({status})"

    return ", ".join(troubles) if troubles else "Normal"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ElkM1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the Elk-M1 sensor platform."""
    elk_data = config_entry.runtime_data
    elk = elk_data.elk
    entities: list[ElkEntity | SensorEntity] = []
    elk_settings: list[Setting] = []

    create_elk_entities(elk_data, elk.counters, "counter", ElkCounter, entities)
    create_elk_entities(elk_data, elk.keypads, "keypad", ElkKeypad, entities)
    create_elk_entities(elk_data, [elk.panel], "panel", ElkPanel, entities)
    create_elk_entities(elk_data, elk.zones, "zone", ElkZone, entities)

    # Add the custom active zones summary sensor
    entities.append(ElkActiveZonesSensor(elk, elk_data))

    entity_registry = er.async_get(hass)
    for setting in elk.settings:
        setting = cast(Setting, setting)
        domain = (
            "time" if setting.value_format is SettingFormat.TIME_OF_DAY else "number"
        )
        orig_unique_id = generate_unique_id(elk_data.prefix, setting)
        new_unique_id = orig_unique_id
        new_entity_id = f"{domain}.elkm1_{setting.name.replace(' ', '_')}".lower()

        if deprecate_entity(
            hass,
            entity_registry,
            "sensor",
            orig_unique_id,
            f"deprecated_sensor_{orig_unique_id}",
            "deprecated_sensor",
            new_unique_id,
            new_entity_id,
        ):
            elk_settings.append(setting)

    create_elk_entities(elk_data, elk_settings, "setting", ElkSetting, entities)
    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SENSOR_COUNTER_REFRESH,
        None,
        "async_counter_refresh",
    )
    platform.async_register_entity_service(
        SERVICE_SENSOR_COUNTER_SET,
        ELK_SET_COUNTER_SERVICE_SCHEMA,
        "async_counter_set",
    )
    platform.async_register_entity_service(
        SERVICE_SENSOR_ZONE_BYPASS,
        ELK_USER_CODE_SERVICE_SCHEMA,
        "async_zone_bypass",
    )
    platform.async_register_entity_service(
        SERVICE_SENSOR_ZONE_TRIGGER,
        None,
        "async_zone_trigger",
    )


def temperature_to_state(temperature: int, undefined_temperature: int) -> str | None:
    """Convert temperature to a state."""
    return f"{temperature}" if temperature > undefined_temperature else None


class ElkSensor(ElkAttachedEntity, SensorEntity):
    """Base representation of Elk-M1 sensor."""

    _attr_native_value: str | None = None

    async def async_counter_refresh(self) -> None:
        """Refresh the value of a counter from the panel."""
        if not isinstance(self, ElkCounter):
            raise HomeAssistantError("supported only on ElkM1 Counter sensors")
        self._element.get()

    async def async_counter_set(self, value: int | None = None) -> None:
        """Set the value of a counter on the panel."""
        if not isinstance(self, ElkCounter):
            raise HomeAssistantError("supported only on ElkM1 Counter sensors")
        if value is not None:
            self._element.set(value)

    async def async_zone_bypass(self, code: int | None = None) -> None:
        """Bypass zone."""
        if not isinstance(self, ElkZone):
            raise HomeAssistantError("supported only on ElkM1 Zone sensors")
        if code is not None:
            self._element.bypass(code)

    async def async_zone_trigger(self) -> None:
        """Trigger zone."""
        if not isinstance(self, ElkZone):
            raise HomeAssistantError("supported only on ElkM1 Zone sensors")
        self._element.trigger()


class ElkActiveZonesSensor(SensorEntity):
    """Sensor that provides a live count and readable list of open zones."""

    _attr_name = "Active Zones"
    _attr_icon = "mdi:shield-alert-outline"
    _attr_native_unit_of_measurement = "Zones"
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, elk: Elk, elk_data: ELKM1Data) -> None:
        """Initialize the active zones sensor."""
        self._elk = elk
        self._prefix = elk_data.prefix
        self._mac = elk_data.mac
        self._unique_id = f"elkm1_{self._prefix}_active_zones".lower()
        self._open_zones: list[str] = []
        self._attr_native_value = 0

    @property
    def unique_id(self) -> str:
        """Return unique id of the element."""
        return self._unique_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes including a readable list of open zones."""
        return {
            "open_entities": ", ".join(self._open_zones) if self._open_zones else "None"
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Device info connecting via the ElkM1 system."""
        return create_elk_system_device_info(self._elk, self._prefix, self._mac)

    async def async_added_to_hass(self) -> None:
        """Register callbacks for all zones to receive instantaneous local-push updates."""
        for zone in self._elk.zones:
            zone.add_callback(self._update_state)
        self._update_state(None, {})

    @callback
    def _update_state(self, element: Any, changeset: dict[str, Any]) -> None:
        """Update the count and list of open zones directly from the hardware."""
        open_list = []
        for zone in self._elk.zones:
            if not zone:
                continue

            logical_val = zone.logical_status.value if hasattr(zone.logical_status, "value") else zone.logical_status
            physical_val = zone.physical_status.value if hasattr(zone.physical_status, "value") else zone.physical_status

            # Definition 2 is Violated/Open for Logical, 1/3 for Physical
            if logical_val == 2 or physical_val in (1, 3):
                name = getattr(zone, "name", f"Zone {zone.index + 1}")
                open_list.append(name)

        self._open_zones = open_list
        self._attr_native_value = len(open_list)
        self.async_write_ha_state()


class ElkCounter(ElkSensor):
    """Representation of an Elk-M1 Counter."""

    _attr_icon = "mdi:numeric"
    _element: Counter

    @override
    def _element_changed(self, element: Element, changeset: dict[str, Any]) -> None:
        self._attr_native_value = str(self._element.value)


class ElkKeypad(ElkSensor):
    """Representation of an Elk-M1 Keypad."""

    _attr_icon = "mdi:thermometer-lines"
    _element: Keypad

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit."""
        return self._temperature_unit

    @property
    @override
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self._temperature_unit

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributes of the sensor."""
        attrs: dict[str, Any] = self.initial_attrs()
        attrs["area"] = self._element.area + 1
        attrs["temperature"] = self._attr_native_value
        attrs["last_user_time"] = self._element.last_user_time.isoformat()
        attrs["last_user"] = self._element.last_user + 1
        attrs["code"] = self._element.code
        attrs["last_user_name"] = self._elk.users.username(self._element.last_user)
        attrs["last_keypress"] = self._element.last_keypress
        return attrs

    @override
    def _element_changed(self, element: Element, changeset: dict[str, Any]) -> None:
        self._attr_native_value = temperature_to_state(
            self._element.temperature, UNDEFINED_TEMPERATURE
        )


class ElkPanel(ElkSensor):
    """Representation of an Elk-M1 Panel."""

    _attr_translation_key = "panel"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _element: Panel

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributes of the sensor."""
        attrs = self.initial_attrs()
        raw_status = str(self._element.system_trouble_status)
        attrs["system_trouble_status_raw"] = raw_status
        attrs["system_trouble_status_parsed"] = get_trouble_status_string(raw_status)
        return attrs

    @override
    def _element_changed(self, element: Element, changeset: dict[str, Any]) -> None:
        if self._elk.is_connected():
            self._attr_native_value = "Paused" if self._elk.is_paused() else "Connected"
        else:
            self._attr_native_value = "Disconnected"


class ElkSetting(ElkSensor):
    """Representation of an Elk-M1 Setting."""

    _attr_translation_key = "setting"
    _element: Setting

    @override
    def _element_changed(self, element: Element, changeset: dict[str, Any]) -> None:
        self._attr_native_value = (
            None if self._element.value is None else str(self._element.value)
        )

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributes of the sensor."""
        attrs: dict[str, Any] = self.initial_attrs()
        attrs["value_format"] = SettingFormat(self._element.value_format).name.lower()
        return attrs


class ElkZone(ElkSensor):
    """Representation of an Elk-M1 Zone."""

    _element: Zone

    @property
    @override
    def icon(self) -> str:
        """Icon to use in the frontend."""
        zone_icons = {
            ZoneType.FIRE_ALARM: "fire",
            ZoneType.FIRE_VERIFIED: "fire",
            ZoneType.FIRE_SUPERVISORY: "fire",
            ZoneType.KEYFOB: "key",
            ZoneType.NON_ALARM: "alarm-off",
            ZoneType.MEDICAL_ALARM: "medical-bag",
            ZoneType.POLICE_ALARM: "alarm-light",
            ZoneType.POLICE_NO_INDICATION: "alarm-light",
            ZoneType.KEY_MOMENTARY_ARM_DISARM: "power",
            ZoneType.KEY_MOMENTARY_ARM_AWAY: "power",
            ZoneType.KEY_MOMENTARY_ARM_STAY: "power",
            ZoneType.KEY_MOMENTARY_DISARM: "power",
            ZoneType.KEY_ON_OFF: "toggle-switch",
            ZoneType.MUTE_AUDIBLES: "volume-mute",
            ZoneType.POWER_SUPERVISORY: "power-plug",
            ZoneType.TEMPERATURE: "thermometer-lines",
            ZoneType.ANALOG_ZONE: "speedometer",
            ZoneType.PHONE_KEY: "phone-classic",
            ZoneType.INTERCOM_KEY: "deskphone",
        }
        return f"mdi:{zone_icons.get(self._element.definition, 'alarm-bell')}"

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributes of the sensor."""
        attrs: dict[str, Any] = self.initial_attrs()
        attrs["physical_status"] = self._element.physical_status.name.lower()
        attrs["logical_status"] = self._element.logical_status.name.lower()
        attrs["definition"] = self._element.definition.name.lower()
        attrs["area"] = self._element.area + 1
        attrs["triggered_alarm"] = self._element.triggered_alarm
        return attrs

    @property
    def temperature_unit(self) -> str | None:
        """Return the temperature unit."""
        if self._element.definition is ZoneType.TEMPERATURE:
            return self._temperature_unit
        return None

    @property
    @override
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class of the sensor."""
        return _DEVICE_CLASS_MAP.get(self._element.definition)

    @property
    @override
    def state_class(self) -> SensorStateClass | None:
        """Return the state class of the sensor."""
        return _STATE_CLASS_MAP.get(self._element.definition)

    @property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        if self._element.definition is ZoneType.TEMPERATURE:
            return self._temperature_unit
        if self._element.definition is ZoneType.ANALOG_ZONE:
            return UnitOfElectricPotential.VOLT
        return None

    @override
    def _element_changed(self, element: Element, changeset: dict[str, Any]) -> None:
        if self._element.definition is ZoneType.TEMPERATURE:
            self._attr_native_value = temperature_to_state(
                self._element.temperature, UNDEFINED_TEMPERATURE
            )
        elif self._element.definition is ZoneType.ANALOG_ZONE:
            self._attr_native_value = f"{self._element.voltage}"
        else:
            self._attr_native_value = pretty_const(self._element.logical_status.name)

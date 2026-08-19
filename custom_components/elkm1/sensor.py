"""Support for control of ElkM1 sensors."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import VolDictType

from .const import ATTR_VALUE, ELK_USER_CODE_SERVICE_SCHEMA
from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData
from .entity import ElkEntity
from .util import deprecate_entity

_LOGGER = logging.getLogger(__name__)

SERVICE_SENSOR_COUNTER_REFRESH = "sensor_counter_refresh"
SERVICE_SENSOR_COUNTER_SET = "sensor_counter_set"
SERVICE_SENSOR_ZONE_BYPASS = "sensor_zone_bypass"
SERVICE_SENSOR_ZONE_TRIGGER = "sensor_zone_trigger"

UNDEFINED_TEMPERATURE = -40

# Map raw Elk integer definitions to Device and State Classes
# 33: Temperature, 34: Analog Zone
_DEVICE_CLASS_MAP: dict[int, SensorDeviceClass] = {
    33: SensorDeviceClass.TEMPERATURE,
    34: SensorDeviceClass.VOLTAGE,
}

_STATE_CLASS_MAP: dict[int, SensorStateClass] = {
    33: SensorStateClass.MEASUREMENT,
    34: SensorStateClass.MEASUREMENT,
}

ELK_SET_COUNTER_SERVICE_SCHEMA: VolDictType = {
    vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(0, 65535))
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the Elk-M1 sensor platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities = []

    # 1. Setup Panel Sensor
    entities.append(ElkPanel(coordinator, config_entry))

    # 2. Setup Active Zones Sensor (Summary)
    entities.append(ElkActiveZonesSensor(coordinator, config_entry))

    # 3. Setup Counters
    counters = coordinator.data.get("counters", []) if coordinator.data else []
    for i, _ in enumerate(counters):
        entities.append(ElkCounter(coordinator, config_entry, i))

    # 4. Setup Keypads
    keypads = coordinator.data.get("keypads", []) if coordinator.data else []
    for i, _ in enumerate(keypads):
        entities.append(ElkKeypad(coordinator, config_entry, i))

    # 5. Setup Zones (Only 33=Temperature and 34=Analog)
    zones = coordinator.data.get("zones", []) if coordinator.data else []
    for i, zone in enumerate(zones):
        if not zone:
            continue
            
        def_val = 0
        if hasattr(zone, "definition"):
            def_obj = zone.definition
            def_val = int(def_obj.value) if hasattr(def_obj, "value") else int(def_obj)

        if def_val in (33, 34):
            entities.append(ElkZone(coordinator, config_entry, i))

    # 6. Setup Settings (with deprecation checks mapping to Number/Time domains)
    settings = coordinator.data.get("settings", []) if coordinator.data else []
    entity_registry = er.async_get(hass)
    
    for i, setting in enumerate(settings):
        # 0 = Number, 1 = Time of Day, 2 = Timer
        fmt_val = 0
        if hasattr(setting, "value_format"):
            fmt_obj = setting.value_format
            fmt_val = int(fmt_obj.value) if hasattr(fmt_obj, "value") else int(fmt_obj)
            
        domain = "time" if fmt_val == 1 else "number"
        setting_name = getattr(setting, "name", f"Setting {i+1}")
        
        orig_unique_id = f"{config_entry.entry_id}_setting_{i+1}"
        new_entity_id = f"{domain}.elkm1_{setting_name.replace(' ', '_')}".lower()

        # Handle entity deprecation migration
        if deprecate_entity(
            hass,
            entity_registry,
            "sensor",
            orig_unique_id,
            f"deprecated_sensor_{orig_unique_id}",
            "deprecated_sensor",
            orig_unique_id,
            new_entity_id,
        ):
            entities.append(ElkSetting(coordinator, config_entry, i))

    async_add_entities(entities)

    # Register entity services
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SENSOR_COUNTER_REFRESH, None, "async_counter_refresh"
    )
    platform.async_register_entity_service(
        SERVICE_SENSOR_COUNTER_SET, ELK_SET_COUNTER_SERVICE_SCHEMA, "async_counter_set"
    )
    platform.async_register_entity_service(
        SERVICE_SENSOR_ZONE_BYPASS, ELK_USER_CODE_SERVICE_SCHEMA, "async_zone_bypass"
    )
    platform.async_register_entity_service(
        SERVICE_SENSOR_ZONE_TRIGGER, None, "async_zone_trigger"
    )


class ElkSensor(ElkEntity, SensorEntity):
    """Base representation of Elk-M1 sensor."""

    def _get_enum_value(self, obj: Any, default: int = 0) -> int:
        """Safely extract integer value from enum or string objects."""
        if hasattr(obj, "value"):
            return int(obj.value)
        if isinstance(obj, str):
            return int(obj) if obj.isdigit() else default
        return int(obj) if isinstance(obj, (int, float)) else default


class ElkActiveZonesSensor(ElkSensor):
    """Sensor that provides a live count and readable list of open zones."""

    _attr_icon = "mdi:shield-alert-outline"
    _attr_native_unit_of_measurement = "Zones"

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the active zones sensor."""
        super().__init__(coordinator, config_entry, "active_zones_summary")
        self._attr_name = "Active Zones"
        self._attr_unique_id = f"{config_entry.entry_id}_active_zones_summary"

    @property
    def native_value(self) -> int:
        """Return the live count of faulted zones from the coordinator."""
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.get("zones_faulted_count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes including a readable list of open zones."""
        if not self.coordinator.data:
            return {"open_entities": "None"}
            
        open_zones = self.coordinator.data.get("faulted_zone_names", [])
        return {"open_entities": ", ".join(open_zones) if open_zones else "None"}


class ElkPanel(ElkSensor):
    """Representation of an Elk-M1 Panel."""

    _attr_translation_key = "panel"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the panel sensor."""
        super().__init__(coordinator, config_entry, "panel_status")
        self._attr_name = "Panel Status"
        self._attr_unique_id = f"{config_entry.entry_id}_panel_status"

    @property
    def native_value(self) -> str:
        """Return the connection state."""
        return "Connected" if self.coordinator.connected else "Disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributes of the sensor."""
        if not self.coordinator.data:
            return {}
            
        panel = self.coordinator.data.get("panel")
        raw_status = str(getattr(panel, "system_trouble_status", "")) if panel else ""
        
        return {
            "system_trouble_status_raw": raw_status,
            "system_trouble_status_parsed": self._parse_troubles(raw_status),
        }

    def _parse_troubles(self, status: str) -> str:
        """Parse Elk panel trouble status into a readable string."""
        if not status or not isinstance(status, str):
            return "Normal"

        troubles = []
        if len(status) >= 1 and status[0] != "0": troubles.append("AC Fail")
        if len(status) >= 2 and status[1] != "0": troubles.append("Box Tamper")
        if len(status) >= 3 and status[2] != "0": troubles.append("Fail To Communicate")
        if len(status) >= 4 and status[3] != "0": troubles.append("EEPROM Error")
        if len(status) >= 5 and status[4] != "0": troubles.append("Low Battery")
        if len(status) >= 6 and status[5] != "0": troubles.append("Transmitter Low Battery")
        if len(status) >= 7 and status[6] != "0": troubles.append("Over Current")
        if len(status) >= 8 and status[7] != "0": troubles.append("Telephone Fault")

        return ", ".join(troubles) if troubles else "Normal"


class ElkCounter(ElkSensor):
    """Representation of an Elk-M1 Counter."""

    _attr_icon = "mdi:numeric"

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator, config_entry, f"counter_{index+1}")
        self._index = index
        self._attr_unique_id = f"{config_entry.entry_id}_counter_{index+1}"
        
        counter_obj = self._get_obj()
        self._attr_name = getattr(counter_obj, "name", f"Counter {index+1}") if counter_obj else f"Counter {index+1}"

    def _get_obj(self) -> Any:
        if self.coordinator.data and "counters" in self.coordinator.data:
            counters = self.coordinator.data["counters"]
            if self._index < len(counters):
                return counters[self._index]
        return None

    @property
    def native_value(self) -> str | None:
        obj = self._get_obj()
        return str(getattr(obj, "value", "")) if obj else None

    async def async_counter_refresh(self) -> None:
        """Read current counter value via raw ASCII command cv."""
        await self.coordinator.send_raw_elk_command(f"cv{self._index + 1:02d}00")

    async def async_counter_set(self, value: int | None = None) -> None:
        """Write counter value via raw ASCII command cx."""
        if value is not None:
            await self.coordinator.send_raw_elk_command(f"cx{self._index + 1:02d}{value:05d}")


class ElkKeypad(ElkSensor):
    """Representation of an Elk-M1 Keypad."""

    _attr_icon = "mdi:thermometer-lines"

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator, config_entry, f"keypad_{index+1}")
        self._index = index
        self._attr_unique_id = f"{config_entry.entry_id}_keypad_{index+1}"
        self._temperature_unit = "°F"  # Ideally dynamically pulled from config
        
        kp_obj = self._get_obj()
        self._attr_name = getattr(kp_obj, "name", f"Keypad {index+1}") if kp_obj else f"Keypad {index+1}"

    def _get_obj(self) -> Any:
        if self.coordinator.data and "keypads" in self.coordinator.data:
            keypads = self.coordinator.data["keypads"]
            if self._index < len(keypads):
                return keypads[self._index]
        return None

    @property
    def native_unit_of_measurement(self) -> str:
        return self._temperature_unit

    @property
    def native_value(self) -> str | None:
        obj = self._get_obj()
        if not obj:
            return None
        temp = getattr(obj, "temperature", UNDEFINED_TEMPERATURE)
        return str(temp) if temp > UNDEFINED_TEMPERATURE else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        obj = self._get_obj()
        if not obj:
            return {}
        
        last_user_time = getattr(obj, "last_user_time", None)
        return {
            "area": getattr(obj, "area", 0) + 1,
            "last_user": getattr(obj, "last_user", 0) + 1,
            "last_user_time": last_user_time.isoformat() if last_user_time else None,
            "code": getattr(obj, "code", ""),
            "last_keypress": getattr(obj, "last_keypress", ""),
        }


class ElkSetting(ElkSensor):
    """Representation of an Elk-M1 Setting."""

    _attr_translation_key = "setting"

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator, config_entry, f"setting_{index+1}")
        self._index = index
        self._attr_unique_id = f"{config_entry.entry_id}_setting_{index+1}"
        
        obj = self._get_obj()
        self._attr_name = getattr(obj, "name", f"Setting {index+1}") if obj else f"Setting {index+1}"

    def _get_obj(self) -> Any:
        if self.coordinator.data and "settings" in self.coordinator.data:
            settings = self.coordinator.data["settings"]
            if self._index < len(settings):
                return settings[self._index]
        return None

    @property
    def native_value(self) -> str | None:
        obj = self._get_obj()
        val = getattr(obj, "value", None) if obj else None
        return str(val) if val is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        obj = self._get_obj()
        if not obj:
            return {}
        return {
            "value_format": self._get_enum_value(getattr(obj, "value_format", 0))
        }


class ElkZone(ElkSensor):
    """Representation of an Elk-M1 Zone (Analog or Temperature)."""

    def __init__(self, coordinator: ElkDataUpdateCoordinator, config_entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator, config_entry, f"sensor_zone_{index+1}")
        self._index = index
        self._attr_unique_id = f"{config_entry.entry_id}_sensor_zone_{index+1}"
        self._temperature_unit = "°F"
        
        obj = self._get_obj()
        self._attr_name = getattr(obj, "name", f"Zone {index+1}") if obj else f"Zone {index+1}"

    def _get_obj(self) -> Any:
        if self.coordinator.data and "zones" in self.coordinator.data:
            zones = self.coordinator.data["zones"]
            if self._index < len(zones):
                return zones[self._index]
        return None

    @property
    def icon(self) -> str:
        obj = self._get_obj()
        def_val = self._get_enum_value(getattr(obj, "definition", 0)) if obj else 0
        return "mdi:thermometer-lines" if def_val == 33 else "mdi:speedometer"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        obj = self._get_obj()
        def_val = self._get_enum_value(getattr(obj, "definition", 0)) if obj else 0
        return _DEVICE_CLASS_MAP.get(def_val)

    @property
    def state_class(self) -> SensorStateClass | None:
        obj = self._get_obj()
        def_val = self._get_enum_value(getattr(obj, "definition", 0)) if obj else 0
        return _STATE_CLASS_MAP.get(def_val)

    @property
    def native_unit_of_measurement(self) -> str | None:
        obj = self._get_obj()
        def_val = self._get_enum_value(getattr(obj, "definition", 0)) if obj else 0
        if def_val == 33:
            return self._temperature_unit
        if def_val == 34:
            return UnitOfElectricPotential.VOLT
        return None

    @property
    def native_value(self) -> str | None:
        obj = self._get_obj()
        if not obj:
            return None
            
        def_val = self._get_enum_value(getattr(obj, "definition", 0))
        if def_val == 33:
            temp = getattr(obj, "temperature", UNDEFINED_TEMPERATURE)
            return str(temp) if temp > UNDEFINED_TEMPERATURE else None
        elif def_val == 34:
            return str(getattr(obj, "voltage", 0.0))
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        obj = self._get_obj()
        if not obj:
            return {}
        return {
            "physical_status": self._get_enum_value(getattr(obj, "physical_status", 0)),
            "logical_status": self._get_enum_value(getattr(obj, "logical_status", 0)),
            "definition": self._get_enum_value(getattr(obj, "definition", 0)),
            "bypassed": getattr(obj, "bypassed", False),
        }

    async def async_zone_bypass(self, code: str | None = None) -> None:
        """Bypass zone via the coordinator."""
        await self.coordinator.bypass_zone(self._index + 1, code)

    async def async_zone_trigger(self) -> None:
        """Trigger zone via the coordinator."""
        await self.coordinator.send_raw_elk_command(f"zt{self._index + 1:03d}")

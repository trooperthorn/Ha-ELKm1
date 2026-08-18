"""Alarm control panel platform for Elk-M1."""

from __future__ import annotations

import logging
from typing import Any

from elkm1_lib.const import ArmLevel

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelState,
)

# Safe imports for optional alarm panel features/formats across HA versions
try:
    from homeassistant.components.alarm_control_panel import (
        AlarmControlPanelEntityFeature,
    )
except ImportError:
    AlarmControlPanelEntityFeature = None

try:
    from homeassistant.components.alarm_control_panel import CodeFormat
except ImportError:
    CodeFormat = None

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

# Map modern enum states
STATE_ALARM_TRIGGERED = AlarmControlPanelState.TRIGGERED
STATE_ARMED_AWAY = AlarmControlPanelState.ARMED_AWAY
STATE_ARMED_HOME = AlarmControlPanelState.ARMED_HOME
STATE_ARMED_NIGHT = AlarmControlPanelState.ARMED_NIGHT
STATE_DISARMED = AlarmControlPanelState.DISARMED

from .coordinator import ElkDataUpdateCoordinator
from .data import ElkRuntimeData
from .entity import ElkEntity

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up alarm control panel platform for all configured areas."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    entities = []
    if coordinator._elk and getattr(coordinator._elk, "areas", None):
        for index, area in enumerate(coordinator._elk.areas):
            if area:
                entities.append(
                    ElkAlarmControlPanel(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        area_index=index,
                    )
                )

    # Fallback if no areas detected via elk instance
    if not entities:
        entities.append(
            ElkAlarmControlPanel(
                coordinator=coordinator,
                config_entry=config_entry,
                area_index=0,
            )
        )

    async_add_entities(entities)


class ElkAlarmControlPanel(ElkEntity, AlarmControlPanelEntity):
    """Elk-M1 alarm control panel partition."""

    _attr_supported_features = (
        (AlarmControlPanelEntityFeature.ARM_AWAY if AlarmControlPanelEntityFeature else 0)
        | (AlarmControlPanelEntityFeature.ARM_HOME if AlarmControlPanelEntityFeature else 0)
        | (AlarmControlPanelEntityFeature.ARM_NIGHT if AlarmControlPanelEntityFeature else 0)
        | (AlarmControlPanelEntityFeature.ARM_VACATION if AlarmControlPanelEntityFeature else 0)
        | (AlarmControlPanelEntityFeature.ARM_CUSTOM_BYPASS if AlarmControlPanelEntityFeature else 0)
        | (AlarmControlPanelEntityFeature.TRIGGER if AlarmControlPanelEntityFeature else 0)
    )
    _attr_code_format = CodeFormat.NUMBER if CodeFormat else None
    _attr_code_arm_required = True

    def __init__(
        self,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        area_index: int = 0,
    ) -> None:
        """Initialize alarm panel partition."""
        area_num = area_index + 1
        super().__init__(coordinator, config_entry, f"alarm_panel_area_{area_num}")
        self._area_index = area_index
        self._attr_name = f"Area {area_num}"
        self._attr_unique_id = f"{config_entry.entry_id}_area_{area_num}"

    @property
    def area(self) -> Any:
        """Helper to get the specific area object from elkm1_lib."""
        if self.coordinator._elk and getattr(self.coordinator._elk, "areas", None):
            if self._area_index < len(self.coordinator._elk.areas):
                return self.coordinator._elk.areas[self._area_index]
        return None

    def _get_enum_value(self, obj: Any, default: int = 0) -> int:
        """Safely extract the raw integer value from elkm1_lib Enum objects."""
        if hasattr(obj, "value"):
            return int(obj.value)
        if isinstance(obj, str):
            return int(obj) if obj.isdigit() else default
        return int(obj) if isinstance(obj, (int, float)) else default

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return state strictly mapped to HA AlarmControlPanelState."""
        area = self.area
        if not self.coordinator.data or not area:
            return None

        alarm_state_val = self._get_enum_value(getattr(area, "alarm_state", 0))
        armed_status_val = self._get_enum_value(getattr(area, "armed_status", 0))
        arm_up_state_val = self._get_enum_value(getattr(area, "arm_up_state", 0))

        # 1. TRIGGERED: Elk AlarmState >= 2
        if alarm_state_val >= 2:
            return STATE_ALARM_TRIGGERED

        # 2. PENDING (Entry Delay): Elk AlarmState == 1 OR Timer1 running while armed
        if alarm_state_val == 1 or (getattr(area, "timer1", 0) > 0 and armed_status_val != 0):
            return AlarmControlPanelState.PENDING

        # 3. ARMING (Exit Delay): Timer2 running or exit state indicated
        if getattr(area, "timer2", 0) > 0 or arm_up_state_val in (3, 5):
            return AlarmControlPanelState.ARMING

        # 4. ARMED_CUSTOM_BYPASS: Armed with Bypass active
        if arm_up_state_val == 6 and armed_status_val != 0:
            return AlarmControlPanelState.ARMED_CUSTOM_BYPASS

        # 5. Stable Arming Modes
        if armed_status_val == 1:
            return STATE_ARMED_AWAY
        elif armed_status_val in (2, 3):
            return STATE_ARMED_HOME
        elif armed_status_val in (4, 5):
            return STATE_ARMED_NIGHT
        elif armed_status_val == 6:
            return AlarmControlPanelState.ARMED_VACATION

        return STATE_DISARMED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with detailed panel information."""
        if not self.coordinator.data or not self.coordinator._elk:
            return {}

        panel = self.coordinator._elk.panel
        area = self.area
        data = self.coordinator.data

        faulted_indices, faulted_names = self._get_live_faulted_zones()
        alarm_state_val = self._get_enum_value(getattr(area, "alarm_state", 0)) if area else 0

        def safe_bool(val: Any) -> bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return val != 0
            if isinstance(val, str):
                return val.lower() not in ("0", "false", "no", "off", "")
            return bool(val)

        return {
            "armed": safe_bool(data.get("armed", False)),
            "armed_mode": data.get("armed_mode", "disarmed"),
            "entry_delay_active": safe_bool(getattr(area, "entry_delay_active", False)) if area else False,
            "exit_delay_active": safe_bool(getattr(area, "exit_delay_active", False)) if area else False,
            "entry_delay_seconds": getattr(area, "entry_delay", 0) if area else 0,
            "exit_delay_seconds": getattr(area, "exit_delay", 0) if area else 0,
            "last_user": data.get("last_user"),
            "last_user_name": data.get("last_user_name", "Unknown"),
            "last_keypad": getattr(panel, "last_keypad", None),
            "zones_faulted": faulted_indices,
            "zones_faulted_count": len(faulted_indices),
            "faulted_zone_names": faulted_names,
            "outputs_active": data.get("outputs_active", []),
            "outputs_active_count": len(data.get("outputs_active", [])),
            "active_output_names": self._get_active_output_names(),
            "trouble_status": safe_bool(getattr(panel, "trouble_status", False)),
            "ac_power": safe_bool(getattr(panel, "ac_power", True)),
            "battery_status": getattr(panel, "battery_status", "Good"),
            "panel_temperature": self._get_primary_temperature(),
            "connection_status": "Connected" if self.coordinator.last_update_success else "Disconnected",
            "last_update": self.coordinator.last_update_success,
            "alarm_triggered": alarm_state_val >= 2,
            "fire_alarm": self._get_fire_alarm_status(),
            "panic_alarm": safe_bool(getattr(area, "panic_state", False)) if area else False,
            "alarm_memory": self._get_alarm_memory_status(),
            "bypassed_zones": self._get_bypassed_zones(),
            "bypassed_zones_count": len(self._get_bypassed_zones()),
        }

    def _get_primary_temperature(self) -> int | float | None:
        """Safely retrieve temperature from keypads."""
        if self.coordinator._elk and hasattr(self.coordinator._elk, "keypads"):
            for keypad in self.coordinator._elk.keypads:
                if keypad and getattr(keypad, "temperature", None) is not None:
                    return keypad.temperature
        return None

    def _is_zone_open(self, zone: Any) -> bool:
        """Helper to check if zone is open."""
        if not zone:
            return False
        logical_val = self._get_enum_value(getattr(zone, "logical_status", 0))
        physical_val = self._get_enum_value(getattr(zone, "physical_status", 0))
        return logical_val == 2 or physical_val in (1, 3)

    def _get_live_faulted_zones(self) -> tuple[list[int], list[str]]:
        """Dynamically scan hardware zones to find open/faulted ones."""
        if not self.coordinator._elk or not hasattr(self.coordinator._elk, "zones"):
            return [], []

        faulted_indices = []
        faulted_names = []
        for i, zone in enumerate(self.coordinator._elk.zones):
            if self._is_zone_open(zone):
                faulted_indices.append(i)
                zone_name = getattr(zone, "name", f"Zone {i + 1}")
                faulted_names.append(f"Zone {i + 1}: {zone_name}")
        return faulted_indices, faulted_names

    def _get_active_output_names(self) -> list[str]:
        """Get names of active outputs."""
        if not self.coordinator.data or not self.coordinator._elk:
            return []
        active_indices = self.coordinator.data.get("outputs_active", [])
        names = []
        for output_index in active_indices:
            if output_index < len(self.coordinator._elk.outputs):
                output = self.coordinator._elk.outputs[output_index]
                if output and output.name:
                    names.append(f"Output {output_index + 1}: {output.name}")
        return names

    def _get_bypassed_zones(self) -> list[str]:
        """Get list of bypassed zones."""
        if not self.coordinator._elk:
            return []
        bypassed = []
        for i, zone in enumerate(self.coordinator._elk.zones):
            if zone and getattr(zone, "bypassed", False):
                bypassed.append(f"Zone {i + 1}: {zone.name}")
        return bypassed

    def _get_fire_alarm_status(self) -> bool:
        """Get fire alarm status."""
        if not self.coordinator._elk:
            return False
        for zone in self.coordinator._elk.zones:
            if not zone:
                continue
            definition = self._get_enum_value(getattr(zone, "definition", 0))
            logical_status = self._get_enum_value(getattr(zone, "logical_status", 0))
            if definition in (9, 10) and logical_status == 2:
                return True
        return False

    def _get_alarm_memory_status(self) -> bool:
        """Check if any area has an active alarm memory state."""
        if not self.coordinator._elk:
            return False
        for area in self.coordinator._elk.areas:
            if area and getattr(area, "alarm_memory", False):
                return True
        return False

    def _get_code_val(self, code: str | None) -> int:
        """Safely convert HA string PIN to Elk required integer."""
        if not code:
            return 0
        try:
            return int(code)
        except ValueError:
            _LOGGER.warning("Invalid PIN code format. Expected numeric digits.")
            return 0

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command to the area."""
        try:
            if self.area:
                self.area.disarm(self._get_code_val(code))
                _LOGGER.info(f"Area {self._area_index + 1} disarmed")
        except Exception as err:
            _LOGGER.error(f"Error disarming area {self._area_index + 1}: {err}")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm stay command to the area."""
        try:
            if self.area:
                self.area.arm(ArmLevel.ARMED_STAY, self._get_code_val(code))
                _LOGGER.info(f"Area {self._area_index + 1} armed home (stay)")
        except Exception as err:
            _LOGGER.error(f"Error arming home area {self._area_index + 1}: {err}")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command to the area."""
        try:
            if self.area:
                self.area.arm(ArmLevel.ARMED_AWAY, self._get_code_val(code))
                _LOGGER.info(f"Area {self._area_index + 1} armed away")
        except Exception as err:
            _LOGGER.error(f"Error arming away area {self._area_index + 1}: {err}")

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send arm night command to the area."""
        try:
            if self.area:
                self.area.arm(ArmLevel.ARMED_NIGHT, self._get_code_val(code))
                _LOGGER.info(f"Area {self._area_index + 1} armed night")
        except Exception as err:
            _LOGGER.error(f"Error arming night area {self._area_index + 1}: {err}")

    async def async_alarm_arm_vacation(self, code: str | None = None) -> None:
        """Send arm vacation command to the area."""
        try:
            if self.area:
                self.area.arm(ArmLevel.ARMED_VACATION, self._get_code_val(code))
                _LOGGER.info(f"Area {self._area_index + 1} armed vacation")
        except Exception as err:
            _LOGGER.error(f"Error arming vacation area {self._area_index + 1}: {err}")

    async def async_alarm_arm_custom_bypass(self, code: str | None = None) -> None:
        """Handle custom bypass request."""
        try:
            if self.area:
                self.area.arm(ArmLevel.ARMED_AWAY, self._get_code_val(code))
                _LOGGER.info(f"Area {self._area_index + 1} armed custom bypass mode")
        except Exception as err:
            _LOGGER.error(f"Error arming custom bypass area {self._area_index + 1}: {err}")

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Trigger the alarm on the area."""
        try:
            if self.area and hasattr(self.area, "trigger"):
                self.area.trigger(self._get_code_val(code))
                _LOGGER.warning(f"Area {self._area_index + 1} alarm manually triggered via HA")
        except Exception as err:
            _LOGGER.error(f"Error triggering alarm area {self._area_index + 1}: {err}")

"""Alarm control panel platform for Elk-M1."""
from __future__ import annotations

import logging
from typing import Any

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

# Map modern enum states to your existing variable names
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
    """Set up alarm control panel platform."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    
    async_add_entities([
        ElkAlarmControlPanel(
            hass=hass,
            coordinator=runtime_data.coordinator,
            config_entry=config_entry,
        )
    ])


class ElkAlarmControlPanel(ElkEntity, AlarmControlPanelEntity):
    """Elk-M1 alarm control panel."""

    _attr_name = "Alarm Panel"
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
        | AlarmControlPanelEntityFeature.ARM_VACATION
        | AlarmControlPanelEntityFeature.ARM_CUSTOM_BYPASS
        | AlarmControlPanelEntityFeature.TRIGGER
    )
    _attr_code_format = CodeFormat.NUMBER
    
    # FORCE FRONTEND PIN PROMPT: Set to True so native HA cards require a PIN
    _attr_code_arm_required = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ElkDataUpdateCoordinator,
        config_entry: ConfigEntry,
        area_index: int = 0,  # Default to Area 1 if single partition
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry, "alarm_panel")
        self._hass = hass
        self._coordinator = coordinator
        self._area_index = area_index

    @property
    def area(self):
        """Helper to get the specific area object from elkm1_lib."""
        if self.coordinator._elk and self.coordinator._elk.areas:
            return self.coordinator._elk.areas[self._area_index]
        return None

    @property
    def state(self) -> str | None:
        """Return state with robust boolean conversion."""
        if not self.coordinator.data:
            return None

        # Safely evaluate alarm state from panel or area, guarding against string '0'
        alarm_state_raw = getattr(self.area, "alarm_state", 0) if self.area else 0
        is_triggered = bool(alarm_state_raw) and alarm_state_raw not in ("0", 0, "False", "false")

        if is_triggered:
            return STATE_ALARM_TRIGGERED

        if self.coordinator.data.get("armed", False):
            armed_mode = self.coordinator.data.get("armed_mode", "").lower()
            
            if "stay" in armed_mode or "home" in armed_mode:
                return STATE_ARMED_HOME
            elif "night" in armed_mode:
                return STATE_ARMED_NIGHT
            else:
                return STATE_ARMED_AWAY
        
        return STATE_DISARMED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with detailed panel information."""
        if not self.coordinator.data or not self.coordinator._elk:
            return {}

        panel = self.coordinator._elk.panel
        area = self.area
        data = self.coordinator.data

        # Get live faulted zones directly from hardware
        faulted_indices, faulted_names = self._get_live_faulted_zones()

        # Safe boolean helper for status flags
        def safe_bool(val) -> bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return val != 0
            if isinstance(val, str):
                return val.lower() not in ("0", "false", "no", "off", "")
            return bool(val)

        attributes: dict[str, Any] = {
            # Armed/Mode information
            "armed": safe_bool(data.get("armed", False)),
            "armed_mode": data.get("armed_mode", "disarmed"),
            "entry_delay_active": safe_bool(getattr(area, "entry_delay_active", False)) if area else False,
            "exit_delay_active": safe_bool(getattr(area, "exit_delay_active", False)) if area else False,
            "entry_delay_seconds": getattr(area, "entry_delay", 0) if area else 0,
            "exit_delay_seconds": getattr(area, "exit_delay", 0) if area else 0,
            
            # User/Access information
            "last_user": data.get("last_user"),
            "last_user_name": data.get("last_user_name", "Unknown"),
            "last_keypad": getattr(panel, "last_keypad", None),
            
            # Zone/Faulted information (Live Hardware Scan)
            "zones_faulted": faulted_indices,
            "zones_faulted_count": len(faulted_indices),
            "faulted_zone_names": faulted_names,
            
            # Output/Relay information
            "outputs_active": data.get("outputs_active", []),
            "outputs_active_count": len(data.get("outputs_active", [])),
            "active_output_names": self._get_active_output_names(),
            
            # System health/status
            "trouble_status": safe_bool(getattr(panel, "trouble_status", False)),
            "ac_power": safe_bool(getattr(panel, "ac_power", True)),
            "battery_status": getattr(panel, "battery_status", "Good"),
            "panel_temperature": self._get_primary_temperature(),
            
            # Connection information
            "connection_status": "Connected" if self.coordinator.last_update_success else "Disconnected",
            "last_update": self.coordinator.last_update_success,
            
            # Alarm state information (Safe evaluation)
            "alarm_triggered": str(getattr(area, "alarm_state", 0) if area else 0),
            "fire_alarm": self._get_fire_alarm_status(),
            "panic_alarm": safe_bool(getattr(area, "panic_state", False)) if area else False,
            "alarm_memory": self._get_alarm_memory_status(),
            
            # Zone bypass information
            "bypassed_zones": self._get_bypassed_zones(),
            "bypassed_zones_count": len(self._get_bypassed_zones()),
        }

        return attributes

    def _get_primary_temperature(self) -> int | float | None:
        """Helper to safely retrieve temperature from keypads since panel lacks temp."""
        if self.coordinator._elk and hasattr(self.coordinator._elk, "keypads"):
            for keypad in self.coordinator._elk.keypads:
                if keypad and getattr(keypad, "temperature", None) is not None:
                    return keypad.temperature
        return None

    def _is_zone_open(self, zone) -> bool:
        """Helper to match exact physical/logical logic."""
        if not zone:
            return False
        logical_val = getattr(getattr(zone, "logical_status", None), "value", getattr(zone, "logical_status", 0))
        physical_val = getattr(getattr(zone, "physical_status", None), "value", getattr(zone, "physical_status", 0))
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

    def _get_faulted_zone_names(self) -> list[str]:
        """Get names of faulted zones."""
        if not self.coordinator.data or not self.coordinator._elk:
            return []

        faulted_indices = self.coordinator.data.get("zones_faulted", [])
        names = []
        
        for zone_index in faulted_indices:
            zone = self.coordinator._elk.zones[zone_index]
            if zone and zone.name:
                names.append(f"Zone {zone_index + 1}: {zone.name}")
        
        return names

    def _get_active_output_names(self) -> list[str]:
        """Get names of active outputs."""
        if not self.coordinator.data or not self.coordinator._elk:
            return []

        active_indices = self.coordinator.data.get("outputs_active", [])
        names = []
        
        for output_index in active_indices:
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
            if (
                zone
                and getattr(zone, "definition", 0) in (9, 10)
                and getattr(zone, "logical_status", 0) == 2
            ):
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

    # ============================================================================
    # Alarm Control Panel Service Actions
    # ============================================================================

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command to the area."""
        try:
            if self.area:
                self.area.disarm(code)
                _LOGGER.info("Panel disarmed")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error disarming: {err}")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command to the area."""
        try:
            if self.area:
                self.area.arm_home(code)
                _LOGGER.info("Panel armed home")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming home: {err}")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command to the area."""
        try:
            if self.area:
                self.area.arm_away(code)
                _LOGGER.info("Panel armed away")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming away: {err}")

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send arm night command to the area."""
        try:
            if self.area:
                self.area.arm_night(code)
                _LOGGER.info("Panel armed night")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming night: {err}")

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Trigger the alarm on the area."""
        try:
            if self.area:
                self.area.trigger(code)
                _LOGGER.info("Panel alarm triggered")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error triggering alarm: {err}")

    async def async_alarm_arm_vacation(self, code: str | None = None) -> None:
        """Arm vacation."""
        try:
            if self.area:
                self.area.arm_vacation(code)
                _LOGGER.info("Panel armed vacation")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming vacation: {err}")

    async def async_alarm_arm_custom_bypass(self, code: str | None = None) -> None:
        """Arm with custom bypass."""
        try:
            if self.area:
                self.area.arm_custom_bypass(code)
                _LOGGER.info("Panel armed custom bypass")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming custom bypass: {err}")

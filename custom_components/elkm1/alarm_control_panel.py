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
    from homeassistant.components.alarm_control_panel import AlarmControlPanelEntityFeature
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
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry, "alarm_panel")
        self._hass = hass
        self._coordinator = coordinator

    @property
    def state(self) -> str | None:
        """Return state."""
        if not self.coordinator.data:
            return None

        # Check if triggered/alarm active
        if getattr(self.coordinator._elk.panel, "alarm_state", False):
            return STATE_ALARM_TRIGGERED

        if self.coordinator.data.get("armed", False):
            armed_mode = self.coordinator.data.get("armed_mode", "").lower()
            
            if "stay" in armed_mode or "home" in armed_mode:
                return STATE_ARMED_HOME
            elif "night" in armed_mode:
                return STATE_ARMED_NIGHT
            else:  # away or default
                return STATE_ARMED_AWAY
        
        return STATE_DISARMED

    # ============================================================================
    # PART 5: Enhanced alarm_control_panel with Attributes
    # Add rich attributes to track alarm state details
    # ============================================================================

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with detailed panel information."""
        if not self.coordinator.data or not self.coordinator._elk:
            return {}

        panel = self.coordinator._elk.panel
        data = self.coordinator.data

        # Build comprehensive attributes dict
        attributes: dict[str, Any] = {
            # Armed/Mode information
            "armed": data.get("armed", False),
            "armed_mode": data.get("armed_mode", "disarmed"),
            "entry_delay_active": getattr(panel, "entry_delay_active", False),
            "exit_delay_active": getattr(panel, "exit_delay_active", False),
            "entry_delay_seconds": getattr(panel, "entry_delay", 0),
            "exit_delay_seconds": getattr(panel, "exit_delay", 0),
            
            # User/Access information
            "last_user": data.get("last_user"),
            "last_user_name": data.get("last_user_name", "Unknown"),
            "last_keypad": getattr(panel, "last_keypad", None),
            
            # Zone/Faulted information
            "zones_faulted": data.get("zones_faulted", []),
            "zones_faulted_count": len(data.get("zones_faulted", [])),
            
            # Get actual zone names for faulted zones
            "faulted_zone_names": self._get_faulted_zone_names(),
            
            # Output/Relay information
            "outputs_active": data.get("outputs_active", []),
            "outputs_active_count": len(data.get("outputs_active", [])),
            "active_output_names": self._get_active_output_names(),
            
            # System health/status
            "trouble_status": getattr(panel, "trouble_status", False),
            "ac_power": getattr(panel, "ac_power", True),
            "battery_status": getattr(panel, "battery_status", "Good"),
            "panel_temperature": getattr(panel, "temperature", None),
            
            # Connection information
            "connection_status": "Connected" if self.coordinator.last_update_success else "Disconnected",
            "last_update": self.coordinator.last_update_success,
            
            # Alarm state information
            "alarm_triggered": getattr(panel, "alarm_state", False),
            "fire_alarm": self._get_fire_alarm_status(),
            "panic_alarm": getattr(panel, "panic_state", False),
            "alarm_memory": self._get_alarm_memory_status(),
            
            # Zone bypass information
            "bypassed_zones": self._get_bypassed_zones(),
            "bypassed_zones_count": len(self._get_bypassed_zones()),
        }

        return attributes

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
                # Definition 9 is standard Fire Alarm, 10 is Fire w/ Verify
                and getattr(zone, "definition", 0) in (9, 10)
                # Logical state 2 is violated/faulted
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
    # End of Part 5 Attributes
    # ============================================================================

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarm."""
        try:
            # Pass the user's PIN code directly to the coordinator
            await self.coordinator.send_disarm(code)
            _LOGGER.info("Panel disarmed")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error disarming: {err}")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Arm home (stay mode)."""
        try:
            # Pass the user's PIN code directly to the coordinator
            await self.coordinator.send_arm_stay(code)
            _LOGGER.info("Panel armed (stay/home mode)")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming home: {err}")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arm away."""
        try:
            # Pass the user's PIN code directly to the coordinator
            await self.coordinator.send_arm_away(code)
            _LOGGER.info("Panel armed (away mode)")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming away: {err}")

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Arm night."""
        try:
            # Pass the user's PIN code directly to the coordinator
            await self.coordinator.send_arm_night(code)
            _LOGGER.info("Panel armed (night mode)")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error arming night: {err}")

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Trigger alarm (panic)."""
        try:
            # Pass the user's PIN code directly to the coordinator
            await self.coordinator.panic_alarm(code)
            _LOGGER.warning("Panic alarm triggered")
        except (OSError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.error(f"Error triggering panic: {err}")

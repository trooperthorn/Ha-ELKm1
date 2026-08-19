"""Alarm control panel platform for Elk-M1."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ElkDataUpdateCoordinator
from .data import ELKM1Data
from .entity import ElkEntity
from .models import ElkRuntimeData

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

# Map modern enum states
STATE_ALARM_TRIGGERED = AlarmControlPanelState.TRIGGERED
STATE_ARMED_AWAY = AlarmControlPanelState.ARMED_AWAY
STATE_ARMED_HOME = AlarmControlPanelState.ARMED_HOME
STATE_ARMED_NIGHT = AlarmControlPanelState.ARMED_NIGHT
STATE_DISARMED = AlarmControlPanelState.DISARMED

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up alarm control panel platform for all configured areas."""
    runtime_data: ElkRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator

    # The coordinator now dictates how many areas exist based on connection parsing
    num_areas = coordinator.data.get("num_areas", 1) if coordinator.data else 1
    
    entities = [
        ElkAlarmControlPanel(
            coordinator=coordinator,
            config_entry=config_entry,
            area_index=i,
        )
        for i in range(num_areas)
    ]

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
    def area_data(self) -> dict[str, Any]:
        """Helper to get the specific area data dictionary from the coordinator."""
        if self.coordinator.data and "areas" in self.coordinator.data:
            return self.coordinator.data["areas"].get(self._area_index, {})
        return {}

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return state strictly mapped to HA AlarmControlPanelState."""
        if not self.coordinator.data:
            return None

        data = self.area_data
        alarm_state_val = data.get("alarm_state", 0)
        armed_status_val = data.get("armed_status", 0)
        arm_up_state_val = data.get("arm_up_state", 0)

        # 1. TRIGGERED: Elk AlarmState >= 2
        if alarm_state_val >= 2:
            return STATE_ALARM_TRIGGERED

        # 2. PENDING (Entry Delay): Elk AlarmState == 1 OR Timer1 running while armed
        if alarm_state_val == 1 or (data.get("timer1", 0) > 0 and armed_status_val != 0):
            return AlarmControlPanelState.PENDING

        # 3. ARMING (Exit Delay): Timer2 running or exit state indicated
        if data.get("timer2", 0) > 0 or arm_up_state_val in (3, 5):
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
        if not self.coordinator.data:
            return {}

        global_data = self.coordinator.data
        area_data = self.area_data

        return {
            "armed": global_data.get("armed", False),
            "armed_mode": global_data.get("armed_mode", "disarmed"),
            "entry_delay_active": area_data.get("entry_delay_active", False),
            "exit_delay_active": area_data.get("exit_delay_active", False),
            "entry_delay_seconds": area_data.get("entry_delay", 0),
            "exit_delay_seconds": area_data.get("exit_delay", 0),
            "last_user": global_data.get("last_user"),
            "last_user_name": global_data.get("last_user_name", "Unknown"),
            "last_keypad": global_data.get("last_keypad"),
            "zones_faulted": global_data.get("zones_faulted", []),
            "zones_faulted_count": len(global_data.get("zones_faulted", [])),
            "faulted_zone_names": global_data.get("faulted_zone_names", []),
            "outputs_active": global_data.get("outputs_active", []),
            "outputs_active_count": len(global_data.get("outputs_active", [])),
            "active_output_names": global_data.get("active_output_names", []),
            "trouble_status": global_data.get("trouble_status", False),
            "ac_power": global_data.get("ac_power", True),
            "battery_status": global_data.get("battery_status", "Good"),
            "panel_temperature": global_data.get("panel_temperature"),
            "connection_status": "Connected" if self.coordinator.last_update_success else "Disconnected",
            "last_update": self.coordinator.last_update_success,
            "alarm_triggered": area_data.get("alarm_state", 0) >= 2,
            "fire_alarm": global_data.get("fire_alarm_active", False),
            "panic_alarm": area_data.get("panic_state", False),
            "alarm_memory": area_data.get("alarm_memory", False),
            "bypassed_zones": global_data.get("bypassed_zones", []),
            "bypassed_zones_count": len(global_data.get("bypassed_zones", [])),
        }

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
        """Send disarm command to the area via the coordinator."""
        try:
            await self.coordinator.async_alarm_disarm(self._area_index, self._get_code_val(code))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Error disarming area {self._area_index + 1}: {err}")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm stay command to the area via the coordinator."""
        try:
            await self.coordinator.async_alarm_arm_home(self._area_index, self._get_code_val(code))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Error arming home area {self._area_index + 1}: {err}")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command to the area via the coordinator."""
        try:
            await self.coordinator.async_alarm_arm_away(self._area_index, self._get_code_val(code))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Error arming away area {self._area_index + 1}: {err}")

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send arm night command to the area via the coordinator."""
        try:
            await self.coordinator.async_alarm_arm_night(self._area_index, self._get_code_val(code))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Error arming night area {self._area_index + 1}: {err}")

    async def async_alarm_arm_vacation(self, code: str | None = None) -> None:
        """Send arm vacation command to the area via the coordinator."""
        try:
            await self.coordinator.async_alarm_arm_vacation(self._area_index, self._get_code_val(code))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Error arming vacation area {self._area_index + 1}: {err}")

    async def async_alarm_arm_custom_bypass(self, code: str | None = None) -> None:
        """Handle custom bypass request via the coordinator."""
        try:
            await self.coordinator.async_alarm_arm_custom_bypass(self._area_index, self._get_code_val(code))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Error arming custom bypass area {self._area_index + 1}: {err}")

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Trigger the alarm on the area via the coordinator."""
        try:
            await self.coordinator.async_alarm_trigger(self._area_index, self._get_code_val(code))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Error triggering alarm area {self._area_index + 1}: {err}")

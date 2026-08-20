"""Tests for alarm_control_panel.py: state mapping and the action-exceptions
fix (a failed command used to be swallowed and only logged - HA's service
call/automation trace would show success even when the panel rejected or
never received the command).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.alarm_control_panel import AlarmControlPanelState
from homeassistant.exceptions import HomeAssistantError

from custom_components.elkm1.alarm_control_panel import ElkAlarmControlPanel
from custom_components.elkm1.models import AreaData, ElkPanelData


def _panel(area_data: AreaData) -> ElkAlarmControlPanel:
    panel = object.__new__(ElkAlarmControlPanel)
    panel._area_index = 0
    coordinator = MagicMock()
    coordinator.data = ElkPanelData(areas={0: area_data})
    panel.coordinator = coordinator
    return panel


@pytest.mark.parametrize(
    ("area_data", "expected_state"),
    [
        (AreaData(alarm_state=2), AlarmControlPanelState.TRIGGERED),
        (AreaData(alarm_state=1), AlarmControlPanelState.PENDING),
        (AreaData(timer2=5), AlarmControlPanelState.ARMING),
        (AreaData(armed_status=1), AlarmControlPanelState.ARMED_AWAY),
        (AreaData(armed_status=2), AlarmControlPanelState.ARMED_HOME),
        (AreaData(armed_status=4), AlarmControlPanelState.ARMED_NIGHT),
        (AreaData(armed_status=6), AlarmControlPanelState.ARMED_VACATION),
        (AreaData(), AlarmControlPanelState.DISARMED),
    ],
)
def test_alarm_state_mapping(area_data, expected_state):
    panel = _panel(area_data)
    assert panel.alarm_state == expected_state


async def test_failed_disarm_raises_homeassistant_error_not_silent_log():
    """A failed command must surface as a real failure, not a logged-and-ignored one."""
    panel = _panel(AreaData())
    panel.coordinator.async_alarm_disarm = AsyncMock(side_effect=RuntimeError("panel offline"))

    with pytest.raises(HomeAssistantError):
        await panel.async_alarm_disarm("1234")


async def test_successful_disarm_does_not_raise():
    panel = _panel(AreaData())
    panel.coordinator.async_alarm_disarm = AsyncMock(return_value=True)

    await panel.async_alarm_disarm("1234")

    panel.coordinator.async_alarm_disarm.assert_called_once_with(0, 1234)


async def test_bypass_and_clear_bypass_both_call_bypass_area():
    """The all-zone bypass command is a toggle - both services call the same coordinator method."""
    panel = _panel(AreaData())
    panel.coordinator.bypass_area = AsyncMock(return_value=True)

    await panel.async_alarm_bypass("1234")
    await panel.async_alarm_clear_bypass("1234")

    assert panel.coordinator.bypass_area.call_count == 2

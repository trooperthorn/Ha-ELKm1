"""Tests for binary_sensor.py: zone device_class mapping and the per-area
door/window aggregate sensor (the primary Better Thermostat integration
point - see docs/cross_integration.md).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from elkm1_lib.const import ZoneLogicalStatus, ZoneType
from elkm1_lib.zones import Zone

from custom_components.elkm1.binary_sensor import (
    _DEVICE_CLASS_MAP,
    _OPENING_DEFINITIONS,
    ElkAreaOpeningsBinarySensor,
)
from custom_components.elkm1.models import ElkPanelData


def _make_zone(index: int, definition: ZoneType, area: int = 0, name: str = "") -> Zone:
    """Build a real elkm1_lib.Zone with the given definition/area, marked configured."""
    conn = MagicMock()
    notifier = MagicMock()
    zone = Zone(index, conn, notifier)
    zone.setattr("definition", definition, False)
    zone.setattr("area", area, False)
    zone._configured = True
    zone.name = name or f"Zone {index + 1}"
    return zone


def test_device_class_map_entry_exit_is_door():
    """Entry/exit zone types (1, 2) map to DOOR, not the old MOTION mistake for value 2."""
    assert _DEVICE_CLASS_MAP[1] == "door"
    assert _DEVICE_CLASS_MAP[2] == "door"


def test_device_class_map_perimeter_instant_is_generic_opening():
    """Perimeter-instant (3) maps to the generic OPENING class, not WINDOW specifically -
    the protocol's zone-definition field encodes arming response, not physical sensor
    type, so claiming WINDOW would overclaim what's actually known.
    """
    assert _DEVICE_CLASS_MAP[3] == "opening"


def test_opening_definitions_cover_entry_exit_and_perimeter():
    assert {1, 2, 3} == _OPENING_DEFINITIONS


def _sensor_for_area(area_index: int, zones: list[Zone]) -> ElkAreaOpeningsBinarySensor:
    sensor = object.__new__(ElkAreaOpeningsBinarySensor)
    sensor._area_index = area_index
    coordinator = MagicMock()
    coordinator.data = ElkPanelData(num_areas=2, zones=zones)
    sensor.coordinator = coordinator
    return sensor


def test_area_openings_sensor_off_when_all_zones_closed():
    door = _make_zone(0, ZoneType.BURGLAR_ENTRY_EXIT_1, area=0, name="Front Door")
    sensor = _sensor_for_area(0, [door])
    assert sensor.is_on is False


def test_area_openings_sensor_on_when_a_door_opens():
    door = _make_zone(0, ZoneType.BURGLAR_ENTRY_EXIT_1, area=0, name="Front Door")
    door.setattr("logical_status", ZoneLogicalStatus.VIOLATED, False)
    sensor = _sensor_for_area(0, [door])

    assert sensor.is_on is True
    assert sensor.extra_state_attributes["open_zones"] == ["Front Door"]
    assert sensor.extra_state_attributes["open_zones_count"] == 1


def test_area_openings_sensor_ignores_non_opening_zone_types():
    """A fire-alarm zone opening shouldn't flip the door/window aggregate sensor."""
    smoke = _make_zone(0, ZoneType.FIRE_ALARM, area=0, name="Smoke Detector")
    smoke.setattr("logical_status", ZoneLogicalStatus.VIOLATED, False)
    sensor = _sensor_for_area(0, [smoke])

    assert sensor.is_on is False


def test_area_openings_sensor_isolates_areas():
    """A door open in area 2 must not affect area 1's aggregate sensor."""
    door_area_1 = _make_zone(0, ZoneType.BURGLAR_ENTRY_EXIT_1, area=0, name="Front Door")
    door_area_2 = _make_zone(1, ZoneType.BURGLAR_ENTRY_EXIT_1, area=1, name="Garage Door")
    door_area_2.setattr("logical_status", ZoneLogicalStatus.VIOLATED, False)

    zones = [door_area_1, door_area_2]
    sensor_area_1 = _sensor_for_area(0, zones)
    sensor_area_2 = _sensor_for_area(1, zones)

    assert sensor_area_1.is_on is False
    assert sensor_area_2.is_on is True

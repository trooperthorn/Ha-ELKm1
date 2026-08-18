"""Constants for Elk-M1 integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from elkm1_lib.const import Max
import voluptuous as vol

from homeassistant.const import ATTR_CODE, CONF_ZONE

DOMAIN = "elkm1"
MANUFACTURER = "Elk Products"
MODEL = "M1 Gold / M1EZ8"
LOGIN_TIMEOUT = 20

# Connection Configuration Keys & Types
CONF_CONNECTION_TYPE = "connection_type"
CONF_SERIAL_PORT = "serial_port"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PIN = "pin"

CONNECTION_SERIAL = "serial"
CONNECTION_NETWORK = "network"

COORDINATOR_UPDATE_INTERVAL = 30

CONF_AUTO_CONFIGURE = "auto_configure"
CONF_AREA = "area"
CONF_COUNTER = "counter"
CONF_KEYPAD = "keypad"
CONF_OUTPUT = "output"
CONF_PLC = "plc"
CONF_SETTING = "setting"
CONF_TASK = "task"
CONF_THERMOSTAT = "thermostat"

DISCOVER_SCAN_TIMEOUT = 10
DISCOVERY_INTERVAL = timedelta(minutes=15)

# Element map required for __init__.py auto_configure logic
ELK_ELEMENTS = {
    CONF_AREA: Max.AREAS.value,
    CONF_COUNTER: Max.COUNTERS.value,
    CONF_KEYPAD: Max.KEYPADS.value,
    CONF_OUTPUT: Max.OUTPUTS.value,
    CONF_PLC: Max.LIGHTS.value,
    CONF_SETTING: Max.SETTINGS.value,
    CONF_TASK: Max.TASKS.value,
    CONF_THERMOSTAT: Max.THERMOSTATS.value,
    CONF_ZONE: Max.ZONES.value,
}

# Keypad and automation event constants
EVENT_ELKM1_KEYPAD_KEY_PRESSED = "elkm1.keypad_key_pressed"

ATTR_DURATION = "duration"
ATTR_KEYPAD_ID = "keypad_id"
ATTR_KEY = "key"
ATTR_KEY_NAME = "key_name"
ATTR_KEYPAD_NAME = "keypad_name"
ATTR_CHANGED_BY_KEYPAD = "changed_by_keypad"
ATTR_CHANGED_BY_ID = "changed_by_id"
ATTR_CHANGED_BY_TIME = "changed_by_time"
ATTR_VALUE = "value"

# Native service schema validation for strict PIN enforcement
ELK_USER_CODE_SERVICE_SCHEMA: dict[Any, Any] = {
    vol.Required(ATTR_CODE): vol.All(vol.Coerce(int), vol.Range(0, 999999))
}

"""Constants for Elk-M1 integration."""
from datetime import timedelta
from typing import Final

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

__all__ = [
    "CONF_HOST",
    "CONF_PASSWORD",
    "CONF_PORT",
    "CONF_USERNAME",
]

DOMAIN: Final = "elkm1"
CONF_URL: Final = "url"

# Config flow keys
CONF_SERIAL_PORT: Final = "serial_port"
CONF_CONNECTION_TYPE: Final = "connection_type"
CONF_PIN: Final = "pin"
CONF_VERIFY_DEVICE: Final = "verify_device"

CONNECTION_SERIAL: Final = "serial"
CONNECTION_NETWORK: Final = "network"

# Device info
MANUFACTURER: Final = "ELK Products, Inc."
MODEL: Final = "M1 Gold/EZ8"

# Connection settings
ELKM1_BAUDRATE: Final = 115200
COORDINATOR_UPDATE_INTERVAL: Final = 5  # seconds, used with timedelta()

# Polling interval (for status updates)
DEFAULT_UPDATE_INTERVAL: Final = timedelta(seconds=60)

# Watchdog settings (detect silent connection loss)
LIVENESS_CHECK_INTERVAL: Final = timedelta(seconds=30)
LIVENESS_TIMEOUT: Final = 60  # seconds without traffic = reconnect

# SECURITY
CONF_INCLUDED_ZONES = "included_zones"
CONF_SYNC_CLOCK = "sync_clock"
CONF_ENABLE_TASKS = "enable_tasks"
CONF_STRICT_PIN = "strict_pin"
CONF_AUTO_CLEAR_MEMORY = "auto_clear_memory"

# Default values
DEFAULT_INCLUDED_ZONES = "1-10"
DEFAULT_SYNC_CLOCK = True
DEFAULT_ENABLE_TASKS = True
DEFAULT_STRICT_PIN = True
DEFAULT_AUTO_CLEAR_MEMORY = False

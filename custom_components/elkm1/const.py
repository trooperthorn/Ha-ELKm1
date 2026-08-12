"""Constants for Elk-M1 integration."""
from typing import Final

DOMAIN: Final = "elkm1"
MANUFACTURER: Final = "Elk Products"
MODEL: Final = "M1 Control Panel"

# Config flow keys
CONF_URL: Final = "url"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_SERIAL_PORT: Final = "serial_port"

# Polling interval (for status updates)
DEFAULT_UPDATE_INTERVAL: Final = timedelta(seconds=60)

# USB detection timeout
USB_DETECTION_TIMEOUT: Final = 10  # seconds

# Elk protocol constants
ELK_BAUDRATE: Final = 115200
ELK_BYTESIZE: Final = 8
ELK_PARITY: Final = "N"
ELK_STOPBITS: Final = 1

# Command queue settings
COMMAND_QUEUE_INTERVAL: Final = 0.1  # 100ms between commands to M1
COMMAND_ACK_TIMEOUT: Final = 2.0  # seconds to wait for ACK

# Connection retry settings
RECONNECT_DELAY: Final = 5  # seconds before retry
MAX_RECONNECT_ATTEMPTS: Final = 10

# Watchdog settings (detect silent connection loss)
LIVENESS_CHECK_INTERVAL: Final = timedelta(seconds=30)
LIVENESS_TIMEOUT: Final = 60  # seconds without traffic = reconnect

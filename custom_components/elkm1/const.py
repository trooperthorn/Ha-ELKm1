"""Constants for Elk-M1 integration."""
from datetime import timedelta
from typing import Final

DOMAIN: Final = "elkm1"

# Config flow keys
CONF_URL: Final = "url"
CONF_SERIAL_PORT: Final = "serial_port"
CONF_CONNECTION_TYPE: Final = "connection_type"
CONF_PIN: Final = "pin"
CONF_VERIFY_DEVICE: Final = "verify_device"

CONNECTION_SERIAL: Final = "serial"
CONNECTION_NETWORK: Final = "network"

# Polling interval (for status updates)
DEFAULT_UPDATE_INTERVAL: Final = timedelta(seconds=60)

# USB detection timeout
...

# Watchdog settings (detect silent connection loss)
LIVENESS_CHECK_INTERVAL: Final = timedelta(seconds=30)
LIVENESS_TIMEOUT: Final = 60  # seconds without traffic = reconnect

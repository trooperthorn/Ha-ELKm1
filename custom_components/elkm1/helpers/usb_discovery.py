"""USB serial port discovery for ELK-M1 integration."""

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from serial.tools import list_ports

_LOGGER = logging.getLogger(__name__)

# Common USB serial adapter VID:PIDs
KNOWN_ADAPTERS = {
    "0403:6001": "FTDI FT232R",
    "067b:2303": "Prolific PL2303",
    "10c4:ea60": "Silicon Labs CP2102",
    "1a86:7523": "CH340",
    "0403:6015": "FTDI FT232H",
}


def get_in_use_serial_ports(hass: HomeAssistant) -> set[str]:
    """Scan Home Assistant config entries to find serial ports actively used by other integrations."""
    in_use = set()
    # Common dictionary keys integrations use to store serial port paths
    serial_keys = {"device", "port", "serial_port", "path", "url"}
    
    for entry in hass.config_entries.async_entries():
        # Check both the static data and dynamic options dicts
        for source in (entry.data, entry.options):
            for key in serial_keys:
                val = source.get(key)
                
                # Standard String Path (e.g., Modbus, Serial, ELK)
                if isinstance(val, str) and val.startswith(("/dev/", "COM", "serial://")):
                    clean_path = val.replace("serial://", "")
                    in_use.add(clean_path)
                    
                # Dictionary Path (e.g., ZHA stores it as {'path': '/dev/ttyUSB0'})
                elif key == "device" and isinstance(val, dict):
                    dict_path = val.get("path")
                    if isinstance(dict_path, str) and dict_path.startswith(("/dev/", "COM")):
                        in_use.add(dict_path)
                        
    return in_use


async def discover_elk_ports(hass: HomeAssistant) -> dict[str, str]:
    """Discover available ELK-M1 compatible serial ports, excluding those in use."""
    loop = asyncio.get_running_loop()
    
    # 1. Get the blacklist of ports already claimed by Home Assistant
    in_use_ports = get_in_use_serial_ports(hass)

    def _list_ports() -> dict[str, str]:
        available_ports = {}
        for port_info in list_ports.comports():
            port_path = (
                port_info.device
                if port_info.device and port_info.device.startswith("/dev/serial/by-id/")
                else (port_info.device or port_info.name)
            )

            # 2. Prevent UI listing and probing if the port is already owned by another integration
            if port_path in in_use_ports or port_info.device in in_use_ports:
                _LOGGER.debug("Skipping in-use serial port: %s", port_path)
                continue

            friendly = _get_friendly_name(port_info)
            available_ports[port_path] = friendly
            _LOGGER.debug("Found available, unused port: %s -> %s", port_path, friendly)

        return available_ports

    try:
        ports = await loop.run_in_executor(None, _list_ports)
    except OSError as e:
        _LOGGER.error("Error discovering ports: %s", e)
        return {}

    return ports


def _get_friendly_name(port_info: Any) -> str:
    """Get friendly name for a serial port."""
    product = port_info.product or "Unknown Device"
    device_name = port_info.name.split("/")[-1] if port_info.name else "unknown"
    return f"{product} ({device_name})"


async def probe_serial_port(port: str, timeout: float = 5.0) -> bool:
    """Test if a serial port actually has an ELK-M1 panel connected.

    Wrapped in extensive error handling to prevent event loop crashes.
    """
    from .baud_probe import BaudProbeError
    from .transport import validate_serial_port

    try:
        await asyncio.wait_for(validate_serial_port(port), timeout=timeout)
        return True
    except BaudProbeError as e:
        _LOGGER.debug("Port %s probe failed gracefully: %s", port, e)
        return False
    except (asyncio.TimeoutError, ConnectionError, OSError, ValueError) as e:
        _LOGGER.debug("Port %s probe failed gracefully: %s", port, e)
        return False
    except Exception as e:  # noqa: BLE001
        _LOGGER.error("Unexpected error during serial probe on %s: %s", port, e)
        return False

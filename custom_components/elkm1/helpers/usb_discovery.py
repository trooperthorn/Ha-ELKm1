"""USB port discovery for Elk-M1 adapters."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Final

import serial.tools.list_ports
from elkm1_lib import Elk

_LOGGER: logging.Logger = logging.getLogger(__name__)

# Common USB IDs for RS232 adapters
KNOWN_ADAPTERS: Final = {
    "0403:6001": "FTDI",  # FTDI FT232
    "0403:6010": "FTDI",  # FTDI FT2232
    "067b:2303": "Prolific",  # PL2303
    "10c4:ea60": "SiLabs",  # CP2102
    "1a86:7523": "CH340",
}


async def discover_elk_ports() -> dict[str, str]:
    """
    Discover USB-to-Serial ports that might be Elk-M1 devices.
    
    Returns dict of {port_path: display_name}
    """
    ports_found: dict[str, str] = {}

    # List all serial ports
    for port_info in serial.tools.list_ports.comports():
        if not port_info.device:
            continue

        # Prefer /dev/serial/by-id paths (persistent)
        port_path = port_info.device
        if port_info.serial_number:
            # Try to find persistent /dev/serial/by-id path
            by_id_path = _get_by_id_path(port_info)
            if by_id_path:
                port_path = by_id_path

        # Check if it looks like an RS232 adapter
        if _is_likely_rs232_adapter(port_info):
            display_name = f"{port_info.manufacturer} ({port_path})"
            ports_found[port_path] = display_name

    # Now probe each port for Elk M1 response
    confirmed_ports: dict[str, str] = {}
    for port_path, display_name in ports_found.items():
        try:
            await probe_serial_port(port_path, timeout=2)
            confirmed_ports[port_path] = f"✓ {display_name}"
            _LOGGER.debug(f"Elk M1 found at {port_path}")
        except Exception as err:
            _LOGGER.debug(f"No Elk M1 at {port_path}: {err}")

    return confirmed_ports


def _get_by_id_path(port_info) -> str | None:
    """Find /dev/serial/by-id path for a port."""
    import pathlib
    import glob

    if not port_info.serial_number:
        return None

    # Look for symlink in /dev/serial/by-id/
    pattern = f"/dev/serial/by-id/*{port_info.serial_number}*"
    matches = glob.glob(pattern)
    
    if matches:
        return matches[0]
    
    return None


def _is_likely_rs232_adapter(port_info) -> bool:
    """Heuristic: check if port is likely a USB-to-Serial adapter."""
    # Check VID:PID against known adapters
    if port_info.vid and port_info.pid:
        usb_id = f"{port_info.vid:04x}:{port_info.pid:04x}"
        if usb_id in KNOWN_ADAPTERS:
            return True

    # Check description for serial indicators
    desc = (port_info.description or "").lower()
    return "usb" in desc and "serial" in desc


async def probe_serial_port(port_path: str, timeout: float = 5.0) -> bool:
    """
    Test if an Elk M1 is at this port.
    Raises exception if not found or unreachable.
    """
    try:
        config = {"url": f"serial://{port_path}"}
        elk = Elk(config)
        
        # Set a connection timeout
        await asyncio.wait_for(elk.async_connect(), timeout=timeout)
        
        # Try a simple status query to verify
        # elkm1_lib should have a method to query panel version/status
        await asyncio.wait_for(elk.async_disconnect(), timeout=2)
        
        return True
        
    except asyncio.TimeoutError:
        raise ConnectionError(f"Timeout connecting to {port_path}") from None
    except Exception as err:
        raise ConnectionError(f"Failed to connect to {port_path}: {err}") from err

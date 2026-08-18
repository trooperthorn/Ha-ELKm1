"""USB serial port discovery for ELK-M1 integration."""

import asyncio
import logging
from typing import Any

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


async def discover_elk_ports() -> dict[str, str]:
    """Discover available ELK-M1 compatible serial ports."""
    loop = asyncio.get_running_loop()

    def _list_ports() -> dict[str, str]:
        available_ports = {}
        for port_info in list_ports.comports():
            # Prefer persistent by-id paths over volatile ttyUSB/COM nodes
            port_path = (
                port_info.device
                if port_info.device and port_info.device.startswith("/dev/serial/by-id/")
                else (port_info.device or port_info.name)
            )

            friendly = _get_friendly_name(port_info)
            available_ports[port_path] = friendly
            _LOGGER.debug(f"Found port: {port_path} -> {friendly}")

        return available_ports

    try:
        ports = await loop.run_in_executor(None, _list_ports)
    except OSError as e:
        _LOGGER.error(f"Error discovering ports: {e}")
        return {}

    return ports


def _get_friendly_name(port_info: Any) -> str:
    """Get friendly name for a serial port.

    Args:
        port_info: pyserial PortInfo object

    Returns:
        Friendly string like "FTDI FT232R (ttyUSB0)" or "Unknown Device (ttyUSB0)"
    """
    product = port_info.product or "Unknown Device"
    device_name = port_info.name.split("/")[-1] if port_info.name else "unknown"
    return f"{product} ({device_name})"


async def probe_serial_port(port: str, timeout: float = 5.0) -> bool:
    """Test if a serial port actually has an ELK-M1 panel connected.

    Attempts to connect, wait for the connected event, and verify panel data.

    Args:
        port: Serial port path (e.g., "/dev/ttyUSB0" or "/dev/serial/by-id/...")
        timeout: Connection timeout in seconds

    Returns:
        True if ELK-M1 data detected, False otherwise
    """
    from elkm1_lib import Elk

    try:
        url = f"serial://{port}"
        _LOGGER.debug(f"Probing port: {url}")

        config = {"url": url}
        connection = Elk(config)

        connected_event = asyncio.Event()

        def on_connected(*args: Any, **kwargs: Any) -> None:
            connected_event.set()

        connection.add_handler("connected", on_connected)

        # connect() is synchronous; starts background background read/write streams
        connection.connect()

        try:
            await asyncio.wait_for(connected_event.wait(), timeout=timeout)
            
            # Wait briefly for initial panel sync telemetry packet
            await asyncio.sleep(1.5)

            if getattr(connection.panel, "elkm1_version", None) or getattr(
                connection.panel, "system_trouble_status", None
            ):
                _LOGGER.info(f"Port {url}: ELK-M1 data verified ✓")
                return True
            
            _LOGGER.debug(f"Port {url}: Port opened, but no ELK-M1 data received.")
            return False

        except asyncio.TimeoutError:
            _LOGGER.debug(f"Port {port}: Connection timeout (no device)")
            return False
        finally:
            connection.disconnect()

    except Exception as e:  # noqa: BLE001
        _LOGGER.debug(f"Port {port}: No ELK-M1 detected - {e}")
        return False

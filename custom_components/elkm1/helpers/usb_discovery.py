"""USB serial port discovery for ELK-M1 integration."""
import asyncio
import logging

from elkm1_lib import Elk
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
    loop = asyncio.get_event_loop()

    def _list_ports():
        available_ports = {}
        for port_info in list_ports.comports():
            if port_info.name.startswith("/dev/serial/by-id/"):
                port_path = port_info.name
            else:
                port_path = port_info.device

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


def _get_friendly_name(port_info) -> str:
    """
    Get friendly name for a serial port.
    
    Args:
        port_info: pyserial PortInfo object
        
    Returns:
        Friendly string like "FTDI FT232R (ttyUSB0)" or "Unknown Device (ttyUSB0)"
    """
    # Try to get product name
    product = port_info.product or "Unknown Device"
    
    # Get device name (ttyUSB0, COM3, etc)
    device_name = port_info.name.split("/")[-1] if port_info.name else "unknown"
    
    return f"{product} ({device_name})"


async def probe_serial_port(port: str, timeout: float = 5.0) -> bool:
    """
    Test if a serial port has an ELK-M1 panel.
    
    Attempts to connect and send a ping command.
    
    Args:
        port: Serial port path (e.g., "/dev/ttyUSB0")
        timeout: Connection timeout in seconds
        
    Returns:
        True if ELK-M1 detected, False otherwise
    """
    # FIX 1: Import the correct Elk class
    from elkm1_lib import Elk
    
    try:
        # Create connection URL
        if port.startswith("/"):
            # Unix path
            url = f"serial://{port}"
        else:
            # Windows COM port
            url = f"serial://{port}"
        
        _LOGGER.debug(f"Probing port: {url}")
        
        # FIX 2: Pass configuration as a dictionary, not as kwargs
        config = {"url": url}
        connection = Elk(config)
        
        async def _connect():
            await asyncio.wait_for(connection.connect(), timeout=timeout)
            # If we got here, connection successful
            # FIX 3: Remove 'await' because disconnect() is a synchronous method
            connection.disconnect()
            return True
        
        result = await _connect()
        _LOGGER.info(f"Port {url}: ELK-M1 detected ✓")
        return result
        
    except asyncio.TimeoutError:
        _LOGGER.debug(f"Port {port}: Connection timeout (no device?)")
        return False
    except Exception as e:  # noqa: BLE001
        # Changed to catch all exceptions to prevent UI crashes if elkm1_lib throws a weird error
        _LOGGER.debug(f"Port {port}: No ELK-M1 detected - {e}")
        return False

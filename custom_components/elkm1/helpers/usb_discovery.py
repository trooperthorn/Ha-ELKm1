"""USB serial port discovery for ELK-M1 integration."""
import asyncio
import logging

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
    
    Attempts to connect and wait for the connected event.
    
    Args:
        port: Serial port path (e.g., "/dev/ttyUSB0")
        timeout: Connection timeout in seconds
        
    Returns:
        True if ELK-M1 detected, False otherwise
    """
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
        
        config = {"url": url}
        connection = Elk(config)
        
        # 1. Use an Event to track when elkm1_lib successfully connects
        connected_event = asyncio.Event()
        
        def on_connected(*args, **kwargs):
            connected_event.set()
            
        # Hook into the native 'connected' callback in elkm1_lib
        connection.add_handler("connected", on_connected)
        
        # 2. connect() is synchronous and returns None. Do NOT await it.
        # This safely creates the background tasks without crashing.
        connection.connect()
        
        try:
            # 3. Wait for the 'connected' event to trigger, up to the timeout limit
            await asyncio.wait_for(connected_event.wait(), timeout=timeout)
            _LOGGER.info(f"Port {url}: ELK-M1 detected ✓")
            return True
        except asyncio.TimeoutError:
            _LOGGER.debug(f"Port {port}: Connection timeout (no device?)")
            return False
        finally:
            # 4. CRITICAL FIX: Guarantee disconnect runs no matter what.
            # This cleanly kills the _read_stream and _write_stream tasks
            # and releases the serial port so other integrations aren't locked out.
            connection.disconnect()
            
    except Exception as e:  # noqa: BLE001
        _LOGGER.debug(f"Port {port}: No ELK-M1 detected - {e}")
        return False

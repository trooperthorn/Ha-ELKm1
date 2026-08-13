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
    Test if a serial port actually has an ELK-M1 panel connected.
    
    Attempts to connect, wait for the connected event, and verify panel data.
    
    Args:
        port: Serial port path (e.g., "/dev/ttyUSB0" or "/dev/serial/by-id/...")
        timeout: Connection timeout in seconds
        
    Returns:
        True if ELK-M1 data detected, False otherwise
    """
    from elkm1_lib import Elk
    import asyncio
    
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
        
        # 1. Use an Event to track when elkm1_lib successfully opens the port
        connected_event = asyncio.Event()
        
        def on_connected(*args, **kwargs):
            connected_event.set()
            
        # Hook into the native 'connected' callback in elkm1_lib
        connection.add_handler("connected", on_connected)
        
        # 2. connect() is synchronous and returns None. Do NOT await it.
        # This safely creates the background tasks without crashing.
        connection.connect()
        
        try:
            # 3. Wait for the port to physically open
            await asyncio.wait_for(connected_event.wait(), timeout=timeout)
            
            # 4. NEW: The port is open, but is an Elk attached? 
            # Wait 1.5 seconds for the panel to send its initial sync data.
            await asyncio.sleep(1.5)
            
            # 5. NEW: Check if the panel object was populated with real data.
            # Empty DB9 ports won't have this.
            if connection.panel.elkm1_version or connection.panel.system_trouble_status:
                _LOGGER.info(f"Port {url}: ELK-M1 data verified ✓")
                return True
            else:
                _LOGGER.debug(f"Port {url}: Port opened, but no ELK-M1 data received.")
                return False
                
        except asyncio.TimeoutError:
            _LOGGER.debug(f"Port {port}: Connection timeout (no device?)")
            return False
        finally:
            # 6. CRITICAL FIX: Guarantee disconnect runs no matter what.
            # This cleanly kills the _read_stream and _write_stream tasks
            # and releases the serial port so you don't get "Resource Busy" locks.
            connection.disconnect()
            
    except Exception as e:  # noqa: BLE001
        _LOGGER.debug(f"Port {port}: No ELK-M1 detected - {e}")
        return False

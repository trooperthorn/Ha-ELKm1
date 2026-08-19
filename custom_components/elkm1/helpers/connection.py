"""Native asyncio connection manager for Elk-M1 (TCP & Serial)."""

import asyncio
import logging
from typing import Callable

_LOGGER = logging.getLogger(__name__)


class ElkConnectionManager:
    """Manages the raw TCP/Serial connection to the Elk-M1 panel."""

    def __init__(
        self,
        connection_url: str,
        on_message_callback: Callable[[str], None],
        is_serial: bool = False,
        baudrate: int = 115200,
    ) -> None:
        """Initialize the connection manager."""
        self._url = connection_url
        self._is_serial = is_serial
        self._baudrate = baudrate
        self._callback = on_message_callback
        
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        
        self._connected = False
        self._reconnect_delay = 2.0
        self._max_reconnect_delay = 60.0
        
        self._read_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected

    async def connect(self) -> None:
        """Establish the connection and start background tasks."""
        await self._connect_internal()
        self._read_task = asyncio.create_task(self._read_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _connect_internal(self) -> None:
        """Internal connection logic with exponential backoff."""
        while not self._connected:
            try:
                if self._is_serial:
                    import serial_asyncio
                    port = self._url.replace("serial://", "")
                    self._reader, self._writer = await serial_asyncio.open_serial_connection(
                        url=port, baudrate=self._baudrate
                    )
                else:
                    host_port = self._url.replace("elk://", "").replace("elks://", "")
                    host, port = host_port.split(":")
                    self._reader, self._writer = await asyncio.open_connection(
                        host=host, port=int(port)
                    )

                self._connected = True
                self._reconnect_delay = 2.0  # Reset delay on success
                _LOGGER.info(f"Successfully connected to Elk-M1 at {self._url}")

            except Exception as err:
                _LOGGER.error(f"Connection failed: {err}. Retrying in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def disconnect(self) -> None:
        """Gracefully close the connection and cancel background tasks."""
        self._connected = False
        
        if self._read_task:
            self._read_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        
        self._reader = None
        self._writer = None
        _LOGGER.info("Disconnected from Elk-M1")

    async def _read_loop(self) -> None:
        """Continuous loop to read data from the Elk-M1."""
        while True:
            if not self._connected or not self._reader:
                await asyncio.sleep(1)
                continue

            try:
                # Elk ASCII protocol terminates with \r\n
                line = await self._reader.readuntil(b'\r\n')
                decoded_line = line.decode('ascii', errors='ignore').strip()
                
                if decoded_line:
                    # Pass the raw ASCII string up to the coordinator for parsing
                    self._callback(decoded_line)

            except asyncio.IncompleteReadError:
                _LOGGER.warning("Elk-M1 connection dropped (IncompleteReadError).")
                await self._handle_disconnect()
            except ConnectionError as err:
                _LOGGER.error(f"Elk-M1 connection error: {err}")
                await self._handle_disconnect()
            except Exception as err:
                _LOGGER.error(f"Unexpected read error: {err}")
                await self._handle_disconnect()

    async def _handle_disconnect(self) -> None:
        """Handle unexpected disconnections and trigger a reconnect."""
        self._connected = False
        if self._writer:
            self._writer.close()
        await self._connect_internal()

    async def write(self, command: str) -> bool:
        """Format a raw Elk ASCII command (calculating length/checksum) and send it."""
        if not self._connected or not self._writer:
            _LOGGER.error("Cannot send command. Not connected to Elk-M1.")
            return False

        try:
            # 1. Format payload: <command> + "00" (reserved bytes for future protocol use)
            payload = f"{command}00"
            
            # 2. Calculate length (payload length + 2 bytes for the length itself)
            length = len(payload) + 2
            packet = f"{length:02X}{payload}"

            # 3. Calculate Checksum (Two's complement of the modulo-256 sum)
            checksum = sum(ord(c) for c in packet) % 256
            checksum = (checksum ^ 0xFF) + 1

            # 4. Construct final string with Carriage Return + Line Feed
            final_string = f"{packet}{checksum & 0xFF:02X}\r\n"

            self._writer.write(final_string.encode('ascii'))
            await self._writer.drain()
            _LOGGER.debug(f"Sent Elk Command: {final_string.strip()}")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to write to Elk-M1: {err}")
            await self._handle_disconnect()
            return False

    async def _heartbeat_loop(self) -> None:
        """Send a keep-alive heartbeat to prevent the M1XEP TCP dropout quirk."""
        while True:
            if self._connected:
                # 'rr' is the Request RTC (Real Time Clock) command.
                # It is extremely lightweight and ensures the TCP socket stays open.
                await self.write("rr")
            await asyncio.sleep(45)  # Ping every 45 seconds

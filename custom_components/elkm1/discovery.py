"""Network discovery helpers for Elk-M1 integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class ElkUDPDiscoveryProtocol(asyncio.DatagramProtocol):
    """Native Asyncio UDP protocol to broadcast and listen for Elk M1XEP modules."""

    def __init__(self, target_event: asyncio.Event, devices: list[dict[str, Any]]):
        self.target_event = target_event
        self.devices = devices

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle incoming M1XEP broadcast responses."""
        try:
            # The Elk panel responds to network discovery with its MAC and details
            message = data.decode("ascii", errors="ignore")
            if message.startswith("M1XEP"):
                # Parse basic info (typically MAC address follows the identifier)
                parts = message.split()
                mac = parts[1] if len(parts) > 1 else "Unknown"
                
                device_info = {
                    "ip_address": addr[0],
                    "port": addr[1],
                    "mac_address": mac,
                }
                
                # Prevent duplicates
                if not any(d["ip_address"] == addr[0] for d in self.devices):
                    self.devices.append(device_info)
                    _LOGGER.debug(f"Discovered Elk-M1 module at {addr[0]}:{addr[1]}")
                    
        except Exception as e:
            _LOGGER.debug(f"Error parsing UDP discovery response: {e}")

async def async_discover_devices(
    hass: HomeAssistant,
    entry: ConfigEntry | None = None,
) -> list[Any]:
    """Discover all Elk-M1 device elements."""
    return []

    try:
        # Elk M1XEP listens for UDP broadcasts on port 2362
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ElkUDPDiscoveryProtocol(discovery_event, devices),
            local_addr=("0.0.0.0", 0),
            allow_broadcast=True,
        )

        try:
            # Broadcast the M1XEP discovery string
            discovery_payload = b"\xE4\xE4\r\n"
            transport.sendto(discovery_payload, ("255.255.255.255", 2362))
            
            # Wait for responses
            await asyncio.sleep(timeout)
            
        finally:
            transport.close()

    except Exception as e:
        _LOGGER.error(f"Network discovery failed: {e}")

    return devices

def _short_mac(mac: str) -> str:
    """Format a MAC address to a short, colon-less string."""
    return mac.replace(":", "").replace("-", "").lower()

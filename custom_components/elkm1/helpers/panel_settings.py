"""Panel settings configuration and verification."""

import asyncio
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Global settings that must be enabled via ElkRP Software for HA to receive broadcasts
REQUIRED_SETTINGS = [
    "Transmit Event Log (G35)",
    "Transmit Zone Changes (G36)",
    "Transmit Output Changes (G37)",
    "Transmit Automation Task Changes (G38)",
    "Transmit Light Changes (G39)",
    "Transmit Keypad Changes (G40)",
]


async def check_panel_version(coordinator: Any) -> str | None:
    """Check ELK-M1 panel version by sending the 'vn' command.

    Args:
        coordinator: ElkDataUpdateCoordinator instance

    Returns:
        Version string (e.g., "4.6.8" or "5.2.0") or None if not available
    """
    try:
        # Send the 'vn' command to request the version string
        await coordinator.send_raw_elk_command("vn")
        
        # Give the panel a moment to respond and the coordinator to parse it
        await asyncio.sleep(2.0)
        
        # Read the parsed version from our normalized dictionary
        version = coordinator.data.get("panel_version")

        if version:
            _LOGGER.info(f"ELK-M1 Panel Version: {version}")

            parts = str(version).split(".")
            major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
            minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

            # Minimum: 4.6.8 or 5.2.0+
            if (major >= 5 and minor >= 2) or (major == 4 and minor >= 6 and patch >= 8):
                _LOGGER.info(f"✓ Panel version {version} is supported")
                return str(version)
            
            _LOGGER.warning(
                f"Panel version {version} may have limited feature support. "
                f"Recommended: 4.6.8+ or 5.2.0+"
            )
            return str(version)
        
        _LOGGER.warning("Could not determine panel version. Did the panel respond?")
        return None

    except Exception as err:
        _LOGGER.debug(f"Error checking panel version: {err}")
        return None


async def verify_panel_configuration(coordinator: Any) -> tuple[bool, dict[str, Any]]:
    """Verify panel is properly configured for Home Assistant."""
    _LOGGER.info("Verifying ELK-M1 panel configuration...")

    details: dict[str, Any] = {}

    # Check version
    version = await check_panel_version(coordinator)
    details["version"] = version

    # Log Required Settings Reminders
    # We no longer attempt to blindly overwrite EEPROM memory via raw ASCII.
    _LOGGER.warning(
        "ELK-M1 INTEGRATION NOTE: Please ensure the following 'Serial Port Transmit Options' "
        "are enabled in your ElkRP software under 'Global Programming' > 'G35-G40' for this "
        "integration to receive real-time state updates:"
    )
    for setting in REQUIRED_SETTINGS:
        _LOGGER.warning(f"  - {setting}")

    # We assume configuration is valid if we successfully connected and got a version
    is_configured = version is not None
    details["configured"] = is_configured

    return is_configured, details

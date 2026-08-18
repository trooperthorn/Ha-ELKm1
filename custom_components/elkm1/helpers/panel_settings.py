"""Panel settings configuration and verification."""

import logging
from typing import Any

from elkm1_lib import Elk

_LOGGER = logging.getLogger(__name__)

# Global settings that should be enabled for proper event reporting
REQUIRED_SETTINGS = {
    35: "Transmit Event Log",
    36: "Transmit Zone Changes",
    37: "Transmit Output Changes",
    38: "Transmit Automation Task Changes",
    39: "Transmit Light Changes",
    40: "Transmit Keypad Changes",
}


async def check_panel_version(elk_connection: Elk) -> str | None:
    """Check ELK-M1 panel version.

    Args:
        elk_connection: Elk instance

    Returns:
        Version string (e.g., "4.6.8" or "5.2.0") or None if not available
    """
    try:
        panel = getattr(elk_connection, "panel", None)
        version = (
            getattr(elk_connection, "panel_version", None)
            or (getattr(panel, "elkm1_version", None) if panel else None)
            or (getattr(panel, "version", None) if panel else None)
        )

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
        
        _LOGGER.warning("Could not determine panel version")
        return None

    except (OSError, TimeoutError, ValueError, AttributeError) as err:
        _LOGGER.debug(f"Error checking panel version: {err}")
        return None


async def read_global_setting(elk_connection: Elk, setting_number: int) -> int | None:
    """Read a global setting from the panel safely."""
    try:
        get_setting_fn = getattr(elk_connection, "get_setting", None)
        if not get_setting_fn and hasattr(elk_connection, "panel"):
            get_setting_fn = getattr(elk_connection.panel, "get_setting", None)

        if not get_setting_fn:
            return None

        value = await get_setting_fn(setting_number) if callable(get_setting_fn) else None
        return value

    except (OSError, TimeoutError, ValueError, AttributeError) as err:
        _LOGGER.debug(f"Error reading global setting {setting_number}: {err}")
        return None


async def write_global_setting(elk_connection: Elk, setting_number: int, value: int) -> bool:
    """Write a global setting to the panel safely."""
    try:
        set_setting_fn = getattr(elk_connection, "set_setting", None)
        if not set_setting_fn and hasattr(elk_connection, "panel"):
            set_setting_fn = getattr(elk_connection.panel, "set_setting", None)

        if not set_setting_fn:
            return False

        if callable(set_setting_fn):
            await set_setting_fn(setting_number, value)

        _LOGGER.info(f"Set global setting {setting_number} to {value}")
        return True

    except (OSError, TimeoutError, ValueError, AttributeError) as err:
        _LOGGER.debug(f"Error writing global setting {setting_number}: {err}")
        return False


async def check_required_settings(elk_connection: Elk) -> dict[int, dict[str, Any]]:
    """Check all required global settings."""
    settings_status = {}

    for setting_num, setting_name in REQUIRED_SETTINGS.items():
        value = await read_global_setting(elk_connection, setting_num)
        is_enabled = value == 1 if value is not None else None

        settings_status[setting_num] = {
            "name": setting_name,
            "enabled": is_enabled,
            "value": value,
        }

        status_str = "✓ Enabled" if is_enabled else "✗ Disabled" if is_enabled is False else "? Unknown"
        _LOGGER.info(f"Setting {setting_num} ({setting_name}): {status_str}")

    return settings_status


async def enable_required_settings(elk_connection: Elk) -> dict[int, bool]:
    """Enable all required global settings."""
    results = {}
    _LOGGER.info("Attempting to enable required global settings...")

    for setting_num, setting_name in REQUIRED_SETTINGS.items():
        current_value = await read_global_setting(elk_connection, setting_num)

        if current_value == 1:
            _LOGGER.info(f"Setting {setting_num} ({setting_name}) is already enabled")
            results[setting_num] = True
        elif current_value == 0:
            _LOGGER.info(f"Enabling setting {setting_num} ({setting_name})...")
            success = await write_global_setting(elk_connection, setting_num, 1)
            results[setting_num] = success
        else:
            _LOGGER.debug(f"Could not read setting {setting_num} (skipping write)")
            results[setting_num] = False

    return results


async def verify_panel_configuration(elk_connection: Elk) -> tuple[bool, dict[str, Any]]:
    """Verify panel is properly configured for Home Assistant."""
    _LOGGER.info("Verifying ELK-M1 panel configuration...")

    details: dict[str, Any] = {}

    # Check version
    version = await check_panel_version(elk_connection)
    details["version"] = version

    # Check settings
    settings_status = await check_required_settings(elk_connection)
    details["settings"] = settings_status

    # Determine if all required settings are enabled or unknown
    all_configured = all(
        status["enabled"] is not False
        for status in settings_status.values()
    )

    if all_configured:
        _LOGGER.info("✓ Panel configuration verified")
        details["configured"] = True
    else:
        disabled_settings = [
            f"{num} ({status['name']})"
            for num, status in settings_status.items()
            if status["enabled"] is False
        ]
        _LOGGER.warning(
            f"Panel has disabled settings: {', '.join(disabled_settings)}"
        )
        details["configured"] = False
        details["disabled_settings"] = disabled_settings

    return all_configured, details

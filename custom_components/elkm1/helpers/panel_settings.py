"""Panel settings configuration and verification."""
import logging
from typing import Any

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


async def check_panel_version(elk_connection) -> str | None:
    """
    Check ELK-M1 panel version.
    
    Args:
        elk_connection: ElkM1Connection instance
        
    Returns:
        Version string (e.g., "4.6.8" or "5.2.0") or None if not available
    """
    try:
        # Get version from panel
        version = getattr(elk_connection, 'panel_version', None)
        
        if version:
            _LOGGER.info(f"ELK-M1 Panel Version: {version}")
            
            # Check for minimum version support
            parts = version.split('.')
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            
            # Minimum: 4.6.8 or 5.2.0+
            if (major >= 5 and minor >= 2) or (major == 4 and minor >= 6 and patch >= 8):
                _LOGGER.info(f"✓ Panel version {version} is supported")
                return version
            else:
                _LOGGER.warning(
                    f"Panel version {version} may have limited feature support. "
                    f"Recommended: 4.6.8+ or 5.2.0+"
                )
                return version
        else:
            _LOGGER.warning("Could not determine panel version")
            return None
            
    except (OSError, TimeoutError, ValueError, AttributeError) as err:
        _LOGGER.error(f"Error checking panel version: {err}")
        return None


async def read_global_setting(elk_connection, setting_number: int) -> int | None:
    """
    Read a global setting from the panel.
    
    Args:
        elk_connection: ElkM1Connection instance
        setting_number: Global setting number (1-64)
        
    Returns:
        Setting value (0 or 1) or None if read failed
    """
    try:
        # Use GS command to read global setting
        # This is a serial protocol command
        value = await elk_connection.get_setting(setting_number)
        return value
        
    except (OSError, TimeoutError, ValueError, AttributeError) as err:
        _LOGGER.error(f"Error reading global setting {setting_number}: {err}")
        return None


async def write_global_setting(
    elk_connection, setting_number: int, value: int
) -> bool:
    """
    Write a global setting to the panel.
    
    Args:
        elk_connection: ElkM1Connection instance
        setting_number: Global setting number (1-64)
        value: Value to set (0 or 1)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Use GS command to write global setting
        await elk_connection.set_setting(setting_number, value)
        _LOGGER.info(f"Set global setting {setting_number} to {value}")
        return True
        
    except (OSError, TimeoutError, ValueError, AttributeError) as err:
        _LOGGER.error(f"Error writing global setting {setting_number}: {err}")
        return False


async def check_required_settings(elk_connection) -> dict[int, dict]:
    """
    Check all required global settings.
    
    Args:
        elk_connection: ElkM1Connection instance
        
    Returns:
        dictionary with setting status:
        {
            35: {"name": "Transmit Event Log", "enabled": True},
            36: {"name": "Transmit Zone Changes", "enabled": False},
            ...
        }
    """
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


async def enable_required_settings(elk_connection) -> dict[int, bool]:
    """
    Enable all required global settings.
    
    Checks each setting and enables it if not already enabled.
    
    Args:
        elk_connection: ElkM1Connection instance
        
    Returns:
        dictionary with results:
        {
            35: True,  # Successfully set
            36: False, # Failed to set
            ...
        }
    """
    results = {}
    
    _LOGGER.info("Attempting to enable required global settings...")
    
    for setting_num, setting_name in REQUIRED_SETTINGS.items():
        # Check current value
        current_value = await read_global_setting(elk_connection, setting_num)
        
        if current_value == 1:
            _LOGGER.info(f"Setting {setting_num} ({setting_name}) is already enabled")
            results[setting_num] = True
        elif current_value == 0:
            # Try to enable it
            _LOGGER.info(f"Enabling setting {setting_num} ({setting_name})...")
            success = await write_global_setting(elk_connection, setting_num, 1)
            results[setting_num] = success
        else:
            _LOGGER.error(f"Could not read setting {setting_num}")
            results[setting_num] = False
    
    return results


# Optional, but good practice: update the return hint to match the dictionary type
async def verify_panel_configuration(elk_connection) -> tuple[bool, dict[str, Any]]:
    """
    Verify panel is properly configured for Home Assistant.
    
    Args:
        elk_connection: ElkM1Connection instance
        
    Returns:
        tuple of (is_configured: bool, details: dict)
    """
    _LOGGER.info("Verifying ELK-M1 panel configuration...")
    
    # FIX: explicitly tell mypy this dictionary can hold anything
    details: dict[str, Any] = {}
    
    # Check version
    version = await check_panel_version(elk_connection)
    details["version"] = version
    
    # Check settings
    settings_status = await check_required_settings(elk_connection)
    details["settings"] = settings_status
    
    # Determine if all required settings are enabled
    all_enabled = all(
        status["enabled"] is True 
        for status in settings_status.values()
    )
    
    if all_enabled:
        _LOGGER.info("✓ Panel is properly configured")
        details["configured"] = True
    else:
        disabled_settings = [
            f"{num} ({status['name']})"
            for num, status in settings_status.items()
            if status["enabled"] is False
        ]
        _LOGGER.warning(
            f"Panel is not fully configured. Disabled settings: {', '.join(disabled_settings)}"
        )
        details["configured"] = False
        details["disabled_settings"] = disabled_settings
    
    return all_enabled, details

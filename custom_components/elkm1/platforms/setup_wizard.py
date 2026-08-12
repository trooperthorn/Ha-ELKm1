"""Setup wizard to check and configure panel on first connection."""

import logging
from typing import Dict
from .panel_settings import (
    check_panel_version,
    check_required_settings,
    enable_required_settings,
    verify_panel_configuration,
)

_LOGGER = logging.getLogger(__name__)


async def run_panel_setup_wizard(elk_connection, connection_type: str) -> Dict:
    """
    Run setup wizard to check and optionally configure panel.
    
    Args:
        elk_connection: ElkM1Connection instance
        connection_type: "serial" or "network"
        
    Returns:
        Setup results dictionary
    """
    results = {
        "version": None,
        "settings_checked": False,
        "settings_enabled": False,
        "details": {},
    }
    
    _LOGGER.info("Running ELK-M1 panel setup wizard...")
    
    # Check version
    version = await check_panel_version(elk_connection)
    results["version"] = version
    
    # Only check settings for serial connections
    if connection_type == "serial":
        _LOGGER.info("Serial connection - checking global settings...")
        
        # Check current settings
        settings = await check_required_settings(elk_connection)
        results["settings_checked"] = True
        results["details"]["initial_settings"] = settings
        
        # Check if all are enabled
        all_enabled = all(s["enabled"] for s in settings.values())
        
        if not all_enabled:
            _LOGGER.info("Some settings are disabled. Attempting to enable...")
            enable_results = await enable_required_settings(elk_connection)
            results["settings_enabled"] = all(enable_results.values())
            results["details"]["enable_results"] = enable_results
            
            # Re-check settings
            settings = await check_required_settings(elk_connection)
            results["details"]["final_settings"] = settings
    
    return results

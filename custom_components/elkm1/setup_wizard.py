"""Setup wizard to check and configure panel on first connection."""

from __future__ import annotations

import logging
from typing import Any

from elkm1_lib import Elk

from .const import CONNECTION_SERIAL
from .helpers import (
    check_panel_version,
    check_required_settings,
    enable_required_settings,
)

_LOGGER = logging.getLogger(__name__)


async def run_panel_setup_wizard(
    elk_connection: Elk, connection_type: str
) -> dict[str, Any]:
    """Run setup wizard to check and optionally configure panel.

    Args:
        elk_connection: Elk instance
        connection_type: "serial" or "network"

    Returns:
        Setup results dictionary
    """
    results: dict[str, Any] = {
        "version": None,
        "settings_checked": False,
        "settings_enabled": False,
        "details": {},
    }

    _LOGGER.info("Running ELK-M1 panel setup wizard...")

    try:
        # Check panel firmware version
        version = await check_panel_version(elk_connection)
        results["version"] = version

        # Global settings inspection is only applicable for direct serial/USB connections
        if connection_type in (CONNECTION_SERIAL, "serial"):
            _LOGGER.info("Serial connection detected - checking global settings...")

            settings = await check_required_settings(elk_connection)
            results["settings_checked"] = True
            results["details"]["initial_settings"] = settings

            # Check if all required settings are currently enabled
            all_enabled = all(s.get("enabled") is True for s in settings.values())

            if all_enabled:
                _LOGGER.info("All required global settings are already enabled ✓")
                results["settings_enabled"] = True
            else:
                _LOGGER.info("Some settings are disabled. Attempting to enable...")
                enable_results = await enable_required_settings(elk_connection)
                results["details"]["enable_results"] = enable_results

                # Re-verify settings after write
                final_settings = await check_required_settings(elk_connection)
                results["details"]["final_settings"] = final_settings
                results["settings_enabled"] = all(
                    s.get("enabled") is True for s in final_settings.values()
                )

    except Exception as err:  # noqa: BLE001
        _LOGGER.error(f"Error encountered during ELK-M1 setup wizard: {err}")
        results["details"]["error"] = str(err)

    return results

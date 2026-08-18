"""Parse and handle system trouble status from ELK-M1."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Map trouble codes to friendly names
TROUBLE_STATUSES = {
    0: "AC Fail",
    1: "Box Tamper",
    2: "Fail To Communicate",
    3: "EEProm Memory Error",
    4: "Low Battery Control",
    5: "Transmitter Low Battery",
    6: "Over Current",
    7: "Telephone Fault",
    8: "Output 2",
    9: "Missing Keypad",
    10: "Zone Expander",
    11: "Output Expander",
    12: "ELKRP Remote Access",
    13: "Common Area Not Armed",
    14: "Flash Memory Error",
    15: "Security Alert",
    16: "Serial Port Expander",
    17: "Lost Transmitter",
    18: "GE Smoke CleanMe",
    19: "Ethernet",
    20: "Display Message In Keypad Line 1",
    21: "Display Message In Keypad Line 2",
    22: "Fire",
}

# Troubles that include zone numbers
ZONE_TROUBLES = {
    "Box Tamper",
    "Transmitter Low Battery",
    "Security Alert",
    "Lost Transmitter",
    "Fire",
}


def parse_trouble_status(panel_object: Any) -> list[str]:
    """Parse trouble status from panel object.

    Args:
        panel_object: Panel object from elkm1_lib

    Returns:
        List of active trouble status strings

    Example:
        ["AC Fail", "Lost Transmitter zone 5"]
    """
    troubles: list[str] = []

    try:
        if not panel_object or not hasattr(panel_object, "trouble_status"):
            return []

        trouble_data = panel_object.trouble_status
        if trouble_data is None:
            return []

        # Handle dictionary payloads
        if isinstance(trouble_data, dict):
            for code, is_active in trouble_data.items():
                if is_active:
                    try:
                        code_int = int(code)
                        trouble_name = TROUBLE_STATUSES.get(code_int, f"Unknown ({code})")
                    except (ValueError, TypeError):
                        trouble_name = str(code)
                    troubles.append(trouble_name)

        # Handle integer bitmask or numeric string representation
        elif isinstance(trouble_data, (int, str)):
            try:
                bitmask = int(trouble_data)
                for bit in range(32):
                    if bitmask & (1 << bit):
                        trouble_name = TROUBLE_STATUSES.get(bit, f"Unknown ({bit})")
                        troubles.append(trouble_name)
            except (ValueError, TypeError):
                pass

        # Handle list, tuple, or set of active codes
        elif isinstance(trouble_data, (list, tuple, set)):
            for code in trouble_data:
                try:
                    code_int = int(code)
                    trouble_name = TROUBLE_STATUSES.get(code_int, f"Unknown ({code})")
                    troubles.append(trouble_name)
                except (ValueError, TypeError):
                    troubles.append(str(code))

        return troubles

    except (AttributeError, KeyError, TypeError) as err:
        _LOGGER.error(f"Error parsing trouble status: {err}")
        return []


def get_trouble_status_string(panel_object: Any) -> str:
    """Get formatted trouble status string for display.

    Args:
        panel_object: Panel object from elkm1_lib

    Returns:
        Comma-separated string of active troubles
    """
    troubles = parse_trouble_status(panel_object)

    if not troubles:
        return "No troubles"

    return ", ".join(troubles)


def has_troubles(panel_object: Any) -> bool:
    """Check if any troubles are active."""
    return len(parse_trouble_status(panel_object)) > 0


def get_critical_troubles(panel_object: Any) -> list[str]:
    """Get only critical trouble statuses."""
    critical = {"AC Fail", "Box Tamper", "Fire", "Security Alert"}
    troubles = parse_trouble_status(panel_object)
    return [t for t in troubles if any(c in t for c in critical)]

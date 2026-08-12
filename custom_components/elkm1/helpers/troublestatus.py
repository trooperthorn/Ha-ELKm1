"""Parse and handle system trouble status from ELK-M1."""

import logging

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


def parse_trouble_status(panel_object) -> list[str]:
    """
    Parse trouble status from panel object.
    
    Args:
        panel_object: Panel object from elkm1_lib
        
    Returns:
        List of active trouble status strings
        
    Example:
        ["AC Fail", "Lost Transmitter zone 5"]
    """
    troubles = []
    
    try:
        # Get trouble status from panel
        # This depends on elkm1_lib implementation
        if hasattr(panel_object, 'trouble_status'):
            trouble_data = panel_object.trouble_status
        else:
            return []
        
        # Parse each trouble bit/value
        if isinstance(trouble_data, dict):
            # If trouble_status is a dict with codes
            for code, is_active in trouble_data.items():
                if is_active:
                    trouble_name = TROUBLE_STATUSES.get(code, f"Unknown ({code})")
                    troubles.append(trouble_name)
        elif isinstance(trouble_data, (int, list)):
            # If it's a bitmask or list of active codes
            if isinstance(trouble_data, int):
                # Parse as bitmask
                for bit in range(32):
                    if trouble_data & (1 << bit):
                        trouble_name = TROUBLE_STATUSES.get(bit, f"Unknown ({bit})")
                        troubles.append(trouble_name)
            else:
                # Parse as list of codes
                for code in trouble_data:
                    trouble_name = TROUBLE_STATUSES.get(code, f"Unknown ({code})")
                    troubles.append(trouble_name)
        
        return troubles
        
    except (AttributeError, KeyError, TypeError) as err:
        _LOGGER.error(f"Error parsing trouble status: {err}")
        return []


def get_trouble_status_string(panel_object) -> str:
    """
    Get formatted trouble status string for display.
    
    Args:
        panel_object: Panel object from elkm1_lib
        
    Returns:
        Comma-separated string of active troubles
        e.g., "AC Fail, Lost Transmitter zone 42"
    """
    troubles = parse_trouble_status(panel_object)
    
    if not troubles:
        return "No troubles"
    
    return ", ".join(troubles)


def has_troubles(panel_object) -> bool:
    """Check if any troubles are active."""
    troubles = parse_trouble_status(panel_object)
    return len(troubles) > 0


def get_critical_troubles(panel_object) -> list[str]:
    """Get only critical trouble statuses."""
    critical = {"AC Fail", "Box Tamper", "Fire", "Security Alert"}
    
    troubles = parse_trouble_status(panel_object)
    return [t for t in troubles if any(c in t for c in critical)]

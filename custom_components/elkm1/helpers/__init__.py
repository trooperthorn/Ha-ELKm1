"""Helpers for Elk-M1 integration."""
# Usually empty - just marks this as a package
# Optionally, you could add convenience imports:
# from .usb_discovery import discover_elk_ports
# from .serial_queue import ElkSerialQueue
from .usb_discovery import discover_elk_ports, probe_serial_port
from .serial_queue import ElkSerialQueue

__all__ = ["discover_elk_ports", "probe_serial_port", "ElkSerialQueue"]

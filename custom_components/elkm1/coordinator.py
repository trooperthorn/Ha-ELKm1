"""Data update coordinator for Elk-M1 Control integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from elkm1_lib import Elk
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PIN,
    CONF_PORT,
    CONF_SERIAL_PORT,
    CONF_USERNAME,
    CONNECTION_NETWORK,
    CONNECTION_SERIAL,
    COORDINATOR_UPDATE_INTERVAL,
)
from .helpers.serial_queue import ElkSerialQueue
from .vocabulary import translate_elk_voice

_LOGGER = logging.getLogger(__name__)


class ElkDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Custom coordinator for Elk-M1 panel data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry_data: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Elk-M1 Control",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )

        self._config_data = config_entry_data
        self._elk: Elk | None = None
        self.serial_queue: ElkSerialQueue | None = None
        self._connection_type: str = config_entry_data[CONF_CONNECTION_TYPE]
        self._pin: str = str(config_entry_data.get(CONF_PIN, ""))

        # Build connection URL based on connection type
        self._url = self._build_connection_url()

        # Internal state dictionary cache
        self.data = {
            "num_areas": 1,
            "areas": {},
            "zones": [],
            "outputs": [],
            "tasks": [],
            "thermostats": [],
            "armed": False,
            "armed_mode": "disarmed",
            "last_user": None,
            "last_user_name": "Unknown",
            "last_keypad": None,
            "zones_faulted": [],
            "faulted_zone_names": [],
            "outputs_active": [],
            "active_output_names": [],
            "trouble_status": False,
            "ac_power": True,
            "battery_status": "Good",
            "panel_temperature": None,
            "fire_alarm_active": False,
            "bypassed_zones": [],
        }

        _LOGGER.info(
            "ElkDataUpdateCoordinator initialized: type=%s, url=%s",
            self._connection_type,
            self._obfuscated_url(),
        )

    def _build_connection_url(self) -> str:
        """Build connection URL based on connection type."""
        if self._connection_type == CONNECTION_SERIAL:
            serial_port = self._config_data.get(CONF_SERIAL_PORT)
            if not serial_port:
                raise ValueError("Serial port not configured")
            return f"serial://{serial_port}"

        if self._connection_type == CONNECTION_NETWORK:
            host = self._config_data.get(CONF_HOST)
            port = self._config_data.get(CONF_PORT, 2101)
            if not host:
                raise ValueError("Host not configured")
            return f"elk://{host}:{port}"

        raise ValueError(f"Unknown connection type: {self._connection_type}")

    def _obfuscated_url(self) -> str:
        """Return connection URL with sensitive data obfuscated for logging."""
        if self._connection_type == CONNECTION_SERIAL:
            return self._url
        host = self._config_data.get(CONF_HOST)
        port = self._config_data.get(CONF_PORT, 2101)
        return f"elk://{host}:{port}"

    def _get_enum_value(self, obj: Any, default: int = 0) -> int:
        """Safely extract integer value from enum or string objects."""
        if hasattr(obj, "value"):
            return int(obj.value)
        if isinstance(obj, str):
            return int(obj) if obj.isdigit() else default
        return int(obj) if isinstance(obj, (int, float)) else default

    async def async_connect(self) -> None:
        """Establish connection to ELK-M1 panel."""
        from .helpers.panel_settings import (
            check_panel_version,
            verify_panel_configuration,
        )

        try:
            _LOGGER.info("Connecting to ELK-M1 at %s", self._obfuscated_url())
            await asyncio.sleep(2.0)

            config = {"url": self._url}
            if self._connection_type == CONNECTION_NETWORK:
                if username := self._config_data.get(CONF_USERNAME, ""):
                    config["userid"] = username
                if password := self._config_data.get(CONF_PASSWORD, ""):
                    config["password"] = password

            self._elk = Elk(config)

            # Initialize serial queue worker if connection is serial/USB
            self.serial_queue = ElkSerialQueue(self._elk, interval=0.1)
            self.hass.async_create_background_task(
                self.serial_queue.start(), "elkm1_serial_queue_worker"
            )

            # Safe voice callback registration
            if (
                hasattr(self._elk, "panel")
                and self._elk.panel is not None
                and hasattr(self._elk.panel, "add_callback")
            ):
                try:
                    self._elk.panel.add_callback(self._handle_voice_message)
                except TypeError:
                    _LOGGER.debug("Panel add_callback using raw VN parser fallback.")

            # Real-time message interceptor
            self._elk.add_handler("unknown", self._elk_broadcast_handler)

            connected_event = asyncio.Event()

            def on_connected(*args: Any, **kwargs: Any) -> None:
                connected_event.set()

            self._elk.add_handler("connected", on_connected)

            if self._connection_type == CONNECTION_SERIAL:
                await asyncio.sleep(1.0)

            self._elk.connect()
            await asyncio.wait_for(connected_event.wait(), timeout=10.0)
            await asyncio.sleep(1.5)

            _LOGGER.info("Connected to ELK-M1 at %s", self._obfuscated_url())
            await check_panel_version(self)

            if self._connection_type == CONNECTION_SERIAL:
                _LOGGER.info("Serial connection detected - checking panel settings...")
                configured, details = await verify_panel_configuration(self)
                if not configured:
                    for setting_num, status in details["settings"].items():
                        if status["enabled"] is False:
                            _LOGGER.warning(
                                "  - Global Setting %s (%s) is disabled",
                                setting_num,
                                status["name"],
                            )

        except (OSError, TimeoutError, ValueError, asyncio.TimeoutError) as err:
            _LOGGER.error("Failed to connect to ELK-M1: %s", err)
            if self.serial_queue:
                await self.serial_queue.stop()
            raise UpdateFailed(f"Connection failed: {err}") from err

    def _elk_broadcast_handler(self, msg: Any) -> None:
        """Intercept ASCII broadcasts and update internal state in real-time."""
        raw_str = msg.get("raw", "") if isinstance(msg, dict) else str(msg)
        if len(raw_str) < 4:
            return

        cmd = raw_str[2:4]

        # 1. Arm Status Report (AS)
        if cmd == "AS" and len(raw_str) >= 28:
            try:
                for idx in range(8):
                    armed_status = int(raw_str[4 + idx])
                    arm_up_state = int(raw_str[12 + idx])
                    alarm_state = int(raw_str[20 + idx])

                    if idx not in self.data["areas"]:
                        self.data["areas"][idx] = {}

                    self.data["areas"][idx].update(
                        {
                            "armed_status": armed_status,
                            "arm_up_state": arm_up_state,
                            "alarm_state": alarm_state,
                        }
                    )
                self.async_set_updated_data(self._build_normalized_data())
            except (ValueError, IndexError) as err:
                _LOGGER.debug("Error parsing AS broadcast: %s", err)

        # 2. Entry / Exit Timer Event (EE)
        elif cmd == "EE" and len(raw_str) >= 13:
            try:
                area_idx = int(raw_str[4:5]) - 1
                is_exit = raw_str[5:6] == "0"
                t1 = int(raw_str[6:9])
                t2 = int(raw_str[9:12])
                armed_state = int(raw_str[12:13])

                if area_idx not in self.data["areas"]:
                    self.data["areas"][area_idx] = {}

                self.data["areas"][area_idx].update(
                    {
                        "timer1": t1,
                        "timer2": t2,
                        "exit_delay_active": is_exit and (t1 > 0 or t2 > 0),
                        "entry_delay_active": not is_exit and (t1 > 0 or t2 > 0),
                        "armed_status": armed_state,
                    }
                )

                self.hass.bus.async_fire(
                    "elkm1_timer_event",
                    {
                        "area": area_idx + 1,
                        "type": "exit" if is_exit else "entry",
                        "timer1": t1,
                        "timer2": t2,
                        "armed_state": armed_state,
                    },
                )
                self.async_set_updated_data(self._build_normalized_data())
            except (ValueError, IndexError) as err:
                _LOGGER.debug("Error parsing EE broadcast: %s", err)

        # 3. Alarm Memory Event (AM)
        elif cmd == "AM" and len(raw_str) >= 12:
            self.hass.bus.async_fire("elkm1_alarm_memory", {"flags": raw_str[4:12]})

        # 4. Version Number (VN) or Voice Announcement (VN)
        elif cmd == "VN":
            # The official Version Number reply is exactly 54 bytes long (length 36)
            if len(raw_str) >= 54:
                try:
                    # Elk returns version in ASCII Hex: UUMMLL (Major, Minor, Patch)
                    major = int(raw_str[4:6], 16)
                    minor = int(raw_str[6:8], 16)
                    patch = int(raw_str[8:10], 16)
                    
                    version_str = f"{major}.{minor}.{patch}"
                    self.data["panel_version"] = version_str
                    self.async_set_updated_data(self._build_normalized_data())
                    _LOGGER.info("Successfully parsed Elk-M1 Version: %s", version_str)
                except ValueError:
                    _LOGGER.debug("Error parsing VN version broadcast")
            
            # Fallback for voice announcement intercepts
            elif len(raw_str) >= 22:
                try:
                    word_str = raw_str[4:22]
                    words = [int(word_str[i : i + 3]) for i in range(0, 18, 3)]
                    self._handle_voice_message(words)
                except ValueError:
                    pass

    async def async_disconnect(self) -> None:
        """Disconnect from ELK-M1 panel and stop queue worker."""
        if self.serial_queue:
            await self.serial_queue.stop()
            self.serial_queue = None

        if self._elk:
            try:
                self._elk.disconnect()
                _LOGGER.info("Disconnected from ELK-M1")
            except (OSError, AttributeError) as err:
                _LOGGER.error("Error disconnecting: %s", err)
            finally:
                self._elk = None

    def _build_normalized_data(self) -> dict[str, Any]:
        """Convert underlying library objects into normalized state dictionary."""
        if not self._elk:
            return self.data

        zones = getattr(self._elk, "zones", [])
        panel = getattr(self._elk, "panel", None)
        areas = getattr(self._elk, "areas", [])
        outputs = getattr(self._elk, "outputs", [])
        tasks = getattr(self._elk, "tasks", [])
        thermostats = getattr(
            self._elk, "thermostats", getattr(self._elk, "thermostat", [])
        )

        num_areas = len(areas) if areas else 1
        areas_dict: dict[int, dict[str, Any]] = self.data.get("areas", {})

        for i, area in enumerate(areas):
            if not area:
                continue
            if i not in areas_dict:
                areas_dict[i] = {}

            alarm_val = self._get_enum_value(getattr(area, "alarm_state", 0))
            armed_val = self._get_enum_value(getattr(area, "armed_status", 0))
            armup_val = self._get_enum_value(getattr(area, "arm_up_state", 0))
            t1 = getattr(area, "timer1", 0)
            t2 = getattr(area, "timer2", 0)

            areas_dict[i].update(
                {
                    "alarm_state": alarm_val,
                    "armed_status": armed_val,
                    "arm_up_state": armup_val,
                    "timer1": t1,
                    "timer2": t2,
                    "entry_delay_active": getattr(area, "entry_delay_active", False) or (t1 > 0 and armed_val != 0),
                    "exit_delay_active": getattr(area, "exit_delay_active", False) or (t2 > 0),
                    "entry_delay": getattr(area, "entry_delay", 0),
                    "exit_delay": getattr(area, "exit_delay", 0),
                    "panic_state": getattr(area, "panic_state", False),
                    "alarm_memory": getattr(area, "alarm_memory", False),
                }
            )

        # Faulted zones
        faulted_indices: list[int] = []
        faulted_names: list[str] = []
        bypassed_names: list[str] = []
        fire_alarm = False

        for i, zone in enumerate(zones):
            if not zone:
                continue
            logical = self._get_enum_value(getattr(zone, "logical_status", 0))
            physical = self._get_enum_value(getattr(zone, "physical_status", 0))
            definition = self._get_enum_value(getattr(zone, "definition", 0))

            if logical == 2 or physical in (1, 3):
                faulted_indices.append(i)
                z_name = getattr(zone, "name", f"Zone {i + 1}")
                faulted_names.append(f"Zone {i + 1}: {z_name}")

            if getattr(zone, "bypassed", False):
                z_name = getattr(zone, "name", f"Zone {i + 1}")
                bypassed_names.append(f"Zone {i + 1}: {z_name}")

            if definition in (9, 10) and logical == 2:
                fire_alarm = True

        # Active outputs
        active_outputs: list[int] = []
        active_output_names: list[str] = []
        for i, output in enumerate(outputs):
            if output and getattr(output, "output_on", False):
                active_outputs.append(i)
                active_output_names.append(f"Output {i + 1}: {output.name}")

        # Primary Keypad Temperature
        panel_temp = None
        if hasattr(self._elk, "keypads"):
            for kp in self._elk.keypads:
                if kp and getattr(kp, "temperature", None) is not None:
                    panel_temp = kp.temperature
                    break

        is_any_armed = any(
            a.get("armed_status", 0) != 0 for a in areas_dict.values()
        )

        return {
            "panel_version": self.data.get("panel_version"),
            "num_areas": num_areas,
            "areas": areas_dict,
            "zones": zones,
            "panel": panel,
            "outputs": outputs,
            "tasks": tasks,
            "thermostats": thermostats,
            "armed": is_any_armed,
            "armed_mode": "armed" if is_any_armed else "disarmed",
            "last_user": getattr(panel, "last_user", None),
            "last_user_name": getattr(panel, "last_user_name", "Unknown"),
            "last_keypad": getattr(panel, "last_keypad", None),
            "zones_faulted": faulted_indices,
            "faulted_zone_names": faulted_names,
            "outputs_active": active_outputs,
            "active_output_names": active_output_names,
            "trouble_status": getattr(panel, "trouble_status", False) if panel else False,
            "ac_power": getattr(panel, "ac_power", True) if panel else True,
            "battery_status": getattr(panel, "battery_status", "Good") if panel else "Good",
            "panel_temperature": panel_temp,
            "fire_alarm_active": fire_alarm,
            "bypassed_zones": bypassed_names,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the ELK-M1 panel."""
        if not self._elk:
            raise UpdateFailed("Not connected to ELK-M1")
        try:
            return self._build_normalized_data()
        except Exception as err:
            _LOGGER.debug("Error fetching coordinator data: %s", err)
            raise UpdateFailed(f"Failed to fetch data: {err}") from err

    async def async_first_refresh(self) -> None:
        """Connect and do first data refresh."""
        try:
            await self.async_connect()
            await super().async_request_refresh()
        except Exception:
            await self.async_disconnect()
            raise

    # ---- STANDARDIZED ALARM CONTROL PANEL METHODS ----

    async def async_alarm_disarm(self, area_index: int, code: int = 0) -> bool:
        """Send disarm command for specific area."""
        return await self._execute_arm_cmd("0", area_index + 1, code)

    async def async_alarm_arm_away(self, area_index: int, code: int = 0) -> bool:
        """Send arm away command for specific area."""
        return await self._execute_arm_cmd("1", area_index + 1, code)

    async def async_alarm_arm_home(self, area_index: int, code: int = 0) -> bool:
        """Send arm stay command for specific area."""
        return await self._execute_arm_cmd("2", area_index + 1, code)

    async def async_alarm_arm_night(self, area_index: int, code: int = 0) -> bool:
        """Send arm night command for specific area."""
        return await self._execute_arm_cmd("4", area_index + 1, code)

    async def async_alarm_arm_vacation(self, area_index: int, code: int = 0) -> bool:
        """Send arm vacation command for specific area."""
        return await self._execute_arm_cmd("6", area_index + 1, code)

    async def async_alarm_arm_custom_bypass(self, area_index: int, code: int = 0) -> bool:
        """Send arm with bypass command for specific area."""
        return await self._execute_arm_cmd("1", area_index + 1, code)

    async def async_alarm_trigger(self, area_index: int, code: int = 0) -> bool:
        """Trigger panic alarm on the area."""
        return await self.panic_alarm(str(code) if code else None)

    async def _execute_arm_cmd(self, mode: str, area_num: int, code: int = 0) -> bool:
        """Construct and send raw arm/disarm ASCII string: a<mode><area><pin>."""
        active_pin = str(code) if code > 0 else self._pin
        formatted_pin = active_pin.zfill(6)
        command = f"a{mode}{area_num}{formatted_pin}"
        await self.send_raw_elk_command(command)
        await self.async_request_refresh()
        return True

    # ---- ADDITIONAL HARDWARE METHODS ----

    async def bypass_zone(self, zone_number: int, pin_code: str | None = None) -> bool:
        """Bypass a zone."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            await self.send_raw_elk_command(f"zb{zone_number:03d}{formatted_pin}")
            await self.async_request_refresh()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to bypass zone %s: %s", zone_number, err)
            return False

    async def unbypass_zone(self, zone_number: int, pin_code: str | None = None) -> bool:
        """Unbypass a zone."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            await self.send_raw_elk_command(f"zu{zone_number:03d}{formatted_pin}")
            await self.async_request_refresh()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to unbypass zone %s: %s", zone_number, err)
            return False

    async def panic_alarm(self, pin_code: str | None = None) -> bool:
        """Trigger panic alarm."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            await self.send_raw_elk_command(f"ap1{formatted_pin}")
            await self.async_request_refresh()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to trigger panic: %s", err)
            return False

    async def send_raw_elk_command(self, command: str) -> None:
        """Format and send a raw ASCII command to the Elk-M1 panel via queue."""
        if not self._elk:
            _LOGGER.error("Cannot send raw command: Elk instance not found.")
            return

        payload = f"{command}00"
        length = len(payload) + 2
        packet = f"{length:02X}{payload}"

        checksum = sum(ord(c) for c in packet) % 256
        checksum = (checksum ^ 0xFF) + 1

        final_string = f"{packet}{checksum & 0xFF:02X}"
        packet_with_crlf = f"{final_string}\r\n"

        if self.serial_queue:
            try:
                await self.serial_queue.async_send_command(
                    "send_raw_command", raw_data=packet_with_crlf
                )
                _LOGGER.debug("Sent Elk command via SerialQueue: %s", packet_with_crlf.strip())
                return
            except Exception as queue_err:  # noqa: BLE001
                _LOGGER.debug("SerialQueue dispatch fallback: %s", queue_err)

        try:
            conn = getattr(self._elk, "_connection", None)
            if not conn:
                return

            writer = getattr(conn, "_writer", None)
            if writer and hasattr(writer, "write"):
                writer.write(packet_with_crlf.encode("ascii"))
                if hasattr(writer, "drain"):
                    await writer.drain()
                return

            if hasattr(conn, "write_data"):
                conn.write_data(final_string)
                return

            transport = getattr(conn, "transport", getattr(conn, "_transport", None))
            if transport and hasattr(transport, "write"):
                transport.write(packet_with_crlf.encode("ascii"))
                return

            _LOGGER.error("Cannot send command: No valid stream writer found.")
        except Exception as e:  # noqa: BLE001
            _LOGGER.debug("Failed to send raw Elk command: %s", e)

    def _handle_voice_message(self, *args: Any, **kwargs: Any) -> None:
        """Process incoming voice command arrays and fire a Home Assistant event."""
        try:
            words = None
            if args:
                words = args[0] if len(args) == 1 else args[-1]
            elif "words" in kwargs:
                words = kwargs["words"]
            elif "changeset" in kwargs:
                words = kwargs["changeset"]

            if not isinstance(words, (list, tuple)):
                return

            word_ints = [int(w) for w in words]
            readable_message = translate_elk_voice(word_ints)

            if readable_message:
                _LOGGER.info(
                    "Elk-M1 Voice Translated: '%s' (Raw IDs: %s)",
                    readable_message,
                    word_ints,
                )
                self.hass.bus.async_fire(
                    "elkm1_voice_announcement",
                    {
                        "source": "elk_m1",
                        "raw_ids": word_ints,
                        "message": readable_message,
                    },
                )
        except Exception:
            _LOGGER.exception("Failed to translate and fire Elk voice message")

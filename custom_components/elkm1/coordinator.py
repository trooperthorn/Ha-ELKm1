"""Data update coordinator for Elk-M1 Control integration."""

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
from .vocabulary import translate_elk_voice

_LOGGER = logging.getLogger(__name__)


class ElkDataUpdateCoordinator(DataUpdateCoordinator):
    """Custom coordinator for Elk-M1 panel data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry_data: dict[str, Any],
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            config_entry_data: Configuration entry data dictionary
        """
        super().__init__(
            hass,
            _LOGGER,
            name="Elk-M1 Control",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )

        self._config_data = config_entry_data
        self._elk: Elk | None = None
        self._connection_type: str = config_entry_data[CONF_CONNECTION_TYPE]
        self._pin = config_entry_data.get(CONF_PIN, "")

        # Build connection URL based on connection type
        self._url = self._build_connection_url()

        _LOGGER.info(
            f"ElkDataUpdateCoordinator initialized: "
            f"type={self._connection_type}, url={self._obfuscated_url()}"
        )

    def _build_connection_url(self) -> str:
        """Build connection URL based on connection type.

        Returns:
            Connection URL for Elk
            - Serial: "serial:///dev/serial/by-id/...?baud=115200"
            - Network: "elk://192.168.1.100:2101"
        """
        if self._connection_type == CONNECTION_SERIAL:
            serial_port = self._config_data.get(CONF_SERIAL_PORT)
            if not serial_port:
                raise ValueError("Serial port not configured")

            url = f"serial://{serial_port}"
            _LOGGER.debug(f"Built serial URL: {url}")
            return url

        if self._connection_type == CONNECTION_NETWORK:
            host = self._config_data.get(CONF_HOST)
            port = self._config_data.get(CONF_PORT, 2101)

            if not host:
                raise ValueError("Host not configured")

            url = f"elk://{host}:{port}"
            _LOGGER.debug(f"Built network URL: {url}")
            return url

        raise ValueError(f"Unknown connection type: {self._connection_type}")

    def _obfuscated_url(self) -> str:
        """Return connection URL with sensitive data obfuscated for logging."""
        if self._connection_type == CONNECTION_SERIAL:
            return self._url

        host = self._config_data.get(CONF_HOST)
        port = self._config_data.get(CONF_PORT, 2101)
        return f"elk://{host}:{port}"

    async def async_connect(self) -> None:
        """Establish connection to ELK-M1 panel."""
        import asyncio

        from .helpers.panel_settings import (
            check_panel_version,
            verify_panel_configuration,
        )

        try:
            _LOGGER.info(f"Connecting to ELK-M1 at {self._obfuscated_url()}")

            # Give the OS/USB subsystem a brief moment to release handles
            # left over from usb_discovery probing.
            await asyncio.sleep(5.0)

            # Create the config dictionary
            config = {"url": self._url}

            if self._connection_type == CONNECTION_NETWORK:
                if username := self._config_data.get(CONF_USERNAME, ""):
                    config["userid"] = username
                if password := self._config_data.get(CONF_PASSWORD, ""):
                    config["password"] = password

            # Initialize Elk with the dictionary
            self._elk = Elk(config)

            # Safe callback registration
            if (
                hasattr(self._elk, "panel")
                and self._elk.panel is not None
                and hasattr(self._elk.panel, "add_callback")
            ):
                try:
                    self._elk.panel.add_callback(self._handle_voice_message)
                except TypeError:
                    _LOGGER.debug(
                        "Panel add_callback expects 2 arguments; relying on raw VN parser."
                    )

            # --- PHASE 1: REAL-TIME BROADCAST INTERCEPTOR ---
            def elk_broadcast_handler(msg: Any) -> None:
                """Intercept broadcasts not fully mapped by elkm1_lib."""
                raw_str = (
                    msg.get("raw", "") if isinstance(msg, dict) else str(msg)
                )
                if len(raw_str) < 4:
                    return

                cmd = raw_str[2:4]

                # Entry/Exit Timer (EE)
                if cmd == "EE":
                    self.hass.bus.async_fire(
                        "elkm1_timer_event",
                        {
                            "area": int(raw_str[4:5]),
                            "type": "exit" if raw_str[5:6] == "0" else "entry",
                            "timer1": int(raw_str[6:9]),
                            "timer2": int(raw_str[9:12]),
                            "armed_state": int(raw_str[12:13]),
                        },
                    )

                # Alarm Memory (AM)
                elif cmd == "AM":
                    self.hass.bus.async_fire(
                        "elkm1_alarm_memory", {"flags": raw_str[4:12]}
                    )

                # Raw ASCII fallback for Voice (VN) commands
                elif cmd == "VN":
                    try:
                        word_str = raw_str[4:22]
                        words = [
                            int(word_str[i : i + 3]) for i in range(0, 18, 3)
                        ]
                        self._handle_voice_message(words)
                    except ValueError:
                        pass

            # Hook into elkm1_lib's fallback handler to catch unrecognized data strings
            self._elk.add_handler("unknown", elk_broadcast_handler)

            # 1. Create the event tracker to monitor connection state
            connected_event = asyncio.Event()

            def on_connected(*args: Any, **kwargs: Any) -> None:
                connected_event.set()

            self._elk.add_handler("connected", on_connected)

            # Release buffer for serial descriptors
            if self._connection_type == CONNECTION_SERIAL:
                await asyncio.sleep(2.0)

            # 2. Call connect synchronously
            self._elk.connect()

            # 3. Wait for the event to trigger, up to a 10 second timeout
            await asyncio.wait_for(connected_event.wait(), timeout=10.0)

            # 4. Wait a brief moment for the initial sync data to populate
            await asyncio.sleep(1.5)

            _LOGGER.info(f"Connected to ELK-M1 at {self._obfuscated_url()}")

            await check_panel_version(self._elk)

            if self._connection_type == CONNECTION_SERIAL:
                _LOGGER.info(
                    "Serial connection detected - checking panel settings..."
                )
                configured, details = await verify_panel_configuration(
                    self._elk
                )
                if not configured:
                    for setting_num, status in details["settings"].items():
                        if status["enabled"] is False:
                            _LOGGER.warning(
                                f"  - Global Setting {setting_num} "
                                f"({status['name']}) is disabled"
                            )

        except (OSError, TimeoutError, ValueError, asyncio.TimeoutError) as err:
            _LOGGER.error(f"Failed to connect to ELK-M1: {err}")
            raise UpdateFailed(f"Connection failed: {err}") from err

    async def async_disconnect(self) -> None:
        """Disconnect from ELK-M1 panel."""
        if self._elk:
            try:
                self._elk.disconnect()
                _LOGGER.info("Disconnected from ELK-M1")
            except (OSError, AttributeError) as err:
                _LOGGER.error(f"Error disconnecting: {err}")
            finally:
                self._elk = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the ELK-M1 panel.

        This is called periodically by the coordinator framework.

        Returns:
            dictionary with panel data:
            {
                "zones": {...},
                "panel": {...},
                "areas": {...},
                "outputs": {...},
                "tasks": {...},
                "thermostat": {...},
            }

        Raises:
            UpdateFailed: If data fetch fails
        """
        if not self._elk:
            raise UpdateFailed("Not connected to ELK-M1")

        try:
            zones = getattr(self._elk, "zones", [])
            panel = getattr(self._elk, "panel", None)
            areas = getattr(self._elk, "areas", [])
            outputs = getattr(self._elk, "outputs", [])
            tasks = getattr(self._elk, "tasks", [])
            thermostat = getattr(
                self._elk, "thermostats", getattr(self._elk, "thermostat", [])
            )

            return {
                "zones": zones,
                "panel": panel,
                "areas": areas,
                "outputs": outputs,
                "tasks": tasks,
                "thermostat": thermostat,
            }
        except Exception as err:
            _LOGGER.exception("Error fetching coordinator data")
            raise UpdateFailed(f"Failed to fetch data: {err}") from err

    async def async_first_refresh(self) -> None:
        """Connect and do first data refresh."""
        try:
            await self.async_connect()
            await super().async_request_refresh()
        except Exception:
            await self.async_disconnect()
            raise

    # ----ARMING---- Service Methods --------

    async def send_disarm(
        self, pin_code: str | None = None, area: int = 1
    ) -> bool:
        """Send disarm command to panel."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            _LOGGER.info(f"Sending disarm command to Area {area}")

            # 'a0' is the ASCII command for Disarm
            self.send_raw_elk_command(f"a0{area}{formatted_pin}")
            await self.async_request_refresh()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to disarm: {err}")
            return False

    async def send_arm_stay(
        self, pin_code: str | None = None, area: int = 1
    ) -> bool:
        """Send arm stay command to panel."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            _LOGGER.info(f"Sending arm stay command to Area {area}")

            # 'a2' is the ASCII command for Arm Stay
            self.send_raw_elk_command(f"a2{area}{formatted_pin}")
            await self.async_request_refresh()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to arm stay: {err}")
            return False

    async def send_arm_away(
        self, pin_code: str | None = None, area: int = 1
    ) -> bool:
        """Send arm away command to panel."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            _LOGGER.info(f"Sending arm away command to Area {area}")

            # 'a1' is the ASCII command for Arm Away
            self.send_raw_elk_command(f"a1{area}{formatted_pin}")
            await self.async_request_refresh()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to arm away: {err}")
            return False

    async def send_arm_night(
        self, pin_code: str | None = None, area: int = 1
    ) -> bool:
        """Send arm night command to panel."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            _LOGGER.info(f"Sending arm night command to Area {area}")

            # 'a4' is the ASCII command for Arm Night
            self.send_raw_elk_command(f"a4{area}{formatted_pin}")
            await self.async_request_refresh()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to arm night: {err}")
            return False

    # ------BYPASS-- Service Methods --------

    async def bypass_zone(
        self, zone_number: int, pin_code: str | None = None
    ) -> bool:
        """Bypass a zone."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            _LOGGER.info(f"Bypassing zone {zone_number}")
            await self._elk.bypass_zone(zone_number, pin=active_pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to bypass zone {zone_number}: {err}")
            return False

    async def unbypass_zone(
        self, zone_number: int, pin_code: str | None = None
    ) -> bool:
        """Unbypass a zone."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            _LOGGER.info(f"Unbypassing zone {zone_number}")
            await self._elk.unbypass_zone(zone_number, pin=active_pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to unbypass zone {zone_number}: {err}")
            return False

    async def panic_alarm(self, pin_code: str | None = None) -> bool:
        """Trigger panic alarm."""
        if not self._elk:
            return False
        try:
            active_pin = pin_code if pin_code is not None else self._pin
            _LOGGER.warning("Sending panic alarm command")
            await self._elk.panic(pin=active_pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to trigger panic: {err}")
            return False

    # --- Phase 2 Raw Commands ---
    async def force_arm_away(
        self, area: int, pin_code: str | None = None
    ) -> bool:
        """Force arm the system to away mode."""
        if not self._elk:
            return False
        try:
            _LOGGER.info(f"Force arming away area {area}")
            active_pin = pin_code if pin_code is not None else self._pin
            formatted_pin = str(active_pin).zfill(6)
            self.send_raw_elk_command(f"a9{area}{formatted_pin}")
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to force arm away area {area}: {err}")
            return False

    async def set_thermostat_temperature(
        self, thermostat_id: int, temperature: float
    ) -> bool:
        """Set thermostat temperature.

        Args:
            thermostat_id: Thermostat ID
            temperature: Temperature in degrees

        Returns:
            True if successful, False otherwise
        """
        if not self._elk:
            _LOGGER.error("Cannot set thermostat: not connected")
            return False

        try:
            _LOGGER.info(
                f"Setting thermostat {thermostat_id} to {temperature}°"
            )
            await self._elk.set_temperature(thermostat_id, temperature)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to set thermostat: {err}")
            return False

    async def activate_task(self, task_number: int) -> bool:
        """Activate a task.

        Args:
            task_number: Task number (1-32)

        Returns:
            True if successful, False otherwise
        """
        if not self._elk:
            _LOGGER.error("Cannot activate task: not connected")
            return False

        try:
            _LOGGER.info(f"Activating task {task_number}")
            await self._elk.activate_task(task_number)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to activate task {task_number}: {err}")
            return False

    def get_zone(self, zone_number: int) -> Any | None:
        """Get zone object by number.

        Args:
            zone_number: Zone number (1-208)

        Returns:
            Zone object or None if not found
        """
        if not self._elk or not self.data:
            return None

        try:
            zones = self.data.get("zones", [])
            for zone in zones:
                if zone.number == zone_number:
                    return zone
            return None
        except (AttributeError, KeyError) as err:
            _LOGGER.error(f"Error getting zone {zone_number}: {err}")
            return None

    def get_area(self, area_number: int) -> Any | None:
        """Get area object by number.

        Args:
            area_number: Area number (1-8)

        Returns:
            Area object or None if not found
        """
        if not self._elk or not self.data:
            return None

        try:
            areas = self.data.get("areas", [])
            for area in areas:
                if area.number == area_number:
                    return area
            return None
        except (AttributeError, KeyError) as err:
            _LOGGER.error(f"Error getting area {area_number}: {err}")
            return None

    def get_output(self, output_number: int) -> Any | None:
        """Get output object by number."""
        if not self._elk or not self.data:
            return None

        try:
            outputs = self.data.get("outputs", [])
            for output in outputs:
                if output.number == output_number:
                    return output
            return None
        except (AttributeError, KeyError) as err:
            _LOGGER.error(f"Error getting output {output_number}: {err}")
            return None

    @property
    def connected(self) -> bool:
        """Return True if connected to panel."""
        return self._elk is not None and self.last_update_success

    @property
    def connection_type(self) -> str:
        """Return connection type (serial or network)."""
        return self._connection_type

    def _handle_voice_message(self, *args: Any, **kwargs: Any) -> None:
        """Process incoming voice command arrays and fire a Home Assistant event."""
        _LOGGER.debug(f"Received voice callback: args={args}, kwargs={kwargs}")
        try:
            # elkm1_lib may pass (element, changes) positionally or via kwargs.
            # We isolate the actual data payload safely regardless of how it arrives.
            words = None
            
            if args:
                # If positional arguments exist, the last one is usually the payload/changeset
                words = args[0] if len(args) == 1 else args[-1]
            elif "words" in kwargs:
                words = kwargs["words"]
            elif "changeset" in kwargs:
                words = kwargs["changeset"]
                
            if not isinstance(words, (list, tuple)):
                return

            readable_message = translate_elk_voice(words)

            if readable_message:
                _LOGGER.info(
                    f"Elk-M1 Voice Message Translated: '{readable_message}' (Raw IDs: {words})"
                )
                self.hass.bus.async_fire(
                    "elkm1_voice_announcement",
                    {
                        "source": "elk_m1",
                        "raw_ids": words,
                        "message": readable_message,
                    },
                )
                _LOGGER.debug(f"Fired Elk voice event: {readable_message}")
        except Exception:
            _LOGGER.exception("Failed to translate and fire Elk voice message")

    # --- PHASE 2: CUSTOM RAW COMMAND SERVICES ---

    async def speak_phrase(self, phrase_number: int) -> bool:
        """Command the Elk-M1 panel to speak a vocabulary word/phrase."""
        if not self._elk:
            return False
        try:
            _LOGGER.info(f"Commanding Elk-M1 to speak phrase ID {phrase_number}")
            # 'sw' is the Elk ASCII command for Speak Word, followed by the 3-digit ID
            self.send_raw_elk_command(f"sw{phrase_number:03d}")
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to speak phrase {phrase_number}: {err}")
            return False

    def send_raw_elk_command(self, command: str) -> None:
        """Format and send a raw ASCII command to the Elk-M1 panel."""
        if not self._elk or not hasattr(self._elk, "_connection"):
            _LOGGER.error("Cannot send raw command: Elk connection not found.")
            return

        # Append the required '00' reserved bytes to the command
        payload = f"{command}00"
        length = len(payload) + 2
        packet = f"{length:02X}{payload}"

        # Calculate Checksum: Modulo 256, Two's Complement
        checksum = sum(ord(c) for c in packet) % 256
        checksum = (checksum ^ 0xFF) + 1

        # Combine packet and checksum. 
        # (write_data automatically appends the \r\n and encodes to bytes)
        final_string = f"{packet}{checksum & 0xFF:02X}"

        try:
            # Approach 1: Use the library's native write_data method if available
            if hasattr(self._elk._connection, "write_data"):
                self._elk._connection.write_data(final_string)
                _LOGGER.debug(f"Sent Elk command via write_data: {final_string}")
                return

            # Approach 2: Fallback to direct asyncio transport injection
            transport = getattr(self._elk._connection, "transport", None)
            if transport:
                packet_with_crlf = f"{final_string}\r\n"
                transport.write(packet_with_crlf.encode("ascii"))
                _LOGGER.debug(f"Sent Elk command via transport: {packet_with_crlf.strip()}")
            else:
                _LOGGER.error("Cannot send command: Neither write_data nor transport available.")

        except Exception as e:  # noqa: BLE001
            _LOGGER.error(f"Failed to send raw Elk command: {e}")

    async def trigger_zone(self, zone_number: int) -> bool:
        """Trigger a virtual zone violation."""
        if not self._elk:
            return False
        try:
            _LOGGER.info(f"Triggering zone {zone_number}")
            self.send_raw_elk_command(f"zt{zone_number:03d}")
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to trigger zone {zone_number}: {err}")
            return False

    async def display_message(
        self, area: int, clear_type: int, beep: bool, timeout: int, line1: str, line2: str
    ) -> bool:
        """Command the Elk-M1 panel to display a message on keypads."""
        if not self._elk:
            return False
        try:
            _LOGGER.info(f"Displaying message on Area {area}: '{line1}' / '{line2}'")
            
            # Adjust the clear/display type based on the beep boolean.
            # Elk modes: 0: clear, 1: clear+beep, 2: timeout, 3: timeout+beep, 4: hold, 5: hold+beep
            mode = clear_type
            if beep and mode in (0, 2, 4):
                mode += 1
                
            # Elk requires exactly 16 characters per line; pad or truncate as needed
            padded_line1 = f"{line1:<16}"[:16]
            padded_line2 = f"{line2:<16}"[:16]
            
            # Format: dm + area (1) + mode (1) + timeout (5) + line1 (16) + line2 (16)
            command = f"dm{area}{mode}{timeout:05d}{padded_line1}{padded_line2}"
            self.send_raw_elk_command(command)
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(f"Failed to display message: {err}")
            return False

    def _log_raw_serial_traffic(self, raw_data: Any) -> None:
        """Log raw frames received from the Elk-M1 serial interface."""
        _LOGGER.debug(f"RAW SERIAL RECEIVED --> {raw_data}")

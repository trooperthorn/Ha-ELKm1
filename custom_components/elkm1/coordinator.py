"""Data update coordinator for Elk-M1 Control integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from elkm1_lib import Elk
from elkm1_lib.const import ArmLevel
from elkm1_lib.message import MessageEncode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_BAUD_RATE,
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
from .helpers.transport import attach_baud_state
from .models import AreaData, ElkPanelData
from .vocabulary import translate_elk_voice

_LOGGER = logging.getLogger(__name__)

# Covers the worst-case baud sweep (5 rates) plus a couple of retry/backoff
# cycles; the transport itself retries indefinitely, so this is a ceiling on
# how long first setup waits before surfacing ConfigEntryNotReady, not a
# retry-count limit.
CONNECT_TIMEOUT = 30.0


class ElkDataUpdateCoordinator(DataUpdateCoordinator[ElkPanelData]):
    """Coordinator for Elk-M1 panel state.

    iot_class: local_push. Once the panel's Global Programming "Xmit ...
    Changes" settings are enabled (see helpers/panel_settings.py), it
    proactively broadcasts state changes; elkm1_lib decodes those and
    updates its own typed Zone/Area/Output/etc. objects, which this
    coordinator observes via per-element callbacks and immediately pushes
    onward via async_set_updated_data(). `update_interval` below is a
    safety-net resync of already-cached state, not the primary data path.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry_data: dict[str, Any],
        on_baud_detected: Callable[[int], None] | None = None,
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
        self._connection_type: str = config_entry_data[CONF_CONNECTION_TYPE]
        self._pin: str = str(config_entry_data.get(CONF_PIN, ""))
        self._on_baud_detected = on_baud_detected
        self._url = self._build_connection_url()
        self.data = ElkPanelData()

    @property
    def connected(self) -> bool:
        """Return True if currently connected to the panel."""
        return self._elk is not None and self._elk.is_connected()

    def _build_connection_url(self) -> str:
        """Build connection URL based on connection type."""
        if self._connection_type == CONNECTION_SERIAL:
            serial_port = self._config_data.get(CONF_SERIAL_PORT)
            if not serial_port:
                raise ValueError("Serial port not configured")
            return f"serial://{serial_port}"

        if self._connection_type == CONNECTION_NETWORK:
            host = self._config_data.get(CONF_HOST)
            if not host:
                raise ValueError("Host not configured")
            if "://" in host:
                # config_flow already builds a fully scheme-prefixed URL
                # (elk://, elks://, elksv1_2://) - use it as-is rather than
                # re-wrapping it in another scheme.
                return host
            port = self._config_data.get(CONF_PORT, 2101)
            return f"elk://{host}:{port}"

        raise ValueError(f"Unknown connection type: {self._connection_type}")

    def _obfuscated_url(self) -> str:
        """Return connection URL with sensitive data obfuscated for logging."""
        if self._connection_type == CONNECTION_SERIAL:
            return self._url
        if "://" in self._url:
            scheme = self._url.split("://", 1)[0]
            return f"{scheme}://<redacted>"
        return "<redacted>"

    @staticmethod
    def _get_enum_value(obj: Any, default: int = 0) -> int:
        """Safely extract integer value from enum or string objects."""
        if hasattr(obj, "value"):
            return int(obj.value)
        if isinstance(obj, str):
            return int(obj) if obj.isdigit() else default
        return int(obj) if isinstance(obj, (int, float)) else default

    async def _async_setup(self) -> None:
        """One-time connection setup, run once before the first refresh."""
        config: dict[str, Any] = {"url": self._url}
        if self._connection_type == CONNECTION_NETWORK:
            if username := self._config_data.get(CONF_USERNAME, ""):
                config["userid"] = username
            if password := self._config_data.get(CONF_PASSWORD, ""):
                config["password"] = password

        elk = Elk(config)
        attach_baud_state(
            elk,
            cached_baud=self._config_data.get(CONF_BAUD_RATE),
            on_baud_detected=self._on_baud_detected,
        )

        elk.add_handler("EE", self._handle_timer_event)
        elk.add_handler("AM", self._handle_alarm_memory)
        if elk.panel is not None:
            elk.panel.add_callback(self._handle_voice_message)

        connected_event = asyncio.Event()
        elk.add_handler("connected", lambda: connected_event.set())

        self._elk = elk
        elk.connect()
        try:
            await asyncio.wait_for(connected_event.wait(), timeout=CONNECT_TIMEOUT)
        except TimeoutError as err:
            elk.disconnect()
            self._elk = None
            raise UpdateFailed(
                f"Timed out connecting to Elk-M1 at {self._obfuscated_url()}"
            ) from err

        self._register_push_callbacks()

    def _register_push_callbacks(self) -> None:
        """Push a fresh snapshot whenever any tracked element changes state."""
        assert self._elk is not None

        def _on_change(_element: Any, _changeset: dict[str, Any]) -> None:
            self.async_set_updated_data(self._build_normalized_data())

        for collection_name in (
            "areas",
            "zones",
            "outputs",
            "tasks",
            "thermostats",
            "lights",
            "counters",
            "settings",
        ):
            for element in getattr(self._elk, collection_name):
                element.add_callback(_on_change)

    def _handle_timer_event(
        self, area: int, is_exit: bool, timer1: int, timer2: int, armed_status: Any
    ) -> None:
        """Fire an HA event for entry/exit timer updates (used by automations)."""
        self.hass.bus.async_fire(
            "elkm1_timer_event",
            {
                "area": area + 1,
                "type": "exit" if is_exit else "entry",
                "timer1": timer1,
                "timer2": timer2,
                "armed_status": self._get_enum_value(armed_status),
            },
        )

    def _handle_alarm_memory(self, alarm_memory: list[bool]) -> None:
        """Fire an HA event when alarm memory changes."""
        self.hass.bus.async_fire(
            "elkm1_alarm_memory",
            {"areas": [i + 1 for i, flagged in enumerate(alarm_memory) if flagged]},
        )

    async def async_disconnect(self) -> None:
        """Disconnect from ELK-M1 panel."""
        if self._elk:
            try:
                self._elk.disconnect()
                _LOGGER.info("Disconnected from ELK-M1")
            except (OSError, AttributeError) as err:
                _LOGGER.error("Error disconnecting: %s", err)
            finally:
                self._elk = None

    def _build_normalized_data(self) -> ElkPanelData:
        """Convert underlying library objects into a typed state snapshot."""
        if not self._elk:
            return self.data

        zones = list(self._elk.zones)
        panel = self._elk.panel
        areas = list(self._elk.areas)
        outputs = list(self._elk.outputs)
        tasks = list(self._elk.tasks)
        thermostats = list(self._elk.thermostats)
        lights = list(self._elk.lights)
        counters = list(self._elk.counters)
        settings = list(self._elk.settings)

        # elkm1_lib always allocates Max.AREAS.value (8) Area objects
        # regardless of how many the panel actually has configured; treat
        # only ones that have received real sync data as "configured" so
        # entity counts reflect the real panel, not the library's ceiling.
        configured_areas = [a for a in areas if a.configured] or areas[:1]
        num_areas = max(len(configured_areas), 1)

        areas_dict: dict[int, AreaData] = {}
        for area in configured_areas:
            t1 = getattr(area, "timer1", 0)
            t2 = getattr(area, "timer2", 0)
            armed_val = self._get_enum_value(area.armed_status)
            areas_dict[area.index] = AreaData(
                alarm_state=self._get_enum_value(area.alarm_state),
                armed_status=armed_val,
                arm_up_state=self._get_enum_value(area.arm_up_state),
                timer1=t1,
                timer2=t2,
                entry_delay_active=(t1 > 0 and armed_val != 0),
                exit_delay_active=t2 > 0,
                panic_state=getattr(area, "panic_state", False),
                alarm_memory=getattr(area, "alarm_memory", False),
            )

        faulted_indices: list[int] = []
        faulted_names: list[str] = []
        bypassed_names: list[str] = []
        fire_alarm = False

        for zone in zones:
            if not zone.configured:
                continue
            logical = self._get_enum_value(zone.logical_status)
            definition = self._get_enum_value(zone.definition)

            # ZoneLogicalStatus: 2 = violated, 5 = violated-and-bypassed.
            if logical in (2, 5):
                faulted_indices.append(zone.index)
                faulted_names.append(f"Zone {zone.index + 1}: {zone.name}")
            if logical == 5:
                bypassed_names.append(f"Zone {zone.index + 1}: {zone.name}")
            if definition in (9, 10) and logical in (2, 5):
                fire_alarm = True

        active_outputs: list[int] = []
        active_output_names: list[str] = []
        for output in outputs:
            if output.configured and output.output_on:
                active_outputs.append(output.index)
                active_output_names.append(f"Output {output.index + 1}: {output.name}")

        panel_temp = None
        for zone in zones:
            if zone.configured and zone.temperature > -60:
                panel_temp = zone.temperature
                break

        is_any_armed = any(a.armed_status != 0 for a in areas_dict.values())

        return ElkPanelData(
            panel_version=getattr(panel, "elkm1_version", None),
            num_areas=num_areas,
            areas=areas_dict,
            zones=zones,
            panel=panel,
            outputs=outputs,
            tasks=tasks,
            thermostats=thermostats,
            lights=lights,
            counters=counters,
            settings=settings,
            armed=is_any_armed,
            armed_mode="armed" if is_any_armed else "disarmed",
            last_user=None,
            last_user_name="Unknown",
            last_keypad=None,
            zones_faulted=faulted_indices,
            faulted_zone_names=faulted_names,
            outputs_active=active_outputs,
            active_output_names=active_output_names,
            trouble_status=bool(getattr(panel, "system_trouble_status", "")),
            ac_power=True,
            battery_status="Good",
            panel_temperature=panel_temp,
            fire_alarm_active=fire_alarm,
            bypassed_zones=bypassed_names,
        )

    async def _async_update_data(self) -> ElkPanelData:
        """Safety-net resync; the primary data path is push via element callbacks."""
        if not self._elk or not self._elk.is_connected():
            raise UpdateFailed("Not connected to Elk-M1")
        return self._build_normalized_data()

    # ---- STANDARDIZED ALARM CONTROL PANEL METHODS ----

    async def async_alarm_disarm(self, area_index: int, code: int = 0) -> bool:
        """Send disarm command for specific area."""
        return await self._execute_arm_cmd(ArmLevel.DISARM, area_index, code)

    async def async_alarm_arm_away(self, area_index: int, code: int = 0) -> bool:
        """Send arm away command for specific area."""
        return await self._execute_arm_cmd(ArmLevel.ARMED_AWAY, area_index, code)

    async def async_alarm_arm_home(self, area_index: int, code: int = 0) -> bool:
        """Send arm stay command for specific area."""
        return await self._execute_arm_cmd(ArmLevel.ARMED_STAY, area_index, code)

    async def async_alarm_arm_night(self, area_index: int, code: int = 0) -> bool:
        """Send arm night command for specific area."""
        return await self._execute_arm_cmd(ArmLevel.ARMED_NIGHT, area_index, code)

    async def async_alarm_arm_vacation(self, area_index: int, code: int = 0) -> bool:
        """Send arm vacation command for specific area."""
        return await self._execute_arm_cmd(ArmLevel.ARMED_VACATION, area_index, code)

    async def async_alarm_arm_custom_bypass(self, area_index: int, code: int = 0) -> bool:
        """Send arm-away command for specific area (custom bypass = arm-away)."""
        return await self._execute_arm_cmd(ArmLevel.ARMED_AWAY, area_index, code)

    async def async_alarm_trigger(self, area_index: int, code: int = 0) -> bool:
        """Trigger panic alarm on the area."""
        return await self.panic_alarm(str(code) if code else None)

    async def _execute_arm_cmd(self, level: ArmLevel, area_index: int, code: int = 0) -> bool:
        """Arm/disarm an area using elkm1_lib's own checksummed Area helpers."""
        if not self._elk:
            return False
        active_pin = code if code > 0 else int(self._pin or 0)
        area = self._elk.areas[area_index]
        if level == ArmLevel.DISARM:
            area.disarm(active_pin)
        else:
            area.arm(level, active_pin)
        return True

    # ---- ADDITIONAL HARDWARE METHODS ----

    async def bypass_zone(self, zone_number: int, pin_code: str | None = None) -> bool:
        """Bypass a zone (1-indexed, matching the panel's own numbering)."""
        if not self._elk:
            return False
        active_pin = int(pin_code) if pin_code else int(self._pin or 0)
        self._elk.zones[zone_number - 1].bypass(active_pin)
        return True

    async def unbypass_zone(self, zone_number: int, pin_code: str | None = None) -> bool:
        """Clear a zone's bypass.

        The Elk ASCII protocol has a single `zb` bypass command with no
        separate "unbypass a specific zone" command - resending it for an
        already-bypassed zone toggles it back off.
        """
        return await self.bypass_zone(zone_number, pin_code)

    async def speak_word(self, word: int) -> bool:
        """Speak a single word from the panel's voice vocabulary."""
        if not self._elk or self._elk.panel is None:
            return False
        self._elk.panel.speak_word(word)
        return True

    async def speak_phrase(self, phrase: int) -> bool:
        """Speak a phrase from the panel's voice vocabulary."""
        if not self._elk or self._elk.panel is None:
            return False
        self._elk.panel.speak_phrase(phrase)
        return True

    async def set_panel_time(self, when: datetime | None = None) -> bool:
        """Write the panel's real-time clock (defaults to the current time)."""
        if not self._elk or self._elk.panel is None:
            return False
        self._elk.panel.set_time(when)
        return True

    async def panic_alarm(self, pin_code: str | None = None) -> bool:
        """Trigger panic alarm."""
        if not self._elk:
            return False
        active_pin = pin_code if pin_code is not None else self._pin
        formatted_pin = str(active_pin).zfill(6)
        await self.send_raw_elk_command(f"ap1{formatted_pin}")
        return True

    async def send_raw_elk_command(self, command: str) -> None:
        """Send a raw Elk ASCII command body (without length/checksum/CRLF).

        Delegates checksum computation and write-queue serialization
        entirely to elkm1_lib's own Connection.send(), rather than
        recomputing the checksum by hand and reaching into connection
        internals - kept as a fallback for commands that don't yet have a
        typed elkm1_lib subsystem helper (see areas.py/zones.py/outputs.py/
        thermostats.py for the ones that do, e.g. Area.arm(), Zone.bypass(),
        Output.turn_on(), used directly above where available).
        """
        if not self._elk:
            _LOGGER.error("Cannot send raw command: Elk instance not found.")
            return
        length_hex = f"{len(command) + 4:02X}"
        self._elk.send(MessageEncode(f"{length_hex}{command}00", None))

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

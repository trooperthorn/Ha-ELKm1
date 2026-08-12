"""Data update coordinator for Elk-M1 Control integration."""
import logging
from datetime import timedelta
from typing import Any

from elkm1_lib.connection import ElkM1Connection
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
    ELKM1_BAUDRATE,
)

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
        self._elk: ElkM1Connection | None = None
        self._connection_type = config_entry_data.get(CONF_CONNECTION_TYPE)
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
            Connection URL for ElkM1Connection
            - Serial: "serial:///dev/ttyUSB0"
            - Network: "elk://192.168.1.100:2101"
        """
        if self._connection_type == CONNECTION_SERIAL:
            # Serial connection
            serial_port = self._config_data.get(CONF_SERIAL_PORT)
            if not serial_port:
                raise ValueError("Serial port not configured")
            
            # Build serial URL: serial:///dev/ttyUSB0
            url = f"serial://{serial_port}"
            _LOGGER.debug(f"Built serial URL: {url}")
            return url
        
        elif self._connection_type == CONNECTION_NETWORK:
            # Network connection
            host = self._config_data.get(CONF_HOST)
            port = self._config_data.get(CONF_PORT, 2101)
            
            if not host:
                raise ValueError("Host not configured")
            
            # Build network URL: elk://192.168.1.100:2101
            url = f"elk://{host}:{port}"
            _LOGGER.debug(f"Built network URL: {url}")
            return url
        
        else:
            raise ValueError(f"Unknown connection type: {self._connection_type}")

    def _obfuscated_url(self) -> str:
        """Return connection URL with sensitive data obfuscated for logging."""
        if self._connection_type == CONNECTION_SERIAL:
            return self._url
        else:
            # Hide password in logs
            host = self._config_data.get(CONF_HOST)
            port = self._config_data.get(CONF_PORT, 2101)
            return f"elk://{host}:{port}"

    async def async_connect(self) -> None:
        """Establish connection to ELK-M1 panel."""
        from .helpers.panel_settings import (
            check_panel_version,
            verify_panel_configuration,
        )

        try:
            _LOGGER.info(f"Connecting to ELK-M1 at {self._obfuscated_url()}")

            if self._connection_type == CONNECTION_SERIAL:
                self._elk = ElkM1Connection(
                    url=self._url,
                    timeout=5.0,
                    baudrate=ELKM1_BAUDRATE,
                )
            else:
                username = self._config_data.get(CONF_USERNAME, "")
                password = self._config_data.get(CONF_PASSWORD, "")
                self._elk = ElkM1Connection(
                    url=self._url,
                    username=username,
                    password=password,
                    timeout=5.0,
                )

            await self._elk.connect()
            _LOGGER.info(f"Connected to ELK-M1 at {self._obfuscated_url()}")

            await check_panel_version(self._elk)

            if self._connection_type == CONNECTION_SERIAL:
                _LOGGER.info("Serial connection detected - checking panel settings...")
                configured, details = await verify_panel_configuration(self._elk)
                if not configured:
                    for setting_num, status in details["settings"].items():
                        if status["enabled"] is False:
                            _LOGGER.warning(
                                f"  - Global Setting {setting_num} "
                                f"({status['name']}) is disabled"
                            )

        except (OSError, TimeoutError, ValueError) as err:
            _LOGGER.error(f"Failed to connect to ELK-M1: {err}")
            raise UpdateFailed(f"Connection failed: {err}") from err

    async def async_disconnect(self) -> None:
        """Disconnect from ELK-M1 panel."""
        if self._elk:
            try:
                await self._elk.disconnect()
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
            # Fetch all panel data
            zones = self._elk.zones
            panel = self._elk.panel
            areas = self._elk.areas
            outputs = self._elk.outputs
            tasks = self._elk.tasks
            thermostat = self._elk.thermostat
            
            # Log for debugging
            _LOGGER.debug(
                f"Coordinator update: "
                f"zones={len(zones) if zones else 0}, "
                f"areas={len(areas) if areas else 0}, "
                f"outputs={len(outputs) if outputs else 0}"
            )
            
            # Log zone states for debugging
            if zones:
                for zone in zones:
                    _LOGGER.debug(
                        f"  Zone {zone.number} ({zone.name}): "
                        f"status={zone.status}, "
                        f"faulted={zone.faulted}, "
                        f"open={zone.open}"
                    )
            
            # Return all data in standardized format
            return {
                "zones": zones if zones else [],
                "panel": panel,
                "areas": areas if areas else [],
                "outputs": outputs if outputs else [],
                "tasks": tasks if tasks else [],
                "thermostat": thermostat,
            }
        except (OSError, AttributeError, KeyError) as err:
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

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and disconnect."""
        await self.async_disconnect()

    # -------- Service Methods --------
    # These methods are called by services (disarm, bypass, etc.)

    async def send_disarm(self) -> bool:
        """Send disarm command to panel.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._elk:
            _LOGGER.error("Cannot send disarm: not connected")
            return False
        
        try:
            _LOGGER.info("Sending disarm command")
            await self._elk.disarm(pin=self._pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to disarm: {err}")
            return False

    async def send_arm_stay(self) -> bool:
        """Send arm stay command to panel."""
        if not self._elk:
            _LOGGER.error("Cannot send arm stay: not connected")
            return False
        
        try:
            _LOGGER.info("Sending arm stay command")
            await self._elk.arm_stay(pin=self._pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to arm stay: {err}")
            return False

    async def send_arm_away(self) -> bool:
        """Send arm away command to panel."""
        if not self._elk:
            _LOGGER.error("Cannot send arm away: not connected")
            return False
        
        try:
            _LOGGER.info("Sending arm away command")
            await self._elk.arm_away(pin=self._pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to arm away: {err}")
            return False

    async def send_arm_night(self) -> bool:
        """Send arm night command to panel."""
        if not self._elk:
            _LOGGER.error("Cannot send arm night: not connected")
            return False
        
        try:
            _LOGGER.info("Sending arm night command")
            await self._elk.arm_night(pin=self._pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to arm night: {err}")
            return False

    async def bypass_zone(self, zone_number: int) -> bool:
        """Bypass a zone.
        
        Args:
            zone_number: Zone number (1-208)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._elk:
            _LOGGER.error("Cannot bypass zone: not connected")
            return False
        
        try:
            _LOGGER.info(f"Bypassing zone {zone_number}")
            await self._elk.bypass_zone(zone_number, pin=self._pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to bypass zone {zone_number}: {err}")
            return False

    async def unbypass_zone(self, zone_number: int) -> bool:
        """Unbypass a zone.
        
        Args:
            zone_number: Zone number (1-208)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._elk:
            _LOGGER.error("Cannot unbypass zone: not connected")
            return False
        
        try:
            _LOGGER.info(f"Unbypassing zone {zone_number}")
            await self._elk.unbypass_zone(zone_number, pin=self._pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to unbypass zone {zone_number}: {err}")
            return False

    async def panic_alarm(self) -> bool:
        """Trigger panic alarm."""
        if not self._elk:
            _LOGGER.error("Cannot trigger panic: not connected")
            return False
        
        try:
            _LOGGER.warning("Sending panic alarm command")
            await self._elk.panic(pin=self._pin)
            await self.async_request_refresh()
            return True
        except (OSError, AttributeError, ValueError) as err:
            _LOGGER.error(f"Failed to trigger panic: {err}")
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
            _LOGGER.info(f"Setting thermostat {thermostat_id} to {temperature}°")
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

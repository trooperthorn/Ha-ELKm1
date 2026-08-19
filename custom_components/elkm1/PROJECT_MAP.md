# Project Map: Modernized Native-Async Elk-M1 Integration

This document provides a comprehensive structural map of the refactored Home Assistant Elk-M1 integration, detailing file organization, core classes, data collection architectures, and cross-integration hooks.

## 1. Core Architecture & Data Flow
The integration has been completely decoupled from the legacy `elkm1-lib` and redesigned around a high-performance, non-blocking asynchronous architecture.
* **Connection Layer (`helpers/connection.py`):** Utilizes native `asyncio` streams and `serial_asyncio` to maintain direct TCP or serial communication with the Elk-M1 panel. It features an automated read loop, exponential backoff reconnection, and an active heartbeat timer (`rr` command) to prevent M1XEP module dropouts during alarms.
* **State Management (`coordinator.py`):** Acts as the single source of truth (`ElkDataUpdateCoordinator`), caching normalized state dictionaries for areas, zones, outputs, keypads, and counters. Real-time ASCII broadcasts (`AS`, `EE`, `AM`, `VN`) are parsed instantly and pushed to Home Assistant without polling delays.
* **Presentation Layer (Platforms):** UI entities (Alarm Control Panels, Binary Sensors, Sensors, Switches) are completely data-agnostic, reading directly from `coordinator.data` and dispatching asynchronous raw ASCII commands back through the coordinator.

---

## 2. File Manifest & Component Descriptions

### Core Integration Files
* `__init__.py`: Manages the config entry lifecycle, integration setup/unload workflows, and runtime data assignment (`ELKM1Data`).
* `config_flow.py`: Implements modern UI setup steps, including smart concurrent hardware serial port probing and network auto-discovery.
* `coordinator.py`: The central hub managing data normalization, periodic updates, state caching, and raw ASCII command formatting/checksum calculations.
* `const.py`: Houses global constants, domain names, service schemas, and hardheaded M1 Gold hardware limits (e.g., 208 zones, 8 areas, 16 keypads).
* `models.py`: Defines the runtime data dataclass (`ELKM1Data`) linking config entries to the coordinator and connection manager.
* `entity.py`: Base entity definitions inheriting from `CoordinatorEntity` and establishing standardized device registry identifiers.

### Helper Modules (`helpers/`)
* `connection.py`: Native non-blocking TCP/serial socket manager with heartbeat and automatic reconnect logic.
* `usb_discovery.py`: OS-level serial port enumeration mapping raw devices to persistent `/dev/serial/by-id/` paths and verifying hardware responses.
* `panel_settings.py`: Verifies minimum panel firmware versions and logs required global configuration reminders.
* `troublestatus.py`: Parses system trouble bitmasks into human-readable diagnostics.

### Platform Entities
* `alarm_control_panel.py`: Manages multi-area partitioning (Areas 1–8), state mapping (`PENDING`, `ARMING`, `TRIGGERED`, `ARMED_*`), and secure PIN-authorized arming/disarming.
* `binary_sensor.py`: Maps raw zone definitions to Home Assistant binary sensor device classes (doors, windows, motion, smoke, CO, water).
* `sensor.py`: Exposes system panel status, active zone summary counters, temperature keypads, analog voltage zones, and user settings.
* `switch.py`: Controls physical output relays, thermostat emergency heat switches, and native proxy triggers for pre-arm blueprints.

### Metadata & Services
* `services.py`: Registers custom platform services (`speak_word`, `speak_phrase`, `set_time`, `get_security_summary`).
* `device_action.py`: Exposes device-level automation actions for the Home Assistant UI editor.
* `diagnostics.py`: Securely exports redacted runtime state diagnostics for troubleshooting.
* `vocabulary.py`: Translates numeric Elk voice vocabulary IDs into readable string phrases.
---
## 2. Recurring Issues & Structural Gotchas (MUST READ)
2.1 The Enum / String / Integer Trap (elkm1_lib Quirks)
   The Problem: elkm1_lib returns payload fields as Python Enum objects, but frequently stores the underlying .value as a numeric string (e.g., '0', '2').

The Danger:

bool(AlarmState.NO_ALARM_ACTIVE) evaluates to True (object is not empty), causing false "Triggered" states.

'0' >= 2 causes a fatal TypeError crash.

'2' == 2 executes safely but silently evaluates to False, causing sensors to never trigger.

The Solution: You MUST route all status evaluations through a strict type-casting helper to guarantee an integer:


## 2. Core Operational Rules & Architectural Gotchas

### Area vs. Coordinator Execution Routing
* **Arming & Disarming:** All security partition actions (`disarm`, `arm_home`, `arm_away`, `arm_night`, `arm_vacation`, `arm_custom_bypass`, `trigger`) must be invoked directly on the **`Area`** element (`self.area.arm_home(code)`), NOT on `self.coordinator`. Calling missing coordinator methods throws an `AttributeError` that fails silently if caught in generic error blocks.
* **Synchronous Call Queuing:** Command methods in `elkm1_lib` are synchronous queuing calls; do not use `await self.area.disarm(code)`.

### Alarm State Evaluation & The String `'0'` Trap
* `elkm1_lib` frequently returns the alarm trigger state as a numeric string (e.g., `'0'` when inactive, `'1'` or alarm type codes when active).
* In Python, `bool('0')` evaluates to `True`. The state evaluation must explicitly parse string representations:
  ```python
  alarm_state_raw = getattr(self.area, "alarm_state", 0) if self.area else 0
  is_triggered = bool(alarm_state_raw) and str(alarm_state_raw) not in ("0", "False", "false", "")
  


## 2. Core Data Flow & Architecture
1. **Connection:** `elkm1_lib` communicates directly with the Elk-M1 panel over serial or network socket.
2. **State Management:** `ElkDataUpdateCoordinator` updates state data dictionaries shared across entities via `entry.runtime_data`.
3. **Execution Routing:** 
   - Panel arm/disarm actions execute directly against partition/area objects (`self.area.disarm(code)`, `self.area.arm_home(code)`).
   - Global diagnostics pull from the core panel object (`self.coordinator._elk.panel`).
   - Group counts cross-reference live hardware objects (`self.coordinator._elk.zones[index]`) using Home Assistant's Entity Registry for naming and device class overrides.

## 3. Key Classes & Naming Conventions
- **Alarm Panel Entity:** `ElkAlarmControlPanel`
  - States: `disarmed`, `armed_home`, `armed_night`, `armed_away`, `triggered`.
  - PIN Code: Numeric code required (`_attr_code_format = CodeFormat.NUMBER`, `_attr_code_arm_required = True`).
- **Zone Group Sensor Entity:** `ElkZoneGroupSensor`
  - Target device classes: `door`, `window`, etc.
  - Native value returns integer count of active/open zones.
  - Attributes return comma-separated lists of open entity names (`open_entities`).

## 4. Custom Services
- `elkm1.speak_phrase`: Triggers voice/speech output on the panel or integrated media targets using dynamic text payloads.
- `elkm1.alarmo_auto_setup`: Scans registered Elk binary sensors and populates notification guides for automated Alarmo integration.

## Recurring Issues & Structural Gotchas (MUST READ)

2.1 The Enum / String / Integer Trap (elkm1_lib Quirks)
* The Problem: elkm1_lib returns payload fields as Python Enum objects, but frequently stores the underlying .value as a numeric string (e.g., '0', '2').
* The Danger:
  * bool(AlarmState.NO_ALARM_ACTIVE) evaluates to True (object is not empty), causing false "Triggered" states.
  * '0' >= 2 causes a fatal TypeError crash.
  * '2' == 2 executes safely but silently evaluates to False, causing sensors to never trigger.
* The Solution: You MUST route all status evaluations through a strict type-casting helper to guarantee an integer:

 Python

  ```python
def _get_enum_value(self, obj, default=0) -> int:
   
    try:
        val = obj.value if hasattr(obj, "value") else obj
        if isinstance(val, int): return val
        if isinstance(val, str) and val.lstrip('-').isdigit(): return int(val)
    except Exception:
        pass
    return default
  ```
   
## 2.2 Strict Elk Protocol Alarm State Mapping
Do not assume alarm_state > 0 means "Triggered." You must map the exact Elk M1 integer protocols to Home Assistant states:
  * alarm_state == 1: Entrance Delay Active -> Maps to AlarmControlPanelState.PENDING.
  * alarm_state >= 2: Actual Alarm (2=Abort Delay, 3+=Alarms) -> Maps to AlarmControlPanelState.TRIGGERED.
  * arm_up_state in (3, 5) OR timer2 > 0: Exit Delay Active -> Maps to AlarmControlPanelState.ARMING.
  
## 2.3 PIN Code Formatting and Type Casting

* The Problem: Home Assistant UI passes the PIN code as a string (e.g., '1234'). The Elk M1 RS-232 serial command (a / arm()) explicitly requires an integer.

* The Solution: Catch, strip, and cast the HA string to an integer before passing it to self.area.arm(), catching ValueError if the code is missing or malformed.

## 2.4 Command Routing (Area vs. Coordinator)
* The Problem: Calling actions on self.coordinator throws missing AttributeError failures.
* The Solution: All partition actions (disarm, arm_home, arm_away, arm_night, arm_vacation, arm_custom_bypass, trigger) must be invoked directly on the partition element (self.area.arm(level, code)).

## 2.5 Live Hardware Scanning vs. Stale Dictionaries
* The Problem: self.coordinator.data.get("zones_faulted") can be empty or stale if background updates lag.
* The Solution: Faulted zones, bypassed zones, and active outputs must be scanned dynamically against live hardware objects (self.coordinator._elk.zones).
  * Violated Zone: logical_status == 2 or physical_status in (1, 3)
  * Fire Zone: Definition 9 or 10 with logical_status == 2

## 2.6 Temperature Sensor Sourcing
* The Problem: The main Elk-M1 control board does not possess an onboard ambient temperature sensor. Calling panel.temperature returns None.
* The Solution: Iterate over enrolled LCD Keypads (self.coordinator._elk.keypads) to extract keypad.temperature for the primary panel attributes.
 
## 2.7 Service Registration API Strictness
* The Problem: Passing a description keyword argument into hass.services.async_register() causes a fatal TypeError crash during integration setup.
* The Solution: Do not pass descriptions in the Python API. All service schemas, parameter types, and UI texts must strictly reside in services.yaml.

## 3. Entity Class Specifications & Supported Features

PlatformClass NameSupported Features / FormatsKey Attributesalarm_control_panelElkAlarmControlPanelARM_AWAY, ARM_HOME, ARM_NIGHT, ARM_VACATION, ARM_CUSTOM_BYPASS, TRIGGERCodeFormat.NUMBERcode_arm_required = Truezones_faulted, zones_faulted_count, faulted_zone_names, entry_delay_seconds, exit_delay_seconds, bypassed_zones, panel_temperaturesensorElkZoneGroupSensorIntrospects Entity Registry device_class overrides (door, window)native_value (integer count), open_entities (comma-separated list of active entity names)binary_sensorElkZoneBinarySensorDevice classes mapped via Elk zone definitions (door, window, motion, smoke, moisture)physical_status, logical_status, definition

## 4. Custom Integration Serviceselkm1.speak_phrase
* File Definition: services.yaml
* Behavior: Broadcasts spoken phrases through the Elk-M1 Output 1 audio driver using panel vocabulary word translation.
* Selector Configuration: Uses string-quoted numeric values (value: "1") to prevent YAML schema parsing errors.elkm1.alarmo_auto_setupFile Definition: alarmo_integration.pyBehavior: Scans all registered Elk-M1 binary sensors and creates a persistent notification detailing zone-to-sensor mapping, recommended arming modes, and device class configurations for Alarmo.

## 5. Integration Ecosystem Hooks
* Alarmo Compatibility: Zones created as binary_sensor with standard security device classes are automatically discovered by Alarmo's sensor engine.
* Better Thermostat Compatibility: Window and door zone binary sensors expose native BinarySensorDeviceClass.WINDOW and BinarySensorDeviceClass.DOOR, enabling automatic HVAC cut-off when openings are violated.

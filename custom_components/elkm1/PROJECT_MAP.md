# ELK-M1 Home Assistant Integration - Master Architectural Reference Map

## 1. Directory Structure & File Architecture
# ELK-M1 Home Assistant Integration - Project Map & Architecture Reference

## 1. Directory Structure & File Architecture
```text
custom_components/elkm1/
├── __init__.py               # Component lifecycle (setup, unload, runtime data, platform forwarding, services)
├── manifest.json             # Integration metadata, requirements (elkm1_lib), code owners, versioning
├── const.py                  # Domain definition (DOMAIN = "elkm1") and configuration keys
├── data.py                   # ElkRuntimeData dataclass (coordinator, serial_port)
├── coordinator.py            # ElkDataUpdateCoordinator (socket loop, polling, real-time push callbacks)
├── entity.py                 # ElkEntity base class (availability, device_info, coordinator subscriptions)
├── alarm_control_panel.py    # ElkAlarmControlPanel entity (Area partition mapping, arming modes, attributes)
├── binary_sensor.py          # Individual Elk hardware zone entities (logical/physical state mapping)
├── sensor.py                 # Diagnostic sensors, keypad temperature sensors, ElkZoneGroupSensor
├── alarmo_integration.py     # Alarmo setup helper (registers elkm1.alarmo_auto_setup service)
├── services.yaml             # Custom service schemas, parameter types, selectors, and UI descriptions
└── translations/
    └── en.json               # Localization strings, UI labels, and service field descriptions
```
---

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

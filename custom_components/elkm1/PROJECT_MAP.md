# ELK-M1 Home Assistant Custom Integration - Architecture Map

## 1. Directory Structure & File Roles
- `custom_components/elkm1/`
  - `manifest.json`: Integration metadata, requirements (`elkm1_lib`), and versioning.
  - `const.py`: Global constants (`DOMAIN`, configuration keys).
  - `__init__.py`: Entry point (`async_setup_entry`, `async_unload_entry`, runtime data allocation, service initializers).
  - `coordinator.py`: `ElkDataUpdateCoordinator` managing socket connections and data sync via `elkm1_lib`.
  - `alarm_control_panel.py`: `ElkAlarmControlPanel` entity mapped to Elk areas, handling arm/disarm/trigger methods and rich attributes.
  - `sensor.py`: `ElkZoneGroupSensor` and diagnostic sensors tracking open doors, windows, and system counts via Entity Registry parsing.
  - `binary_sensor.py`: Individual zone binary sensors mapped to physical/logical states and device classes.
  - `alarmo_integration.py`: Auto-setup helper that registers `elkm1.alarmo_auto_setup` to sync zones with the Alarmo integration.

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

# Elk-M1 Control for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_elkm1?style=for-the-badge)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)
![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.4+-blue.svg?style=for-the-badge)

Built though Gemini AI using the ElkM1 Technical manual, the Elk Library, lots of QA.

A fully-featured custom integration for Home Assistant to monitor and control **Elk-M1 Gold** and **Elk-M1 EZ8** alarm and automation panels. A robust, asynchronous custom integration for the Elk-M1 Gold and Elk-M1 EZ8 security/automation panels in Home Assistant. This integration communicates directly with your Elk panel via serial or network connections, providing real-time state updates and advanced control.

This integration uses the modern [elkm1_lib](https://github.com/gwww/elkm1) Python library and supports both direct Serial/USB connections and Network connections via the Elk M1XEP.



# ELK-M1 Custom Integration for Home Assistant

A high-performance, asynchronous Home Assistant integration for ELK-M1 Gold security and automation controls[cite: 1]. This integration provides real-time state synchronization, full area partition control[cite: 1], live zone status tracking, dynamic open door/window counting, voice phrase broadcasting, and automated setup integration with **Alarmo** and **Better Thermostat**.

---

## Features

- Integration 5 other Integrations: Automate with Davis Weather, Unifi Protect, Better Thermostat, Browser Mod, and ESP32 Bluetooth Proxy
  
- **Full Area Partition Control**: Arm in Home, Away, Night, Vacation, or Custom Bypass modes, disarm with PIN enforcement, and manually trigger emergency panics[cite: 1].
- **Live Hardware Scanning**: Real-time evaluation of faulted, bypassed, and troubled zones directly from panel memory buffers.
- **Dynamic Group Sensors**: Aggregate sensors that scan your Home Assistant Entity Registry to report live counts and formatted lists of open windows and doors.
- **Voice Announcement Service**: Send dynamic speech announcements to the Elk-M1 internal voice driver using native vocabulary word mapping (`elkm1.speak_phrase`)[cite: 1].
- **Alarmo Auto-Setup Helper**: One-click service to scan all configured Elk security zones and generate complete configuration guidelines for the Alarmo integration.
- **Better Thermostat Ready**: Proper `device_class` attributes on all contact sensors to enable automatic HVAC suspension when windows or doors are opened.

---

##  Integration Ecosystem & Automation Blueprints
- Alarmo & Better Thermostat Compatibility: Standardized binary sensor device classes enable automatic Alarmo zone mapping and HVAC cut-off when doors or windows open.

- UniFi Protect Integration: Bridges panel states and zone triggers with camera recording, motion snapshots, push notifications, and full perimeter lockdowns.

- Atmospheric Pre-Arm Check: Intercepts arming requests, cross-referencing Elk window sensors with Davis Vantage weather telemetry (wind speed and precipitation rate) to prevent storm damage.

- Smart Chimes & Perimeter Guards: Dynamic hardware vocabulary speech synthesis that reads out door/window counts and individual open sensor names with precise timing delays.

- Presence & Kiosk Control: ESPHome Bluetooth proxy presence tracking for automated departure/arrival arming, combined with Browser-Mod for emergency wall kiosk video popups.

- TODO: Codebase Integrity (Watchman): Automated startup audits scanning all YAML configurations, scripts, and blueprints for missing entities or broken service calls.


### Method 1: HACS (Recommended)
1. Open HACS in Home Assistant.
2. Click the 3-dots in the top right corner and select **Custom repositories**.
3. Add the URL of this repository and select **Integration** as the category.
4. Click **Install** on the Elk-M1 Control card.
5. Restart Home Assistant.

### Method 2: Manual
1. Download the latest release from this repository.
2. Extract the `custom_components/elkm1` folder into your Home Assistant `custom_components` directory.
3. Restart Home Assistant.



1. Restart Home Assistant.
2. In Home Assistant, navigate to **Settings** > **Devices & Services** > **Add Integration** and search for **Elk-M1**.
3. Configure your connection (Serial Port path or Network IP / Port).

---

## Available Services

### `elkm1.speak_phrase`
Broadcasts a spoken phrase through the Elk-M1 Output 1 voice driver[cite: 1].


service: elkm1.speak_phrase
data:
  phrase: "Front door open"


## Installation

## Services

This integration exposes several custom services to interact with the panel. Security-sensitive actions require a PIN code to execute.

* `elkm1.arm_away` / `elkm1.arm_stay` / `elkm1.arm_night`
* `elkm1.disarm`
* `elkm1.bypass_zone` / `elkm1.unbypass_zone`
* `elkm1.trigger_zone` (Momentary virtual violation)
* `elkm1.speak_phrase`

For advanced configuration, automations, and custom events, please see the [Wiki](https://github.com/trooperthorn/ha_int_elkm1/wiki).

---
*Disclaimer: This is a community-developed custom component and is not officially affiliated with Elk Products, Inc.*
---

## 🐛 Troubleshooting & Debugging

If you are experiencing connection issues or entities aren't updating, you can enable debug logging IN THE INTEGRATION to see the raw communication between Home Assistant and your panel.

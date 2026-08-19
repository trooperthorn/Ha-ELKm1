# Elk-M1 Control for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_elkm1?style=for-the-badge)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)
![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.4+-blue.svg?style=for-the-badge)

Built though Gemini AI using the ElkM1 Technical manual, the Elk Library, lots of QA.


# Elk-M1 Security Control Integration for Home Assistant

A modern, native-async Home Assistant custom integration for controlling **Elk-M1 Gold** and **M1EZ8** security control panels[cite: 1, 19, 31]. This integration bypasses legacy third-party libraries in favor of a direct, high-performance asynchronous connection manager designed for Home Assistant 2026.8 and Python 3.14.2.

## Features
* **100% Native Async Architecture:** Direct non-blocking TCP (M1XEP) and Serial/USB communication with zero legacy library overhead.
* **Bulletproof Reliability:** Built-in TCP keep-alive heartbeats and exponential backoff reconnection routines to handle network drops and alarm events gracefully.
* **Smart Serial Discovery:** Automatically scans operating system ports, resolves persistent `/dev/serial/by-id/` paths, and probes hardware to identify active Elk panels.
* **Deep Ecosystem Integration:** Fully compatible with **Alarmo**, **Better Thermostat**, **Unifi Protect**, **Browser Mod**, and **ESP32 Bluetooth Proxies**.
* **Real-Time State Streaming:** Instantaneous updates via raw ASCII broadcast interceptors (`AS`, `EE`, `AM`, `VN`).

---

## Requirements
* Home Assistant 2026.8 or newer.
* Python 3.14.2 or newer.
* An Elk-M1 Security Panel connected via an M1XEP Ethernet module or a direct serial/USB cable.

---

## Installation via HACS
1. Open **HACS** in your Home Assistant instance.
2. Navigate to **Integrations**.
3. Click the three dots in the top right corner and select **Custom repositories**.
4. Paste your repository URL, select category **Integration**, and click **Add**.
5. Search for **Elk-M1 Security**, click **Download**, and restart Home Assistant.




## Features

- Integration 5 other Integrations: Automate with Davis Weather, Unifi Protect, Better Thermostat, Browser Mod, and ESP32 Bluetooth Proxy
  
- **Full Area Partition Control**: Arm in Home, Away, Night, Vacation, or Custom Bypass modes, disarm with PIN enforcement, and manually trigger emergency panics[cite: 1].
- **Live Hardware Scanning**: Real-time evaluation of faulted, bypassed, and troubled zones directly from panel memory buffers.
- **Dynamic Group Sensors**: Aggregate sensors that scan your Home Assistant Entity Registry to report live counts and formatted lists of open windows and doors.
- **Voice Announcement Service**: Send dynamic speech announcements to the Elk-M1 internal voice driver using native vocabulary word mapping (`elkm1.speak_phrase`)[cite: 1].
- **Alarmo Auto-Setup Helper**: One-click service to scan all configured Elk security zones and generate complete configuration guidelines for the Alarmo integration.
- **Better Thermostat Ready**: Proper `device_class` attributes on all contact sensors to enable automatic HVAC suspension when windows or doors are opened.

---


## OLD INFO I WANT TO ADD BACK AND VERIFY

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

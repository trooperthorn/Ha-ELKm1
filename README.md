# Elk-M1 Control for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_elkm1?style=for-the-badge)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)
![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.4+-blue.svg?style=for-the-badge)

A fully-featured custom integration for Home Assistant to monitor and control **Elk-M1 Gold** and **Elk-M1 EZ8** alarm and automation panels. A robust, asynchronous custom integration for the Elk-M1 Gold and Elk-M1 EZ8 security/automation panels in Home Assistant. This integration communicates directly with your Elk panel via serial or network connections, providing real-time state updates and advanced control.

This integration uses the modern [elkm1_lib](https://github.com/gwww/elkm1) Python library and supports both direct Serial/USB connections and Network connections via the Elk M1XEP.


## Features

* **Alarm Control Panel:** Full support for Arming (Away, Stay, Night) and Disarming with secure PIN validation.
* **Zones & Sensors:** Real-time monitoring of all hardwired and wireless zones via Binary Sensors.
* **Outputs:** Control Elk relays and voltage outputs via HA Switches.
* **Tasks:** Trigger programmed Elk tasks directly from Home Assistant.
* **Thermostats & Lighting:** Integration with Elk-managed automation devices.
* **Voice Announcements:** Native interception of Elk voice broadcasts, translated into human-readable text events for HA automations.

## Installation

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

## Configuration

This integration is configured entirely via the Home Assistant UI (Config Flow). 

1. Go to **Settings > Devices & Services**.
2. Click **+ Add Integration** and search for **Elk-M1 Control**.
3. Select your connection method:
   * **Serial:** Provide the port path (e.g., `/dev/serial/by-id/...`).
   * **Network:** Provide the IP address/Hostname and Port.
4. Enter your Elk User PIN (used for security actions).


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

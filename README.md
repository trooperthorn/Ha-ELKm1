# Ha-ELKm1

Home Assistant custom integration providing **Elk M1 Gold & Platinum** support with expanded **Set Command** access.

---

[![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_elkm1?style=for-the-badge)](https://github.com/trooperthorn/ha_int_elkm1/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/m/trooperthorn/ha_int_elkm1?style=for-the-badge)](https://github.com/trooperthorn/ha_int_elkm1/commits/master)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)

## Features

- **Flexible Connection Modes:** Supports both direct Serial/USB and Ethernet (M1XEP) connections.
- **Enhanced Control:** Advanced access to Elk-M1 set commands directly through Home Assistant.
- **Smart Hardware Discovery:** Built-in validation during setup safely probes your system's hardware to ensure target ports match an authentic Elk-M1 panel, automatically resolving persistent, reboot-safe USB paths.

---

## Installation

### HACS (Recommended)
1. Open HACS in Home Assistant.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add `https://github.com/trooperthorn/ha_int_elkm1` as an **Integration**.
4. Click **Download** and restart Home Assistant.

### Manual
1. Download the latest release.
2. Copy the `custom_components/elkm1` directory into your Home Assistant `config/custom_components` directory.
3. Restart Home Assistant.

---

## Setup & Configuration Flow

The integration features a guided UI setup flow allowing you to choose between standard connection protocols. Go to **Settings** > **Devices & Services** > **Add Integration** and search for **Elk M1 Control**.

### Option A: Serial/USB (Direct Connection)
The integration automatically scans your system and safely tests available serial ports to find your panel.
1. Select **Serial/USB**.
2. Open the **Port** dropdown. The integration will identify the panel with an `(ELK-M1 Panel Detected) 🎯` tag.
3. Enter your optional validation PIN and submit.

### Option B: Network (Elk M1XEP or Remote)
1. Select **Network**.
2. Enter the **Host** IP address of your M1XEP.
3. Enter your Elk-M1 **Username** and **Password** (and optional PIN). 
4. The integration will test the connection and configure the device.

---

## Panel Configuration Requirements

To ensure Home Assistant properly tracks state changes, you must enable Global Settings 35-40 on your Elk panel using ElkRP. These settings dictate what events the panel broadcasts over the serial/network connection.

| Setting | Function | Impact if Disabled |
| :---: | :--- | :--- |
| **35** | Event Log (who armed/disarmed) | Cannot track user state changes |
| **36** | Zone Changes | Zones do not update in real-time |
| **37** | Output Changes | Outputs do not update |
| **38** | Automation Tasks | Tasks do not report |
| **39** | Light Changes | Lights do not update |
| **40** | Keypad Changes | Alarm state does not update |

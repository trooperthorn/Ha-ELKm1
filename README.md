# Elk-M1 Control for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_elkm1?style=for-the-badge)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)
![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.4+-blue.svg?style=for-the-badge)

A fully-featured custom integration for Home Assistant to monitor and control **Elk-M1 Gold** and **Elk-M1 EZ8** alarm and automation panels. 

This integration uses the modern [elkm1_lib](https://github.com/bdraco/elkm1_lib) Python library and supports both direct Serial/USB connections and Network connections via the Elk M1XEP.

## ✨ Features

* **UI Configuration:** Fully configurable via the Home Assistant UI (no `configuration.yaml` required).
* **Dual Connection Support:** Connect via Network (M1XEP) or direct Serial/USB.
* **Auto-Discovery:** Automatically scans and suggests available USB/Serial ports during setup.
* **Setup Wizard:** Automatically verifies panel compatibility and checks required global settings during installation.
* **Instant Updates:** Uses asyncio for rapid, real-time state updates.
* **Supported Entities:**
  * 🛡️ **Alarm Control Panel:** Monitor and control Areas (Arm, Disarm, Night, Stay, Away).
  * 🚪 **Sensors & Binary Sensors:** Real-time state of all Zones (Open, Closed, Bypassed, Faulted).
  * 💡 **Switches:** Control and monitor panel Outputs.
  * 🌡️ **Climate:** Monitor and control attached Thermostats.
  * 🔘 **Buttons:** Trigger panel Automation Tasks.

---

## 📥 Installation

### Option 1: HACS (Recommended)
1. Open HACS in Home Assistant.
2. Click the 3-dots menu in the top right and select **Custom repositories**.
3. Add the URL of this repository and select **Integration** as the category.
4. Click **Download** on the Elk-M1 Control repository.
5. Restart Home Assistant.

### Option 2: Manual Installation
1. Download the latest release from this repository.
2. Copy the `custom_components/elkm1` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

---

## ⚙️ Configuration

1. In Home Assistant, go to **Settings > Devices & Services**.
2. Click **+ Add Integration** in the bottom right corner.
3. Search for **Elk-M1 Control**.
4. Choose your connection type:
   * **Serial/USB:** Select your serial port from the discovered list (or enter manually) and optionally provide a PIN for alarm control.
   * **Network (M1XEP):** Enter your panel's IP Address (Host), Port (default 2101), Username, Password, and optionally a PIN.
5. The integration will test the connection. If successful, it will verify your panel settings and add your devices!

### ⚠️ Important Panel Settings
For Home Assistant to receive real-time updates from your Elk-M1, the panel **must** be configured to transmit state changes. The setup wizard will attempt to verify and enable these automatically, but if you have issues, ensure the following **Global Settings (35-40)** are checked in ElkRP2:

* Transmit Event Log
* Transmit Zone Changes
* Transmit Output Changes
* Transmit Automation Task Changes
* Transmit Light Changes
* Transmit Keypad Changes

---

## 🛠️ Custom Services

This integration provides several custom services that can be used in Home Assistant automations and scripts:

| Service | Description | Data Parameters |
| :--- | :--- | :--- |
| `elkm1.bypass_zone` | Bypass a specific zone | `zone_number` (int) |
| `elkm1.unbypass_zone` | Unbypass a specific zone | `zone_number` (int) |
| `elkm1.activate_task` | Trigger an Elk automation task | `task_number` (int) |
| `elkm1.panic_alarm` | Trigger the panel's panic alarm | None |

*(Standard alarm services like `alarm_control_panel.alarm_arm_away` are also fully supported via the generated Alarm Control Panel entities).*

---

## 🐛 Troubleshooting & Debugging

If you are experiencing connection issues or entities aren't updating, you can enable debug logging to see the raw communication between Home Assistant and your panel.

Add the following to your `configuration.yaml` and restart Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.elkm1: debug
    elkm1_lib: debug

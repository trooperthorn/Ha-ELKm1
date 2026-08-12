# Ha-ELKm1

Home Assistant integration providing **Elk M1 Gold & Platinum** support with expanded **Set Command** access.

---

## Features

- **Flexible Connection Modes:** Supports both direct Serial/USB and Ethernet (M1XEP) connections.
- **Enhanced Control:** Advanced access to Elk-M1 set commands directly through Home Assistant.
- **Auto-Discovery Verification:** Built-in validation during setup to ensure target devices match an authentic Elk-M1 panel.

---

## Setup & Configuration Flow

The integration features a guided setup flow allowing you to choose between standard connection protocols:

## Setup & Configuration Flow

The integration features a guided setup flow allowing you to choose between standard connection protocols:




"How to connect?"
  ☑ Serial/USB
  ☐ Network

[Network] > [Text field] "Enter IP" > [Verify] > ✅ Created


[Serial] > [Verify] "Select port" [Dropdown] > [Verify] > ✅ Created

What Gets Checked and Configured using a PIN
Global Settings 35-40 (Required for Event Reporting)
Setting	Enables	Impact if Disabled
35	Event Log (who armed/disarmed)	Can't track user changes
36	Zone Changes	Zones don't update in real-time
37	Output Changes	Outputs don't update
38	Automation Tasks	Tasks don't report
39	Light Changes	Lights don't update
40	Keypad Changes	Alarm state doesn't update

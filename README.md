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

```mermaid
flowchart TD
    Start([Start Setup]) --> ConnectionType{How to connect?}
    
    ConnectionType -->|Serial/USB| SerialPath[Select Serial Port]
    ConnectionType -->|Network| NetworkPath[Enter IP & Port]
    
    SerialPath --> SerialVerify[Verify & Authenticate]
    NetworkPath --> NetworkVerify[Verify & Authenticate]
    
    SerialVerify --> Done[✅ Created]
    NetworkVerify --> Done



User starts setup
        ↓
"How to connect?"
  ☑ Serial/USB
  ☐ Network
        ↓
   [User selects]
     /          \
    /            \
[Serial]        [Network]
    ↓               ↓
"Select port"    "Enter IP"
[Dropdown]       [Text field]
    ↓               ↓
[Verify]        [Verify]
    ↓               ↓
✅ Created      ✅ Created



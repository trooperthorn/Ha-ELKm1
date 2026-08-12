# Ha-ELKm1
Elk M1 Platinum Support with Set command access

User chooses connection type
Serial → dropdown port selector
Network → IP address + port

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

┌─────────────────────────────────┐
│ Connect to Elk-M1               │
├─────────────────────────────────┤
│ How would you like to connect?  │
│                                 │
│ Connection Type:                │
│ ☑ Serial/USB (Direct)           │
│ ☐ Network (M1XEP or remote)    │
│                                 │
│ [SUBMIT]                        │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ Serial/USB Connection           │
├─────────────────────────────────┤
│ Found 1 serial ports.           │
│                                 │
│ Serial Port: [FTDI FT232R ▼]   │
│ Username: [_____________]       │
│ Password: [_____________]       │
│ ☑ Verify device is Elk-M1      │
│                                 │
│ [SUBMIT]                        │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ Network Connection              │
├─────────────────────────────────┤
│ IP Address: [192.168.1.100    ] │
│ Port: [2101                    ] │
│ Username: [_________________] │
│ Password: [_________________] │
│                                 │
│ [SUBMIT]                        │
└─────────────────────────────────┘

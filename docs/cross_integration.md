# Cross-integration support

This integration's cross-integration support is deliberately tiered, based on
whether the other product actually exchanges data with the Elk-M1 panel or
simply lives alongside it in Home Assistant:

- **Code-level integration** (Alarmo, Better Thermostat): this repository
  ships Python code and/or entities specifically built to talk to that
  product.
- **Automation-layer support** (Davis Weather, Unifi Protect, Browser Mod,
  ESP32 Bluetooth Proxy): there is no direct data link between the Elk panel
  and these products, so support means standards-compliant entities (correct
  `device_class`, stable `unique_id`s, sensible naming) plus ready-made
  [Blueprints](../blueprints/automation/) that wire the two together in an
  automation - not new integration code.

## Alarmo (code-level)

`alarmo_integration.py` registers `elkm1.alarmo_auto_setup`, a service that
scans the entity registry for this integration's zone `binary_sensor`
entities and posts a persistent notification listing them, so you can add
them to Alarmo's **Sensors** tab in a couple of clicks instead of hunting
through the entity list by hand. `blueprints/automation/auto_setup_alarmo.yaml`
runs it automatically on Home Assistant startup once the Elk panel is online.

Alarmo discovers `binary_sensor` entities on its own; this integration's job
is only to make its zones easy to find, not to duplicate Alarmo's arming
logic. Zone `device_class` is derived from the panel's zone-definition field
best-effort - see the comment above `_DEVICE_CLASS_MAP` in `binary_sensor.py`
for what the protocol does and doesn't tell us about physical sensor type.

## Better Thermostat (code-level)

Two separate paths, because the more broadly useful one doesn't require the
Elk panel to have any Elk-connected thermostats - most installations don't.

### Primary: per-area door/window aggregate sensor

`binary_sensor.py` creates one `binary_sensor.elk_m1_area_N_openings` entity
per configured area (`device_class: opening`), which is on when any
door/window zone assigned to that area is violated. This is Elk's real value
for climate control: its door/window contact zones, not its thermostats.

Feed this sensor into Better Thermostat's own window-sensor setting (Better
Thermostat restores the exact prior mode/temperature automatically when the
window closes), or use
`blueprints/automation/pause_climate_on_opening.yaml` for any other climate
integration that lacks native window-sensor support - it works with any
`climate.*` entity, not just an Elk-connected one.

Door/window classification is best-effort: the Elk protocol's zone
"definition" field encodes the panel's *arming response* for a zone (entry/
exit delay, perimeter-instant, interior, etc.), not its physical sensor type.
Entry/exit zones are assumed to be doors and perimeter-instant zones are
exposed as the generic `opening` class rather than `window` specifically,
since the protocol has no way to confirm either.

### Secondary: wrapping an Elk-connected thermostat directly

If the panel does have Elk-connected thermostats, `climate.py`'s
`ElkThermostat` entity is a standards-compliant `climate.ClimateEntity`
(correct `hvac_modes`, `hvac_action`, `supported_features`) that Better
Thermostat - or any other climate-wrapping integration - can use as its
underlying entity like any other thermostat. Pair it with the per-zone
temperature-probe `sensor` entities as Better Thermostat's external
temperature sensor input.

## Davis Weather, Unifi Protect, Browser Mod, ESP32 Bluetooth Proxy (automation-layer)

None of these exchange data with the Elk panel directly, so there is no
integration code for them here - only Blueprints that combine their
entities with this integration's:

- `blueprints/automation/elk_davis_atmospheric_pre_arm.yaml` - checks Davis
  Weather conditions (rain, wind) before allowing an Elk area to arm.
- `blueprints/automation/unifi_protect_example.yaml` - snapshots/records a
  Unifi Protect camera in response to an Elk zone fault.
- `blueprints/automation/kiosk_security_popup.yaml` - pops up a Browser Mod
  kiosk alert on an Elk security event.
- ESP32 Bluetooth Proxy has no dedicated blueprint yet; it's a `bluetooth`
  platform, not an entity domain, so it participates through whatever
  `device_tracker`/presence entities it feeds - see
  `blueprints/automation/presence_arming.yaml` for a presence-driven
  arm/disarm example that works with any presence source, BLE-proxy-derived
  or not.

These blueprints use area-based entity matching where practical (matching an
Elk zone's area to a camera or notification target in the same area) rather
than hardcoding entity IDs, so they adapt to your own naming instead of
requiring edits before use.

# Changelog

All notable changes to this project will be documented in this file.

## [2026.08.20]

A complete rework aimed at genuinely exceeding Home Assistant's Platinum quality
bar - the previous release self-declared `quality_scale: platinum` while the
integration did not actually work (platform modules the manifest referenced didn't
exist, the coordinator's update method wasn't wired into `DataUpdateCoordinator`, and
a bug in `__init__.py` masked every real connection failure behind a `NameError`).

### Added
- Host-side baud-rate auto-detection for serial connections (the protocol has no way
  to query/negotiate baud rate on the wire): sweeps standard rates, confirms with a
  real `vn` round-trip, and caches the winning rate on the config entry.
- `climate`, `light`, `number`, `time`, and `scene` platforms (previously referenced
  in `manifest.json` but never implemented, so the integration failed to load).
- Granular system-trouble `binary_sensor` entities (one per condition, disabled by
  default) instead of one coarse trouble flag; per-zone voltage/temperature sensors;
  zone bypass as a `switch`.
- A per-area "any door/window open" aggregate `binary_sensor` - the primary,
  hardware-independent integration point for Better Thermostat (or any climate
  integration), since it doesn't require the panel to have Elk-connected thermostats.
- Options flow (poll-interval fallback), reconfigure flow (network + serial), and
  reauth flow, triggered by a real login-rejection event from the panel rather than a
  generic connection timeout.
- USB discovery (known serial adapter VID:PIDs) alongside the existing DHCP discovery
  for M1XEP network modules.
- Real entity services that were declared in `services.yaml` but never registered
  anywhere (`alarm_bypass`, `alarm_clear_bypass`, `alarm_arm_home_instant`,
  `alarm_arm_night_instant`, `sensor_counter_refresh`, `sensor_counter_set`), plus a
  working `display_message` service.
- `docs/cross_integration.md` and `blueprints/automation/pause_climate_on_opening.yaml`,
  honestly tiering cross-integration support: Alarmo and Better Thermostat get real
  code-level integration; Davis Weather, Unifi Protect, Browser Mod, and ESP32
  Bluetooth Proxy get standards-compliant entities plus blueprints, not new
  integration code.
- A real test suite (68 tests) replacing two near-placeholder files, one of which had
  a permanently-failing test.
- An honest `quality_scale.yaml`, ruff configuration (`pyproject.toml`), and a
  genuinely `strict = true` `mypy.ini` scoped to the package.

### Changed
- Replaced the transport layer's connection-opening logic with native `asyncio`
  (`helpers/transport.py`), keeping `elkm1-lib` for protocol message encode/decode and
  the panel's typed subsystem objects rather than reimplementing the protocol.
- Coordinator waits for the panel's actual `"login"` event instead of a raw socket
  "connected" event before considering setup complete.
- Corrected zone `device_class` mapping: the Elk zone-definition field encodes the
  panel's arming response (entry/exit delay, perimeter-instant, interior), not
  physical sensor type - entry/exit is now mapped to `door` (was incorrectly split
  door/motion across its two values), and perimeter-instant to the generic `opening`
  class instead of overclaiming `window`.
- `alarm_control_panel.py`'s command methods now raise `HomeAssistantError` on
  failure instead of only logging it, so a failed arm/disarm/bypass command is
  visible to the user instead of looking like success.
- `alarmo_integration.py`'s zone-entity matching now uses `unique_id` instead of an
  `entity_id` substring check that real (panel-named) installations never matched.

### Fixed
- Zone (and output/thermostat/light/task/counter/custom-value) entities could fail to
  appear at all: `elkm1_lib` only marks an element `.configured` once the panel's
  reply to a per-index name request for it has arrived, and that sync is a fully
  sequential, one-index-at-a-time exchange (up to 208 round-trips for zones alone)
  that routinely outlasts the coordinator's setup, which only waits for the panel's
  login to be confirmed. Every platform that filters entity creation on `.configured`
  was doing so in a single pass at startup, so any element not yet synced at that
  moment was silently dropped for good - on a real panel, this could mean **no**
  zone `binary_sensor` entities (door/window/motion/etc.) appeared at all. Fixed via
  a new `entity.async_add_dynamic_entities()` helper: platforms now keep adding
  entities as elements individually become configured, woken by a new coordinator
  handler for the panel's `"SD"` name-reply message.
- `hass.components.persistent_notification` (removed from Home Assistant core) was
  called unconditionally by the Alarmo auto-setup service - every invocation crashed.
- `async_setup_services()` was called without `await` in `async_setup()`, silently
  never running.
- `ZoneLogicalStatus` checks for a nonexistent value 5 ("violated-and-bypassed") -
  the real enum only has 4 members (normal/trouble/violated/bypassed); bypass is its
  own status, not a flag on top of violated.
- `zone.bypassed` was read via `getattr(zone, "bypassed", False)`, which always
  silently returned `False` since `Zone` has no such attribute.
- `unbypass_zone()` sent a nonexistent "zu" command; the protocol's `zb` bypass
  command is a single toggle with no separate unbypass variant.
- The panel clock-set service sent "cs" (Control-output Status request in the real
  protocol, not a clock command); now uses `elkm1_lib`'s own `Panel.set_time()`.
- `device_action.py`'s `display_message`/`speak_phrase` actions called services with
  parameter names that didn't match the registered schema.
- `PARALLEL_UPDATES = 1` was missing from `alarm_control_panel`, `switch`, and
  `sensor` (which has write-capable entity services) despite the panel having a
  single serialized command buffer.
- Removed `manifest.json`'s `quality_scale: platinum` self-declaration - the honest
  `quality_scale.yaml` produced by this rework doesn't fully satisfy even Bronze yet
  (external `brands` submission, and full config-flow test coverage, remain open).

## [2.0.0] - 2026-01-15

### Added
- Event firing for zone changes
- 25+ alarm panel attributes
- Alarmo auto-setup service
- Binary sensor platform for zones
- Switch platform for relays
- USB port auto-detection

### Changed
- Improved connection stability
- Enhanced error handling

### Fixed
- Silent connection loss
- Zone synchronization

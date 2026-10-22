# Changelog — Carrier SmartHome Native

## 0.1.0a9 — controls consolidation and cleanup (2026-10-22)

**Goal:** consistent HA controls without redundant entities or stale documentation.

- One primary climate control for mode, fan, and (opt-in) targets. One companion HVAC Power switch; discarded an unshipped duplicate select platform.
- Three separate command implementations consolidated into a single guarded, serialized write/preflight/readback routine shared by climate and power. One mutation per action, no blind retries.
- Separate opt-in fan Auto/On (Circulation cloud enum unverified), mode/power and setpoint writes. Setpoints require mode/power enabled.
- New last-cloud-reported diagnostics disabled by default to keep the device page uncluttered; existing registry settings are respected.
- Accurate online/offline semantics, tests for mode/fan/power, and documentation reconciled with live evidence.
- No Matter dependencies, GitHub Actions, or experimental live device writes were added.

## 0.1.0a8 — initial controls and LAN reconnaissance

- Added guarded experimental native GraphQL HVAC mode and power functions, optional read-only single-device LAN probes.

## 0.1.0a7 — Wi-Fi loss investigation

- Restored live climate unavailability when Carrier reports offline, retaining last-cloud-reported diagnostics.

## 0.1.0a6 — official-app/GraphQL correlation

- Guided official app setpoint comparison; later fixed false-positive full restoration when other fields changed.

## 0.1.0a1–a5 — foundation

- Authenticated Carrier native GraphQL cloud discovery; HACS package, sensors, diagnostics, read-only probes, and startup hardening. Refer to individual [`research/`](research/) documents for complete evidence and limitations.

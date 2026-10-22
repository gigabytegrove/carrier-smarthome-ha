# Changelog

## v0.5.0 — Home Assistant controls baseline + comprehensive proprietary LAN reconnaissance

- Version baseline explicitly set to `0.5.0`, replacing the alpha numbering. UI branding simplified to Carrier SmartHome; domain and entity IDs unchanged.
- Preserve the cleaned, single Home Assistant climate entity and native cloud mode/fan/temperature controls. No new UI toggles, duplicate selectors, or redundant switch.
- Introduce a **single** deep LAN probe engine: verified current Omada client MAC/IP, strict redacted.invalid/16 boundary, time and timezone validation, full TCP 1–65535 option, TLS/HTTP status fingerprint, MQTT anonymous CONNECT (no subscriptions/publications), and read-only UDP mDNS/SSDP/CoAP discovery.
- Retire duplicate network-probe logic. Old `Probe-VerifiedCarrierLAN` commands forward to the new engine for backwards compatibility.
- Sanitize local reports to omit MAC, private IP, SSID, thermostat serial, names, TLS certificate fingerprints, passwords and authentication material.
- Add offline identity/freshness/protocol payload, mocked TCP/MQTT tests and documentation on why negative results cannot prove local control is impossible.
- No DNS redirection, firmware modification, Matter pairing, API writes or HVAC commands. Local protocol support remains research until proven with the actual device.

# Changelog

## 0.1.0a10 — Standard climate controls, no configuration gates

- Fix only-Off mode selector caused by persisted `enable_control=false` options.
- Show all supported modes directly in HA, including Off/Heat/Cool/Auto/Fan Only.
- Offer fan Auto/On and setpoint controls in the same climate UI without separate option toggles.
- Remove duplicate HVAC Power switch, obsolete `power_on_mode` setting, and legacy OptionsFlow.
- Migrate old config entries, clear obsolete options and clean up only old Carrier HVAC Power entities.
- Remember last Carrier-reported active mode during this HA session for turn_on; never invent a default mode.
- Preserve serialized single-write preflight, cloud confirmation, offline blocking and rate limits.
- Native Carrier command path remains experimental until validated on physical equipment; no Matter.

For historical alpha releases, see Git commit history.

# Changelog

## v0.5.2 — Home Assistant cloud synchronization and stale-command prevention

- Owner confirmed native HA Off/Cool toggles appear in both independent Carrier GraphQL views, while HA presentation lagged. Manual temperature adjustments during tests were intentional.
- Push only verified detail-query mode, fan, or target values to the HA DataUpdateCoordinator immediately when the account listing is behind; preserve unrelated sensor values and device identity. This is a verified state push, **not optimistic control**.
- Reject overlapping mode/fan/setpoint writes while a previous command is awaiting confirmation, instead of silently queueing stale user actions behind a potentially 64-second lock. Never issue a repeated mutation automatically.
- Check independent detail at 8 seconds and later bounded intervals, maintaining the existing 64-second observation window and rate-limit protection.
- Reduce routine cloud polling from 60 to 30 seconds; preserve cloud rate-limit backoff, no new background services and no Matter.
- Update regression tests for delayed confirmation, state publishing, offline safety, overlapping command rejection, and HACS compatibility.
- A PowerShell clone of v0.5.1 alone does **not** prove the running Home Assistant integration was upgraded; verify the manifest shown by HA diagnostics.

## v0.5.1 — Carrier delayed cloud confirmation (no duplicate HVAC writes)

- Confirmed against the owner's thermostat: Carrier acknowledged HA's mode mutation; the physical setting changed after the old short verification window, which caused a misleading HA service error.
- Use `DataUpdateCoordinator.async_refresh()` for fresh preflight and confirmation instead of debounced `async_request_refresh()` (which can return without another network read during its 10-second cooldown).
- Extend read-only confirmation to nine polls across about 64 seconds; use the verified detailed GraphQL path as a bounded independent cross-check. **Exactly one mutation per requested command** remains the invariant.
- Respect cloud rate limits rather than repeatedly probing after a rate-limit response. Report uncertainty accurately when no confirmation arrives, without claiming the HVAC command failed.
- Add regression coverage for delayed state propagation, transient polling faults and rate limiting; preserve no-Matter, no-defaults and online-only command rules.
- Avoid stale-summary no-op errors: when the summary already appears to match an explicitly requested HVAC mode, cross-check the detailed GraphQL view before deciding not to send any mutation. If detail disagrees, execute the user-requested command only once.
- LAN research still requires a fresh Omada client export; a stale 08:14 archive cannot be used to identify a current IP.


## v0.5.0 — Home Assistant controls baseline + comprehensive proprietary LAN reconnaissance

- Version baseline explicitly set to `0.5.0`, replacing the alpha numbering. UI branding simplified to Carrier SmartHome; domain and entity IDs unchanged.
- Preserve the cleaned, single Home Assistant climate entity and native cloud mode/fan/temperature controls. No new UI toggles, duplicate selectors, or redundant switch.
- Introduce a **single** deep LAN probe engine: verified current Omada client MAC/IP, strict 172.20.0.0/16 boundary, time and timezone validation, full TCP 1–65535 option, TLS/HTTP status fingerprint, MQTT anonymous CONNECT (no subscriptions/publications), and read-only UDP mDNS/SSDP/CoAP discovery.
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

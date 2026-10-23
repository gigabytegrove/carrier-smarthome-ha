## 0.5.7b1 — experimental Matter test build (feature branch, not stable v0.5.6)

- Add explicit per-thermostat Cloud only / Matter only / Prefer Matter control preferences; existing installations remain cloud-only by default.
- Add Matter Server WebSocket climate reads with verified Carrier Matter product identity and 20-second local polling.
- Add temperature unit conversions and guarded single-write local mode/setpoint commands, plus no cloud fallback following uncertain Matter writes.
- Block unsupported independent fan mode on Matter-only and simultaneous local dual-setpoint writes. Require owner confirmation of physical-node identity.
- Add offline protocol and routing regression suites; physical-device commissioning and Home Assistant validation remain pending.
- Experimental branch manifest set to **0.5.7b1** to distinguish a test installation from stable v0.5.6. The published stable release remains unchanged.

# Changelog

## v0.5.6 — Clear thermostat sensor names and diagnostic cleanup

- Display native thermostat terminology in the Home Assistant Diagnostics section: **Max Heating Setpoint**, **Min Cooling Setpoint**, **Heating Setpoint**, **Cooling Setpoint**, **HVAC Mode**, **Fan Mode**, **Schedule Enabled**, **Room Temperature**, **Indoor Humidity**, and **Outdoor Temperature**.
- Map the limits precisely: `htsp.max` = maximum heating setpoint; `clsp.min` = minimum cooling setpoint. Values, units, and conversion handling are unchanged.
- Preserve the unique IDs and history of the ten retained diagnostic entities; renaming a display label does **not** change the existing entity ID, user-defined names, or cloud data.
- Retire only this integration's obsolete `stage_status` and `current_scene` diagnostic entities, which are unsupported/unavailable for the tested `TSTATCCEWF-01` thermostat. Keep corresponding raw optional read fields for future compatibility research.
- Even without the repetitive prefix, **all ten are historical Carrier cloud reports**. Their attributes continue to identify the source, unknown timestamp, stale-data risk, and warning not to use them for HVAC automation.
- No changes to local control, cloud command mutation behavior, authentication, or Matter exclusion.


## v0.5.5 — Availability recovery and Carrier cloud backoff

- Prevent a single cloud/API read failure from causing immediate whole-device flicker: retain only previously verified **online** readings for at most 90 seconds, mark them potentially stale, and still block any HVAC writes without a fresh successful Carrier read.
- Keep the cloud API health binary sensor readable during an outage, report `Off`, and include last successful poll, sanitized failure category, retry wait and failed-poll count in Home Assistant diagnostics.
- Respect HTTP 429 `Retry-After` across Carrier GraphQL reads and writes; use bounded backoff on transport errors and return automatically to the normal update interval on recovery.
- Pass the supported `UpdateFailed(retry_after=...)` field to Home Assistant so it schedules Carrier's requested cooldown rather than hammering the service.
- Avoid replacing a known thermostat with an empty coordinator listing during a transient cloud response. Preserve last cloud-reported diagnostics after an API error, without falsely labeling them live.
- Set regular cloud polling to 60 seconds to reduce repeated requests; verified cloud mode/fan/target readback still updates HA immediately, without waiting for the background poll.
- No changes to native cloud mutation payloads, thermostat identity, Home Assistant climate entity IDs, local control research, or Matter exclusion. Physical device recovery remains to be owner-tested.

## 0.5.4 — Direct local-IP investigation and release-readiness cleanup

- Permit explicitly authorized single-host probes at the already identified thermostat IP, without repeating the Omada export process. Explicitly disclose that a previous IP is not an independently verified current MAC/IP binding.
- Keep bounded, read-only TCP/UDP and protocol fingerprinting; no Matter, no local HVAC writes, no firmware/DNS modifications.
- Update documentation, release metadata, privacy checks and regression coverage. Preserves cloud HVAC mode support and current entity IDs.
- This is **not** a claim of functional local HVAC control; 1.0 remains dependent on real device tests.

## v0.5.3 — Carrier SmartHome naming, artwork, faster confirmed cloud feedback

- Rename HACS display name to **Carrier SmartHome**, matching the integration title; preserve the existing `carrier_smarthome` internal domain, config entry and entity identifiers.
- Bundle the owner-provided Carrier SmartHome app artwork under `custom_components/carrier_smarthome/brand/icon.png`, the native brand location supported by Home Assistant 2026.3+.
- Document the **only verified physical thermostat**: `TSTATCCEWF-01` (cloud-reported as `TSTATCCEEF-01`). Do not claim universal Carrier compatibility or an established proprietary LAN control API.
- For a single acknowledged Carrier cloud mutation, start native detailed-query verification on the **first** readback rather than after eight seconds. Subsequent readbacks back off over a bounded 64-second window; no automatic retries of the mutation.
- Retain verified-state-only HA coordinator updates, non-queued HVAC writes and 30-second background polling.
- GitHub Releases are required for HACS version labels; HACS `main` commit hash on its download dialog is not itself evidence of an installed HA version. Fix the PowerShell release command to avoid terminating on `gh release view` 404 in Windows PowerShell 5.1.
- Put HACS, Buy Me a Coffee and PayPal badges at the top of a product-oriented README; add GitHub funding metadata and explicit single-model compatibility.
- Proprietary LAN control remains research; no Matter or unverified HVAC control packets.

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

# Changelog

## v0.5.10 — Homeowner Matter code preparation and cloud setup clarity

- Add clear guidance for owners of Carrier TSTATCCEWF-01 thermostats to
  photograph the rear **Smart Home** QR label and record any manual Matter
  code *before* wall mounting, when practical. Explain why scanning a code
  behind a powered thermostat is impractical and how a previously recorded
  code avoids needing another live scan.
- Distinguish the Smart Home QR from Carrier's **Mobile Onboarding** QR,
  and distinguish knowing the code from opening a Matter commissioning
  window. No unsupported thermostat button sequence is implied.
- Update the Home Assistant sign-in description with optional future
  Matter preparation while stating clearly that **this integration is
  cloud-only and requires no Matter code**.
- No change to Carrier API control, entities, local protocols, version,
  diagnostic formats or existing configuration.


## v0.5.9 — Deduplicate thermostat control writes and diagnostics

- Correct the v0.5.8 behavior observed in owner diagnostics: Cool, then Fan On, then Fan Auto sent the previously pending Cool mode in all three cloud mutations. Pending state remains merged in Home Assistant's display, but only the newly requested mode/fan/temperature fields are transmitted to Carrier.
- Repeating an already pending target no longer creates another cloud mutation or restarts the confirmation window. Ignore independent already-selected fields while other thermostat controls are pending.
- Distinguish `requested` (the actual new control) from `pending_overlay` (all unconfirmed displayed settings) and include newly sent fields in the `mutation_sent` event.
- Compress repetitive verification observations: record each source's first reading and changes, then a `verification_summary` containing actual detail/list read counts and the count of unchanged samples suppressed. Preserve the existing one-write guard, command supersession, cloud-backoff and 64-second bounded confirmation.
- Preserve explicit cloud mutation for a true rapid reversal (Cool → Off), and require evidence of transition instead of claiming confirmation based on a stale Off reading.
- Do not claim that Fan On or Fan Only has been physically validated. Existing controls and all entity IDs are preserved; no new Matter, proprietary LAN or scheduling operations are introduced.
- Extend offline regression tests around the exact owner-observed sequence, repeated clicks, unchanged fan selections and verification-summary counting.
- Add a separate passive, per-source cloud control transition history (100 events) to diagnostics. Log initial observations and genuine subsequent changes in mode, fan, targets and schedule-enabled flag from polling and detailed readback. Avoid claiming that cloud changes without a pending HA command were caused by the Carrier schedule, official app or thermostat. Do not log secrets or identifiers, and do not overwrite device telemetry.

## v0.5.8 — Rapid consecutive thermostat changes

- Fix the "Previous Carrier command still being verified" failure when changing HVAC mode twice quickly.
- Hold the control lock only for a fresh cloud preflight and one Carrier mutation, not the up-to-64-second read-only observation window. Return control to Home Assistant after cloud acknowledgment while background confirmation updates the local optimistic display.
- Allow a newer user command to supersede an earlier pending command immediately. Coalesce commands still waiting for their turn to write, so stale queued mode selections do not override the latest selection.
- Never cancel an in-flight Carrier mutation. Serialize actual writes, stop only superseded read-only confirmation, and clean up confirmation tasks when the integration unloads.
- Explicitly issue the latest change on rapid reversals (Cool → Off) even when preflight cloud data is still at the old Off state. Require independent evidence of a transition before declaring a reversal verified when the reported state was already at the requested target.
- Preserve other in-progress mode, fan and target values in a combined subsequent command when controls change rapidly.
- Keep all commands privacy-sanitized in the bounded diagnostics history, including supersessions, mutation acknowledgment, cancellations, verification and rollbacks.
- Preserve the integration domain, entity IDs, existing configuration, supported model, single cloud mutation per transmitted command, and no Matter or unverified proprietary local control.

## v0.5.7 — Immediate thermostat feedback and command diagnostics

- Show an operator's requested HVAC mode, fan setting or target temperature on the Home Assistant climate entity immediately, before cloud preflight and Carrier command readback. The new state is visibly marked `control_status: pending_cloud_confirmation`.
- Keep optimistic values in a transient, climate-only overlay. The Carrier-reported telemetry, last-reported diagnostic sensors, temperature/humidity, connectivity state and cloud confirmation evidence remain unchanged.
- After Carrier verifies a command, clear the overlay and display the verified report. Roll it back automatically after a rejection, failed preflight, cancellation, or unresolved readback; label ambiguous acknowledged-but-unconfirmed outcomes separately from confirmed rejection.
- Add the most recent 160 privacy-sanitized command events to Home Assistant Download diagnostics, including request, preflight, one mutation, individual readbacks, confirmation or rollback, with correlation IDs and times but **no serials, names, account data or tokens**.
- Preserve one cloud mutation per request, no queued writes, 64-second read-only verification, offline safety, rate limiting, existing entity IDs, no Matter and no claim of proprietary LAN control.
- Includes offline regression coverage for overlay isolation, multi-zone behavior, privacy, bounded history, rollback and stale completions.

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
- Introduce a **single** deep LAN probe engine: verified current Omada client MAC/IP, strict redacted.invalid/16 boundary, time and timezone validation, full TCP 1–65535 option, TLS/HTTP status fingerprint, MQTT anonymous CONNECT (no subscriptions/publications), and read-only UDP mDNS/SSDP/CoAP discovery.
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

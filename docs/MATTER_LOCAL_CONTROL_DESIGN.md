# Carrier SmartHome: Matter dual-transport foundation (experimental branch)

**Baseline protected:** v0.5.6 (`4b4ed50c3ecc764263446b36deb24049f450da85`) on `main`. Feature branch only; do **not** install this as a working local-control release. No public issues created.

## User-facing objective

One Carrier SmartHome integration / one climate entity and three explicitly selectable policies:

| Policy | Data/control source | Fallback |
| --- | --- | --- |
| Cloud only | Existing Carrier GraphQL | Never sends Matter commands |
| Matter only | Local Matter thermostat (after commissioned and validated) | Never sends cloud HVAC commands |
| Prefer Matter | Matter while safely reachable; otherwise native Carrier cloud | **Only** before a local write starts; an ambiguous Matter acknowledgment MUST NOT cause a duplicate cloud command |

Existing installs default to Cloud only and preserve unique IDs, HACS metadata, diagnostic entity names, climate entities and credentials. No separate Matter climate device should remain visible to users.

## Why the separate OHF Matter Server?

Matter is not an MQTT-style broker. It needs device attestation, a persistent fabric, commissioning, encrypted CASE sessions, subscriptions, certificate stores and secure writes. The current **matter.js Matter Server** provides this controller machinery and a documented WebSocket API (`ws://127.0.0.1:5580/ws` on the same host). The client code in this branch talks to that controller **directly**; it does not delegate control through an unrelated Home Assistant climate entity, and it never implements an ad-hoc Matter handshake.

Official protocol docs: https://github.com/matter-js/matterjs-server/blob/main/docs/websockets_api.md

## Work completed in this branch

- Pure fail-closed Matter Thermostat cluster **0x0201** mapping for `systemMode` (0x001c), local temperature (0x0000), occupied cooling/heating setpoints (0x0011/0x0012) in hundredths of degrees Celsius, and thermostat setpoint limits. Device must report Carrier Matter VID 0x10EE / PID 0x0800 and correct cluster on selected endpoint.
- A bounded, one-at-a-time WebSocket client for official `get_node`, `read_attribute` and `write_attribute` RPCs with schema checks and readback. No pairing codes stored; the server manages its own fabric.
- Three-way transport routing policy with no fallback after any possibly sent write.
- Offline tests for mappings, identities, unit conversions, selection, unsafe destinations, RPC sequence and uncertain write outcomes.
- Dedicated `DualTransportRouter` enforcing all three modes, serialized user commands and **no second cloud write** following an uncertain Matter result. Cloud fallback is restricted to safe, pre-write Matter failure.
- Zero changes to stable cloud coordinator, commands or entity registry.

## Gating work before enabling Matter in HA

1. A Matter Server must be deployed **on the reachable thermostat network**, preferably host networking on a properly configured VLAN 30 segment, with valid IPv6 reachability. Merely observing tagged VLAN 30 frames on `enp2s0` does not mean `dockeradm` has a VLAN 30 IP interface; no such interface was present in the owner's audit. Do not change the host's physical networking without a rollback plan.
2. Commission the owner's thermostat using the already available Smart Home setup code, *not* the Wi-Fi onboarding QR. Never upload setup codes or log them. Confirm VID/PID, endpoint cluster and available attributes from the actual device.
3. Verify initial **read-only** Matter telemetry against the existing Carrier cloud values. Confirm supported modes/feature flags and actual setpoint limits. Do not infer fan control from a mode enum.
4. Add a validated Home Assistant OptionsFlow (Cloud / Matter / Prefer Matter) and per-device node binding only after commission/identity checks; ensure a cloud outage cannot disable the Matter-only entity.
5. Wire controller reads into one existing Carrier climate entity, preserve its original unique ID, write-lock semantics and cloud diagnostics; don't create duplicate climate devices. Convert temperature units through Home Assistant conversion routines. Explicitly surface active control transport and health.
6. With owner supervision, test one reversible Heat/Cool/Off and setpoint change over Matter, confirm readback, check cloud synchronization; test offline and uncertain-write protections. Never auto-retry an uncertain HVAC write.
7. Complete complete offline and real HA tests before marking anything for v1.0. **No GitHub Actions, no unapproved background services.**

## Validation

Run `python -m unittest discover -s tests -q` from the checkout. Matter mapping tests require no network and never change HVAC state.


## New experimental HA integration wiring (this branch)

- Home Assistant **Configure** offers per-device Cloud only, Matter only or Prefer Matter.
- Only an explicitly bound and *already commissioned* Matter Server node is eligible.
  Saving an option performs a read-only VID/PID/endpoint check.
- One Carrier climate entity retains its existing unique ID. Local temperature
  and setpoints are converted from Matter's hundredths °C into the Carrier
  climate entity's configured temperature unit. 20-second local polling keeps
  locally confirmed state fresh for at most 45 seconds, separately from cloud.
- Local mode and individual temperature writes are routed through the existing
  validated Matter client. Unknown writes never trigger cloud commands.
  Simultaneous dual-setpoint updates are intentionally blocked from Matter
  until an atomic and hardware-verified implementation is available.
- Independent fan control remains cloud-only: Matter-only refuses it.
- Existing installations have **no behavior change** until configured.
- Configuring Matter does not install a controller, alter VLAN/firewall rules,
  expose pairing codes, or prove physical-device identity beyond VID/PID and
  the owner's explicit node binding. The local path still needs real hardware
  validation before public release.
- The Matter Server WebSocket API defaults to unauthenticated local ws. Private
  LAN addresses are accepted so HA and Matter Server can run in different
  containers/hosts; never expose TCP 5580 beyond a trusted network. Use wss
  via a trusted TLS reverse proxy when the network is not fully trusted.

Cloud-first startup still requires the original Carrier account and a
successful initial cloud thermostat listing. Fully cloud-independent cold
startup requires a separately validated persistent identity/device cache and
is not claimed by this branch.

### Implementation verification checklist (not hardware-tested)

- Confirm default cloud-only config and original entity IDs remain unchanged.
- Confirm HA OptionsFlow serial/zone list, read-only node verification and
  owner acknowledgement. Test two same-model units; wrong-node binding is
  rejected by the user's verification gate and duplicate node/endpoint binding
  is refused for the account.
- Exercise 20-second Matter readings with Carrier cloud blocked. Existing
  climate should remain available for local control while independent cloud
  diagnostic entities remain cloud-specific.
- Exercise no-ACK Matter write (must NOT send cloud command); verify cloud
  fallback only before local write. Matter-only independent fan mode is hidden.
- Never make test changes to live setpoints or HVAC modes without supervised
  reversible device-level confirmation.

## Test-readiness safety hardening

- A Matter write now performs an actual `read_attribute` operation before the
  write rather than trusting an old `get_node` subscription snapshot. This
  read must return the exact attribute and numeric value or no write starts.
- Already-matching setpoints/modes short-circuit without an unnecessary HVAC
  write. After a possibly transmitted write, any uncertain ACK blocks all
  automatic cloud fallback.
- Local writes share the legacy cloud write lock. A pending cloud confirmation
  prevents a local command from being queued or racing the cloud control.
- In Matter-only mode, TURN_ON is not offered from stale cloud history.
  Only a genuinely observed previous local non-Off mode may be restored.
- Cloud-derived humidity and fan state are explicitly marked cloud-reported.
  These attributes must not be interpreted as local Matter telemetry.

## Hardware verification correction: Matter snapshots vs live reads

Matter Server's `get_node` is a server-maintained cache. We now perform
an actual `read_attribute` of the Thermostat system mode on every local
state refresh; this is used as a reachability check before cloud-to-local
fallback. Every command separately reads its destination attribute before
sending a write and skips the write when that attribute is already at target.

The protocol now respects Thermostat `MinSetpointDeadBand` attribute 0x0019
in tenths of a degree Celsius and refuses a requested target that would
silently move the opposite target. See Matter Application Clusters §4.3.
No hardware-based feature-map assumption or fan-control claim was added.

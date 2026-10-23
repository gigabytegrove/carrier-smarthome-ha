# Carrier SmartHome v0.5.7b1 — Experimental Local Matter Test Build

**Purpose of this update:** introduce user-selectable **local Matter HVAC control alongside existing Carrier cloud control**. This build is designed for hardware evaluation and is **not production-verified**. Stable v0.5.6 remains unchanged.

## Included in this test build

- Explicit per-thermostat **Cloud only**, **Matter only**, and **Prefer Matter** settings under Carrier SmartHome → Configure. Existing accounts default to Cloud only without migration of existing entity IDs or credentials.
- Commissioned OHF Matter Server WebSocket integration, with Carrier certified VID 4334 / PID 2048 and thermostat endpoint validation. Physical identity remains owner-confirmed; model identity alone is not proof that two thermostat records refer to the same physical unit.
- A single existing Home Assistant climate entity for the thermostat; local system mode and thermostat temperature/heating/cooling setpoints, conversion between Celsius and Fahrenheit, and independently reported cloud telemetry.
- Actual local read-before-write of the intended attribute, a maximum of one Matter write per requested change, and readback confirmation. Uncertain local writes **never** cause automatic Carrier cloud retries.
- Shared Matter/cloud HVAC write exclusion, rejection of queued commands, conditional cloud fallback only before a Matter write, and suppression of unsupported independent Matter fan control and non-atomic two-setpoint changes.
- Thermostat deadband/limit protections to avoid moving a second target unexpectedly.
- Privacy-limited read-only `tools/check_matter_readiness.py` probe plus isolated protocol, routing, runtime and fake-server tests. No network/host changes required to run the probe.

## Known test limitations

- **Requires** an independently installed OHF Matter Server and a *commissioned* physical thermostat. Commissioning codes, fabrics and device setup are handled exclusively by that server. We have not verified commissioning on the owner's hardware.
- **Cold startup still depends on Carrier cloud authentication/device discovery**, even for the Matter-only control preference. Local operation can continue during later cloud polling failures **while the integration is already loaded**, provided Matter remains responsive.
- Independent Matter fan control is not implemented. In Matter-only mode it is hidden. In Matter-preferred mode, independent fan commands use Carrier cloud.
- Cloud-reported humidity/fan diagnostics must not be interpreted as freshly sampled Matter readings.
- Home Assistant-on-hardware testing and real reversible Heat/Cool/Off/setpoint testing have not been performed in the development environment.
- Matter Server WebSocket access should be restricted to the trusted LAN; plain `ws://` is not encrypted or authenticated.

## Recommended testing sequence

1. Keep existing stable v0.5.6 available for rollback and record the old installed component version.
2. Verify Matter Server and VLAN 30 IPv6 reachability. Run the read-only probe in `docs/MATTER_READINESS.md`.
3. Commission and identify the correct thermostat node, then configure Matter only (or Prefer Matter) in the integration.
4. Compare Matter temperature and system mode against the physical thermostat **without sending any HVAC command**.
5. Under supervision, perform one reversible change at a time and validate the physical state, both HA display and cloud synchronization. Test network interruptions without issuing surprise writes.
6. If the controller is unavailable, restore Cloud only or revert the prior component. Report anonymized logs, never pairing secrets.

**Version:** `0.5.7b1`. **Branch:** `feature/matter-dual-transport-foundation`. No GitHub Actions or GitHub Issues were created.

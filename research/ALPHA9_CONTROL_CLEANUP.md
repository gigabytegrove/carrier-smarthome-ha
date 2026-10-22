# Alpha 9 — consolidation and release audit

Motivation: owner feedback identified excessive per-alpha accumulation and confusing inability to access HVAC mode/fan controls even with a recognized HA thermostat. The previously developed extra `select.py` would duplicate climate mode/fan and was removed before publication. Canonical controls are the climate entity and one optional HVAC Power switch.

## Integration source changes

- `const.PLATFORMS` reduced to the four intended platforms: climate, sensor, binary_sensor, switch.
- `control.py` uses one preflight and readback implementation for mode, fan and setpoints. All writes acquire a coordinator-scoped lock, check latest cloud online status, send exactly one mutation and verify three bounded reads. No blind retries.
- Fan experimental values limited to Auto/On. Circulation is not guessed or enabled; no proven physical fan write yet.
- Fresh Carrier setpoint limits are revalidated after the preflight poll.
- Config options validate dependency of setpoint control on HVAC mode/power control. New entries store all opt-out values explicitly.
- Optional last-cloud-reported diagnostic sensors are disabled in the HA entity registry by default for new installs, reducing activity and controls clutter without deleting existing owner settings.
- README and HACS docs rewritten to present current behavior and evidence rather than obsolete alpha warnings. Changelog holds version history.
- LAN PowerShell wrapper no longer exposes the private thermostat MAC suffix as a default; the actual IP and fresh Omada export must still be verified before any probe.

## Evidence and remaining boundaries

- Native cloud login, device MAC identity and read path were owner-verified. A physical Wi-Fi disconnect before Alpha 6 correlated with the cloud initially reporting offline then online after restart.
- Official app changed cooling target and both GraphQL queries observed the change. This is **not** proof that HA's own mutation works; all HA write paths remain experimental and disabled until opt-in.
- Offline regression tests include mode and fan via climate, power switch, no duplicate select, concurrent writes, freshest cloud limit, non-repeated mutations and disconnect blocking.
- Local TCP protocols and proprietary LAN write operations remain unproven. No Matter.

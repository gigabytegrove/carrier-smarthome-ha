# Carrier SmartHome 0.1.0a3 — offline research & integration hardening

**Date:** 2026-10-22. **Transport:** native Carrier SmartHome GraphQL only; **no Matter support.**

## What the owner has actually proven live

1. The Carrier `assistedLogin` request succeeded with the owner's account.
2. `getEntryLevelSystems` returned exactly one entry-level device, with one zone.
3. An independent APK-derived `getEntryLevelSystemData` query also succeeded.
4. Both queries reported cloud model `TSTATCCEEF-01`. Physical printed model is `TSTATCCEWF-01`; **this is an unresolved backend-vs-label discrepancy**, not an automatic model conversion.
5. Both queries reported `connection.isConnected=false`. Room temperature, humidity, HVAC mode and setpoints were present, but they **might be cached/stale**. This is not proof of a connected thermostat or a successful control operation.
6. No write/mutation has been executed against the owner's thermostat; the alpha remains read-only by default.

## What changed from alpha 2

- `api.py`: parse bounded HTTP 429 Retry-After; avoid tight polling loops with `CarrierRateLimitError`. Treat explicit GraphQL `UNAUTHENTICATED`-class error *codes* as expired auth without exposing server message text.
- `coordinator.py`: forward rate-limit delay to Home Assistant's 2025+ coordinator retry system.
- `api.py`: reject NaN/infinite setpoints, boolean zone indices and overlong serial strings before any request.
- HA platforms: add new zones/devices when Carrier's account listing changes, without duplicating existing entity identities; unregister listeners when the entry unloads.
- `diagnostics.py`: privacy-minimized HA diagnostics with anonymous device indices and cloud state, marked stale when Carrier reports offline.
- `tools/Observe-SmartHomeCloud.py`: optional 1-12 read-only polls, comparing anonymized climate changes and connectivity; bounded interval; no secrets or serials in output.
- `tools/Probe-SmartHomeFeatures.py`: optional read-only schedules/reminders/notification-preferences GraphQL queries from APK, reporting only availability and record counts. These calls have NOT been proven against the owner's account yet.
- `tools/Probe-VerifiedCarrierLAN.py`: compares a *current* connected Omada client against the known hardware label suffix before six bounded TCP connect checks; refuses offline/historical IPs. No HTTP GET, MQTT, Matter or control commands.
- New tests for all of the above; existing VLAN/Omada research preserved.

## Limits and test requirements

- All new tests are offline/mock tests; they do not prove HA bootstrap on a real HA instance, successful Carrier capability queries, local TCP connectivity or heating/cooling writes.
- Runtime must be tested on the target Home Assistant release; no instance credentials are available in this development environment.
- When cloud says offline, the climate entity must remain unavailable. The separate connectivity entity still reports offline.
- Device match and IP were identified in a previous Omada export; the owner device was offline then. Its old last-known IP must **not** be used as proof of current address.
- **No Matter, no reverse proxy, no local MQTT assumptions, no provisioning / BLE write attempts.**

## First owner-side tests when available

```
# Windows PowerShell in a checked-out repo. First run Test-Cloud.ps1 to create venv.
.\tools\Test-Cloud.ps1 -SkipDependencyInstall
.\tools\Observe-Cloud.ps1 -Samples 3 -IntervalSeconds 60
.\tools\Probe-CloudFeatures.ps1
.\tools\Probe-VerifiedCarrierLAN.ps1 -PlanOnly
```

The feature probe and observer prompt for credentials locally. Nothing is committed or uploaded automatically. The local probe requires a fresh Omada export whose thermostat entry is actually connected. **Do not enable experimental writes until cloud state is online and reported values match the physical thermostat.**

# Alpha 6: physical thermostat ↔ Carrier native cloud mismatch

## Confirmed owner-side evidence on October 22, 2026

- Official Carrier SmartHome phone app operates the physical TSTATCCEWF-01.
- Owner's cloud test authenticates and returns a single entry-level system, zone 0, cloud model string `TSTATCCEEF-01`.
- The hardware MAC in `user.locations.entryLevels` matches the physical unit's WLAN MAC; actual MAC is intentionally **not recorded in the public repo**.
- Three independently queried `isConnected` fields (`entryLevelSystems`, `entryLevelSystem`, and `user.locations.entryLevels`) are all `false`.
- Repeat GraphQL readings reported room 73 °F, heat 70 °F, cool 76 °F, humidity 47%, outside 51 °F, `mode=off`; no device-generated timestamp.
- Therefore authentication and identity are no longer plausible explanations for these conflicting signals. Phone-app control is affirmative evidence of some working proprietary Carrier control path, but there is **no proof yet** that the GraphQL query returns fresh data, and no owner-tested Home Assistant write.

## This pass

`tools/Compare-AppChange.ps1` and `.py` provide an opt-in, interactive A/B test: read baseline from both GraphQL operations, wait for a manual one-degree setpoint change made ONLY through the official app, take at most six read pairs at 20-second intervals (configurable), prompt for manual restoration in the official app, and verify the return to baseline. The tool does not make ANY GraphQL mutation, local call, or Matter request. It keeps account/hardware identifiers out of output, sends credentials and serials only as part of required authenticated Carrier reads, avoids file persistence, and does not interpret `isConnected=false` as definitively unreachable.

**Decision table:**

| Observed result | Meaning | HA follow-up |
|---|---|---|
| App adjustment appears in account and detail reads | Both cloud views can track at least one app-side change | Explore user-approved reversible native API write validation; connection flag still unreliable |
| Appears only in one GraphQL read | There is a per-query cache or update difference | Prefer and further test the responsive query |
| Appears in neither read | Queries may be cached or app uses another native transport | Investigate app's AWS IoT/realtime messages and read subscriptions; do not enable writes |
| Restore does not return to baseline in cloud | Unresolved backend/stale-state problem | Recheck the official app and block writes |

The owner is responsible for restoring any app-side change, even if interrupted. No device was tested from the developer's environment.

# Alpha 5: app functional, Carrier GraphQL reports `isConnected=false`

## Verified observations (2026-10-22)

- Owner successfully authenticated to Carrier SmartHome native GraphQL.
- Entry-level list and detail queries both returned one cloud thermostat, one zone.
- Returned model string was `TSTATCCEEF-01`, while physical label reads `TSTATCCEWF-01`.
- Carrier cloud listing and detail reported `connection.isConnected=false`.
- Three reads over two minutes returned unchanged, plausible temperatures/setpoints/humidity.
- **Owner reports the Carrier phone app can currently control the physical thermostat.**

**Interpretation:** GraphQL access to a record is proven; physical device freshness, and whether this is the exact currently installed unit, remain unresolved. A false API flag could be stale, derived from a different backend, or refer to a different thermostat. The phone app's working control path does not independently establish whether it uses the same cloud queries or proprietary local communication.

## Alpha 5 implementation

- Home Assistant climate can present cloud-returned temperature, targets and mode whenever polling succeeds and a zone exists. Attributes prominently mark freshness `unverified_may_be_cached` and show Carrier's unverified connection flag. This avoids an always-unavailable thermostat entity merely because Carrier's status field reads false.
- **No false assertion of live device connectivity:** live humidity/outdoor sensors still require Carrier's online flag. Separately named *last cloud-reported* diagnostic sensors expose the cached/unverified measurements without creating false HA statistics.
- Experimental writes remain opt-in **and additionally require confirmed Carrier online status**. The HA mode/target capabilities are suppressed while that status is false. The new API-readable connectivity sensor indicates API polling success, not physical device reachability.
- Read-only owner-side cross-check reads the established systems listing, previously verified detail endpoint, and (if available) an independent Android app-shaped `getUserWithDevices` query. It compares a physical MAC locally without printing hardware identifiers, device IDs, token, account or network information. Query rejection is classified as unavailable, not offline.

## Next owner-side test

Run `tools/Verify-CarrierConnectivity.ps1 -ExpectedMac '<thermostat MAC>'` in the existing isolated PowerShell cloud environment. The expected MAC is *not committed* to GitHub, not printed by the diagnostic, and not stored in any report file. A real hardware match would strengthen the attribution of the returned cloud record to the physical unit; contradictory status flags would suggest a status-source difference. Neither result alone proves telemetry freshness.

After confirming identity, one safe manual phone-app target change followed by read-only cloud queries, followed by restoring the original value in the app, can demonstrate whether the cloud record tracks the owner's actual device. The owner controls any HVAC changes; this project does not change settings automatically.

**No Matter, no proprietary LAN commands, no third-party account access.**

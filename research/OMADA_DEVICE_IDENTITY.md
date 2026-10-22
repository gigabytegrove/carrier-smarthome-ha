# Carrier TSTATCCEWF-01: identification in Omada controller

## Evidence from owner-supplied export (October 22, 2026, 08:14 local time)

- Export contains OnlineClient, OfflineClient, PastConnection files. These are *private* and are not stored here.
- Exact matching thermostat label **serial equals exported hardware MAC**; only the final suffix `144B` is retained here.
- Omada client name: `Smart Thermostat-144B`.
- Last recorded IP: **`redacted.invalid`** on VLAN 30 (`GG Smart Home`), Hallway AP, 2.4 GHz.
- The thermostat was **offline at export time**, with last online record at **08:08:40 local, October 22, 2026**. Its presence in the older ICMP scan does not prove it is presently reachable.
- Thirteen historical connection records for the same exact MAC include **seven distinct IPs** across earlier leases. This proves IP can change; never hardcode `.51` in the integration.
- A *different* historical client also used `.51`; IP address alone cannot identify a device.
- The export includes a **different** named thermostat (`Smart Thermostat-702B`) in the offline table, with no last IP. The analyzer intentionally refuses to choose automatically between names unless the known label suffix `144B` is supplied.
- `redacted.invalid` is explicitly identified as `Sainlogic-6AE8D8` in the current online export. It is **not** a viable Carrier identification by IP/vendor alone.
- Other historical-known devices in `redacted.invalid/24` can be cross-referenced by MAC when needed, but must not be treated as permanent IP exclusions.

## Security and architecture locks

1. **No Matter integration, bridge, or fallback.** Use the Carrier SmartHome cloud API first; research proprietary LAN functions in parallel, if they are supported by this hardware.
2. Do not commit the owner's full device MAC, serial, QR codes, onboarding/PIN codes, AP/client inventories, HAR tokens, or raw Omada ZIP.
3. Read-only discovery only until the correct API/identity and auth are verified.
4. Historical offline IPs are clues, not confirmed active local endpoints. Verify current Omada client/lease against exact MAC before any directed protocol test.
5. Never imply an `80/443/1883/8883/8080/8443` port scan proves or disproves a proprietary LAN API.

## Repeatable analysis

`tools/Review-OmadaExport.ps1` finds the latest `Client_*.zip` in Downloads and reads the latest `iot-private.json` automatically, entirely offline. `tools/omada_identity.py` is the standard-library analyzer. On a ZIP containing several named thermostats it refuses to choose without `--suffix` or `--mac` supplied locally. The Windows wrapper supplies the verified suffix `144B` for this exact research unit. This identifier must never be added to source control.

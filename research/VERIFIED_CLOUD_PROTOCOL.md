# Carrier entry-level native-cloud protocol — confidence ledger

## Source categories

- **A — Observed owner account:** reported successful 2026-10-22 PowerShell native cloud tests.
- **B — Recovered Android XAPK:** Carrier SmartHome 1.2.42 bytecode and Android production BuildConfig. Strings alone are not executed-code proof.
- **C — Independent open source:** MIT-licensed `dahlb/carrier_api` entry-level Python implementation; useful cross-check, not owner live device proof.
- **D — Product regulatory/manual:** UEI FCC ID `MG3-J1TH024`, Carrier quick start states BLE used during Wi-Fi onboarding. BLE setup does **not** establish ongoing proprietary LAN control.

## Positive live evidence (A)

| API step | Result | Caution |
|---|---|---|
| POST `/graphql-no-auth` `assistedLogin` | PASS | Password remains private; no tokens persisted in repo |
| POST `/graphql` `getEntryLevelSystems` | PASS | Returned one single-zone entry-level thermostat |
| POST `/graphql` `getEntryLevelSystemData` | PASS | Detail agreed on model, zone and disconnected state |
| Temperature, humidity, heating/cooling setpoints, mode | VALUES RETURNED | Could be stale: `isConnected=false` |
| Reversible setpoint mutation | UNTESTED | Real HVAC write must not be performed without owner approval |
| WebSocket events | UNTESTED | URL present in app, runtime subscription unverified |
| Schedule/reminder/prefs queries | UNTESTED | APK documents recovered; optional read-only probe exists |
| Proprietary on-LAN API | UNPROVEN | Wi-Fi/MQTT code string alone is inadequate evidence |

## Backend string discrepancy

Physical housing label `TSTATCCEWF-01`; owner account GraphQL `model` field returns `TSTATCCEEF-01`. The numerical model suffix is not enough to assert these two designations are equivalent. The stable identity for entity registration is the account-returned serial; keep the raw cloud model in the Device Registry until Carrier confirms mapping. No fake relabeling and no model-name-based feature flags.

## Cloud endpoint evidence (B + A)

- `https://dataservice.infinity.iot.carrier.com/graphql-no-auth` — authenticated account login **observed**.
- `https://dataservice.infinity.iot.carrier.com/graphql` — entry-level thermostat data **observed**.
- `https://sso.carrier.com/oauth2/default/v1/token` — compiled OAuth refresh endpoint, code modeled from existing Carrier client, not yet exercised live by our owner.
- `wss://realtime.infinity.iot.carrier.com` — compiled URL, not yet exercised live by our owner.
- `a2pznvrwmtzhom-ats.iot.us-east-1.amazonaws.com` — compiled AWS IoT endpoint; remote service, **not a thermostat-local API**.

## Local boundary (A + B + D)

- Omada identified the physical thermostat through a MAC/label match; its most recent export marked it disconnected. Previous IPv4 lease is historical only.
- The Quick Start Guide instructs onboarding using a Bluetooth connection between SmartHome and thermostat. This likely explains *some* BLE/session-key operations in the APK, but does not establish whether the app uses a proprietary runtime-local transport.
- Do not treat local MQTT port 1883/8883, generic `LocalControl` symbols, or a Matter-enabled Wi-Fi radio as proof of an on-device API.
- The owner explicitly prohibits Matter for this project. Native Cloud is the proven communication channel; proprietary LAN research proceeds independently.

## Security

- User-owned device only. No bypassing the Carrier login flow or removing TLS protections.
- Do not log credentials, hardware identifiers, auth tokens, HAR exports, Omada raw inventories, Wi-Fi details or onboarding QR/PIN.
- Read-only APIs and bounded connect probes first. Avoid modifying HVAC operation until tested with operator present.

## External references

- Carrier product page: https://www.carrier.com/us/en/residential/smart-thermostats/tstatccewf-01/
- UEI FCC grant: https://fccid.io/MG3-J1TH024
- Carrier Quick Start: https://www.manualslib.com/manual/3690658/Carrier-Tstatccewf-01.html
- Open-source API client: https://github.com/dahlb/carrier_api
- Home Assistant climate entity reference: https://developers.home-assistant.io/docs/core/entity/climate/

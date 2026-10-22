# Evidence ledger

## 2026-10-21 — Cloud-first APK follow-through

- **APK_STATIC CONFIRMED:** 140 GraphQL operation/fragment definitions: 58 queries, 77 mutations, 5 fragments. 137 standalone definitions; three partial fragments retained separately, not executable. Full files and typed-variable catalog are in `research/graphql/`, `graphql-catalog.json` and `GRAPHQL_CATALOG.md`.
- **APK_STATIC CONFIRMED:** Separate `entry_level` and `infinity` operation sets; TSTATCCEWF-01 backend mapping is still unverified.
- **APK_STATIC CONFIRMED:** `classes3.dex` contains `https://dataservice.infinity.iot.carrier.com`, `https://platform.iot.carrier.com`, Okta authorize/token URLs on `sso.carrier.com`, and `wss://realtime.infinity.iot.carrier.com`.
- **APK_STATIC CONFIRMED:** Hermes includes runtime key names `ENTRY_TIER_ENV_URL`, `HASURA_API_URL`, `REST_API_URL`, `OKTA_TOKEN_URL` and GraphQL route strings `/graphql`, `/graphql-no-auth`. These key names are not actual URL values.
- **APK_STATIC CONFIRMED:** LocalControl/MQTT symbols exist in Hermes; no demonstrated link to this thermostat.
- **IMPLEMENTED:** Automated public cloud configuration inspection, auto LAN neighbor/port discovery for Windows, complete catalog generation, and offline tests.
- **NOT VERIFIED:** Active production entry-level GraphQL hostname, account login/token refresh, serial classification, status values, cloud control, local thermostat IP/MAC, Matter pairing, or proprietary local API availability.

## 2026-10-21 — Foundation

- Extracted APK Hermes operations and built cautious manual cloud/local probes.
- Results for a real thermostat and live account were not obtained.

Never put unredacted private device, account, token or network data into Git.

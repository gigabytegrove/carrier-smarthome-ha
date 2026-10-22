# Carrier SmartHome Android — Offline API research

**Target thermostat:** Carrier TSTATCCEWF-01  
**Application:** `com.carrier.home` / SmartHome 1.2.42 / Android version code 854  
**Evidence source:** User-supplied `SmartHome_1.2.42_APKPure.xapk`  
**Method:** Static inspection of XAPK manifest and the base APK's Hermes v96 JavaScript string table. No account, device, server or thermostat was contacted.

## Results

- XAPK includes **20 APK components**: one base APK and 19 resource / ABI splits.
- Application uses **React Native / Expo 54** and a **Hermes v96 JavaScript bundle**.
- Hermes parsing recovered **80,776 uniquely indexed JavaScript strings**.
- **140 GraphQL operation/fragment definitions** extracted: 58 queries, 77 mutations, 5 fragments. Of these, **137 are standalone document strings**; 3 introspection-related fragment strings include leading bytes from a preceding context and are saved as `*.partial.txt` instead of being misrepresented as runnable GraphQL.
- GraphQL route literals: **`/graphql`** and **`/graphql-no-auth`**.
- API configuration key literals: `API_URL`, `REST_API_URL`, `HASURA_API_URL`, `WEBSOCKET_API_URL`, `OKTA_TOKEN_URL`, `ENTRY_TIER_ENV_URL`, and related identity-provider names. These are **configuration key names, not recovered endpoint hostnames**.

## Important finding: separate thermostat API families

The same application includes legacy **Infinity** operations (`infinitySystems`, `infinityProfile`, `infinityStatus`, `infinityConfig`, `updateInfinityZoneConfig`) and newer **Entry Level** operations (`entryLevelSystem`, `entryLevelSchedules`, `updateEntryLevelSystem`, `updateEntryLevelZone`, `updateEntryLevelComfortProfile`). Their coexistence does **not** establish that both API families can control any one thermostat.

**TSTATCCEWF-01 applicability:** The entry-level family is a **strong candidate** for this model based on its thermostat controls, scheduling, BLE setup support, and app product structure. The XAPK does not contain the literal `TSTATCCEWF-01` in its decoded Hermes string table. A live authenticated device listing is still required to establish the model-to-backend mapping.

## Verified GraphQL queries and mutations

All operations listed below were found **verbatim** in the decoded JavaScript string table. Open their `.graphql` files for exact field selections and required GraphQL *input type names*.

| Function | Operation name | File name identifier |
|---|---|---|
| Discover account devices | `getUser` / `getUserWithDevices` | `query_getUser_821.graphql`, `query_getUserWithDevices_1169.graphql` |
| Read newer-style thermostat | `getEntryLevelSystemData` | `query_getEntryLevelSystemData_1099.graphql` |
| Read schedules | `getEntryLevelSchedules` | `query_getEntryLevelSchedules_690.graphql` |
| Update HVAC zone | `updateEntryLevelZone` | `mutation_updateEntryLevelZone_339.graphql` |
| Update device-level settings | `updateEntryLevelSystem` | `mutation_updateEntryLevelSystem_461.graphql` |
| Update comfort profiles | `updateEntryLevelComfortProfile` | `mutation_updateEntryLevelComfortProfile_1107.graphql` |
| Update individual schedule entry | `updateEntryLevelSchedule` | `mutation_updateEntryLevelSchedule_410.graphql` |
| Create schedule batch | `createEntryLevelScheduleBatch` | `mutation_createEntryLevelScheduleBatch_1112.graphql` |
| Remove schedule | `removeEntryLevelSchedule` | `mutation_removeEntryLevelSchedule_463.graphql` |
| Read maintenance reminders | `getEntryLevelReminders` | `query_getEntryLevelReminders_825.graphql` |
| Read Entry Level notification prefs | `getEntryLevelNotificationPrefs` | `query_getEntryLevelNotificationPrefs_1086.graphql` |
| Update Entry Level notifications | `updateEntryLevelPushNotificationPrefs` | `mutation_updateEntryLevelPushNotificationPrefs_520.graphql` |
| BLE setup session key | `getEtBleSessionKey` | `query_getEtBleSessionKey_1171.graphql` |
| Generic device command | `sendCommand` | `mutation_sendCommand_696.graphql` |
| Start retrieving auth token | `fetchAccessToken` | `mutation_fetchAccessToken_813.graphql` |
| Assisted login token response | `assistedLogin` | `mutation_assistedLogin_1001.graphql` |
| Read old Infinity thermostat | `getInfinitySystem` | `query_getInfinitySystem_587.graphql` |

**Do not automatically invoke** `sendCommand`, `updateEntryLevelZone`, or setup/session operations without confirming the actual input schema, account permissions, and their effect on this model.

## Confirmed fields exposed by `getEntryLevelSystemData`

The GraphQL document requests:

- **Temperature / humidity:** `zones[].rt`, `zones[].rh`, `zones[].clsp.current`, `zones[].htsp.current`, high/low setpoint limits.
- **HVAC / fan state:** `zones[].mode`, `zones[].system_type`, `zones[].subsystem_type`, `zones[].stage_status`, `zones[].fan_mode`, `zones[].fan_type`, heating/cooling cycles.
- **Scheduling:** `zones[].current_scene_name`, `zones[].current_schedule_id`, `zones[].schedule_enabled`, `zones[].schedule[]` with day/start time/heat/cool setpoints.
- **Comfort profiles:** `zones[].comfort_profile.{wake,home,away,sleep}.{htsp,clsp}`.
- **Usage/runtime:** `day_cool_equip_run_time`, `day_heat_equip_run_time`, `hour_aux_heat_run_time`, `hour_emg_heat_run_time`.
- **Connectivity:** `connection.isConnected`, Wi-Fi signal and SSID, `firmware`, `hw_version`.
- **Advanced options:** ventilation, humidification/dehumidification, hold end time, display settings, InteliSense subfields.

**Caution:** A field included in a request does not mean the server fills it in for every model or that the user can control it. Home Assistant entities must be created from demonstrated values and supported commands.

## Authentication and transport

- String-table evidence includes REST and GraphQL API configuration, GraphQL document transport, WebSocket-related symbols, and an `graphql-transport-ws` protocol identifier.
- OAuth and provider-related string evidence includes **Okta**, **Microsoft Entra**, and GraphQL token-related mutations.
- The precise Carrier production API hostname, HTTP headers, OAuth grant shape, endpoint-to-GraphQL mapping, token refresh behavior, and subscription format were **not established** from the static-only artifact.
- The `resources.dataservice.infinity.iot.carrier.com` URLs in the bundle point to static manuals, FAQ material, and videos. **They are not proven API request endpoints.** Likewise `my.carrier.com` links are not proof of the modern Android app's API hostname.

## Home Assistant integration requirements before a deployable build

1. Confirm one authenticated `getUserWithDevices` response containing a TSTATCCEWF-01 and determine whether it appears under `entryLevels`, `systems`, or `devices`.
2. Resolve `REST_API_URL` / `HASURA_API_URL` for the active carrier production environment, then test `getEntryLevelSystemData` and inspect returned values.
3. Establish a supported login and refresh flow for the device owner without exposing credentials in log files or software configuration.
4. Discover input object shapes for `EntryLevelZoneInput`, `EntryLevelSystemInput`, and `EntryLevelComfortProfileInput`; the mutation operation strings only identify input **types**, not all their fields.
5. Validate reversible read/write changes on the user-owned thermostat with rate limits and error handling. Do not change diagnostic, installer, safety, or unrelated household settings automatically.
6. Determine whether a WebSocket carries state changes; implement polling fallback and avoid cloud overload.
7. Add Home Assistant config and reauthentication flows, a `DataUpdateCoordinator`, one climate entity per verified zone, and supported diagnostic sensors. Avoid claiming Matter-based functionality is equivalent to proprietary cloud API features.

**Status:** Static API surface mapped. **Not yet a working authenticated client or installable Home Assistant integration.** No live appliance or Carrier account testing was performed.

## Project files

- `graphql-index.csv` / `.json`: indexed operation list with confidence on standalone-document completeness.
- `graphql/`: original operation document strings from Hermes; includes the three explicitly marked partial fragments.
- `transport-configuration-hints.json`: exact endpoint-path and environment-variable names recovered from the APK.
- `package-metadata.json` and `summary.json`: independently verifiable app and extraction metadata.
- `analyze_xapk.py`: repeatable, stdlib-only offline parser for the original uploaded XAPK (validated only for Hermes v96).

This research package deliberately omits APK binaries, media assets, user passwords, tokens, and any automatically inferred production hostnames.

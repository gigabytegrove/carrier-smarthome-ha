# Cloud protocol: findings, implementation, and validation gates

## Proven from installed Carrier SmartHome 1.2.42 XAPK

**App identity:** `com.carrier.home`, version code 854. Main app in Hermes bytecode v96. GraphQL string documents are the exact operation content recovered from the app, not generated examples.

- Route literals: `/graphql`, `/graphql-no-auth`.
- Environment keys: `API_URL`, `REST_API_URL`, `HASURA_API_URL`, `WEBSOCKET_API_URL`, `ENTRY_TIER_ENV_URL`, `OKTA_TOKEN_URL`, `OKTA_CLIENT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_TENANT_URL`, `SOCIAL_LOGIN_ISSUER`.
- Native service literals: `https://dataservice.infinity.iot.carrier.com`, `https://platform.iot.carrier.com`, `https://sso.carrier.com/oauth2/default/v1/authorize`, `https://sso.carrier.com/oauth2/default/v1/token`, and `wss://realtime.infinity.iot.carrier.com`.
- Separate `infinity` and `entryLevel` GraphQL operation families exist in the same app.

**Important:** An endpoint literal is not proof of selected runtime configuration. The old publicly documented carrier_api client already uses `dataservice.infinity.iot.carrier.com/graphql`; that does not verify it for a TSTATCCEWF-01. None of the available data proves the current user's device responds to the Entry Level API yet.

## Direct production BuildConfig mappings

DEX static field values explicitly configure `API_URL=https://dataservice.infinity.iot.carrier.com`, `REST_API_URL=https://platform.iot.carrier.com`, `OKTA_TOKEN_URL=https://sso.carrier.com/oauth2/default/v1/token`, `WEBSOCKET_API_URL=wss://realtime.infinity.iot.carrier.com`, and `ENTRY_TIER_ENV_URL=a2pznvrwmtzhom-ats.iot.us-east-1.amazonaws.com`. The last is an AWS IoT ATS hostname consistent with entry-level device MQTT provisioning or state communications. It is **not a LAN IP**. This evidence does **not** prove that this exact thermostat uses these services at runtime. See `BUILD_CONFIG_EVIDENCE.md`.

## Actual useful entry-level operation documents

The following exact document files are in `research/graphql/entry_level/`:

| Operation | Type | Purpose |
|---|---|---|
| `getEntryLevelSystemData($serial: String!)` | query | Full status, zones, telemetry, equipment, settings |
| `getEntryLevelSchedules($serial: String!)` | query | Device schedules |
| `getEntryLevelReminders($serial: String!)` | query | Reminders |
| `getEntryLevelNotificationPrefs($serial: String!)` | query | Notification preferences |
| `runtimeUsageEntryLevel($input: GetRuntimeUsageInput!)` | query | Runtime usage |
| `getEtBleSessionKey($input: EntryLevelSessionInput)` | query | BLE setup helper, **do not invoke** |
| `updateEntryLevelZone($input: EntryLevelZoneInput!)` | mutation | Potential basic thermostat controls |
| `updateEntryLevelSystem($input: EntryLevelSystemInput!)` | mutation | Potential device settings |
| `updateEntryLevelComfortProfile($input: EntryLevelComfortProfileInput!)` | mutation | Wake/Home/Away/Sleep profiles |
| `updateEntryLevelSchedule($input: UpdateEntryLevelScheduleInput!)` | mutation | Schedule change |
| `createEntryLevelSchedule($input: CreateEntryLevelScheduleInput!)` | mutation | Schedule create |
| `createEntryLevelScheduleBatch($input: CreateEntryLevelScheduleBatchInput!)` | mutation | Schedule batch |
| `removeEntryLevelSchedule($input: RemoveEntryLevelScheduleInput!)` | mutation | Remove schedule |

*Operation presence does not establish API authorization for a device or which fields are mutable.*

## Auth research

The app has Okta and Microsoft Entra hints, and `fetchAccessToken` / `assistedLogin` GraphQL mutations returning `access_token`, `expires_in`, and `refresh_token`. Their input object types are named but field contents, refresh handling, and which provider applies to owner accounts are **not** known. We will not invent passwords-as-GraphQL-input or hardcode OAuth client secrets.

Use a securely captured, user-authorized web login (or mobile app traffic metadata) to learn endpoint routing and grant configuration. `tools/analyze_har.py` deliberately discards values and response bodies. It provides enough to identify endpoints and operation shapes, but NOT sufficient to reproduce authentication. A later authenticated test will necessarily require an owner-approved mechanism without committing credentials.

## Implementation already in source

`tools/cloud_protocol.py` includes:

- Carrier-domain HTTPS allowlisting and `/graphql` route checks;
- no cross-host HTTP redirects;
- injected token provider rather than embedded credentials;
- bounded JSON response size and structured failures;
- read-only operation enforcement (mutations rejected before any network request);
- no raw server-error values in exceptions.

`tools/discover_cloud.py` obtains public frontend resources, extracting potential runtime configuration from Carrier's web portal with no account activity. The browser portal may be a different frontend from the Android app; findings require attribution.

## Actual cloud development gates

**C1:** Resolve production SmartHome host and selected login mechanism. **Unverified.**

**C2:** Authenticate a test owner account with correct renewal strategy and safe storage. **Unverified.**

**C3:** Match `getUserWithDevices` entry to a TSTATCCEWF-01, verify model and serial without publishing them. **Unverified.**

**C4:** Read and normalize thermostat climate status (modes, heat/cool setpoints, temperatures, humidity, connectivity). **Unverified.**

**C5:** Update and restore a single setpoint, respecting device limits and verifying feedback, without changing installer/safety settings. **Unverified.**

**C6:** Implement HA config/reauth flows, coordinator, entities and tests. **Not yet built.**

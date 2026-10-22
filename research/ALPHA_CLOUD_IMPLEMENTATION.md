# Native Carrier SmartHome cloud alpha: implementation and evidence

## New finding: existing independently implemented entry-level GraphQL support

`dahlb/carrier_api`, a public MIT-licensed research client, includes an `EntryLevelSystem` model and GraphQL methods `getEntryLevelSystems` and `updateEntryLevelZone`. Its client also documents how an authenticated user can call `assistedLogin` at `https://dataservice.infinity.iot.carrier.com/graphql-no-auth`, `getEntryLevelSystems` at `/graphql`, and refresh via `https://sso.carrier.com/oauth2/default/v1/token`. Our extracted SmartHome v1.2.42 APK corroborates the hostnames, authentication mutation, entry-tier schema and zone mutation. We implemented a self-contained lightweight aiohttp client based on these observed interfaces; no runtime `carrier_api` dependency or Matter is used.

Source: https://github.com/dahlb/carrier_api/blob/main/src/carrier_api/api_connection_graphql.py (MIT). We reviewed the publicly available implementation but did not vendor its source files.

**Important:** Neither project has yet demonstrated that *this user's specific TSTATCCEWF-01 and account* authenticate and respond correctly. Every positive assertion about live connectivity requires a user-side smoke test.

## Alpha capabilities

- Home Assistant config flow accepting **Carrier account username and password**, no API URL, MAC or IP required.
- Native GraphQL `assistedLogin`, token expiry, concurrency-safe refresh, read-only `getEntryLevelSystems` discovery.
- HA shared 60s polling coordinator with reauthentication and startup retry.
- Actual cloud data-bound climate entities, connected binary sensors, humidity and outside-temperature sensors. No simulated entities.
- Experimental setpoint/mode write implementation based on `EntryLevelZoneInput`, **disabled by default** and opt-in via Home Assistant integration options. Fan writes and schedule writes intentionally deferred.
- Fully separate, existing VLAN and Omada research tooling remains available for proprietary LAN discovery.
- Standalone **read-only** smoke test accepts username/password interactively, prints counts and model names, never serials, LAN data or tokens.

## Verification gates for alpha

1. Offline tests and Python bytecode compilation — executed in build environment.
2. Run `tools/Smoke-TestSmartHomeCloud.py` on user network with their Carrier account; no writing.
3. Confirm `TSTATCCEWF-01` appears in `Reported models`, `Entry-level devices > 0`, and `Connected devices > 0`.
4. Install `custom_components/carrier_smarthome` under Home Assistant's `/config/custom_components` and restart HA.
5. Add integration through Settings > Devices & services > Add integration > Carrier SmartHome (Native Cloud Alpha). Complete Carrier account login.
6. Confirm cloud-reported temperature, humidity and mode match physical thermostat.
7. Only *after* state validation, enable experimental control in integration options and perform a single reversible test with HVAC equipment monitored. Require explicit user choice.

## Boundaries

The installed integration does not use Matter, a Matter bridge, or a Matter fallback. Local Wi-Fi connectivity and the Omada MAC identify the device but do not establish a proprietary LAN control protocol. The integration cannot claim locally functional controls or offline HVAC control yet. Login can fail if Carrier uses a different SSO method for this account; errors are explicit rather than bypassed.

**Secret handling:** User credentials remain on their own device/HA instance. HA's config entry persistence stores the account password for re-login; this is a current alpha limitation. The library keeps tokens in memory and does not write them to logs or GitHub. Do not upload raw diagnostic dumps.

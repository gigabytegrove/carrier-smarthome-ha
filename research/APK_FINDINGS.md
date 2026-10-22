# Verified APK observations — SmartHome Android 1.2.42

Provenance: user-provided `SmartHome_1.2.42_APKPure.xapk` (`com.carrier.home`, version code `854`) inspected offline with Hermes bytecode v96 string extraction. An APK is not a live session, and the app includes code for multiple product families. Nothing in this report establishes that a given symbol applies to TSTATCCEWF-01.

- React Native / Expo; recovered 80,776 Hermes JS strings.
- Recovered 140 named GraphQL operation/fragment definitions (58 queries, 77 mutations, 5 fragments), including 3 partial fragments. These counts refer to strings, not successful server API calls.
- Cloud transport clues: `/graphql`, `/graphql-no-auth`, `API_URL`, `REST_API_URL`, `HASURA_API_URL`, `WEBSOCKET_API_URL`, `ENTRY_TIER_ENV_URL`, `OKTA_TOKEN_URL`, `ENTRA_CLIENT_ID`. **These are keys and paths, not proven API hostnames.**
- Entry-level query: `getEntryLevelSystemData($serial: String!)` selects firmware, connectivity, zones (`rt`, `rh`, `mode`, `htsp`, `clsp`), schedule, comfort profiles, operating stages and runtime.
- Account discovery: `getUserWithDevices` exposes `user.locations.devices` and device type. Must test authenticated classification.
- Possible local code symbols: `LocalControlReqPacket`, `LocalControlReqCommand`, `SendLocalControlCommand`, `SendLocalControlCommandRead`, `SendLocalControlCommandWrite`, `sendLocalControlCommand`. They could be used for a different supported device category. **Do not claim proprietary LAN thermostat control without packet captures and proof.**
- Matter is a separate standardized local method, not proof of a local Carrier HTTP API.

Next evidence needed: router-confirmed IP/MAC; mDNS/port observations; verified authenticated cloud API host, nonsecret request shape and redacted response type structure. Store sanitized findings in STATUS.md and never upload secrets.

Additional login URL strings found in APK: `https://prod.consumerportal.carrier.com/login` and `https://pprod.consumerportal.carrier.com/login`. They appear to be consumer portal login pages, **not verified GraphQL API addresses**.

Full operation index, extracted GraphQL documents and reproducible Hermes extraction script are under `research/`. The original proprietary APK is intentionally excluded.

# Cloud-first, LAN-in-parallel validation plan

**Target**: TSTATCCEWF-01 / Carrier SmartHome 1.2.42 (`com.carrier.home`).

## Current evidence

| Question | APK evidence | Can act on it today? |
|---|---|---|
| Account lists devices | `getUserWithDevices`, `getUser` GraphQL documents | Document syntax yes; authenticated API request not yet |
| Thermostat status | `getEntryLevelSystemData(serial: String!)` | Document syntax yes; device backend not yet |
| Setpoint changes | `updateEntryLevelZone(input: EntryLevelZoneInput!)` | NO: input object fields and live behavior unverified |
| Thermostat settings | `updateEntryLevelSystem(input: EntryLevelSystemInput!)` | NO: mutation may have configuration side effects |
| Schedule/comfort profiles | Read and write GraphQL operations | Read research now; writes only after live schema validation |
| Login | Okta/Entra config names and embedded native SSO URLs | Candidate discovery only; **do not invent OAuth client IDs or grant** |
| API base host | Native APK contains IoT data/platform hosts; Hermes contains config key names | Public config discovery; not yet proven active GraphQL endpoint |
| WebSockets | Native realtime host and Hermes GraphQL WebSocket protocol | Candidate; not yet a connected stream |
| Proprietary LAN | LocalControl/MQTT symbols | Device applicability and framing unknown |
| Matter LAN | Model has Matter-over-Wi-Fi capability | Validate with official HA Matter controller, not emulated Matter stack |

## Next demonstrated milestones

**CLOUD 1:** Get verified Carrier web-client production configuration through `tools/discover_cloud.py` public asset discovery or an authorized session observation. Compare API hosts to native DEX candidates; do not conflate legacy Infinity routes with SmartHome entry-tier routes.

**CLOUD 2:** Recover *exact* login and token-refresh behavior from the app. Use interactive account-owner login when needed; do not store client secrets, tokens, codes or passwords in research fixtures. Handle MFA and web login safely.

**CLOUD 3:** Read devices, locate the thermostat under `entryLevels`/other actual observed collection; query known serial read-only. Record schema (keys/types), not identifying values.

**CLOUD 4:** Validate one owner-approved, reversible thermostat setpoint change, confirmed with a second read. Only then enable writable HA controls.

**LOCAL 1:** Discover subnet, LAN neighbors, any Matter advertisements and conventional TCP listeners automatically. Correlate thermostat identity through observed DHCP/Matter details; never infer device identity solely from open 80/443.

**LOCAL 2:** Validate Home Assistant's Matter setup and Internet-disconnected control separately. Do not reset/repair existing pairing without owner approval.

**LOCAL 3:** If the thermostat demonstrably uses proprietary local control, document discovered transport and authenticate it safely. Do not port generic MQTT/LocalControl app code by assumption.

### Evidence classification

`APK_STATIC` = string or GraphQL document in APK; `WEB_PUBLIC` = no-auth Carrier-owned public page/JS evidence; `LAN_OBSERVED` = device discovered on owner's LAN; `CLOUD_AUTHORIZED` = live account-scoped response; `CONTROL_CONFIRMED` = a successful read-after-write on owner's device. Never promote a milestone without corresponding evidence.

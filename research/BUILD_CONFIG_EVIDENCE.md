# Major finding: production Android BuildConfig field-to-value mapping

**Direct evidence:** `SmartHome_1.2.42_APKPure.xapk` → `com.carrier.home.apk` → `classes3.dex` → class `Lcom/carrier/home/BuildConfig;` → its DEX `static_values` array, mapped to individual field IDs in the same class. Extracted with the reproducible `trace_native_constants.py`, not a guess based on nearby APK strings.

| BuildConfig field | Actual compile-time value | Meaning / limitation |
|---|---|---|
| `API_URL` | `https://dataservice.infinity.iot.carrier.com` | Explicit configured Carrier data-service base; `/graphql` is present separately as an app route literal. Also used by older Infinity client; **new-model behavior untested** |
| `REST_API_URL` | `https://platform.iot.carrier.com` | Carrier IoT REST/platform base; routes and credentials untested |
| `OKTA_TOKEN_URL` | `https://sso.carrier.com/oauth2/default/v1/token` | OAuth token URL in the compiled app; grant and refresh format not inferred |
| `SOCIAL_LOGIN_ISSUER` | `https://sso.carrier.com/oauth2/default/v1/authorize` | Authorization endpoint value; it is named `SOCIAL_LOGIN_ISSUER` in BuildConfig |
| `WEBSOCKET_API_URL` | `wss://realtime.infinity.iot.carrier.com` | Configured Carrier realtime base; subscription protocol not verified |
| **`ENTRY_TIER_ENV_URL`** | **`a2pznvrwmtzhom-ats.iot.us-east-1.amazonaws.com`** | **An AWS IoT Core ATS-style hostname, consistent with MQTT/TLS infrastructure. This is a high-value lead for entry-level-device transport, not evidence of a local LAN API** |
| `REDIRECT_URI` | `com.carrier.home:/smarthome/callback` | Android application's configured callback URI; OAuth parameters not fully known |
| `ENV` | `prod` | Built against production configuration |
| `FLAVOR` | `carrier` | Carrier flavor |
| `APPLICATION_ID` | `com.carrier.home` | Android application ID |
| `VERSION_NAME` | `1.2.42` | APK version |

## Sensitive data excluded

The BuildConfig class also includes embedded API keys, an apparent `DUCTLESS_ROOT_KEY`, and other third-party SDK configuration. **These values are intentionally not exported to GitHub.** We are not relying on private keys, firmware changes, certificate-pinning bypasses or guessed authentication.

## Why this matters

This resolves several ambiguities in the earlier analysis: `API_URL` is no longer merely a *string key*; it has a directly mapped compile-time value. The same is true for the OAuth token URL, websocket service, and the new entry-tier AWS IoT hostname. We now know which values are compiled in, **but not which branches execute at runtime** or whether the TSTATCCEWF-01 is controlled through GraphQL, MQTT via AWS IoT, or a combination.

**Next cloud-first path:** verify authorization/login and use `getUserWithDevices` to identify a real entry-level thermostat. Separately, examine authenticated client traffic to distinguish GraphQL status/control from IoT MQTT registration, provisioning, and state delivery. Neither should require the user to guess an API host.

**Next LAN path:** capture bounded on-LAN neighbor, mDNS and TCP results automatically. Do not confuse the AWS IoT hostname (a public cloud service) with the thermostat's LAN IP or assume that local MQTT is exposed.

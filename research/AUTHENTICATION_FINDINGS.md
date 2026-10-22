# Authentication and API discovery — evidence-led findings

This is not a working login client. The APK includes multiple backend/authentication families; a string's presence is not proof of which path controls the TSTATCCEWF-01.

## Actual recovered GraphQL operations

- `fetchAccessToken(input: FetchAccessTokenInput!)` returns `success`, `errorMessage`, and `data { token_type, expires_in, access_token, scope, refresh_token }`.
- `assistedLogin(input: AssistedLoginInput!)` returns `success`, `status`, `errorMessage`, `data { token_type, expires_in, access_token, scope, refresh_token }`, and `provider`.
- `getUserWithDevices` reads the authenticated account's devices and exposes an `entryLevels` collection.

These are verbatim GraphQL document definitions. **The input object schemas and the operation-to-host mapping are not established.** Do not infer that entering a Carrier email/password directly in these mutations is appropriate; the app may use an external identity-provider flow, bearer tokens, a browser SSO session, or additional challenges.

## Separate native endpoint evidence

`classes3.dex` contains:

- `https://sso.carrier.com/oauth2/default/v1/authorize`
- `https://sso.carrier.com/oauth2/default/v1/token`
- `https://dataservice.infinity.iot.carrier.com`
- `https://platform.iot.carrier.com`
- `wss://realtime.infinity.iot.carrier.com`

Hermes contains `OKTA`, `ENTRA`, `fetchOktaToken`, runtime configuration keys `OKTA_TOKEN_URL`, `ENTRA_TENANT_URL`, `OKTA_CLIENT_ID`, `HASURA_API_URL`, `REST_API_URL`, `WEBSOCKET_API_URL`, and GraphQL route literals `/graphql`, `/graphql-no-auth`.

**Crucial caveat:** Nothing in these findings establishes that the exact `sso.carrier.com` URL or native IoT hosts power the TSTATCCEWF-01 SmartHome entry-tier API. They could support only legacy Infinity functionality in this multi-product app.

## Safe cloud path toward a real integration

1. Recover active SmartHome configuration from public web-client JS (`tools/discover_cloud.py`) without account access or guessed API hosts.
2. Establish precise provider/client/login flow from app-side static analysis or one **authorized** traffic capture, not from assumed conventions.
3. Keep all OAuth secrets and sessions out of Git and normal diagnostic logs. Support MFA, reauthentication, expiry, and refresh.
4. Query `getUserWithDevices` read-only to prove model-backend classification, then get zone/state data before any mutation.
5. Implement actual Home Assistant config/auth flow only once working authorized credential exchange has been demonstrated.

The `probe_cloud.py --discovery-report <report>` option can use a **publicly observed explicit HASURA GraphQL endpoint** from discovery output. It deliberately refuses to append `/graphql` onto guessed IoT bases or select one among ambiguous candidates. A user-authorized account token is still required for private device reads. If automatic discovery cannot isolate a valid endpoint, it will stop with an explicit error instead of pretending to have one.

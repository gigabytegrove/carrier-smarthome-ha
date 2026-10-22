# Carrier SmartHome for Home Assistant

Unofficial, experimental research project for **Carrier Smart Thermostat TSTATCCEWF-01** using the **Carrier SmartHome** Android app (`com.carrier.home`). This is **not** the legacy `ha_carrier` Infinity integration.

**Project focus:** reverse-engineer the official app exhaustively; validate its **cloud API first**, while investigating safe **local LAN / Matter** operation in parallel. The integration isn't installable yet; claiming otherwise would be misleading.

## Already extracted from SmartHome 1.2.42

- **140** GraphQL operation/fragment definitions recovered: 58 queries, 77 mutations, 5 fragments; **137** complete document strings and **3** marked partial fragments.
- Distinct **entry-level** and legacy **Infinity** API families; no unsupported assumption that the two protocols work with the same device.
- Native DEX strings identifying Carrier data service, platform, SSO and realtime WebSocket *candidates*. All are identified as **embedded strings**, not verified active requests for this model.
- GraphQL route strings `/graphql` and `/graphql-no-auth`; runtime config keys `HASURA_API_URL`, `REST_API_URL`, `ENTRY_TIER_ENV_URL`, `OKTA_TOKEN_URL` and related settings.
- Proprietary `LocalControl`/MQTT symbols in Hermes; applicability to **this thermostat** remains **unproven**.

See [full GraphQL inventory](research/GRAPHQL_CATALOG.md), [DEX findings](research/native-dex-findings.json), [APK report](research/ANALYSIS_REPORT.md), and [evidence ledger](research/STATUS.md).

## Zero-knowledge discovery: you do NOT supply a thermostat IP or API host

### A. Windows: discover local network devices automatically

From a clone of the repository, in **Windows PowerShell** (no Python or admin rights needed):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Probe-CarrierSmartHome.ps1 -Output "$env:TEMP\carrier-smarthome-lan.json"
```

It identifies your LAN default route, limits discovery to **at most one directly connected private /24**, performs a bounded ICMP sweep, reads the OS neighbor table, and checks common TCP listeners for **detected LAN neighbors**. No router settings, credentials, assumed IP, thermostat changes, HTTP commands, or firmware operations.

**Important:** a discovered IP is a *candidate LAN device*, not a proven thermostat. Devices may block ICMP and Matter devices use local IPv6/UDP. DHCP labels and Matter mDNS evidence help correlate the identity; even then, no conventional open TCP port does not mean no local control.

### B. Find Carrier cloud configuration automatically

With **Python 3.10+** (standard library only):

```powershell
py -3 .\tools\discover_cloud.py --output "$env:TEMP\carrier-smarthome-cloud.json"
```

No API URL, username, password, token, device ID or manual browser inspection is required. The tool prints the app's recovered public cloud candidates, then reads only unauthenticated **Carrier-owned public portal HTML and same-origin JavaScript** to look for runtime API configuration. No login, GraphQL account queries, or thermostat changes are attempted. It will label unknowns accurately if nothing additional is exposed by the public web client.

Run `py -3 .\tools\discover_cloud.py --offline` to skip all network requests and display APK-only candidates.

### C. Enhanced Matter/mDNS discovery (optional)

```powershell
py -3 .\tools\probe_local.py
```

Pass no arguments to query Matter-related local multicast advertisements and your OS neighbor table. This does not commission, pair, or change any device. Home Assistant's **official Matter integration** is the preferred baseline local-control path. Proprietary Carrier LAN commands are a distinct research track.

## Cloud research, then the actual Home Assistant integration

1. Confirm the live active SmartHome GraphQL host using publicly recoverable app/web config or an authorized, redacted network observation. **Do not use guessed hostnames or routes for authenticated API calls.**
2. Implement and validate a user-authorized sign-in/refresh flow without saving credentials in diagnostic reports or in Git.
3. Run read-only `getUserWithDevices` and `getEntryLevelSystemData` to prove TSTATCCEWF-01 device classification and field responses.
4. Test a reversible setpoint operation on the owner's thermostat only after confirming the API input schema.
5. Add proper Home Assistant config flow, climate entity, capability-backed sensors, rate-limited coordinator, reauth and diagnostics.
6. Validate Matter/local discovery independently and see whether any **additional**, device-specific proprietary LAN API is available. Keep local and cloud experiments separate so that one cannot interfere with the other.

Existing `tools/probe_cloud.py` is an explicit authorized **read-only GraphQL** tool. It requires an actual observed endpoint and session token because the login process is not yet established. It is **not** the recommended first step; `discover_cloud.py` now handles initial endpoint research automatically.

## Repository structure

- `research/graphql/` — all extracted GraphQL documents (partial fragments clearly marked)
- `research/graphql-catalog.json`, `research/GRAPHQL_CATALOG.md` — stable catalog and input types
- `research/analyze_xapk.py`, `research/analyze_native_apk.py`, `research/build_graphql_catalog.py` — offline reproducible APK evidence processing
- `research/native-dex-findings.json` — native URL candidates and classified feature evidence
- `tools/discover_cloud.py` — public website configuration discovery without authentication
- `tools/Probe-CarrierSmartHome.ps1` — automatic zero-input Windows LAN neighbor and TCP discovery
- `tools/probe_local.py` — separate, low-impact mDNS and neighbor utility
- `tools/probe_cloud.py` — opt-in read-only GraphQL query driver after endpoint/auth confirmation
- `tests/` — stdlib-only offline unit tests

Run tests:

```powershell
py -3 -m unittest discover -s tests -v
```

## Security and reproducibility

Do not commit APK/XAPK binaries, bearer tokens, credential files, private account responses, device serial numbers, or raw LAN reports. Public source **strings and GraphQL operation definitions** are separated from actual credentials. Reverse engineering does not imply API compatibility or Carrier endorsement. This repository is independent of Carrier.

# Carrier SmartHome for Home Assistant — research foundation

**Target thermostat:** Carrier **TSTATCCEWF-01** · **App:** `com.carrier.home` v1.2.42 (Android) · **Status:** native Carrier cloud HA alpha `0.1.0a3` available for manual installation; authenticated device discovery proved against a real SmartHome account on 2026-10-22.

This project is **not** the older Carrier Infinity custom integration. We are building a new native Home Assistant integration around the Carrier SmartHome application, prioritizing **cloud GraphQL control** and researching **LAN/proprietary local control in parallel**. **Matter is explicitly out of scope** for this project.

## Alpha 3: installation and owner-side verification

The October 22 owner-side read-only cloud test authenticated successfully and loaded a Carrier entry-level thermostat (one zone). Its *cloud-reported* model is `TSTATCCEEF-01`, different from the physical `TSTATCCEWF-01` label. The cloud currently says **offline**, so the reported room temperature and setpoints may be cached. These readings are not proof of live control. The first actual Home Assistant installation remains untested.

**Test commands on Windows (inside a clone of this repo):**

```powershell
# First-time: creates an isolated Python environment, then tests native Carrier login.
.\tools\Test-Cloud.ps1
# Later: reuses the environment; records privacy-safe changes over 3 samples.
.\tools\Observe-Cloud.ps1 -Samples 3 -IntervalSeconds 60
# Additional read-only APK-derived endpoint discovery; no HVAC changes.
.\tools\Probe-CloudFeatures.ps1
# Verify a CURRENT Omada lease before single-host TCP checks (plan only).
.\tools\Probe-VerifiedCarrierLAN.ps1 -PlanOnly
```

**Home Assistant install:** Copy `custom_components/carrier_smarthome` to `/config/custom_components/carrier_smarthome` on your HA server, restart Home Assistant, then select **Settings → Devices & services → Add integration → Carrier SmartHome (Native Cloud Alpha)**. Enter your account credentials in the HA setup UI. Climate, outdoor temperature, humidity and cloud connectivity entities should appear if setup succeeds. **Experimental thermostat controls are OFF by default; leave them off while Carrier reports the thermostat offline.** Unknown live behavior is an alpha limitation—not a successful test. After any installed update, restart or reload the integration.

Cloud API credentials are collected on your own machine and never committed. This project does **not** implement Matter. For detailed claims and evidence gates see [`research/VERIFIED_CLOUD_PROTOCOL.md`](research/VERIFIED_CLOUD_PROTOCOL.md) and [`research/ALPHA3_TEST_MATRIX.md`](research/ALPHA3_TEST_MATRIX.md).

## What we extracted from the actual XAPK

| Evidence | Result | Limits |
|---|---:|---|
| Hermes bytecode | v96 | Extracted offline |
| Hermes string records | **80,776** | Strings are not proof of executed code |
| Native Android DEX files | **7** | Analyzed string tables |
| GraphQL definitions | **140** | 58 queries, 77 mutations, 5 fragments; 3 incomplete fragments |
| Entry Level operations | **16** | 6 queries, 10 mutations |
| Carrier URL literals in Hermes | **60** | Mostly static help resources; not all APIs |
| Carrier service URL literals in DEX | **5** | Backend selection not established |
| Environment/configuration key names | **10** | Runtime values not established |
| Local/MQTT code symbols | **14** | TSTATCCEWF-01 applicability unconfirmed |

**New runtime-config evidence:** `research/native-constant-xrefs.json` maps compiled Android `BuildConfig` fields directly to their values, including `API_URL=https://dataservice.infinity.iot.carrier.com`, `ENTRY_TIER_ENV_URL=a2pznvrwmtzhom-ats.iot.us-east-1.amazonaws.com` (AWS IoT ATS), and the Android OAuth redirect URI. This is more definitive than isolated APK strings but does **not** confirm which protocol is used for TSTATCCEWF-01. See `research/BUILD_CONFIG_EVIDENCE.md`.

The app includes `getUserWithDevices`, `getEntryLevelSystemData`, `getEntryLevelSchedules`, `updateEntryLevelZone`, and `updateEntryLevelComfortProfile`. These are exact operation strings, not guessed API endpoints or validated responses. Cloud discovery must prove authentication, the active hostname, and the backend family for this model.

## Targeted IoT VLAN discovery (known network)

**Confirmed network:** the owner's Carrier thermostat is associated with **`redacted.invalid/16`**, *not* the computer's `192.168.0.x` LAN. Historical Omada client export associates the thermostat with a last-known IP; this is not a confirmed current DHCP lease. The scanner now targets **only** `redacted.invalid/16` by default, without requiring a thermostat IP, router login, or cloud URL.

**Already ran the full sweep?** Use the saved results; **do not scan the `/16` again** just to obtain a device list:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Run-Discovery.ps1 -ReviewOnly
```

The review-only mode locates the newest `iot-private.json` automatically and prints all candidate IPs, the separate ICMP/neighbor evidence, and the exact open ports per host. It does not perform any network traffic or cloud requests. The first owner-side scan on 2026-10-22 found 63 candidates (all in `redacted.invalid/24`) and 10 **port results** (not necessarily 10 hosts). Thermostat identity remains unconfirmed. See `research/IOT_VLAN_172_20.md`.

Run the **existing** entry point in Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Run-Discovery.ps1
```

The script performs a bounded 65,534-host **ICMP** discovery on the confirmed IoT network (up to 128 requests concurrently), then tests common TCP listeners **only on responding/neighbor-cache hosts**. This avoids sending six TCP connects to every address on the /16 by default. Response-free devices and blocked inter-VLAN traffic remain possible; absence from the report does **not** mean the thermostat was ruled out. The general 192.168 LAN **is not scanned**.

```powershell
# Inspect the exact plan without network requests:
.\tools\Discover-CarrierIoT.ps1 -PlanOnly
# Optional thorough scan: include TCP 80/443 even when ping is blocked (more traffic/time):
.\tools\Run-Discovery.ps1 -DeepIoT
# Only when deliberately wanted: also scan other connected private networks:
.\tools\Run-Discovery.ps1 -IncludeOtherNetworks
# Limit the scan to a particular confirmed /24 inside the IoT VLAN:
.\tools\Run-Discovery.ps1 -IoTSubnet 'redacted.invalid/24'
```

**Routing and Matter caveats:** Your Windows PC may send packets toward this VLAN via its existing router, but firewall rules can prevent replies. We do not add routes or bypass segmentation. Matter runs over IPv6/UDP and mDNS; an IPv4-only scan cannot establish a Matter endpoint or prove the absence of proprietary control. This project does not commission devices with Matter; no mDNS or Matter discovery substitutes for a demonstrated proprietary Carrier LAN protocol.

Reports go under `%LOCALAPPDATA%\CarrierSmartHome-Research\<UTC-date>` and may contain private IP/MAC information; **do not commit or post raw scans**. The cloud phase still investigates APK-derived services without guessed URLs, and an authenticated control request remains unverified.

The original multi-network scanner remains available for general research as `tools/Probe-CarrierSmartHome.ps1`. The independent Python `tools/auto_discover.py` still enforces /24-sized scopes and is **not** the preferred scanner for this known /16.

See [`research/IOT_VLAN_172_20.md`](research/IOT_VLAN_172_20.md) for scope, scan-depth tradeoffs, output details and limitations.

## Cloud-first next stage

1. **Static extraction complete:** `research/transport-evidence.json`, `research/native-dex-findings.json`, `research/graphql/`, and `research/graphql-catalog.json` contain source-tagged evidence.
2. **Endpoint proof:** On 2026-10-22 an owner-run read-only test successfully authenticated at the APK-derived GraphQL service and discovered one entry-level device and one zone. The backend returned model `TSTATCCEEF-01`, while the thermostat label identifies `TSTATCCEWF-01`; this mapping is unresolved. Cloud connection was reported offline at test time.
3. **Optional user-authorized session capture:** When needed, capture a browser session from Carrier SmartHome's existing web portal, then analyze **locally** with `python tools/analyze_har.py private.har --output safe-capture-summary.json`. The analyzer records only Carrier hosts, safe route patterns, GraphQL operation names, variable names, and authentication **mechanism**, never values. Never publish/upload the original HAR.
4. **Authenticated owner query:** The `entryLevelSystems` login/list flow now works on a real account. The detailed APK query is added as an optional read-only cross-check in the smoke test. No secrets or device serials are printed.
5. **Write controls:** Only after reading actual schema, verify reversible heat/cool setpoint changes; add schedule/profile writes later.
6. **Home Assistant package:** An installable native cloud alpha is now provided under `custom_components/carrier_smarthome`; device discovery works outside HA. HA runtime and actual write operations are not yet owner-verified, and controls remain opt-in.

`tools/cloud_protocol.py` already enforces Carrier-only HTTPS GraphQL endpoints, token redaction, response limits, no redirects, and read-only queries. It does not implement invented OAuth parameters or a fake password login.

## Local investigation in parallel

- DHCP/ARP/MAC and subnet discovery → automatically identify **candidate** IPs.
- Read-only protocol fingerprinting only after a **current online Omada MAC/IP identity match**; no Matter protocol.
- Optional bounded TCP connects (no HTTP commands, no login, no MQTT publishes).
- Correlate a cloud-reported `connection.macaddress` or `connection.deviceId` to LAN neighbors when authenticated API listing is working.
- APK symbols `LocalControlReqPacket`, `SendLocalControlCommandRead`, `SendLocalControlCommandWrite`, and `MqttProxy` are **research leads only**. They may apply to another SmartHome product.

## Tests and verification

```bash
python -m unittest discover -s tests -v
python -m compileall -q tools research
```

Testing is offline: simulated GraphQL responses, URL safety, HAR secret redaction, subnet restrictions, and mDNS parsing. No user account, thermostat, or cloud service was accessed by the test suite. No GitHub Actions or other hosted CI is required.

## Safety, provenance and boundaries

- No APK/XAPK binary or decrypted secrets committed. Never publish captured authorization headers, session cookies, device serial numbers or raw HAR files.
- All network probes are read-only. TCP connect tests are limited to visible, specifically routed, or authorized RFC1918 subnets (maximum /24 each); no attempt to bypass authentication or certificate pinning.
- Matter is explicitly excluded. Proprietary LAN API support remains unproven.
- Document evidence sources precisely and label **unverified** conclusions. The authenticated TSTATCCEWF-01 read/write path has **not** yet been exercised.

See `research/ANALYSIS_REPORT.md`, `research/CLOUD_PROTOCOL.md`, `research/LOCAL_PROTOCOL.md`, `research/TEST_PLAN.md`, and `research/STATUS.md`.

# Carrier SmartHome for Home Assistant — research foundation

**Target thermostat:** Carrier **TSTATCCEWF-01** · **App:** `com.carrier.home` v1.2.42 (Android) · **Status:** research and protocol discovery (not an installable HA integration yet).

This project is **not** the older Carrier Infinity custom integration. We are building a new native Home Assistant integration around the Carrier SmartHome application, prioritizing **cloud GraphQL control** and researching **LAN/proprietary local control in parallel**. Home Assistant's existing Matter integration is a valid local alternative, not proof that Carrier exposes a separate IP API.

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

## Zero-URL, zero-IP discovery on Windows

You do **not** need to know your thermostat's IP address or Carrier's cloud URL. Clone this private repository using your existing GitHub authentication and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Run-Discovery.ps1
```

That script does three **read-only** things: discovers **all visible connected and specifically routed private LANs / IoT VLANs** (each limited to `/24`, eight networks by default), collects per-subnet ICMP/neighbor/TCP evidence, and displays native APK cloud service evidence. If Python is installed, it also inspects public Carrier portal JavaScript without logging in or asking for a token. Results are stored under `%LOCALAPPDATA%\CarrierSmartHome-Research\<UTC-date>`; they are **not** uploaded to GitHub.

**IoT VLAN support:** If the thermostat is on a different private VLAN and your PC has a connected interface or specific route for it, the scanner finds the subnet automatically. If **only the primary LAN is reported**, a normal default gateway route does not reveal other VLAN subnet addresses. In that case, run discovery on a device connected to the IoT VLAN, or provide the actual authorized subnet from your router with `-AdditionalSubnets`. We **do not guess** an IoT CIDR. The default scan performs a bounded TCP connect sweep even for devices that ignore ping; use `-Quick` for a faster partial scan.

```powershell
.\tools\Run-Discovery.ps1 -Quick
.\tools\Run-Discovery.ps1 -MaxNetworks 12
# Only when router VLAN settings confirm that subnet:
.\tools\Run-Discovery.ps1 -AdditionalSubnets '192.168.50.0/24'
```

`192.168.50.0/24` is a documentation example, **not a discovered network**. See [`research/VLAN_DISCOVERY.md`](research/VLAN_DISCOVERY.md) for routed-VLAN, mDNS, Matter/IPv6 limitations, and security boundaries.

More thorough cross-platform discovery (Python 3.10+; Windows/Linux) is also available:

```bash
python tools/auto_discover.py --list-only
python tools/auto_discover.py --output carrier-private-local.json
python tools/discover_cloud.py --output carrier-public-cloud.json
```

The private discovery JSON may contain LAN IP/MAC addresses. Keep it private. A detected TCP port or mDNS service does **not** identify a thermostat unless its MAC/hostname/serial is correlated.

## Cloud-first next stage

1. **Static extraction complete:** `research/transport-evidence.json`, `research/native-dex-findings.json`, `research/graphql/`, and `research/graphql-catalog.json` contain source-tagged evidence.
2. **Endpoint verification pending:** The embedded `dataservice.infinity.iot.carrier.com` host is known publicly as an **older Infinity** GraphQL endpoint. Do not assume TSTATCCEWF-01 uses that host. App runtime configuration may choose a different service.
3. **User-authorized session capture:** When needed, capture a browser session from Carrier SmartHome's existing web portal, then analyze **locally** with `python tools/analyze_har.py private.har --output safe-capture-summary.json`. The analyzer records only Carrier hosts, safe route patterns, GraphQL operation names, variable names, and authentication **mechanism**, never values. Never publish/upload the original HAR.
4. **Authenticated owner query:** Once the actual endpoint and authentication flow are verified, read `getUserWithDevices`, select the user's TSTATCCEWF-01 by reported model/serial, and read `getEntryLevelSystemData` with a privacy-preserving client.
5. **Write controls:** Only after reading actual schema, verify reversible heat/cool setpoint changes; add schedule/profile writes later.
6. **Home Assistant package:** Build a native custom integration after successful live read, login refresh, and write tests; do not fabricate a working integration before the protocol is verified.

`tools/cloud_protocol.py` already enforces Carrier-only HTTPS GraphQL endpoints, token redaction, response limits, no redirects, and read-only queries. It does not implement invented OAuth parameters or a fake password login.

## Local investigation in parallel

- DHCP/ARP/MAC and subnet discovery → automatically identify **candidate** IPs.
- mDNS → check Matter discovery, especially Matter operational IPv6/UDP behavior.
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
- The thermostat's Matter support is separate from proprietary cloud control; proprietary LAN API support remains unproven.
- Document evidence sources precisely and label **unverified** conclusions. The authenticated TSTATCCEWF-01 read/write path has **not** yet been exercised.

See `research/ANALYSIS_REPORT.md`, `research/CLOUD_PROTOCOL.md`, `research/LOCAL_PROTOCOL.md`, `research/TEST_PLAN.md`, and `research/STATUS.md`.

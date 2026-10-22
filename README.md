# Carrier SmartHome for Home Assistant

**Research/experimental** project for **Carrier TSTATCCEWF-01**, running the **Carrier SmartHome** app (`com.carrier.home`). This is **not** the legacy Carrier Infinity integration. No thermostat-control integration is published yet; this repository contains tested read-only discovery utilities and documented APK findings.

## Research status

| Area | Evidence | Status |
|---|---|---|
| Android app | SmartHome `1.2.42`, version code `854`; uploaded XAPK | Static analysis complete |
| GraphQL | `entryLevelSystem`, `entryLevelSchedules`, `updateEntryLevelZone` operations | Operation strings recovered; backend untested |
| Cloud base URL, OAuth | Configuration names in APK; no validated production host or login | Requires user-authorized traffic capture |
| Proprietary LAN API | `SendLocalControlCommandRead/Write` symbols exist in app | **Not linked to TSTATCCEWF-01** |
| Matter | Thermostat model supports Matter over Wi-Fi | Test with HA's native Matter integration |
| Device IP | Not contained in APK; assigned by local DHCP | Discover on user's LAN |

## Run safe discovery on Windows

From a checked-out copy of this **private** repository, in Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Probe-CarrierSmartHome.ps1
# Once the thermostat IP is known from your router, test common TCP listeners:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Probe-CarrierSmartHome.ps1 -Target redacted.invalid
```

Replace `redacted.invalid` with the IP reported by your router. No IP is assumed or inferred from the XAPK. The Windows probe reads existing neighbor entries and probes **only an explicit private IP**. A thermostat not in the neighbor list is normal. Reachable TCP port != a working control API; no exposed ports != no Matter connectivity.

## Run enhanced local discovery with Python 3.10+

```bash
python tools/probe_local.py
python tools/probe_local.py --target redacted.invalid
# Opt-in, bounded TCP scan of a subnet YOU own:
python tools/probe_local.py --cidr redacted.invalid/24 --scan
```

The Python probe queries Matter-related mDNS records, reads ARP/neighbors, and optionally tests TCP connectivity for ports `80,443,8080,8443,1883,8883`. It does not send HTTP, MQTT, Matter commissioning, or thermostat commands. Note that Matter normally uses **UDP 5540**, and mDNS may report nothing for already commissioned devices. Check your router DHCP lease list as the **most reliable way** to find the device IP. Do not scan networks you do not manage.

## Cloud API research (no guessing)

1. Sign in to [Carrier SmartHome](https://my.carrier.com/) in a browser you control, or observe your own Android app's metadata traffic. In browser developer tools → Network → Fetch/XHR, identify the real HTTPS GraphQL URL and request headers. Do **not** post HAR files, account cookies, bearer tokens, device serials, or API response bodies to GitHub.
2. Identify the authentication flow. Do not assume an Okta/Entra/API URL from a string name. Save an authorized short-lived access token in a local file, never in this repository.
3. Once identified, run a **read-only** query; `getUserWithDevices` may require the account's `userName` variable. User data and serials are redacted from displayed results by the probe.

```bash
python tools/probe_cloud.py --endpoint 'https://YOUR-VERIFIED-HOST/graphql' \
  --query queries/getUserWithDevices.graphql \
  --variables /private/path/variables.json --prompt-token
```

The example host is intentionally not real. The tool uses normal TLS certificate verification, blocks redirects, rejects GraphQL mutation/subscription operations, and prints **response field names/types only**. The cloud probe requires an observed endpoint and an account-authorized Bearer token. It does **not** perform login, token refreshing, or guessed API traffic.

## Documentation

- [APK technical findings](research/APK_FINDINGS.md)
- [Local and cloud test plan](research/TEST_PLAN.md)
- [Security and data sharing](research/SECURITY.md)
- [Project status and checkpoints](research/STATUS.md)
- `queries/`: verbatim read-only GraphQL documents extracted from SmartHome v1.2.42.

## Development gates

1. Confirm the device's local IP from the router; correlate mDNS and neighbor information.
2. Check the thermostat's Matter availability in Home Assistant (do not disturb an existing pairing).
3. Confirm whether any non-Matter LAN protocol exists; APK symbols alone are insufficient.
4. Verify real production cloud hostname, authorized authentication and device classification.
5. Implement cloud read operations and mocked tests; only then test reversible owner-approved thermostat writes.
6. Deliver Home Assistant config flow, climate entity, diagnostics and robust recovery after those APIs are validated.

**Privacy:** Do not commit APK binaries, private API data, access tokens, IP/MAC inventories, or device serial numbers. This is an independent community research project and not affiliated with Carrier.

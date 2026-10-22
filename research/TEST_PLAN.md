# Read-only investigation plan

## A. Locate the thermostat

1. Record the DHCP lease from the local router (device name, IP, MAC **privately**); cross-check Wi-Fi SSID shown on thermostat. Do not publish the real IP/MAC or serial.
2. Run Windows `Probe-CarrierSmartHome.ps1` without a target to view neighbor entries. The cache may omit quiet devices.
3. Run Python `probe_local.py` for mDNS `_matter._tcp.local`, `_matterc._udp.local`, `_matterd._udp.local` records. Failure to advertise does not rule out operational Matter.
4. Probe the **router-confirmed IP** with `--target`. TCP open-port signals are descriptive, not permission to call undocumented APIs.
5. For explicit confirmation of local control, use Home Assistant Matter commissioning and verify setpoint/control with Internet disconnected only during a planned safe test (do not interrupt active heating/cooling).

## B. Cloud mapping

1. From an authenticated session on your own account, locate the **actual** GraphQL HTTPS endpoint in the Network tab (avoid saving raw HAR).
2. Document login method and refresh flow at a structural level; do not upload tokens.
3. Send only `getUserWithDevices` first; confirm `entryLevels`/device classification and redact IDs.
4. Then query `getEntryLevelSystemData` with the device serial stored privately; inspect field types and null behavior.
5. Only after successful reads and model verification, evaluate reversible control mutations with a live owner-approved test.

## Interpretation

- No TCP listeners: not evidence against Matter/UDP or cloud-only design.
- Open 443: not proof it is HTTP or unauthenticated; avoid TLS-bypass scripts.
- mDNS name includes Matter: potentially Matter capable, **not** proof it is the thermostat until paired to DHCP/device identity.
- GraphQL documents in APK: request templates, **not** evidence the server supports every field or model.
- Never post raw network logs; retain local data privately and report sanitized summaries.

## Multi-VLAN discovery update (2026-10-22)

The scanner now includes multiple private connected networks, explicit routed VLAN prefixes, and optional authorized CIDRs, bounded to /24 each. The supplied scan log only demonstrates main-LAN `redacted.invalid/24` discovery; the IoT VLAN subnet is still unknown. See [`VLAN_DISCOVERY.md`](VLAN_DISCOVERY.md) for procedures and limitations. No thermostat-specific LAN IP or API has been confirmed.

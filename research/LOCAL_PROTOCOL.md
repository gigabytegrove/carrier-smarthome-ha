# Local IP discovery and proprietary LAN feasibility

The TSTATCCEWF-01 connects via Wi-Fi and has Matter support. Neither fact proves that the Carrier SmartHome app directly controls it using a proprietary TCP or HTTP listener. The actual device IP is assigned by the router's DHCP server and cannot be extracted from a generic APK.

## Cloud versus LAN boundary

The Android production BuildConfig maps `ENTRY_TIER_ENV_URL` to `a2pznvrwmtzhom-ats.iot.us-east-1.amazonaws.com`, an AWS IoT Core ATS-style endpoint. This is a **public cloud hostname**, not a thermostat-local endpoint. MQTT-related app symbols therefore cannot be taken as evidence of local MQTT. `BUILD_CONFIG_EVIDENCE.md` has source mapping.

## Verified source-code hints

Hermes and native identifiers include `LocalControl`, `LocalControlReqPacket`, `LocalControlReqCommand`, `SendLocalControlCommandRead`, `SendLocalControlCommandWrite`, `MqttProxy` and `MqttProxyControl`. These show local/MQTT code in the **multi-device** SmartHome app, not that this specific thermostat uses that code path.

## Discovery now available without a known address

- Windows built-in: `tools/Run-Discovery.ps1` runs `tools/Probe-CarrierSmartHome.ps1` and detects an active private default-route subnet.
- Cross-platform Python: `python tools/auto_discover.py` discovers active LAN interfaces, mDNS records, neighbor-cache addresses and common TCP listeners.
- Both limit active scanning to a private /24 or smaller. No authentication attempts, configuration writes, or remote access.
- Neighbor entries are **candidate IPs**, never verified thermostat identities. Lack of TCP listeners does not exclude operational Matter over IPv6/UDP.

## How we will identify *the* thermostat IP

Once C3 provides `connection.macaddress` and the owner has run the local probe, compare the reported MAC to LAN neighbor-cache MACs. A match becomes strong device identity evidence, subject to VLAN bridges, MAC randomization, and the cloud returning a different interface MAC. DHCP lease name/manufacturer is supporting evidence, not conclusive.

With a confirmed IP, only then inspect open ports and protocol fingerprints with read-only requests. Matter is explicitly out of scope. Never send guessed MQTT payloads, BLE provisioning commands or installer commands.

## Local progress criteria

**L1:** Verify on-LAN private subnet, neighbor inventory, and mDNS/IPv6 results. **Tools implemented, device untested.**

**L2:** Correlate device identity to a specific IP via cloud MAC or DHCP evidence. **Not tested.**

**L3:** Determine whether local Carrier API is separate from Matter. **Unknown.**

**L4:** If there is an authenticated proprietary LAN protocol, document read-only session setup and one proven request. **Unknown.**

**L5:** No Matter transport, dependencies or fallback. Proprietary native local control must be proven independently or remain unsupported. **Locked requirement.**

## Multi-VLAN discovery update (2026-10-22)

The scanner now includes multiple private connected networks, explicit routed VLAN prefixes, and optional authorized CIDRs, bounded to /24 each. The supplied scan log only demonstrates main-LAN `192.168.0.0/24` discovery; the IoT VLAN subnet is still unknown. See [`VLAN_DISCOVERY.md`](VLAN_DISCOVERY.md) for procedures and limitations. No thermostat-specific LAN IP or API has been confirmed.


## October 22, 2026 update

Omada offline export identified the physical unit by MAC/label suffix. Its last-known IPv4 address is **not** a current lease. `tools/Probe-VerifiedCarrierLAN.py` now requires a matching, currently CONNECTED Omada export before probing common TCP listener ports on exactly one approved IPv4 host. It does not send HTTP, MQTT, BLE, Matter or thermostat control commands. Public Carrier Quick Start instructions confirm BLE-based **onboarding**, not native LAN control. Do not infer a local API from the app's `LocalControl` strings.

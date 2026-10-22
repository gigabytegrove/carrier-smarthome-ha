# Local discovery across LANs and IoT VLANs

**Current confirmed IoT CIDR: `172.20.0.0/16`.** The historical background and sample `/24` commands below predate that discovery. The project's current default scanner uses `172.20.0.0/16`; see [`IOT_VLAN_172_20.md`](IOT_VLAN_172_20.md).

## Background

The 2026-10-22 user scan ran from Windows `192.168.0.133` and selected **only** `192.168.0.0/24`. It found 78 neighbor-cache entries and many TCP listeners, but **did not identify the Carrier thermostat**. There is no evidence the IoT VLAN was scanned. The provided log does not include the IoT VLAN prefix; none is assumed here.

## Corrected multi-network behavior

`tools/Run-Discovery.ps1` invokes `tools/Probe-CarrierSmartHome.ps1`, which now:

1. Collects **all connected private IPv4 interfaces**, not merely the default-gateway interface.
2. Collects specific `/24`–`/30` **private routed prefixes** where Windows has an explicit next-hop route (such as `192.168.50.0/24 via 192.168.0.1`). Default-route `0.0.0.0/0` is **not** expanded into guessed networks.
3. Accepts additional **user-authorized `/24`–`/32` RFC1918 CIDRs** when a router knows a VLAN the PC cannot enumerate.
4. Deduplicates scopes and limits discovery to **eight networks** by default, max 16; each scope is no wider than `/24`.
5. Records per-network ICMP responders, local ARP/neighbor data (if any), and TCP listeners (`80`, `443`, `8080`, `8443`, `1883`, `8883`). TCP connection checks do not send application-layer commands.
6. In normal mode scans the full **bounded** subnet for those TCP ports, including devices which ignore ICMP. `-Quick` limits TCP probes to ICMP/neighbor candidates; `-NoTcp` disables TCP.
7. Separately reports each network's reachability and marks **all device identities as unverified**.
8. Saves IP/MAC-bearing results **only to a local private JSON file**, never to GitHub.

The independently usable Python `tools/auto_discover.py` uses the same source-of-truth rules for scopes. It can report mDNS on the local multicast domain, but does not claim cross-VLAN mDNS discovery.

## Run the updated scanner

On a Windows PC with an authenticated GitHub CLI checkout:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Run-Discovery.ps1
```

This detects all visible private NICs and specific routes. No thermostat IP, cloud URL, or CIDR is required **if the VLAN is visible in those sources**. To quickly list networks without probing hosts:

```powershell
python tools\auto_discover.py --list-only
```

If the result shows **only the primary LAN**, the IoT VLAN behind the gateway is not discoverable from the PC's routing table. Either run the same script on a computer attached to the IoT VLAN (preferable), or read the VLAN's subnet **from the router's VLAN configuration** and authorize it:

```powershell
.\tools\Run-Discovery.ps1 -AdditionalSubnets '192.168.50.0/24'
```

`192.168.50.0/24` is a **format example only**, not a claim about this user's network. If inter-VLAN firewall rules deny access, scanning from the main LAN will not work even with the correct CIDR. No bypass is attempted.

If many networks exist:

```powershell
.\tools\Run-Discovery.ps1 -MaxNetworks 12
```

For a faster, less complete check:

```powershell
.\tools\Run-Discovery.ps1 -Quick
```

## What the scan can and cannot prove

| Evidence | Interpretation |
|---|---|
| RFC1918 host responds to ICMP | IP is reachable; **not** proof of Carrier identity |
| TCP port 443/8883 responds | Listener exists; **not** proof of Carrier's API or MQTT control |
| ARP MAC exists on the same VLAN | Device present in L2 segment; routed VLANs will usually show gateway MAC, not endpoint MAC |
| No ping or TCP response | Could still be the thermostat, especially a cloud-outbound-only client |
| Matter mDNS / operational IPv6 | Requires an IPv6-capable probe in the same multicast domain, or a deliberately configured reflector |
| `LocalControl` strings in APK | APK feature exists; applicability to TSTATCCEWF-01 is unconfirmed |

**Next correlation step:** Once cloud GraphQL lists the thermostat, compare any reported `macaddress`, `deviceId`, hostname or network metadata with the local discovery results. Treat the thermostat address as *unknown* until identity matches. No traffic redirection, credentials, app proxying, firmware changes, or thermostat commands are performed in these probes.

## Security boundaries

- Scopes are limited to private RFC1918 IPv4 `/24` or smaller, capped by `-MaxNetworks` / `--max-networks`.
- The probe targets only directly connected, explicitly routed, or user-authorized networks; it never invents VLAN subnet addresses.
- It performs ICMP, OS neighbor reads, and TCP connects only; no MQTT publishes, no HTTP requests to devices, no Matter pairing changes.
- Cloud configuration discovery is separate from VLAN discovery.
- Do not commit or publicly share raw scans, MAC addresses, tokens, serial numbers, or private LAN diagrams.

## Confirmed target update

The user subsequently identified the relevant IoT network as `172.20.0.0/16`. The previous example-only `/24` instructions above remain relevant for the generic multi-VLAN tool but **are no longer the correct default for the Carrier project**. Use `tools/Run-Discovery.ps1` to scan only the IoT `/16` by default, or see `research/IOT_VLAN_172_20.md`. No further subnet entry is needed.

## No fresh ZIP? Use Omada Connected Clients directly

**Live UI alternative (does not rely on the stale 08:14 ZIP):** Open Omada **Connected Clients** and select the Carrier thermostat. While that page is open, run the PowerShell wrapper with `-LiveOmada` (and optionally `-FullTCP -Concurrency 12`). It prompts for the **current IPv4** and **full Wi-Fi MAC** exactly as displayed, and requires the explicit phrase `I-SEE-IT-CONNECTED`. It validates the MAC suffix, IP syntax, and permitted IoT network, and scans **that one supplied host only**.

This is **owner attestation**, not an independently verified MAC-to-IP binding. Do not use a cached IP, historical screenshot, offline client or the old export. Refresh Omada immediately before running; a changed DHCP assignment can invalidate a manual target. No IP or full MAC is saved to the report. For independently checked snapshot identity, continue using the fresh ZIP method below.

```powershell
.\tools\Probe-CarrierLocalDeep.ps1 -LiveOmada -FullTCP -Concurrency 12
```

# v0.5.0 — Comprehensive Carrier SmartHome proprietary LAN discovery

This is **not** the legacy Carrier Infinity protocol. The target is a Carrier SmartHome TSTATCCEWF-01 (cloud-reported TSTATCCEEF-01). The protocol for native *proprietary* LAN control remains unproven. **Matter is excluded.** No command in this guide turns the HVAC on/off, changes fan or mode, pairs a device, flashes firmware, or alters Wi-Fi/router/DNS settings.

## Before running

1. On the thermostat or official Carrier app, ensure Wi-Fi is connected. The thermostat previously suffered a real Wi-Fi outage; an offline device or old IP cannot be tested reliably.
2. In Omada, open the **current connected clients** view and export a **fresh Client ZIP** to the Windows computer's `Downloads` folder. This must contain `OnlineClient_*.csv`, `OfflineClient_*.csv`, and `PastConnection_*.csv` from the same export. A screenshot or an old offline-client entry does not prove current address ownership.
3. Within 30 minutes of exporting, run the command from a current checkout. Python 3.11+ and `gh` CLI should already be installed from the cloud research. Do not upload the Omada archive to the public repo.
4. Enter the last four hexadecimal characters of the Wi-Fi MAC observed in Omada or the thermostat label when prompted. The tool resolves the MAC in memory; the suffix is not stored in source or the report.
5. The Windows machine must have routing/firewall permission to reach the IoT subnet. Cross-VLAN routing can block responses. The script **does not** alter firewall rules or network routes.

## Windows PowerShell (run from a fresh GitHub clone)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Probe-CarrierLocalDeep.ps1 -PlanOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Probe-CarrierLocalDeep.ps1 -FullTCP
```

The **plan** validates export freshness and current single-device identity offline. The **full** run then connects to all TCP ports `1..65535` on **that one verified device**, with a maximum of 32 simultaneous connections and a 0.45-second connect timeout (both bounded and adjustable). The scan has progress messages, probes candidate HTTP/TLS and MQTT listeners, then sends just three UDP discovery requests directly to the verified host. These operations may take significant time on a firewalled VLAN; an embedded thermostat may not tolerate highly aggressive repeated scanning. Run one scan, not multiple concurrent scans.

To use a specific ZIP or tune the rate:

```powershell
.\tools\Probe-CarrierLocalDeep.ps1 -ArchivePath 'C:\Users\you\Downloads\Client_2026-10-22-14-00.zip' -FullTCP -Concurrency 16 -TcpTimeout 0.8
```

If the controller's timestamp uses a different civil-time zone from your Windows workstation and UTC, specify its UTC offset explicitly (e.g. `-ControllerUtcOffset -4`). **This does not bypass the timestamp or freshness check.** A stale ZIP must be replaced; simply copying/renaming an old export is not a fix. Both the ZIP mtime and embedded OnlineClient timestamp are checked.

## What exactly is tested

| Test | Behavior | What it proves |
| --- | --- | --- |
| Active Omada lease | Current online MAC suffix, unique active IP, authorized `redacted.invalid/16`, recent snapshot | Network target selection only |
| Broad TCP scan | Default TCP 1–1024 + common higher IoT ports; optional all TCP 1–65535 | TCP connections accepted at scanning moment |
| HTTPS/TLS | Handshake and TLS version/ALPN on candidate open TLS ports | An encrypted listener, **not** HVAC API authorization |
| HTTP | One `HEAD /` on known candidate web listener ports | HTTP response code only, no body/credentials |
| MQTT | Anonymous `CONNECT` then `DISCONNECT` on candidate MQTT listener ports only | MQTT broker CONNACK if returned, no topic discovery/write |
| UDP mDNS | Unicast DNS-SD PTR discovery to device UDP 5353 | Whether this specific unicast request got a response |
| UDP SSDP | Unicast `M-SEARCH` to device UDP 1900 | Whether device answered this direct request |
| UDP CoAP | Confirmable `GET /.well-known/core` to device UDP 5683 | Whether standard CoAP discovery answered |

There is **no multicast across the VLAN** in this scanner. Cross-VLAN mDNS/SSDP can require multicast routing; silence is inconclusive. UDP scanning does not establish that a port is closed. A device could also use outbound-only MQTT/TLS/WebSockets, proprietary encrypted UDP, Bluetooth provisioning, or other non-listening transports. None of those imply local control is possible.

## What to share and what not to share

The console prints only ports, response flags and status codes. A sanitized JSON report is saved under `%LOCALAPPDATA%\CarrierSmartHome-Research\carrier-local-0.5.0-*.json`. This excludes device/household identity and credentials; review it before posting anywhere. **Never share** the raw Omada ZIP, actual MAC, IP, hardware ID, Wi-Fi credentials, pairing QR, HAR, pcap, unredacted DNS client log or access token publicly. The report intentionally does not include enough identifying information to reconstruct the local target.

## Next research phase if no listeners respond

1. Capture *passive traffic metadata* using Omada AP/gateway logs or port mirroring with authorization, focusing on the thermostat's association, outbound destination ports, DNS names, and connection patterns. Capture near an official-app action, with consent. Do not assume a packet capture on the Windows primary VLAN sees traffic from the IoT Wi-Fi VLAN.
2. Correlate client and thermostat traffic behavior using timestamps from the same Wi-Fi session. The app may communicate only with cloud services, while the thermostat maintains an **outbound** AWS IoT TLS connection; this does not create an inbound LAN listener.
3. Examine APK-derived `LocalControlReqPacket`, `MqttProxy`, and related symbols in context of code execution and product family before claiming they apply to this entry-level thermostat.
4. If verified local traffic exists, design one *read-only, authenticated* protocol proof. No brute force, MITM certificate substitution, firmware changes, insecure DNS redirection, or Matter implementation.

**A negative test does not prove no local API exists. A positive network port does not prove native HVAC control exists.**

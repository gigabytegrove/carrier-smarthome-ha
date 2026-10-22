# Confirmed IoT range: redacted.invalid/16

Source: User confirmed that their Carrier TSTATCCEWF-01 is connected to the redacted.invalid/16 IoT network, and not on the redacted.invalid/16 network. Prior user-side discovery covered redacted.invalid/24 and returned 78 neighbor entries but did not establish the thermostat's address.

## Scope and objective

The default `tools/Run-Discovery.ps1` calls `tools/Discover-CarrierIoT.ps1` with the confirmed network. It scans only redacted.invalid to 172.20.255.255. There are 65,536 addresses total and 65,534 usable host addresses; an unknown IP cannot be determined offline from an APK, because it is assigned on the user's LAN. No static route or firewall changes are made.

## Scan strategy

1. Inspect Windows' selected route to an address in this VLAN; record but do not treat a route as proof of permitted access.
2. ICMP sweep the full known `/16`, with at most 128 concurrent ICMP requests by default. Include existing local-neighbor records if available.
3. On responsive IPs only, probe TCP `80`, `443`, `8080`, `8443`, `1883`, `8883` using connect-only checks. These are not claims that the thermostat listens on those ports.
4. Write a private JSON report with the responsive addresses, any neighbor MACs, TCP listeners, a breakdown by `/24` slice, actual probe coverage, and explicit unconfirmed-model flags.
5. Optional `-DeepIoT` checks TCP 80 and 443 on otherwise silent hosts within the range as a second pass. This takes longer and creates more traffic; it does not inspect MQTT payloads or send HTTP requests.
6. Optional `-PlanOnly` runs an offline planning path. The general multi-LAN scanner is invoked only when `-IncludeOtherNetworks` is specified.

## Interpretation

- A missing ICMP response does not establish that the host is absent; DHCP hosts can block echo requests, and VLAN firewalls may deny forwarding/replies.
- A closed common TCP port does not establish that Carrier has no local API; it could use a different port/protocol or exclusively outbound cloud control.
- A responsive IP or `8883` socket does not identify a Carrier device. Correlate its MAC or observed device metadata with the *authenticated* cloud device inventory when it becomes available.
- mDNS/Matter discovery may fail across VLANs without multicast forwarding and IPv6 routing. A host inside the IoT VLAN may be necessary.
- `redacted.invalid/16` is confirmed by the user; **the specific thermostat IP is still unknown**.

## Evidence requirements

Before claiming that the thermostat has a local API, collect a model-confirming identity, the service endpoint/port and a validated, owner-authorized read-only request. Before claiming cloud support, confirm the real authentication flow and the `entryLevelSystem` mapping. All such discoveries remain separate from static APK string matches.

## Offline validation

- Cross-platform contract tests: `python -m unittest discover -s tests -v`
- Native PowerShell plan/safety tests (on Windows): `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests\\Test-IoTDiscovery.ps1`
- Real network scan has **not** been run from this analysis environment.

## First owner-side full-range scan (2026-10-22)

The owner ran `tools/Run-Discovery.ps1` against the configured IoT `/16` from Windows (`Ethernet 2`). The console reports:

| Observation | Actual console result | Interpretation |
|---|---:|---|
| IP addresses attempted | 65,534 | Full `/16` ICMP sweep completed |
| ICMP/neighbor candidates | 63 | The report keeps separate lists of real ICMP replies and neighbor records; counts must not be conflated |
| TCP open port results | 10 | **Ports**, not necessarily ten hosts |
| Candidate /24 | `redacted.invalid/24` | All reported candidates fall in this slice; does not establish thermostat is among them |
| Wall-clock time | 277.6 seconds | Do not repeat full scan merely to read results |
| IPv4 route | Blank prefix and next hop | Reporting defect in `Find-NetRoute` output; use `Get-NetRoute` |
| Thermostat IP identified | No | No model identity, DHCP lease or cloud MAC correlation available |

The **existing private** report is stored on the owner's PC under `%LOCALAPPDATA%\CarrierSmartHome-Research\20261022-114459\iot-private.json`. Never commit private raw scan reports to GitHub.

Review the saved report with no network traffic using `tools/Run-Discovery.ps1 -ReviewOnly`. This uses `tools/Review-IoTScan.ps1`, which automatically finds the newest `iot-private.json` and runs the independently tested Python parser `tools/triage_iot.py`. The parser reports each candidate IP, actual ICMP evidence, any neighbor-cache MAC, and per-host TCP port list. It keeps separate totals for ports versus hosts with ports. It does **not** claim a host with open TCP 80/443 is the thermostat.

For independent identity confirmation, compare the actual Carrier Wi-Fi client in the VLAN's router/DHCP client list with any available hostname/MAC. When the authenticated cloud `getUserWithDevices` flow works, correlate reported device identity and MAC if returned. Neither is required merely to review this scan. If MACs are absent, this is normal for traffic routed from the primary LAN into a different VLAN.

The original scanner's route-line defect has been corrected by reading `Get-NetRoute` entries and selecting the longest IPv4 prefix match. The line is labelled a *route-table observation*, not a verified path through VLAN firewall rules. The correction applies to **future scans only**; the `-ReviewOnly` command does not rewrite old evidence.

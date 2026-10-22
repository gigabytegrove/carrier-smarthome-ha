# Evidence-based status — 2026-10-21

| Workstream | Status | Verifiable artifact |
|---|---|---|
| Android XAPK unpack / Hermes v96 string extraction | COMPLETE | `analyze_xapk.py`, `summary.json` |
| Extract 140 GraphQL operation/fragment definitions | COMPLETE | `graphql/`, `graphql-index.json`, `graphql-catalog.json` |
| Parse 7 native DEX string sets | COMPLETE | `analyze_native_apk.py`, `native-dex-findings.json` |
| Resolve compiled BuildConfig field values and AWS IoT entry-tier hostname | COMPLETE (static) | `trace_native_constants.py`, `native-constant-xrefs.json`, `BUILD_CONFIG_EVIDENCE.md` |
| Attribute 60 Hermes / 5 DEX Carrier URL literals | COMPLETE | `map_transport_evidence.py`, `transport-evidence.json` |
| Document cloud auth/token and entry-level operations | STATIC EVIDENCE | `CLOUD_PROTOCOL.md` |
| Implement sanitized Carrier HAR inspection | TESTED OFFLINE | `tools/analyze_har.py`, `tests/test_discovery.py` |
| Implement cloud GraphQL read-only client core | TESTED OFFLINE | `tools/cloud_protocol.py`, `tests/test_discovery.py` |
| Automatically discover private IP subnet, neighbors, mDNS, TCP | TESTED OFFLINE (LAN pending) | `tools/auto_discover.py`, `tools/Run-Discovery.ps1` |
| Identify a TSTATCCEWF-01 private IP | NOT YET | Requires on-LAN result / identity correlation |
| Confirm SmartHome new thermostat API hostname | NOT YET | Requires runtime evidence; legacy host ≠ proof |
| Authenticate and fetch owner entry-level thermostat | NOT YET | Requires user-authorized account session |
| Home Assistant entity registration and real device controls | NOT YET | Depends on successful live cloud path |

No live Carrier account or TSTATCCEWF-01 was accessed during this research pass. All tests are offline and self-contained. Do not present cloud or local control as operational until observed against an owner device.

## Multi-VLAN discovery update (2026-10-22)

The scanner now includes multiple private connected networks, explicit routed VLAN prefixes, and optional authorized CIDRs, bounded to /24 each. The supplied scan log only demonstrates main-LAN `redacted.invalid/24` discovery; the IoT VLAN subnet is still unknown. See [`VLAN_DISCOVERY.md`](VLAN_DISCOVERY.md) for procedures and limitations. No thermostat-specific LAN IP or API has been confirmed.

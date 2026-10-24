<div align="center">
  <img src="custom_components/carrier_smarthome/brand/icon.png" width="144" alt="Carrier SmartHome icon" />

  # Carrier SmartHome

  **Home Assistant control for the Carrier Smart Thermostat TSTATCCEWF-01.**

  [![Install with HACS](https://img.shields.io/badge/HACS-Install%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gigabytegrove&repository=carrier-smarthome-ha&category=integration)
  [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-FFDD00?logo=buymeacoffee&logoColor=000000)](https://buymeacoffee.com/gigabytegrove)
  [![PayPal Donate](https://img.shields.io/badge/PayPal-Donate-00457C?logo=paypal&logoColor=white)](https://paypal.me/gigabytegrove)
  [![Latest release](https://img.shields.io/github/v/release/gigabytegrove/carrier-smarthome-ha?label=Release)](https://github.com/gigabytegrove/carrier-smarthome-ha/releases)

  Unofficial Home Assistant integration · Carrier's native SmartHome cloud API · **No Matter**
</div>

## What it does

**Carrier SmartHome** brings a supported Carrier thermostat into Home Assistant as a **single, standard climate device**. Change heating/cooling modes, view indoor temperature and humidity, manage thermostat targets, and use the familiar Home Assistant interface—without separate power switches, duplicate controls, or artificial configuration gates.

The integration authenticates with the same Carrier SmartHome account used in the Android app (`com.carrier.home`). It communicates with Carrier's native cloud GraphQL service; **local-only HVAC control has not yet been established**.

### Compatibility: one verified thermostat

| Physical thermostat | Carrier cloud model | Status |
|---|---|---|
| **Carrier Smart Thermostat `TSTATCCEWF-01`** | `TSTATCCEEF-01` | **Verified with actual hardware** |

**This is the only thermostat model we currently claim is supported.** Carrier reports a slightly different cloud model identifier for the same verified device. Support for other Carrier SmartHome models, Carrier Infinity controls, and legacy Carrier integrations has **not** been established; don't assume compatibility based on branding alone.

### Features

- **Native Home Assistant climate entity:** Off, Heat, Cool, Heat/Cool (Auto), and Fan Only choices, with setpoint controls where the mode permits them. **Off/Cool switching has been verified on the physical thermostat**; other mode commands still require individual hardware validation.
- **Thermostat telemetry:** current indoor temperature, indoor humidity, outdoor temperature, targets, reported HVAC mode and fan setting.
- **Fan control:** Auto/On choices are exposed by the integration; independent HA-originated fan commands have **not yet been fully verified** on this model.
- **Connectivity-aware display:** a Carrier-reported Wi-Fi disconnect immediately disables live entities. A brief cloud/API interruption retains the most recent verified online readings for at most **90 seconds**, visibly flagged as potentially stale, while *all HVAC writes remain blocked* until a successful fresh cloud poll. Separately labeled last-reported diagnostics remain readable.
- **Safe command handling:** a single native cloud mutation per command, a current connection check, serialized cloud mutations, latest-wins coalescing of unsent commands, and independent read-only post-command confirmation. Pending mode, fan and setpoint selections remain visible together, but subsequent cloud mutations include only the newly adjusted fields; a fan adjustment never needlessly re-sends Cool/Heat. Repeated clicks on the same still-pending value are ignored safely. You can make another adjustment as soon as the previous cloud mutation is acknowledged—without waiting for the previous verification window. Home Assistant displays the requested mode, fan setting or temperature immediately while confirmation is pending. This is a **temporary optimistic display only**: the raw Carrier telemetry and historical sensors remain unchanged until Carrier actually reports new values. Cloud rejection, preflight failure, cancelled commands and inconclusive 64-second verification revert the display to the last Carrier-reported state; an inconclusive result does not prove the physical thermostat ignored the command.
- **Simple configuration:** sign in with your Carrier SmartHome credentials and use the normal climate card; no separate options are required to unlock mode controls.

## Installation via HACS

[![Open repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gigabytegrove&repository=carrier-smarthome-ha&category=integration)

1. In Home Assistant open **HACS → ⋮ → Custom repositories**. Paste `https://github.com/gigabytegrove/carrier-smarthome-ha`, choose **Integration**, and add it. This integration is **not currently listed in the default HACS catalog**.
2. Open **Carrier SmartHome** in HACS and download the latest published release. If the screen still offers a commit hash, refresh HACS metadata or explicitly choose the available version; HACS download does **not** restart Home Assistant.
3. **Restart Home Assistant.** Go to **Settings → Devices & services → Add integration → Carrier SmartHome** and sign into your Carrier SmartHome account.
4. Open the discovered thermostat's **climate card**. Mode and supported temperature controls are available directly on that card.

**Updating:** download the new release in HACS, **restart Home Assistant**, and check **Carrier SmartHome → Download diagnostics → `integration_manifest.version`** to verify the installed version. Cloning the repository on a different computer does not update the running Home Assistant container. Existing `carrier_smarthome` entities and account configuration remain compatible with upgrades.

Alternative manual installation: copy `custom_components/carrier_smarthome/` into your Home Assistant `config/custom_components/` directory and restart. [Detailed setup and troubleshooting](docs/HACS_INSTALLATION.md).

## Thermostat diagnostics

**Command trace (v0.5.9):** Download diagnostics groups meaningful command stages by a local command ID. The event field `requested` means the control fields newly requested by Home Assistant; `pending_overlay` shows all unverified preferences temporarily displayed together. `mutation_sent.requested` lists the *actual fields submitted to Carrier*, not merely the optimistic display. Readback events log only the first observation per source and changes, followed by a `verification_summary` counting all cloud reads and suppressed repeated samples. Multiple read-only detail/listing checks are not duplicate writes. The in-memory trace is limited to 160 events and resets when Home Assistant restarts. It does not identify whether a service call originated from a user, script or automation.

**Passive cloud history (v0.5.9):** Diagnostics also include `cloud_control_trace_started_utc` and `cloud_control_transition_history` (up to 100 events). On each successful Carrier listing poll, the integration saves a sanitized baseline and subsequent changes in reported mode, fan, targets and schedule-enabled status. Detailed-query observations are tracked independently so cloud propagation differences are not mislabeled as physical thermostat changes. A transition without an active Home Assistant command is tagged only as an observed cloud-state change; it **does not** establish whether the schedule, thermostat, official app, another controller, or delayed cloud propagation caused it. This timeline is RAM-only, resets on restart, and never includes serials, account identity or tokens.


Home Assistant diagnostic entities have concise names (for example **Max Heating Setpoint**, **Min Cooling Setpoint**, **Heating Setpoint**, and **Fan Mode**). These are **last cloud-reported values**, not guaranteed live thermostat measurements; their `value_source`, `value_freshness`, and `last_successful_poll_utc` attributes document the distinction. Do not use these diagnostic entities for HVAC automation. Existing unique IDs and history are preserved on upgrade; Home Assistant may retain existing entity IDs or user-customized labels. The unsupported Comfort Profile and Equipment Status diagnostics are retired.

## Cloud connection resilience (v0.5.5)

If Carrier cloud polling fails momentarily, live readings no longer disappear instantly. The last *successfully confirmed online* values can remain visible for up to 90 seconds with `telemetry_freshness: brief_cloud_recovery_grace_may_be_stale`, **but controls are blocked** until Carrier successfully responds again. On a genuine Carrier-reported thermostat disconnection, live entities become unavailable immediately. After the grace period, live entities become unavailable; last-reported diagnostics remain separately labeled.

The `Native cloud API readable` binary sensor now shows **Off** (rather than `Unavailable`) on a failed poll, and its attributes expose the last successful poll, failure category and recovery delay. The privacy-sanitized Home Assistant diagnostics expose the same information, helping identify a temporary outage versus rate limiting, authentication failure or an empty listing. The integration respects HTTP 429 `Retry-After`, uses bounded reconnect backoff, and no longer erases devices on a transient empty query. These changes improve recovery; they are **not a claim that Carrier caused the screenshot incident**. Actual HA logs are needed to establish that.

## Cloud-control performance

**v0.5.5** retains rapid confirmation from v0.5.3 and checks Carrier's detailed native GraphQL view at the **first** post-command readback instead of waiting for a later attempt. The Home Assistant climate card now reflects a valid new request **immediately** (marked `control_status: pending_cloud_confirmation`) rather than waiting on Carrier, and promotes the state to Carrier-reported once cloud readback confirms it. Rejected or unconfirmed requests automatically revert. A bounded, identifier-free `control_event_history` in Download diagnostics records cloud preflight, the single mutation, readbacks and rollback/verification; it never contains login credentials, serials, MACs or cloud device IDs. Confirmation runs in the Home Assistant process without blocking another control request. It remains bounded to roughly 64 seconds for unusually slow cloud propagation; it **never** repeats a mutation automatically. A rapid reversal always sends the new requested mode even when old cloud telemetry already displays that target. Since Carrier does not provide a physical execution sequence number, the integration will report an uncertain result rather than falsely confirm a fast reversal from unchanged cached telemetry. Routine polling is **60 seconds** to reduce unnecessary Carrier API requests; a confirmed user-initiated command updates the Home Assistant coordinator immediately without waiting for that poll.

Because this is a cloud service, the physical thermostat and the cloud can still take time to reconcile. Faster readbacks improve *Home Assistant display latency*, not the thermostat's physical actuation speed. Readback behavior on real hardware should continue to be validated after updates.

## Proprietary local control: targeted device investigation

**v0.5.4 lets the owner investigate the already identified thermostat IP directly—no repeated Omada ZIP export.** Run the source-provided PowerShell probe with `-DirectIP` and `-AcknowledgeIpRisk`, starting in `-PlanOnly` mode. Only a single explicitly selected host is contacted. The address was previously verified but might have been reassigned by DHCP; owner authorization does **not** establish current device identity. The recommended full-mode scan is bounded to 12 concurrent connections for this embedded device.

```powershell
.\tools\Probe-CarrierLocalDeep.ps1 -DirectIP '<thermostat-ip>' -AcknowledgeIpRisk -PlanOnly
.\tools\Probe-CarrierLocalDeep.ps1 -DirectIP '<thermostat-ip>' -AcknowledgeIpRisk -FullTCP -Concurrency 12
```

For completeness, the older export-based and live-Omada selection methods remain supported, but are no longer mandatory. An all-closed port scan is **not evidence** that Carrier has no local protocol: the thermostat may connect outbound to its cloud service, use an untested UDP protocol, or be blocked across VLANs. See [LAN probe guide](docs/LOCAL_PROBE_GUIDE.md).



**Local HVAC commands are not implemented or advertised as working.** The Android application contains hints of local command and MQTT code, but we haven't proved an authenticated, non-Matter LAN control protocol is active on the `TSTATCCEWF-01` firmware.

The repository includes an owner-side, **single verified thermostat** reconnaissance tool for TCP/UDP discovery. It can target an owner-authorized **known thermostat IP directly** without an Omada export, or independently verify a fresh Omada MAC/IP association. Known-IP mode explicitly warns that DHCP ownership has not been reverified. It scans only the selected host and never issues an HVAC write. A closed TCP port scan alone cannot rule out local control using UDP, BLE, or outbound connections.

See the [local discovery guide](docs/LOCAL_PROBE_GUIDE.md) and [protocol research](research/LOCAL_PROTOCOL_050.md). For the known device, start with the [direct-IP LAN probe](docs/LOCAL_PROBE_GUIDE.md), then inspect its sanitized results. If no inbound ports respond, the next evidence is a passive traffic capture at the IoT gateway during official-app control. Do not claim local control until a real command is verified. No Matter pairing, DNS hijacking, or firmware changes are required.

## Support this integration

If Carrier SmartHome makes your Home Assistant setup easier, support the ongoing maintenance and protocol research:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-FFDD00?logo=buymeacoffee&logoColor=000000)](https://buymeacoffee.com/gigabytegrove) [![PayPal](https://img.shields.io/badge/PayPal-Donate%20%40gigabytegrove-00457C?logo=paypal&logoColor=white)](https://paypal.me/gigabytegrove)

You can also [report an issue](https://github.com/gigabytegrove/carrier-smarthome-ha/issues) or review the [changelog](CHANGELOG.md).

## Privacy and attribution

Your account credentials are stored by Home Assistant for Carrier authentication; this project does not require Matter pairing or a separate cloud account. **Never post** credentials, raw diagnostics, MACs, IP addresses, serials, unredacted packet captures, or authentication tokens in public GitHub issues.

Carrier SmartHome is an **independent community integration**, not affiliated with, endorsed by, or supported by Carrier. Carrier names, logos, and product marks belong to their respective owners. The project icon identifies the supported Carrier equipment; its inclusion does not imply an official relationship.

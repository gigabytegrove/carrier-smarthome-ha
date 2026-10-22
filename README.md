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
- **Connectivity-aware display:** live entities are unavailable when Carrier reports the thermostat disconnected; clearly labeled last-cloud-reported diagnostics may contain cached values.
- **Safe command handling:** a single native cloud mutation per command, a current connection check, no hidden command queue, and read-only post-command confirmation. Home Assistant only publishes states observed from Carrier, never invented optimistic states.
- **Simple configuration:** sign in with your Carrier SmartHome credentials and use the normal climate card; no separate options are required to unlock mode controls.

## Installation via HACS

[![Open repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gigabytegrove&repository=carrier-smarthome-ha&category=integration)

1. In Home Assistant open **HACS → ⋮ → Custom repositories**. Paste `https://github.com/gigabytegrove/carrier-smarthome-ha`, choose **Integration**, and add it. This integration is **not currently listed in the default HACS catalog**.
2. Open **Carrier SmartHome** in HACS and download the latest published release. If the screen still offers a commit hash, refresh HACS metadata or explicitly choose the available version; HACS download does **not** restart Home Assistant.
3. **Restart Home Assistant.** Go to **Settings → Devices & services → Add integration → Carrier SmartHome** and sign into your Carrier SmartHome account.
4. Open the discovered thermostat's **climate card**. Mode and supported temperature controls are available directly on that card.

**Updating:** download the new release in HACS, **restart Home Assistant**, and check **Carrier SmartHome → Download diagnostics → `integration_manifest.version`** to verify the installed version. Cloning the repository on a different computer does not update the running Home Assistant container. Existing `carrier_smarthome` entities and account configuration remain compatible with upgrades.

Alternative manual installation: copy `custom_components/carrier_smarthome/` into your Home Assistant `config/custom_components/` directory and restart. [Detailed setup and troubleshooting](docs/HACS_INSTALLATION.md).

## Cloud-control performance

**v0.5.3** checks Carrier's detailed native GraphQL view at the **first** post-command readback instead of waiting for a later attempt. When Carrier confirms the changed mode, fan setting, or target, the integration pushes that **verified response** into Home Assistant immediately. Confirmation remains bounded to roughly 64 seconds for unusually slow cloud propagation; it **never** sends the command again automatically. Routine polling is 30 seconds to reduce unnecessary requests.

Because this is a cloud service, the physical thermostat and the cloud can still take time to reconcile. Faster readbacks improve *Home Assistant display latency*, not the thermostat's physical actuation speed. Readback behavior on real hardware should continue to be validated after updates.

## Proprietary local control: ongoing investigation

**Local HVAC commands are not implemented or advertised as working.** The Android application contains hints of local command and MQTT code, but we haven't proved an authenticated, non-Matter LAN control protocol is active on the `TSTATCCEWF-01` firmware.

The repository includes an owner-side, **single verified thermostat** reconnaissance tool for TCP/UDP discovery. It refuses stale Omada exports, does not scan unrelated devices, and never issues an HVAC write. A closed TCP port scan alone cannot rule out local control using UDP, BLE, or outbound connections.

See the [local discovery guide](docs/LOCAL_PROBE_GUIDE.md) and [protocol research](research/LOCAL_PROTOCOL_050.md). The next evidence needed is a fresh connected-client export and/or a sanitized passive traffic capture from the IoT gateway while operating the official Carrier SmartHome app. No Matter pairing, DNS hijacking, or firmware changes are required.

## Support this integration

If Carrier SmartHome makes your Home Assistant setup easier, support the ongoing maintenance and protocol research:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-FFDD00?logo=buymeacoffee&logoColor=000000)](https://buymeacoffee.com/gigabytegrove) [![PayPal](https://img.shields.io/badge/PayPal-Donate%20%40gigabytegrove-00457C?logo=paypal&logoColor=white)](https://paypal.me/gigabytegrove)

You can also [report an issue](https://github.com/gigabytegrove/carrier-smarthome-ha/issues) or review the [changelog](CHANGELOG.md).

## Privacy and attribution

Your account credentials are stored by Home Assistant for Carrier authentication; this project does not require Matter pairing or a separate cloud account. **Never post** credentials, raw diagnostics, MACs, IP addresses, serials, unredacted packet captures, or authentication tokens in public GitHub issues.

Carrier SmartHome is an **independent community integration**, not affiliated with, endorsed by, or supported by Carrier. Carrier names, logos, and product marks belong to their respective owners. The project icon identifies the supported Carrier equipment; its inclusion does not imply an official relationship.

## Local-control research — current state

Local proprietary control is **not yet demonstrated** on TSTATCCEWF-01. The Wi-Fi/cloud integration works; the APK contains local-command names but no verified LAN HVAC protocol has been identified. For live single-device discovery **without an Omada ZIP**, see [Live Connected Clients procedure](docs/LOCAL_PROBE_GUIDE.md). It requires the actual current IP and full MAC from the Omada Connected Clients screen and never reuses the historical lease. Manual selection is owner-attested, not independently authenticated. No Matter implementation is included.

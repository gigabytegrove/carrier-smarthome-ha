# Carrier SmartHome Native for Home Assistant

**Unofficial experimental integration · Alpha 9 · Native Carrier GraphQL cloud · No Matter**

For Carrier SmartHome entry-level thermostats (physical unit tested: `TSTATCCEWF-01`, cloud model: `TSTATCCEEF-01`). This is independent of the older Carrier Infinity Home Assistant integration.

## Install and update with HACS

1. In Home Assistant, open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/gigabytegrove/carrier-smarthome-ha` as an **Integration** repository.
3. Download **Carrier SmartHome Native** from HACS. Select the default `main` branch if prompted.
4. **Restart Home Assistant**, then open **Settings → Devices & services → Add integration → Carrier SmartHome**.
5. Sign in with your existing Carrier SmartHome account. Credentials remain in your HA configuration; never post them in issues.
6. On later updates, download the new revision in HACS and restart HA. Check the integration manifest version.

[Detailed HACS installation and troubleshooting](docs/HACS_INSTALLATION.md)

## Thermostat controls

The **climate entity is the primary thermostat control** for Off, Heat, Cool, Auto, Fan Only, Auto/On fan, and setpoints. The single **HVAC Power** switch is a convenience for one-click On/Off; there are no redundant mode or fan selector entities.

Commands change physical HVAC operation. They are **disabled by default** until the owner deliberately enables them. In **Settings → Devices & services → Carrier SmartHome → Configure/Options**:

| Option | Enables | Default |
|---|---|---|
| Experimental HVAC mode and power | Climate Off/Heat/Cool/Auto/Fan Only and HVAC Power switch | Off |
| HVAC Power On mode | Heat/Cool/Auto/Fan Only when power switch turns On | Unset (no automatic On mode) |
| Experimental fan Auto/On | Climate fan Auto/On selector | Off |
| Experimental temperature setpoints | Climate heating/cooling target changes; requires mode/power control | Off |

**Do not enable every option merely to test installation.** First verify the physical thermostat is online and reading correctly. Enable one feature at a time. The precise Carrier fan Circulation enum has not been established, so it is not offered.

Each command performs a fresh Carrier online check, sends **one** `updateEntryLevelZone` mutation, and compares subsequent cloud reads. A failed read-back results in an error; the integration **never blindly retries the write**. Mode, fan, and setpoint writes have not yet been owner-verified on the physical thermostat; use the official Carrier app to restore a desired state if needed. Turning the HVAC off may interrupt heating/cooling.

## State and diagnostics

- When Carrier reports the thermostat **online** and an API poll succeeds, HA displays the climate and live sensors.
- When Carrier reports it **offline**, the live climate and measurement entities become unavailable. Last cloud-reported values may be stale, so they are separate **diagnostic entities disabled by default** on new installations. You may enable individual diagnostic entities if useful.
- Carrier-reported device connectivity and Carrier API readability are separate binary sensors.
- Multiple thermostats/zones are discovered and added without duplicates.

On October 22, 2026, the owner verified Carrier cloud sign-in, device identity, model mapping discrepancy, and app-to-cloud synchronization. A real Wi-Fi disconnection occurred earlier; after reboot, the Carrier online flag and GraphQL updates resumed. The app-side cooling target changed from 76°F to 73°F and back in both read paths; the final heat setpoint and HVAC mode also changed, so **full state restoration was not established**. No HA-originated write has been physically validated.

## Research and LAN probes

Research tools remain under [`tools/`](tools/) and supporting evidence under [`research/`](research/). A proprietary Carrier LAN control interface **has not yet been demonstrated**. The Wi-Fi radio, Bluetooth capability, and APK symbols are not proof of a LAN HVAC API. **No Matter integration, fallback, or commissioning** is in this project.

For current-lease-only, read-only LAN fingerprinting, export an **up-to-date Omada Client ZIP** and use the safety-checked `tools/Probe-VerifiedCarrierLAN.ps1 -PlanOnly` first; it refuses old exports. See [LAN and cloud control research](research/ALPHA8_CLOUD_CONTROLS_AND_LAN.md).

## Development and test status

Run offline regressions from the repository root:

```bash
python -m unittest discover -s tests -v
python tools/validate_hacs.py
python -m compileall -q custom_components/carrier_smarthome tools
```

Offline tests use simulated Home Assistant entities and Carrier responses. They do **not** prove HVAC hardware behavior or standalone HACS runtime compatibility. Do not commit secrets, Omada exports, cloud tokens, network captures, private MACs, or device serials. See [release history](CHANGELOG.md).

# Install and operate Carrier SmartHome Native through HACS

This is a **public custom HACS Integration repository** for Carrier SmartHome's **native cloud GraphQL** API. It is not in HACS's default catalog, not the older Infinity integration, and it contains no Matter code.

## Install / update

1. In HA open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/gigabytegrove/carrier-smarthome-ha` as an **Integration**.
3. Find **Carrier SmartHome Native**, choose **Download**, and select `main` if asked for a version.
4. Restart Home Assistant. **Settings → Devices & services → Add integration → Carrier SmartHome (Native Cloud Alpha)**; log in with the official Carrier SmartHome account.
5. On updates, redownload the newer commit from HACS and restart/reload HA. Confirm `custom_components/carrier_smarthome/manifest.json` version `0.1.0a9` if HA is still using old code. No GitHub Release is required for this custom repository.

## Enabling controls without confusing duplicates

The **primary Climate entity** has HVAC Off / Heat / Cool / Auto / Fan Only, optional target temperature adjustments, and Auto/On fan mode. There is also one **HVAC Power** switch to turn the HVAC Off and back On with a user-specified mode. There are **no independent mode/fan select platforms** and no duplicate control entities. The two controls intentionally share the same guarded command handler.

All HVAC commands are **experimental writes** and **disabled by default**. Find **Settings → Devices & services → Carrier SmartHome → Configure** and explicitly enable:

- **HVAC mode and power control:** Enables the climate mode selector and HVAC Power switch.
- **Power On mode:** Must be Heat / Cool / Auto / Fan Only before the power switch can turn the equipment On. The default Unset deliberately prevents accidental mode selection.
- **Fan Auto/On control:** Separately enable the climate fan selector; Circulation is not offered because the backend value is unverified.
- **Setpoint changes:** Separately opt into climate temperature changes; this requires HVAC mode/power enabled too.

An online Carrier device is required before any write. One command is sent, then bounded cloud read-back; on unconfirmed state the user must inspect the official Carrier app rather than repeatedly hitting the control. A failed readback is *not* proof the mutation failed; do not blindly retry. Changing HVAC mode or fan may physically start/stop equipment. The first live HA write must be tested under owner supervision.

## Online, offline and diagnostics

When the Carrier `connection.isConnected` flag is true and cloud polling succeeds, live climate and sensor values are available. If it reports offline, live climate/measurements are unavailable. Separate **Last cloud-reported** sensors contain data that may be stale and are **disabled in the registry by default on new installations**; manually enable desired diagnostics as needed. Existing HA entity registry preferences are preserved during upgrades.

See **Settings → Devices & services → Carrier SmartHome → Download diagnostics** for sanitized diagnostics. Never post raw tokens, login details, serials, Omada exports, full MACs or pairing information.

## If expected controls aren't visible

1. Verify the HACS installation shows the new version and restart HA after updating Python files.
2. Confirm experimental mode/power control is enabled in **Configure**; otherwise the climate entity intentionally exposes only its current HVAC mode.
3. Check the device is Carrier-reported **Connected** and the cloud API readable sensor is Connected; otherwise control is blocked.
4. Click the **climate entity** in Controls to open the full HVAC mode and fan selector. The HVAC Power switch is an additional convenience, not a replacement for the climate control.
5. For fan settings, separately enable fan control. For target temperatures, separately enable setpoint control.
6. If startup or option save fails, consult **Settings → System → Logs** for domain `carrier_smarthome`, and report a sanitized stack trace (never credentials).

## Proprietary LAN reconnaissance

LAN control **has not** been verified. Export a **new Omada Client ZIP** while the thermostat is connected. `tools/Probe-VerifiedCarrierLAN.ps1 -PlanOnly -Suffix XXXX` validates online MAC/IP identity and export time before sending traffic. Replace `XXXX` locally with the last four MAC hex characters from the device label when multiple thermostats match. Do not add your MAC to the GitHub source. Next run the same command without `-PlanOnly` to test bounded TCP listeners; `-HttpFingerprint` optionally sends a single HTTP HEAD request to a verified device. A rejected old export is a safe stop; don't reuse an old DHCP lease. No Matter, MQTT write or broad network scan.

## Limitations and verification

Cloud sign-in, reads, MAC/device match and official-app-to-GraphQL convergence were owner-verified October 22, 2026. An actual thermostat Wi-Fi dropout explains the earlier offline response reasonably well. Mode, fan and setpoint **mutations from Home Assistant have not been owner-verified**; the code is opt-in and the test suite uses mocks. Local proprietary control remains a research topic. See [Changelog](../CHANGELOG.md) and [Alpha 8 cloud/LAN notes](../research/ALPHA8_CLOUD_CONTROLS_AND_LAN.md).

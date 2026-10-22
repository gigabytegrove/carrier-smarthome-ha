# Alpha 4: baseline cloud values into HA diagnostics

## Evidence and limits

On 2026-10-22 the owner successfully used Carrier GraphQL `assistedLogin`, `getEntryLevelSystems`, and APK-derived `getEntryLevelSystemData` with a real account. At that time the cloud reported one zone, room temperature 73 F, relative humidity 47%, heat 70 F, cool 76 F, outdoor 51 F, mode `off`, and `isConnected=false`. **These were not proven live measurements.** A cloud model `TSTATCCEEF-01` was returned for physical label `TSTATCCEWF-01`. Do not silently normalize those model strings.

## New read-only field inventory

`tools/Get-CarrierValues.ps1` uses the already-working isolated Python environment. It performs authenticated baseline list + a separate, optional APK-derived extended detail query. Output contains only whitelisted climate values; no thermostat identifier or account credential is printed or saved. Detail-query rejection does not hide a successful baseline read. All diagnostics are captured locally if `-NoSave` is omitted, never committed. No Matter. No thermostat mutation.

The expanded optional detail query is **not yet owner-verified**. It requests `current_scene_name` and `connection.rssi` alongside known fields, based on the extracted Android query source. It is not automatically used by Home Assistant polling until verified.

## HA entities added in alpha 4

All are **last cloud-reported**, disabled for ordinary dashboards by the diagnostic entity category, do not set HA measurement statistics and are permitted to show cached values if the last API poll succeeded:

- HVAC mode, fan setting, equipment stage, schedule enabled / disabled.
- Heating maximum and cooling minimum limits where provided.
- Comfort profile (only if returned by the cloud and matched to a safe standard profile; custom names redacted).

Existing live climate and regular humidity/outdoor temperature sensors remain unavailable when `connection.isConnected` is not `true`. The connectivity binary sensor retains cloud online/offline/unknown meaning. These extra entities have no writes. The optional extended query is **not added to automatic HA polling**, preventing an unverified query from causing integration failures.

## Next owner-side steps

1. Clone `main`, run `tools/Get-CarrierValues.ps1` (with `tools/Test-Cloud.ps1` first only if the existing isolated environment is missing). Paste the sanitized console report into the conversation.
2. Install/update the HACS custom integration and restart HA. New diagnostic entities may be hidden from dashboards by default; enable them in the device's entity list if desired.
3. Confirm actual cloud connectivity; no thermostat writes until `online` is verified and readings match the physical thermostat.

# HACS installation and native Carrier SmartHome testing

1. Add `https://github.com/gigabytegrove/carrier-smarthome-ha` under **HACS → ⋮ → Custom repositories**, category **Integration**.
2. Download the latest `main` branch. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Carrier SmartHome**. Enter Carrier credentials in HA, not on GitHub.
4. Open the thermostat climate entity. Its standard mode selector has Off, Heat, Cool, Heat/Cool and Fan Only, independent of integration options. Select the desired mode to turn the system on. When already on, select Off to stop heating/cooling. Fan Auto/On and temperature target controls live in the same climate entity. The retired HVAC Power switch should disappear on setup as part of a targeted registry cleanup.
5. **First write test:** Check the official Carrier app and thermostat are online. Try ONE reversible mode command while observing the physical system. Wait for the HA readback; do not repeatedly click if the command times out. Restore the desired HVAC mode from the official app if unconfirmed.
6. If Carrier reports disconnected, live controls are unavailable and labeled last-cloud-reported diagnostic sensors can remain visible as potentially stale.

**Known limits:** Authenticated cloud reads and official-app → cloud synchronization have been proved. The alpha's outgoing `updateEntryLevelZone` writes have not yet been owner-verified. Fan On is an experimental Carrier GraphQL value; Circulation is not exposed. `turn_on` cannot invent an initial mode. If no prior non-Off Carrier mode has been observed since startup, select Heat, Cool or Auto manually. No Matter and no verified proprietary LAN API.

For update troubleshooting, check manifest `0.5.0` and integration logs. Do not share credentials, hardware identifiers or raw Omada archives.

# HACS installation and native Carrier SmartHome testing

1. Add `https://github.com/gigabytegrove/carrier-smarthome-ha` under **HACS → ⋮ → Custom repositories**, category **Integration**.
2. Download the latest `main` branch. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Carrier SmartHome**. Enter Carrier credentials in HA, not on GitHub.
4. Open the thermostat climate entity. Its standard mode selector has Off, Heat, Cool, Heat/Cool and Fan Only, independent of integration options. Select the desired mode to turn the system on. When already on, select Off to stop heating/cooling. Fan Auto/On and temperature target controls live in the same climate entity. The retired HVAC Power switch should disappear on setup as part of a targeted registry cleanup.
5. **First write test:** Check the official Carrier app and thermostat are online. Try ONE reversible mode command while observing the physical system. Wait for the HA readback; do not repeatedly click if the command times out. Restore the desired HVAC mode from the official app if unconfirmed.
6. If Carrier reports disconnected, live controls are unavailable and labeled last-cloud-reported diagnostic sensors can remain visible as potentially stale.

**Known limits:** Authenticated cloud reads and official-app → cloud synchronization have been proved. The alpha's outgoing `updateEntryLevelZone` writes have not yet been owner-verified. Fan On is an experimental Carrier GraphQL value; Circulation is not exposed. `turn_on` cannot invent an initial mode. If no prior non-Off Carrier mode has been observed since startup, select Heat, Cool or Auto manually. No Matter and no verified proprietary LAN API.

For update troubleshooting, check manifest `0.5.2` and integration logs. Do not share credentials, hardware identifiers or raw Omada archives.

## v0.5.1: Cloud state confirmation after a write

The owner observed Carrier accept an HA mode command but apply the physical mode only after HA's earlier six-second verification window. The old `async_request_refresh()` was debounced and could return without a fresh network fetch; v0.5.1 uses forced reads for command preflight and confirmation with one mutation only. A click to Off that does not change the device must not be declared successful without an actual later cloud observation. Do not repeatedly click Off on error; first check the official Carrier app, then use the read-only `tools/Read-CarrierMode.ps1` script to compare account and detail read paths. No Matter.

## v0.5.2: confirmed mode sync and command queue safety

Owner tests showed Off/Cool toggles initiated in Home Assistant were mirrored by both Carrier GraphQL queries (online throughout); the values changed at successive 15-second observations. This confirms working native HA mode control but not the precise physical activation time of every individual selection. Normal HA background polling was 60 seconds; it is now 30 seconds with Carrier retry-after backoff preserved. When Carrier's *detailed* read returns the requested mode while the account listing lags, HA now receives the verified mode via the coordinator immediately. No guessed or optimistic state is published. While a command is pending confirmation, the next command is rejected rather than queued to run later. If you see a pending-command message, wait and check Carrier before making another change.

The PowerShell observer only READS Carrier and does not itself update Home Assistant. Merely cloning a newer version for PowerShell tests does not update the installed HA container: check the running integration version in HA diagnostics and restart after HACS redownload.

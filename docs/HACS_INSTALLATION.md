# HACS installation and safe alpha verification

This is an unofficial, experimental integration for Carrier SmartHome entry-tier devices, including the cloud-reported `TSTATCCEEF-01` class. The target physical housing is `TSTATCCEWF-01`; do not assume the cloud model string is the same hardware part number. The repository is public, but it is **not** part of the default HACS catalog.

## HACS installation

1. Open **Home Assistant → HACS → ⋮ → Custom repositories**.
2. Paste `https://github.com/gigabytegrove/carrier-smarthome-ha`, set category **Integration**, and add.
3. Find **Carrier SmartHome Native** in HACS, choose **Download**, and use `main` if prompted for a version.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**, find **Carrier SmartHome (Native Cloud Alpha)**, and sign into your **own Carrier account**. Passwords are not needed in GitHub issues or logs.

No Matter setup, pairing code, Wi-Fi address, MQTT broker, or local IP is needed for this cloud alpha. HACS installs only `custom_components/carrier_smarthome`, not the network research tools.

## First test checklist

- [ ] HA starts successfully with the custom integration installed.
- [ ] Carrier account authentication completes in the HA UI.
- [ ] One Carrier cloud-reported thermostat and associated sensors appear.
- [ ] When Carrier reports offline, the climate entity shows *last cloud-reported, unverified* values; live statistical sensors remain unavailable, and the Carrier-reported connectivity binary sensor shows **off**. This is not proof that the physical thermostat is unreachable.
- [ ] With thermostat online, compare displayed temperature, setpoints, and mode with the Carrier SmartHome mobile app.
- [ ] Leave experimental writes **off** until online telemetry and identity are verified.
- [ ] Use **Settings → Devices & services → Carrier SmartHome → ⋮ → Download diagnostics** if you need to share sanitized diagnostic output. Check contents before sharing any diagnostics.

If nothing appears in HACS, check that its custom repository category is **Integration** and the URL is exact, then reload HACS. If the integration does not appear in Add integration after downloading, restart HA and refresh the browser. Look in **Settings → System → Logs** for the `carrier_smarthome` domain rather than sharing credentials.

## How updates work

A public custom HACS repo can be installed from its default branch without a GitHub Release. With no release, HACS displays a commit hash rather than a neat version; it still supports the update workflow. A separately published release can be added later, but is **not** required for initial installation. HACS installations must be restarted/reloaded for Python code updates to take effect.

## Safe publication

Do not file issues containing usernames, tokens, raw HAR files, appliance pairing information, serials, full MAC addresses, private Omada archives or unredacted logs. **Changing files on `main` cannot delete any identifiers already present in GitHub commit history**; a deliberate history rewrite would require a separate safety review and approval.

## Project boundaries

Native Carrier SmartHome cloud GraphQL first; proprietary LAN control only after confirming it exists. No Matter integration, bridge, or fallback. Experimental HVAC commands are intentionally disabled by default and have not been verified against the owner's equipment.

## Alpha 5 connection discrepancy

If your Carrier mobile app can control the thermostat but the `Carrier-reported device connection` sensor says `off`, that binary sensor is faithfully displaying Carrier's GraphQL flag; it does **not** prove the physical thermostat is unreachable. The `Native cloud API readable` sensor independently represents successful API polling. The climate entity displays unverified cloud-reported readings, with an explicit freshness warning. Experimental HVAC writes remain blocked whenever the online flag is false. See `research/ALPHA5_CONNECTION_DISCREPANCY.md` and `tools/Verify-CarrierConnectivity.ps1`.

## Alpha 6: official-app to cloud correlation

The owner has verified that the reported cloud record matches the thermostat MAC, yet **all three native GraphQL queries still report offline** while the phone app controls the unit. Do not treat this flag as authoritative reachability.

On Windows, run `tools/Compare-AppChange.ps1` from a current clone. The script first reads two cloud sources, pauses while you make a **manual, reversible one-degree change** in the official phone app, reads the cloud again, and asks you to **manually restore** the original setting. It then checks whether both queried sources return to baseline.

Only the owner makes or restores thermostat changes. The script never issues thermostat commands, does not log identifiers, and must not be considered a substitute for live HA control validation. It does send credentials and a private serial to Carrier for authenticated reads, as expected.

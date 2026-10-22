# Thermostat identification from Omada export (private evidence summarized)

The supplied private Omada archive recorded an offline Carrier-named smart thermostat, with several historical IP assignments. Matching the printed thermostat serial to the client MAC is stronger evidence than a hostname, IP address, or vendor prefix. The export also contained at least one **other** smart thermostat client, so selecting the first record by name is unsafe.

**No MAC, serial, IP address, matching suffix, SSID, AP name, or full client inventory is published here.** Earlier commits contained some identifiable test fixtures; see the privacy note in `docs/HACS_INSTALLATION.md` before reusing public history. The original owner-side export remains private and is not included in this repository.

The correlation utility `tools/omada_identity.py` matches by validated device MAC, and refuses ambiguous matches. `tools/Review-OmadaExport.ps1` automatically finds the latest local archive and saved scan, but no longer embeds a device-specific MAC suffix. If Omada lists more than one thermostat, supply `-MacSuffix` locally (last four hex digits of its label MAC) to select the intended device; **never commit that value**. A historical IP alone never confirms a current connected lease.

Project scope: Native Carrier SmartHome cloud access first, proprietary LAN research second. No Matter bridge, client, or fallback. No active or invasive thermostat changes during local identification.

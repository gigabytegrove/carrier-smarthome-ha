# v0.1.0-alpha.1 — first installable Carrier SmartHome native-cloud integration

- First Home Assistant custom integration, not a research-only collection of scripts.
- Uses the Carrier SmartHome account username/password directly in the HA config flow (no IP or URL fields).
- Implements login and refresh based on the documented assistedLogin Carrier cloud GraphQL flow.
- Entry-level device discovery via either `getEntryLevelSystems` or the APK-derived `getUserWithDevices` + `getEntryLevelSystemData` fallback.
- Read-only climate entities for actual returned HVAC mode, current temperature, humidity and setpoints. Sensors for humidity and outside temperature, plus cloud online status.
- Polling, connection recovery, reauthentication and managed HA platform lifecycle.
- Experimental HVAC mode/setpoint mutation with validation, disabled unless the owner explicitly enables it in integration options.
- No Matter, firmware modifications, local connection impersonation or fake entity data.
- Includes independent read-only cloud smoke test for Windows/PC before Home Assistant installation, plus `tools/Test-Cloud.ps1` isolated environment setup.
- Existing IoT VLAN, Omada identification, APK GraphQL catalog and LAN research retained unchanged.

**Testing:** Offline unit tests completed; does not claim live Carrier account or Home Assistant core validation. Actual success of the SmartHome credentials, cloud schema, command execution and device compatibility still needs user-side evidence. Treat this as an engineering alpha, not a production HVAC controller.

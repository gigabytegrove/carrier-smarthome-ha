# Alpha 8 — native Carrier cloud HVAC control and proprietary LAN reconnaissance

## Verified before this release

- The official Carrier Android application successfully changed the matching physical thermostat cooling target from 76 F to 73 F and restored it to 76 F; both Carrier native `getEntryLevelSystems` and `getEntryLevelSystemData` queries updated within two polls.
- The thermostat experienced a Wi-Fi disconnection earlier; after manual restart the Carrier cloud flag became online, and Home Assistant's owner screenshot showed its connected state and real humidity/temperature data.
- The printed physical model is `TSTATCCEWF-01`; Carrier's cloud identifies the matching device as `TSTATCCEEF-01`. Firmware observed in Home Assistant, but no claim about firmware's local APIs.
- There is **no** live owner-side test yet of our `updateEntryLevelZone` mutation. Therefore controls are opt-in and considered experimental.

## How to test the Home Assistant Controls area

1. HACS: redownload/upgrade the custom Carrier SmartHome Native repository, restart Home Assistant, confirm integration manifest `0.1.0a8`.
2. Settings -> Devices & services -> Carrier SmartHome (Native Cloud Alpha) -> Configure/Options. Enable experimental HVAC mode control. **Leave separate setpoint-write control off**. Select an explicit Power On mode (Heat, Cool or Auto). Do not leave Unset if you want the HVAC Power switch's On command.
3. Open the device page. Check Carrier-reported connection is Connected. A new **HVAC power** switch should appear in Controls, and the climate card offers Off / Heat / Cool / Auto modes. Switching Off sends native GraphQL `updateEntryLevelZone` mode `off`. Switching On sends your selected mode.
4. Before any live write, check the official app's present mode and heat/cool setpoints and ensure the thermostat is safely testable; do NOT assume Off is a harmless no-op. Select one mode change from Home Assistant and verify the official app/thermostat agrees. Restore desired mode if necessary.
5. The write helper requires a fresh cloud poll, validates the online status, submits the mutation only once, and performs up to 3 cloud readbacks. If not confirmed, HA returns an error telling you to verify directly in Carrier's app. **Never automatically repeat an unverified write.**
6. If control doesn't appear, check Options, enabled entities and the integration version. Take a sanitized HA diagnostics export if needed; never share credentials or raw MQTT/Omada exports.

## Local protocol boundary and read-only experiment

Carrier's published documentation and UEI's Wi-Fi/Bluetooth FCC grant establish radio hardware and cloud/app operation, **not an authenticated proprietary local HVAC API**. The Android strings `LocalControlReqPacket`, `SendLocalControlCommandRead/Write`, and `MqttProxy` are leads, not evidence these code paths execute for this model. AWS IoT endpoint references may represent **outbound connections** and do not mean the thermostat runs a LAN MQTT broker.

1. In Omada, export a **new** Client ZIP after confirming the actual thermostat is connected in the client list (not a stale lease).
2. On Windows with the cloned repo, `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Probe-VerifiedCarrierLAN.ps1 -PlanOnly`. The script checks archive freshness and resolves the target from its matching MAC suffix without printing the full address. Old Omada exports fail closed.
3. Run the same command without `-PlanOnly` to test bounded TCP connections to 80, 443, 8080, 8443, 1883, 8883. This does not send protocol commands.
4. Add `-HttpFingerprint` to ask any reachable HTTP/HTTPS listener a single unauthenticated `HEAD /`; it reports only whether an HTTP status was returned. No cookies, logins, HTTP POST, MQTT publish, UDP protocol interaction, or Matter.
5. An all-closed result **does not** rule out local control via UDP, BLE, outbound cloud TLS, or a dynamically opened service. No successful local HVAC control has been demonstrated.

## Remaining verifications

Actual HA service execution; mutation acceptance; physical thermostat mode change; cloud post-write convergence; switching to Off and back; account reauth after refresh token expiry; local TCP reachability and classification on a *fresh* Omada client lease. The offline test suite uses simulated carrier/HA responses and cannot establish any of these.

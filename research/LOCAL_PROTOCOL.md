# Native proprietary LAN protocol status — v0.5.0

**Scope:** Carrier SmartHome entry-level thermostat `TSTATCCEWF-01` (cloud alias `TSTATCCEEF-01`), not legacy Infinity. No Matter transport, DNS interception, firmware replacement, secret extraction, or guessed HVAC command.

## Verified versus unresolved

- A real owner Carrier account can authenticate against native Carrier GraphQL, retrieve device mode, temperature, humidity and setpoints, and observe official-app changes in cloud telemetry.
- Omada history identified the target Wi-Fi MAC, but an historical IP is **not** a current lease. The deep probe requires a new current connected-client ZIP and confirms one unique active MAC/IP in the authorized IoT VLAN before sending packets.
- Native app BuildConfig contains an AWS IoT ATS hostname; this may be the endpoint for an **outbound** TLS/MQTT connection. It does not establish an inbound LAN MQTT port.
- APK `LocalControlReqPacket`, `SendLocalControlCommandRead/Write` and `MqttProxy` symbols are leads only; usage on this thermostat is **unverified**.
- Carrier's product description documents app/cloud remote control, not a public proprietary LAN API. Older Carrier Infinity local-control projects apply to different device families and may require intrusive DNS/firmware changes.

## v0.5.0 tool

[Read the comprehensive native LAN probe guide](../docs/LOCAL_PROBE_GUIDE.md). `tools/Probe-CarrierLocalDeep.ps1` (single engine Python + Windows wrapper) checks a currently verified single target. Legacy `Probe-VerifiedCarrierLAN` filenames are compatibility shims pointing at this engine, **not independent scanners**. With `-FullTCP` it attempts TCP 1–65535, with bounded concurrency and timeouts, then candidate HTTP/TLS/MQTT fingerprints and three read-only unicast UDP discovery requests. Only redacted summary data is saved. No local HVAC write is attempted.

## Follow-up proof criteria

1. Connected current device record in Omada. **Tool implemented; fresh owner export required.**
2. Actual device port/service evidence. **Not yet obtained.**
3. Specific non-Matter local protocol, authentication and a read-only result. **Unknown.**
4. Reversible local HVAC command with physical feedback, safety and rollback. **Unknown.**

A positive listener test only proves a listener. A negative result can be caused by firewall/VLAN rules or an outbound-only/cloud architecture. For references and research boundaries see [LOCAL_PROTOCOL_050.md](LOCAL_PROTOCOL_050.md).

## Live Connected Clients option

An alternative to fresh ZIP is now available: the owner reads the CURRENT IP and full MAC directly from Omada's Connected Clients screen and confirms the live screen in the Windows probe (`-LiveOmada`). Validation is syntax/network/suffix only; this is **not independent proof of a MAC-to-IP binding**. The report explicitly marks it as owner-attested and never includes the IP or MAC. The old saved 08:14 ZIP never gets silently used as a fallback. Keep the sample rate bounded and run the full scan only once.

## Additional owner-provided Android APK string-table evidence (v1.2.42)

A fresh offline inspection of the original Hermes v96 JS bundle (80,776 string entries) found the exact symbol names `sendLocalControlCommand`, `SendLocalControlCommandRead`, `SendLocalControlCommandWrite`, `GenerateLocalcontrolRequestPacket`, and `LocalControlReqPacket`. It also contains diagnostic messages concerning an encrypted/decrypted response and a key, `MqttProxyControl`, and an independent `getEtBleSessionKey` GraphQL operation. **These strings do not establish which transport carries a command, whether it runs for this model, or how to authenticate.** In particular, BLE session keys may be for device provisioning. Do not send guessed encrypted packets, publish MQTT messages, or flash firmware. Correlate traffic from an actual authorized app operation and the exact model first.

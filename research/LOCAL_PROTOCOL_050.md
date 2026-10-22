# v0.5.0 — Evidence-based native LAN protocol research

## What has been established

- Owner-confirmed physical thermostat model: TSTATCCEWF-01, cloud model: TSTATCCEEF-01. The connected home device is linked to its cloud record using MAC identity without committing full device identifiers.
- Carrier's native GraphQL API now authenticated successfully and mirrored official app setpoint changes; the cloud route is real, but not a local protocol.
- Carrier's official material describes Wi-Fi-connected remote control via the SmartHome application and third-party compatibility, **not a public or supported proprietary LAN endpoint**. Source: https://www.carrier.com/us/en/residential/smart-thermostats/tstatccewf-01/
- APK constants include an AWS IoT Core ATS hostname and GraphQL endpoints. AWS IoT is an **outbound cloud** lead; an MQTT listener on the thermostat is not implied.
- Hermes/DEX symbols include `LocalControlReqPacket`, `SendLocalControlCommandRead`, `SendLocalControlCommandWrite` and `MqttProxy`. They are leads from a multi-product app, **not proof of execution on TSTATCCEWF-01**.

## What older projects do NOT establish

- `Infinitude` (https://github.com/nebulous/infinitude) targets Carrier/Bryant Infinity systems and rewrites server communication, not this verified thermostat.
- `Anantha` (https://github.com/anupcshan/anantha) targets Infinity models and notes that firmware modification and DNS interception disable official Carrier app communication. It is **not** a supported drop-in local protocol for TSTATCCEWF-01, and its intrusive methods are excluded.
- Matter branding is not evidence of a separate proprietary LAN API and **Matter must never be substituted** for this project's requested protocol.

## New offline-tested instrumentation

`tools/Probe-CarrierLocalDeep.ps1` calls the single Python engine `tools/Probe-CarrierLocalDeep.py`. Legacy probe filenames now forward rather than maintain a second scanner. It accepts a fresh currently CONNECTED Omada export, validates online MAC uniqueness, restricts the target to the authorized IoT VLAN, then performs an optional full 1..65535 TCP sweep and bounded harmless protocol discovery. Report excludes identifying addresses and secrets.

## Evidence gates

L1: target authenticated via fresh Omada online client record. **Tool implemented; new owner export still required.**

L2: target-only TCP/UDP listener fingerprints observed on actual device. **Not tested on owner hardware.**

L3: protocol identified as distinct from Matter, with authorization and read-only request proven. **Unknown.**

L4: local HVAC command safely and reversibly verified; official app behavior and rollback observed. **Unknown.**

Firmware patching, pairing changes, device setup code extraction, DNS interception, credentials capture, or unsafe commands are not part of this test plan.

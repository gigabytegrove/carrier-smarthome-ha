# Carrier SmartHome native cloud alpha — test procedure

Use **Carrier SmartHome**, not the legacy Infinity app, and **do not pair Matter**.

## First, read-only proof of API

On Windows, launch `tools/Test-Cloud.ps1` (it creates an isolated Python environment and installs aiohttp automatically). On any other machine with Python 3.11+ and `aiohttp` installed:

```
python tools/Smoke-TestSmartHomeCloud.py
```

Enter your normal Carrier SmartHome account email and password when prompted. The program does **not** accept a cloud URL or thermostat IP, print secrets, change HVAC setpoints, or save credentials. A successful result prints:

```
Authentication: PASS
Entry-level devices: <count>
Connected devices: <count>
Offline devices: <count>
Unknown connection state: <count>
Thermostat zones: <count>
Reported models: <models>
READ-ONLY THERMOSTAT DATA (may be stale if offline)
Device 1: model=<reported model> connection=<online/offline/unknown> unit=<unit>
  Zone 0: mode=<mode> room=<temperature> heat=<target> cool=<target> humidity=<value> outside=<value>
APK DETAIL QUERY CROSS-CHECK
Device 1: <PASS/NOT AVAILABLE>
```

If login fails, report *only the status lines* (no email/password, tokens, or serial). This is the earliest possible verification of the native cloud API. This is a research tool and does not authenticate against Matter.

## Then the HA alpha

1. Copy the **entire** `carrier_smarthome` directory from `custom_components/` into your Home Assistant `/config/custom_components/` directory.
2. Restart Home Assistant (not just a dashboard reload).
3. In **Settings > Devices & services > Add integration**, choose **Carrier SmartHome (Native Cloud Alpha)**.
4. Enter the same Carrier SmartHome credentials used by the Android app. No IP, endpoint or pairing code needed.
5. Confirm at least one Carrier Smart Thermostat device and its sensor/climate entities. If setup fails, read the UI error and sanitized logs.
6. Controls default to **read-only**. To test writing *after* live state is correct, enable **Experimental thermostat writes** under the integration's Options; one small reversible setpoint adjustment is enough.

### Failure codes

- `Authentication: FAIL`: username/password rejected, MFA required, or current device/app account uses a different auth method.
- `Cloud API: FAIL`: endpoint or GraphQL routing/schema differs, server unavailable, or network failure.
- `Entry-level devices: 0`: login works, but the account's device is not in the discovered entry-level GraphQL family.
- HA error `no_devices`: no entry-level systems were returned; the integration will not create fake entities.

Native cloud login and one entry-level device listing were **owner-tested successfully** on 2026-10-22. The alpha has **not yet** been tested inside Home Assistant and no native-cloud writes have been confirmed. Proprietary local control remains a separate verification goal.


### Verified first read (2026-10-22)
Owner already ran version 0.1.0a1: authentication PASSED, one entry-level device and one zone found. Cloud reported device offline and model `TSTATCCEEF-01`, differing from the physical sticker `TSTATCCEWF-01`. Rerun the 0.1.0a2 smoke test when the thermostat is installed and online; the expanded output includes **real API-returned** temperature and setpoints (which may be stale when offline) and attempts a second APK-derived detail query. Do not enable experimental writes while offline or until units and setpoints are verified.

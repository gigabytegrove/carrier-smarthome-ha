# Carrier SmartHome native cloud alpha — test procedure

Use **Carrier SmartHome**, not the legacy Infinity app, and **do not pair Matter**.

## First, read-only proof of API

From any machine with Python 3.11+ and `aiohttp` installed:

```
python tools/Smoke-TestSmartHomeCloud.py
```

Enter your normal Carrier SmartHome account email and password when prompted. The program does **not** accept a cloud URL or thermostat IP, print secrets, change HVAC setpoints, or save credentials. A successful result prints:

```
Authentication: PASS
Entry-level devices: <count>
Connected devices: <count>
Thermostat zones: <count>
Reported models: <models>
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

The alpha has **not yet** been tested with your Carrier account or running HA instance. The direct app controls and local network control remain separate verification goals.

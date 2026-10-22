# Carrier SmartHome for Home Assistant

Unofficial native Carrier SmartHome Cloud integration targeting the Carrier Smart Thermostat (`TSTATCCEWF-01` on the physical label; `TSTATCCEEF-01` in Carrier cloud). The GraphQL read path has been confirmed against an owner device. **Version 0.5.0.** Cloud mode/fan write behavior still requires physical-device verification. Matter is not implemented or used.

## Install / update with HACS

In **HACS → ⋮ → Custom repositories**, add `https://github.com/gigabytegrove/carrier-smarthome-ha` as an **Integration**. Download from `main`, restart Home Assistant, and add Carrier SmartHome through **Settings → Devices & services**. If already installed, redownload the current `main` revision and restart.

## Normal thermostat controls (v0.5.0)

Open the single **Home** climate device. It advertises **Off, Heat, Cool, Auto (Heat/Cool), Fan Only**, fan **Auto/On**, and temperature targets in the appropriate active mode. These are ordinary Home Assistant climate controls, with **no setup options to unlock the interface**. The previous redundant HVAC Power switch, preset Power On mode, and experimental-control options were removed. Your existing climate entity unique ID is preserved.

Off is a selectable HVAC mode. To turn the system on when Off, choose Heat, Cool or Auto directly. If the climate `turn_on` service is used, it restores the last non-Off mode **observed from Carrier during the current integration session**. If none is known, choose the mode from the selector first rather than silently defaulting to an unsafe mode.

All native writes: require Carrier-reported online status, refresh device state, allow one mutation, and require a matching cloud readback. Unconfirmed writes are **not automatically retried**. The cloud API does not provide a device sample timestamp. Fan Circulation is not exposed because the enum is not verified. No proprietary LAN command is implemented; local research remains read-only.

For a comprehensive single-thermostat native LAN reconnaissance (without Matter), see [Local probe guide](docs/LOCAL_PROBE_GUIDE.md).

See [HACS installation and verification](docs/HACS_INSTALLATION.md), [Changelog](CHANGELOG.md), and [Alpha 10 control architecture](research/ALPHA10_NATIVE_CLIMATE_CLEANUP.md). Avoid publishing raw logs, tokens, Omada exports, private IPs or device identifiers in GitHub issues. Old git history can still contain earlier research records.

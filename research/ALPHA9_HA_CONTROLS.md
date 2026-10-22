# Alpha 9 — Device-page controls and guarded fan mode

Owner observed Home Assistant climate entity but no accessible mode/fan controls in alpha 8. Root cause: default-off `enable_control` masks HVAC modes; separate `enable_setpoint_control` masks temperature changes; experimental fan mutation was explicitly rejected.

Alpha 9 adds a native HA `select` platform with **HVAC mode (Off / Heat / Cool / Auto / Fan Only)** and **Fan setting (Auto / On)** directly under device Controls. Mode, fan and setpoint writes each require distinct opt-in from Carrier SmartHome Options. The existing HVAC Power switch remains. Any write requires freshly polled Carrier-connected status, sends one GraphQL `updateEntryLevelZone` mutation and checks Carrier's reported state up to three times; it never blindly repeats a write. The fan query field and update input are grounded in publicly implemented `dahlb/carrier_api` and the extracted Carrier GraphQL mutation. Live acceptance on this physical thermostat remains unverified.

**Fan circulation:** Carrier's physical user documentation lists Auto, On and Circulation, but backend spelling for Circulation is unknown, so it is NOT offered as a write. Fan Only is a hardware-listed HVAC mode; its GraphQL mutation remains experimental.

## First live test

Update via HACS, restart HA, open Carrier SmartHome integration **Configure/Options**, enable experimental HVAC mode/power, optionally experimental fan, select explicit Power On mode, save, allow integration reload. Open device page; use *HVAC mode* select for Off / Cool / Heat / Auto. Check the official app after one change. Don't test heat/cool switches if equipment isn't safe to operate. The *Fan setting* select is available only when its separate opt-in is on. If command fails, do NOT repeat; report exact error and check official app state. Setpoints remain separate.

No Matter, no credentials or device identifiers included.

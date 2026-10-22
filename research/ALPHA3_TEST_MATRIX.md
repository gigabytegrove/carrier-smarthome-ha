# Alpha 3 verification matrix — no invented live results

| Capability | Static/Mock | Live cloud | HA runtime | Device control |
|---|---|---|---|---|
| Username/password assistedLogin | Tested offline | **PASS**, 2026-10-22 | Not tested | N/A |
| Account entry-level device listing | Tested offline | **PASS**, one device/zone | Not tested | N/A |
| Detailed device read | Tested offline | **PASS**, one zone | Not tested | N/A |
| Offline state correctness | Tested offline | **PASS**, reports offline | Not tested | N/A |
| Auth token refresh | Tested offline | Not observed during owner's short test | Not tested | N/A |
| HTTP rate-limit cooldown | Tested offline | Not observed | Not tested | N/A |
| HA climate/sensor/binary entities | Parsed/compiled | Source data proven | **Not tested** | Disabled by default |
| HA dynamic new-account devices | Tested via callback/unit checks | Not observed | Not tested | N/A |
| HA privacy-safe diagnostics | Tested offline | Source data proven | Not tested | N/A |
| HVAC setpoint/mode mutation | Input and error mock tests | Not attempted | Not tested | **Not tested** |
| Schedule/reminder/prefs read | APK queries recovered, mock tests | **Not tested** | Not exposed as entities | Read-only |
| Cloud telemetry trends | Privacy/diff mock tests | Single owner snapshot, no trend | N/A | Read-only |
| LAN identity | Previous Omada export matched label | N/A | N/A | Historical last-IP only |
| Proprietary LAN service | TCP probe and safety logic mocked | N/A | N/A | Unproven; no local commands |
| Matter | Not implemented | Not used | Not used | Out of scope |

This project distinguishes *code shipped*, *offline test passed* and *verified on the user's thermostat*. These categories must never be collapsed.

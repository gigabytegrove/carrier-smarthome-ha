# Alpha 8 — native cloud live-change evidence and restoration guard

October 22, 2026: User-run read-only `Compare-AppChange.ps1` test established:

- Carrier native GraphQL authenticated and returned the correct hardware identity (verified in prior owner-run test).
- Account `entryLevelSystems` and serial-specific `entryLevelSystem` both reflected the official phone app's 76→73→76 °F cooling setpoint sequence.
- The Carrier connection flag returned `online` during that experiment, having returned `offline` in earlier reads. A subsequent Alpha 7 repository update documents a genuine Wi-Fi disconnect and reconnect, so the older offline responses are consistent with a real network interruption, not proof of a faulty status flag.
- The first observed update also included mode `off`→`cool`. The final read contained heat setpoint `69` versus starting `70`, and mode `cool` versus starting `off`. **The original Alpha 6 script incorrectly declared complete restoration because it checked only the changed cooling setpoint.**
- The extended Alpha 8 script compares **all five observed baseline settings** (heat, cool, mode, fan and schedule) from **both available GraphQL sources** and exits nonzero on any mismatch. It does not write commands and cannot restore the thermostat automatically.

## Verified vs not verified

**Verified:** cloud login, device match, live propagation of a phone-app-initiated cooling target change (to two independent GraphQL reads), native GraphQL reads and connection status transitions.

**Not verified:** native GraphQL writes from the Home Assistant integration, firmware/control acknowledgments, real-time timestamping, proprietary LAN API, fan writes, safety/installer settings.

The Home Assistant integration continues to expose the reported cloud fields, without Matter. Writes remain **user opt-in** and subject to the online/readable gates. **Do not assert native thermostat control is working until a deliberate owner-authorized write/readback test passes**.

## Regression rule

A setpoint restoration cannot be called a complete restore if another known baseline HVAC setting (especially mode or the other setpoint) changed. The tool must print only whitelisted values and avoid device/account identifiers and secrets.

# Changelog

## 0.1.0a10 — Standard climate controls, no configuration gates

- Fix only-Off mode selector caused by persisted `enable_control=false` options.
- Show all supported modes directly in HA, including Off/Heat/Cool/Auto/Fan Only.
- Offer fan Auto/On and setpoint controls in the same climate UI without separate option toggles.
- Remove duplicate HVAC Power switch, obsolete `power_on_mode` setting, and legacy OptionsFlow.
- Migrate old config entries, clear obsolete options and clean up only old Carrier HVAC Power entities.
- Remember last Carrier-reported active mode during this HA session for turn_on; never invent a default mode.
- Preserve serialized single-write preflight, cloud confirmation, offline blocking and rate limits.
- Native Carrier command path remains experimental until validated on physical equipment; no Matter.

For historical alpha releases, see Git commit history.

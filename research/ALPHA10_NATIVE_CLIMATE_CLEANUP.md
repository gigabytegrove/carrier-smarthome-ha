# Alpha 10: Remove configuration gates and redundant thermostat controls

Root cause: New config entries stored `enable_control = false`. `hvac_modes` returned only `[current mode]` while this legacy setting was false. Home Assistant therefore rendered a single **Off** choice even though Carrier was online. HACS upgrades kept this value indefinitely. An additional switch with a manually configured `power_on_mode` duplicated the climate mode interface.

Corrections:
- Single standard climate entity holds Off/Heat/Cool/Auto/Fan Only, Auto/On fan, and targets; features no longer depend on saved integration options.
- Remove the obsolete `OptionsFlow`, config fields, switch platform and `switch.py`; prior `enable_*` options are ignored and discarded when HA migrates the config entry to version 2.
- Existing climate unique IDs remain unchanged. On setup remove ONLY obsolete `switch` registry entries owned by this config entry/platform and ending `_hvac_power`.
- Climate `turn_on` uses last real non-Off mode observed from Carrier during this runtime. Never arbitrarily choose Cool/Heat on cold startup. The mode selector can always initiate a known mode.
- Retain existing safety: require online state, fresh cloud poll, finite bounds validation, single serialized `updateEntryLevelZone` mutation, bounded readback and no write retries.
- Cloud write acceptance and physical impact remain unverified until a supervised owner-side HA test; Matter remains excluded.

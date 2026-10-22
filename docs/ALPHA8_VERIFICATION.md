# Alpha 8: verified cloud propagation and full restore checks

Alpha 7 already fixed Home Assistant availability after the owner documented a real Wi-Fi dropout and reconnect. **Alpha 8 preserves all those changes**; it does not reclassify offline devices as online.

The user-run native Carrier Cloud experiment demonstrated that the official app changed the cooling target 76→73→76 °F and both cloud GraphQL views followed. The physical device's cloud flag returned online. **This does not prove this integration can write HVAC controls.** No Matter.

A real defect in the earlier guided comparison reported restoration while the final cloud state still had heat 69°F instead of 70°F and mode cool instead of Off. Alpha 8 compares both setpoints, mode, fan and schedule state across all available cloud query views. Any observable difference produces a nonzero exit. No mutations or restores are issued by diagnostic scripts.

## Next safe test on Windows

Clone this repository and run:

```powershell
.\tools\Check-CarrierState.ps1
```

The check reads the latest cloud-reported fields, both account and detail query, without modifying thermostat settings. If and only if the *intended* configuration was the original experiment baseline, compare it explicitly:

```powershell
.\tools\Check-CarrierState.ps1 -ExpectedHeat 70 -ExpectedCool 76 -ExpectedMode off -ExpectedFan auto -ExpectedSchedule enabled
```

A mismatch is not automatically an error in your HVAC preference; it means the current cloud state is different from the requested baseline. The script must never restore the settings on your behalf. If current settings were deliberately changed, omit the expectations.

## HACS update

HACS custom repository: `https://github.com/gigabytegrove/carrier-smarthome-ha`. Redownload/update `main`, restart Home Assistant and verify the manifest reports `0.1.0a8`. The Home Assistant climate and sensor behavior from Alpha 7 is preserved. Experimental HVAC write option is disabled by default and remains unverified on the physical thermostat.

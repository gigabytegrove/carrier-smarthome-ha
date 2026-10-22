# October 22 app/cloud synchronization correction

The official app changed cool 76 to 73 then back to 76, and both native GraphQL queries followed. The connection field reported online. However the final reading differed from baseline: heat 70 -> 69 and HVAC mode off -> cool. The previous comparator checked only the altered setpoint and falsely reported full restoration.

The revised comparison checks all known heat/cool targets, HVAC mode, fan mode, and schedule state in both query sources, displays remaining differences, and exits nonzero if full restoration was not observed. No device write is sent by this script. The user may choose to restore baseline heat 70 and mode off in the official app. This does not validate any custom integration mutation; Matter remains excluded.

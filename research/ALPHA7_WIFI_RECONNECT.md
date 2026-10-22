# Alpha 7: Wi-Fi outage and cloud status interpretation

On October 22, 2026, the owner reported a real Wi-Fi disconnection immediately before the successful Alpha 6 app/cloud correlation. Restarting the thermostat restored Wi-Fi without reprovisioning. Previously, Carrier GraphQL read paths repeatedly showed `isConnected=false`, with unchanged potentially cached readings. After the restart Carrier reported online; official-app cooling changes 76 F -> 73 F -> 76 F appeared in both Carrier GraphQL read paths.

**Interpretation:** A real Wi-Fi outage is the leading explanation for earlier offline status; the earlier theory that `isConnected` is unreliable is now superseded. The exact moment of the disconnection was not independently logged; this is correlation, not packet-level proof.

**Home Assistant policy:** When Carrier reports offline or cloud polling fails, live climate and measurement entities become unavailable. Distinct `Last cloud-reported` diagnostic sensors can remain readable as possibly cached values. API readability and device connection remain separate binary sensors. Writes remain opt-in and unvalidated. No Matter.

**If it recurs:** Inspect Omada Hallway AP 2.4-GHz client association/disconnect events, RSSI, DHCP lease and renewals, AP firmware/restarts and VLAN reachability at the incident time. No particular RF, DHCP, firmware or Carrier cause has been established. Do not commit raw client logs, MACs or device identifiers.

**Separate prior finding:** The Alpha 6 phone-app test restored the cool target, but the final reading showed heating target 69 F (original 70 F) and mode Cool (original Off). The original comparison script was corrected to require full baseline restoration.

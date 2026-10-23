# Carrier SmartHome — Matter hardware readiness (read-only)

This is for the **experimental Matter branch** only. Stable v0.5.6 remains cloud-only.

The bundled `tools/check_matter_readiness.py` runs with Home Assistant's
existing `aiohttp` dependency and never sends a Matter `write_attribute` or
`device_command`. It reports counts, matching vendor/product identity and
read-only liveness without printing serials, MACs, fabric keys or node IDs.

**Prerequisites:** An existing OHF Matter Server at a trusted, private LAN
IP. The Carrier thermostat must be paired/commissioned on its fabric first.
The Matter Server host must have working multicast and IPv6 reachability
to the thermostat on VLAN 30. No Docker or VLAN changes are performed by
this tool. Full scan of the 172.20.0.0/16 network is unnecessary.

On the **Home Assistant host**, from a checkout of the feature branch:

```bash
# Adjust the private LAN address only if your Matter Server is NOT on 192.168.0.19.
docker cp tools/check_matter_readiness.py HOME_ASSISTANT_CONTAINER:/tmp/carrier-matter-check.py
docker exec HOME_ASSISTANT_CONTAINER python3 /tmp/carrier-matter-check.py --url ws://192.168.0.19:5580/ws
```

After commissioned node ID and endpoint are confirmed in the Matter Server's
dashboard, append `--node NODE_ID --endpoint 1` for the active thermostat
readback. Node IDs and commissioning codes must not be posted publicly.

Exit codes: 0 = matching certified product available and requested check
succeeded; 2 = connectivity/protocol error; 3 = zero matching available nodes
or requested node/endpoint not validated. Nonzero does not mean a write failed,
because this tool never issues writes.

**Safety:** The controller's WebSocket port usually has no authentication.
Do not expose TCP 5580 to the Internet or untrusted VLANs. A trusted private
address is required; never bypass the URL validation to connect publicly.

Once this read-only probe succeeds, select Carrier SmartHome → Configure,
pick the thermostat, confirm its physical identity and select either Matter
only or Prefer Matter. Follow supervised, reversible tests in
`docs/MATTER_LOCAL_CONTROL_DESIGN.md`. Avoid tests that could surprise
occupants by changing HVAC operation without notice.

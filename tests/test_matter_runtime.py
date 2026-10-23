"""Offline tests: local cache, unit conversion and cross-transport safety."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"
PKG = "carrier_matter_runtime_tests"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package
for name in ("matter_protocol", "matter_client", "matter_routing", "matter_runtime"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
p = sys.modules[PKG + ".matter_protocol"]
r = sys.modules[PKG + ".matter_routing"]
m = sys.modules[PKG + ".matter_runtime"]


class FakeCoordinator:
    def __init__(self):
        self.last_update_success = True
        self.data = {"TEST": {"connection": {"isConnected": True}}}
        self.notifications = 0

    def async_update_listeners(self):
        self.notifications += 1


class FakeClient:
    def __init__(self, *, online=True):
        self.online = online
        self.writes = []
        self.state_value = object()

    async def get_state(self):
        if not self.online:
            raise p.MatterNotReady("Matter unreachable")
        return self.state_value

    async def write(self, **kwargs):
        self.writes.append(kwargs)
        return {"confirmed": True}


def runtime(policy=p.MATTER_ONLY):
    coordinator = FakeCoordinator()
    options = {"matter_bindings": {"TEST|0": {
        "policy": policy, "url": "ws://127.0.0.1:5580/ws",
        "node_id": 1, "endpoint": 1
    }}}
    manager = m.MatterManager(None, options, coordinator)
    client = FakeClient()
    manager._clients["TEST|0"] = client
    manager._routers["TEST|0"] = r.DualTransportRouter(
        client, lambda: manager._cloud_ready("TEST|0"))
    return manager, coordinator, client


class BasicTests(unittest.TestCase):
    def test_fahrenheit_celsius_roundtrip(self):
        self.assertEqual(m.degrees_from_c(20, "°F"), 68)
        self.assertAlmostEqual(m.degrees_to_c(68, "°F"), 20)
        self.assertEqual(m.degrees_from_c(None, "°C"), None)

    def test_default_cloud_has_no_matter_connection(self):
        manager = m.MatterManager(None, {}, FakeCoordinator())
        self.assertFalse(manager.has_bindings)
        self.assertEqual(manager.policy("TEST", 0), p.CLOUD_ONLY)
        self.assertIsNone(manager.state("TEST", 0))


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_read_updates_entity_listeners(self):
        manager, coordinator, client = runtime()
        self.assertTrue(await manager.refresh_one("TEST|0"))
        self.assertIs(manager.state("TEST", 0), client.state_value)
        self.assertEqual(coordinator.notifications, 1)
        client.online = False
        self.assertFalse(await manager.refresh_one("TEST|0"))
        self.assertIsNone(manager.state("TEST", 0))

    async def test_matter_only_never_cloud_writes(self):
        manager, coordinator, client = runtime()
        cloud_called = []

        async def cloud_write():
            cloud_called.append("cloud")

        result = await manager.execute("TEST", 0, cloud_write,
                                       lambda c: c.write(mode="heat"))
        self.assertEqual(result, "matter")
        self.assertEqual(client.writes, [{"mode": "heat"}])
        self.assertEqual(cloud_called, [])

    async def test_matter_unavailable_never_cloud_writes_for_matter_only(self):
        manager, coordinator, client = runtime()
        client.online = False
        cloud_called = []

        async def cloud_write():
            cloud_called.append("cloud")

        with self.assertRaises(p.MatterNotReady):
            await manager.execute("TEST", 0, cloud_write,
                                  lambda c: c.write(mode="heat"))
        self.assertEqual(client.writes, [])
        self.assertEqual(cloud_called, [])

    async def test_prefer_matter_cloud_fallback_prior_to_write(self):
        manager, coordinator, client = runtime(p.MATTER_PREFERRED)
        client.online = False
        calls = []

        async def cloud_write():
            calls.append("cloud")

        self.assertEqual(await manager.execute(
            "TEST", 0, cloud_write, lambda c: c.write(mode="heat")), "cloud")
        self.assertEqual(calls, ["cloud"])
        self.assertEqual(client.writes, [])

    async def test_uncertain_matter_ack_never_falls_back_to_cloud(self):
        manager, coordinator, client = runtime(p.MATTER_PREFERRED)
        calls = []

        async def cloud_write():
            calls.append("cloud")

        async def uncertain_write(_):
            raise p.MatterWriteUncertain("ACK lost")

        with self.assertRaises(p.MatterWriteUncertain):
            await manager.execute("TEST", 0, cloud_write, uncertain_write)
        self.assertEqual(calls, [])

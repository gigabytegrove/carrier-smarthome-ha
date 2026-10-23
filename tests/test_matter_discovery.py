"""Offline contract tests for Home Assistant's built-in Matter source.

No Docker, commissioning, BLE, Matter write or Home Assistant startup required.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from types import MappingProxyType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"
PKG = "carrier_matter_builtin_test"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package


def load(name):
    spec = importlib.util.spec_from_file_location(
        f"{PKG}.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


p = load("matter_protocol")
c = load("matter_client")
discovery = load("matter_discovery")
r = load("matter_routing")
runtime = load("matter_runtime")


class FakeEntries:
    def __init__(self, loaded=None):
        self.loaded = loaded or []

    def async_loaded_entries(self, domain):
        assert domain == "matter"
        return self.loaded


def make_hass(entry_id="matter-1", url="ws://core-matter-server:5580/ws"):
    entry = SimpleNamespace(
        entry_id=entry_id,
        data=MappingProxyType({"url": url}))
    return SimpleNamespace(config_entries=FakeEntries([entry]))


class OfficialMatterDiscoveryTests(unittest.TestCase):
    def test_loaded_config_entry_url_supports_mappingproxy(self):
        source = discovery.find_home_assistant_matter(make_hass())
        self.assertEqual(source.entry_id, "matter-1")
        self.assertEqual(source.server_url,
                         "ws://core-matter-server:5580/ws")

    def test_no_native_matter_returns_none(self):
        self.assertIsNone(discovery.find_home_assistant_matter(None))
        empty = SimpleNamespace(config_entries=FakeEntries())
        self.assertIsNone(discovery.find_home_assistant_matter(empty))

    def test_auto_bind_uses_live_native_url_not_options_url(self):
        binding = {
            "source": discovery.HA_MATTER_SOURCE,
            "matter_entry_id": "matter-1",
            "fabric_id": 1234,
            "url": "ws://8.8.8.8:5580/ws",
        }
        url, trusted, fabric = discovery.resolve_source(make_hass(), binding)
        self.assertEqual(url, "ws://core-matter-server:5580/ws")
        self.assertTrue(trusted)
        self.assertEqual(fabric, 1234)

    def test_changing_config_entry_fails_closed(self):
        binding = {
            "source": discovery.HA_MATTER_SOURCE,
            "matter_entry_id": "matter-1", "fabric_id": 1234,
        }
        with self.assertRaises(ValueError):
            discovery.resolve_source(make_hass(entry_id="matter-2"), binding)
        with self.assertRaises(ValueError):
            discovery.resolve_source(None, binding)

    def test_manual_mode_does_not_gain_trusted_dns(self):
        binding = {"url": "ws://8.8.8.8:5580/ws"}
        url, trusted, fabric = discovery.resolve_source(make_hass(), binding)
        self.assertFalse(trusted)
        with self.assertRaises(p.MatterNotReady):
            c.MatterWsClient(None, url, 1, 1,
                             trusted_ha_source=trusted)
        with self.assertRaises(p.MatterNotReady):
            c.MatterWsClient(None,
                             "ws://core-matter-server:5580/ws", 1, 1)

    def test_native_hostnames_require_explicit_trust(self):
        url = c.validate_server_url("ws://core-matter-server:5580/ws",
                                    trusted_ha_source=True)
        self.assertEqual(url, "ws://core-matter-server:5580/ws")
        for host in ("https://core-matter-server:5580/ws",
                     "ws://user:secret@core-matter-server:5580/ws",
                     "ws://public..invalid:5580/ws"):
            with self.subTest(host=host), self.assertRaises(p.MatterNotReady):
                c.validate_server_url(host, trusted_ha_source=True)


class StubWS:
    def __init__(self, *, fabric=1234):
        self.fabric = fabric
        self.reply = None
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def receive_json(self, timeout=None):
        if self.reply:
            value, self.reply = self.reply, None
            return value
        return {"schema_version": 14, "min_supported_schema_version": 11,
                "compressed_fabric_id": self.fabric}

    async def send_json(self, msg):
        self.commands.append(msg["command"])
        nodes = [
            {"node_id": 7, "available": True, "attributes": {
                "0/40/2": 4334, "0/40/4": 2048, "1/513/28": 3,
                "1/513/0": 2200, "1/513/17": 2500,
                "1/513/18": 2000}},
            {"node_id": 8, "available": True, "attributes": {
                "0/40/2": 100, "0/40/4": 200, "1/513/28": 3}},
        ]
        result = nodes if msg["command"] == "get_nodes" else None
        self.reply = {"message_id": msg["message_id"], "result": result}


class StubSession:
    def __init__(self, fabric=1234):
        self.ws = StubWS(fabric=fabric)

    def ws_connect(self, *_args, **_kwargs):
        return self.ws


class NativeServerApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_discovery_filters_other_products(self):
        session = StubSession()
        client = c.MatterWsClient(
            session, "ws://core-matter-server:5580/ws", 1, 1,
            trusted_ha_source=True)
        fabric, thermostats = await client.discover_thermostats()
        self.assertEqual(fabric, 1234)
        self.assertEqual(thermostats, [{"node_id": 7, "endpoint": 1}])
        self.assertEqual(session.ws.commands, ["get_nodes"])

    async def test_fabric_mismatch_fails_before_any_control(self):
        session = StubSession(fabric=9999)
        client = c.MatterWsClient(
            session, "ws://core-matter-server:5580/ws", 7, 1,
            trusted_ha_source=True, expected_fabric_id=1234)
        with self.assertRaises(p.MatterNotReady):
            await client.write(mode="heat")
        self.assertEqual(session.ws.commands, [])


class RuntimeNoCloudRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_matter_only_unloaded_controller_never_cloud_commands(self):
        coordinator = SimpleNamespace(
            hass=SimpleNamespace(config_entries=FakeEntries()),
            last_update_success=True,
            data={"TEST": {}},
            write_lock=__import__("asyncio").Lock())
        options = {"matter_bindings": {"TEST|0": {
            "source": discovery.HA_MATTER_SOURCE,
            "matter_entry_id": "matter-1",
            "fabric_id": 1234, "node_id": 7, "endpoint": 1,
            "policy": p.MATTER_ONLY}}}
        manager = runtime.MatterManager(None, options, coordinator)
        self.assertEqual(manager.policy("TEST", 0), p.MATTER_ONLY)
        self.assertFalse(manager.has_bindings)
        cloud_called = []

        async def cloud_write():
            cloud_called.append(True)

        with self.assertRaises(p.MatterNotReady):
            await manager.execute("TEST", 0, cloud_write,
                                  lambda client: client.write(mode="heat"))
        self.assertEqual(cloud_called, [])

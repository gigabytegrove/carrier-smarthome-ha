"""Offline, no real network/hardware: Matter identity, protocol and safety."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"
PKG = "carrier_matter_tests"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package
for filename in ("matter_protocol", "matter_client"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{filename}", ROOT / f"{filename}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
p = sys.modules[PKG + ".matter_protocol"]
c = sys.modules[PKG + ".matter_client"]


def node(**replace):
    attrs = {"0/40/2": 0x10EE, "0/40/4": 0x800, "1/513/0": 2250,
             "1/513/17": 2600, "1/513/18": 2000,
             "1/513/28": 3, "1/513/22": 3000, "1/513/23": 1600}
    attrs.update(replace)
    return {"available": True, "attributes": attrs}


class MatterMappingTests(unittest.TestCase):
    def test_read_decode(self):
        s = p.decode(node(), 1)
        self.assertEqual((s.mode, s.temperature_c, s.heat_target_c,
                          s.cool_target_c), ("cool", 22.5, 20, 26))
        self.assertEqual((s.max_heat_c, s.min_cool_c), (30, 16))

    def test_vendor_product_and_offline_safety(self):
        for n in (node(**{"0/40/2": 99}), node(**{"0/40/4": 99}),
                  {**node(), "available": False}):
            with self.assertRaises(p.MatterNotReady):
                p.decode(n, 1)

    def test_matter_modes_and_fanonly_unverified(self):
        self.assertEqual(p.plan_mode(node(), 1, "heat"), ("1/513/28", 4))
        with self.assertRaises(p.MatterNotReady):
            p.plan_mode(node(), 1, "fanonly")

    def test_setpoint_limit_validation(self):
        self.assertEqual(p.plan_setpoint(node(), 1, "cool", 23.5),
                         ("1/513/17", 2350))
        for k, v in (("heat", 40), ("cool", 10), ("heat", float("nan"))):
            with self.assertRaises(p.MatterNotReady):
                p.plan_setpoint(node(), 1, k, v)

    def test_mode_policy_distinguishes_cloud_and_matter(self):
        self.assertEqual(p.select_transport("cloud", matter_ready=True,
                                            cloud_ready=True), "cloud")
        self.assertEqual(p.select_transport("matter_preferred", matter_ready=True,
                                            cloud_ready=True), "matter")
        self.assertEqual(p.select_transport("matter_preferred", matter_ready=False,
                                            cloud_ready=True), "cloud")
        with self.assertRaises(p.MatterNotReady):
            p.select_transport("matter", matter_ready=False, cloud_ready=True)

    def test_private_lan_matter_server_urls(self):
        for url in ("ws://127.0.0.1:5580/ws", "ws://127.0.0.1:5580/",
                    "ws://127.0.0.1:5580",
                    "ws://192.168.0.19:5580/ws", "wss://172.20.0.4:5580/ws"):
            self.assertEqual(c.validate_server_url(url),
                             url.rstrip("/") + ("/ws" if not url.endswith("/ws") else ""))
        for url in ("ws://8.8.8.8:5580/ws",
                    "ws://0.0.0.0:5580/ws", "ws://169.254.5.4:5580/ws",
                    "ws://user:pw@127.0.0.1:5580/ws",
                    "http://127.0.0.1:5580/ws", "ws://127.0.0.1:99999/ws"):
            with self.assertRaises(p.MatterNotReady):
                c.validate_server_url(url)


class FakeWs:
    def __init__(self, *, confirm=True, corrupt=False):
        self.commands = []
        self.confirm = confirm
        self.corrupt = corrupt
        self.reply = None

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return None

    async def send_json(self, payload):
        self.commands.append(payload)
        command = payload["command"]
        if command == "get_node":
            result = node()
        elif command == "write_attribute":
            result = [{"Status": 0}]
        elif command == "read_attribute":
            result = {payload["args"]["attribute_path"]: 4 if self.confirm else 3}
        else:
            raise AssertionError(f"Unexpected RPC: {command}")
        self.reply = (RuntimeError("lost after write") if
                      self.corrupt and command == "write_attribute" else
                      {"message_id": payload["message_id"], "result": result})

    async def receive_json(self, timeout=None):
        if self.reply is not None:
            response, self.reply = self.reply, None
            if isinstance(response, Exception):
                raise response
            return response
        return {"schema_version": 14}


class FakeSession:
    def __init__(self, **options): self.ws = FakeWs(**options)
    def ws_connect(self, *args, **kwargs): return self.ws


class MatterWebsocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_connection(self):
        session = FakeSession()
        state = await c.MatterWsClient(session, "ws://127.0.0.1:5580/ws", 17, 1).get_state()
        self.assertEqual(state.mode, "cool")
        self.assertEqual([x["command"] for x in session.ws.commands], ["get_node"])

    async def test_single_write_and_confirm(self):
        session = FakeSession()
        await c.MatterWsClient(session, "ws://127.0.0.1:5580/ws", 17, 1).write(mode="heat")
        self.assertEqual([x["command"] for x in session.ws.commands],
                         ["get_node", "write_attribute", "read_attribute"])
        self.assertEqual(session.ws.commands[1]["args"]["value"], 4)

    async def test_post_write_disconnect_never_retries(self):
        session = FakeSession(corrupt=True)
        with self.assertRaises(p.MatterWriteUncertain):
            await c.MatterWsClient(session, "ws://127.0.0.1:5580/ws", 17, 1).write(mode="heat")
        self.assertEqual([x["command"] for x in session.ws.commands],
                         ["get_node", "write_attribute"])

    async def test_unconfirmed_readback_never_retries(self):
        session = FakeSession(confirm=False)
        with self.assertRaises(p.MatterWriteUncertain):
            await c.MatterWsClient(session, "ws://127.0.0.1:5580/ws", 17, 1).write(mode="heat")
        self.assertEqual(sum(x["command"] == "write_attribute"
                             for x in session.ws.commands), 1)

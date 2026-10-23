"""Fake Matter Server validates that readiness probe never sends writes."""
import importlib.util
import pathlib
import unittest
from aiohttp import web

HERE = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = HERE / "tools" / "check_matter_readiness.py"
spec = importlib.util.spec_from_file_location("carrier_matter_probe", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NODE = {"node_id": 1, "available": True, "attributes": {
    "0/40/2": 4334, "0/40/4": 2048, "1/513/28": 3,
    "1/513/0": 2200, "1/513/17": 2500, "1/513/18": 2000}}


class Tests(unittest.IsolatedAsyncioTestCase):
    def test_ip_validation(self):
        self.assertEqual(module.checked_url("ws://192.168.0.19:5580"),
                         "ws://192.168.0.19:5580/ws")
        for url in ("http://192.168.0.19:5580", "ws://8.8.8.8:5580/ws",
                    "ws://0.0.0.0:5580/ws",
                    "ws://admin:pass@127.0.0.1:5580/ws"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                module.checked_url(url)

    async def asyncSetUp(self):
        self.writes = []

        async def websocket(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"schema_version": 14,
                                "min_supported_schema_version": 11})
            async for frame in ws:
                content = frame.json()
                self.writes.append(content["command"])
                command = content["command"]
                if command == "get_nodes":
                    value = [NODE]
                elif command == "get_node":
                    value = NODE
                elif command == "read_attribute":
                    value = {x: NODE["attributes"][x]
                             for x in content["args"]["attribute_path"]}
                else:
                    value = None
                await ws.send_json({"message_id": content["message_id"],
                                    "result": value})
            return ws

        self.app = web.Application()
        self.app.router.add_get("/ws", websocket)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.port = self.site._server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_connection_no_writes(self):
        report = await module.inspect(
            f"ws://127.0.0.1:{self.port}/ws", node_id=None, endpoint=1)
        self.assertEqual(report["matching_carrier_nodes"], 1)
        self.assertEqual(report["writes_sent"], 0)
        self.assertEqual(self.writes, ["get_nodes"])

    async def test_read_only_thermostat(self):
        report = await module.inspect(
            f"ws://127.0.0.1:{self.port}/ws", node_id=1, endpoint=1)
        self.assertEqual(report["selected_thermostat"],
                         "matching_carrier_product_online")
        self.assertEqual(report["live_attribute_read"], "success")
        self.assertEqual(self.writes,
                         ["get_nodes", "get_node", "read_attribute"])

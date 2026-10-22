"""Regression checks for safely reporting a real, possibly offline thermostat."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"


def load(name):
    spec = importlib.util.spec_from_file_location("status_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


models = load("models")
api = load("api")


class LiveSummaryTests(unittest.TestCase):
    def test_disconnected_is_not_unknown(self):
        systems = [{"serial": "private-A", "model": "TSTATCCEEF-01", "connection": {"isConnected": False},
                    "zones": [{"index": 0, "rt": 74, "clsp": {"current": 76}, "htsp": {"current": 68}}]}]
        summary = models.sanitize_device_summary(systems)
        self.assertEqual(summary["online_count"], 0)
        self.assertEqual(summary["offline_count"], 1)
        self.assertEqual(summary["unknown_connection_count"], 0)
        self.assertEqual(summary["zone_count"], 1)
        self.assertEqual(models.sanitize_telemetry(systems)[0]["cloud_connection"], "offline")

    def test_unknown_connection_is_not_offline(self):
        systems = [{"zones": [{"index": 0}]}, {"connection": {"isConnected": "false"}}]
        summary = models.sanitize_device_summary(systems)
        self.assertEqual(summary["unknown_connection_count"], 2)
        self.assertEqual(summary["offline_count"], 0)

    def test_safe_zone_telemetry(self):
        systems = [{"serial": "DO-NOT-PRINT", "name": "MY-HOME-SECRET", "deviceId": "SECRET",
                   "model": "TSTATCCEEF-01", "temp_unit_format": "F",
                   "connection": {"isConnected": True, "deviceId": "PRIVATE-ID"},
                   "zones": [{"index": 0, "rt": 70, "rh": 33, "mode": "heat",
                              "htsp": {"current": 69}, "clsp": {"current": 75}}]}]
        output = models.sanitize_telemetry(systems)
        self.assertEqual(output[0]["zones"][0]["room_temperature"], 70.0)
        self.assertEqual(output[0]["temperature_unit"], "°F")
        self.assertEqual(output[0]["cloud_connection"], "online")
        for secret in ("DO-NOT-PRINT", "MY-HOME-SECRET", "PRIVATE-ID"):
            self.assertNotIn(secret, repr(output))

    def test_invalid_mode_and_device_model_do_not_leak(self):
        result = models.sanitize_telemetry([{"model": "username@example.com", "zones": [{"index": 0, "mode": {"bad": 1}}]}])
        self.assertEqual(result[0]["model"], "unknown")
        self.assertEqual(result[0]["zones"][0]["mode"], "unknown")

    def test_finite_readings_and_zone_limits(self):
        data = [{"zones": [{"index": n, "rt": "nan"} for n in range(22)]}]
        result = models.sanitize_telemetry(data)
        self.assertEqual(len(result[0]["zones"]), 8)
        self.assertIsNone(result[0]["zones"][0]["room_temperature"])

    def test_original_cloud_model_is_not_silently_remapped(self):
        data = models.sanitize_telemetry([{"model": "TSTATCCEEF-01", "zones": []}])
        self.assertEqual(data[0]["model"], "TSTATCCEEF-01")


class DetailReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_detail_query(self):
        client = api.CarrierSmartHomeClient(object(), "account", "pw")
        client._graphql = AsyncMock(return_value={"entryLevelSystem": {
            "serial": "SECRET-DEVICE", "zones": [{"index": 0}]}})
        detail = await client.async_get_system_detail("SECRET-DEVICE")
        self.assertEqual(detail["serial"], "SECRET-DEVICE")
        self.assertEqual(client._graphql.await_args.args[0], "getEntryLevelSystemData")
        self.assertEqual(client._graphql.await_args.args[2], {"serial": "SECRET-DEVICE"})
        self.assertEqual(client._graphql.await_count, 1)

    async def test_rejected_detail_query_can_be_handled_by_smoke_test(self):
        client = api.CarrierSmartHomeClient(object(), "account", "pw")
        client._graphql = AsyncMock(return_value={"entryLevelSystem": None})
        with self.assertRaises(api.CarrierQueryError):
            await client.async_get_system_detail("SECRET-DEVICE")

    async def test_invalid_device_identity_does_not_send_network(self):
        client = api.CarrierSmartHomeClient(object(), "account", "pw")
        client._graphql = AsyncMock()
        for serial in ("", None, "a" * 129):
            with self.assertRaises(ValueError):
                await client.async_get_system_detail(serial)
        self.assertEqual(client._graphql.await_count, 0)


if __name__ == "__main__":
    unittest.main()

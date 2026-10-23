"""Offline regression tests for immediate climate intent and privacy-safe diagnostics."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"
spec = importlib.util.spec_from_file_location("carrier_optimistic_feedback_tests", ROOT / "optimistic.py")
optimistic = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = optimistic
spec.loader.exec_module(optimistic)


class OptimisticFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.changed = []
        self.state = optimistic.OptimisticControlTracker(lambda: self.changed.append(True))

    def test_mode_is_visible_before_any_cloud_response(self):
        desired = {"mode": "cool"}
        token = self.state.begin("SECRET-SERIAL", 0, desired, {"mode": "off"}, 1)
        desired["mode"] = "heat"
        self.assertEqual(self.state.overlay("SECRET-SERIAL", 0), {"mode": "cool"})
        self.assertEqual(len(self.changed), 1)
        self.state.record(token, "mutation_acknowledged")
        self.state.finish("SECRET-SERIAL", 0, token, "verified")
        self.assertEqual(self.state.overlay("SECRET-SERIAL", 0), {})
        self.assertEqual(len(self.changed), 2)

    def test_rejected_command_rolls_back_without_mutating_report(self):
        report = {"mode": "off"}
        token = self.state.begin("SECRET", 0, {"mode": "cool"}, report, 1)
        self.state.finish("SECRET", 0, token, "reverted", reason="mutation_rejected")
        self.assertEqual(report, {"mode": "off"})
        self.assertEqual(self.state.overlay("SECRET", 0), {})
        self.assertEqual(self.state.events[-1]["stage"], "optimistic_rollback")

    def test_acknowledged_but_unverified_is_not_reported_as_success(self):
        token = self.state.begin("A", 0, {"mode": "cool"}, {"mode": "off"}, 1)
        self.state.record(token, "mutation_acknowledged")
        self.state.finish("A", 0, token, "unconfirmed", reason="cloud_readback_uncertain")
        self.assertEqual(self.state.overlay("A", 0), {})
        self.assertEqual(self.state.events[-2]["stage"], "unconfirmed")

    def test_zones_independent_and_old_completion_ignored(self):
        a = self.state.begin("A", 0, {"fan_mode": "on"}, {"fan_mode": "auto"}, 1)
        b = self.state.begin("B", 0, {"mode": "heat"}, {"mode": "off"}, 2)
        self.state.finish("A", 0, a, "verified")
        self.assertEqual(self.state.overlay("B", 0), {"mode": "heat"})
        self.state.finish("A", 0, a, "reverted")
        self.state.finish("B", 0, b, "cancelled", reason="task_cancelled")
        self.assertEqual(self.state.overlay("B", 0), {})

    def test_history_bounded_and_sanitized(self):
        command = self.state.begin("my.account@example.com", 1, {"mode": "heat"},
                                   {"mode": "off"}, 1)
        for idx in range(240):
            self.state.record(command, "verification_read", source="detail", attempt=idx + 1,
                              observed={"mode": "off", "fan_mode": {"secret": "SECRET"}})
        self.assertEqual(len(self.state.events), 160)
        self.assertNotIn("my.account@example.com", repr(self.state.events))
        self.assertNotIn("SECRET", repr(self.state.events))
        self.state.finish("my.account@example.com", 1, command, "verified")
        self.assertEqual(self.state.active_diagnostics, [])

    def test_unsafe_request_and_log_tags_are_rejected(self):
        with self.assertRaises(ValueError):
            self.state.begin("S", 0, {"mode": "secret password"}, {"mode": "off"}, 1)
        with self.assertRaises(ValueError):
            self.state.begin("S", 0, {"cool_setpoint": float("nan")}, {}, 1)
        with self.assertRaises(ValueError):
            self.state.record(1, "error password=123")
        with self.assertRaises(ValueError):
            self.state.record(1, "error", reason="secret token")


class ControlIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Real command path with stubbed Home Assistant and Carrier cloud."""

    async def asyncSetUp(self):
        import asyncio
        import types
        from unittest.mock import AsyncMock, patch
        self.asyncio = asyncio
        self.AsyncMock = AsyncMock
        self.pkg = "carrier_optimistic_control_test"
        def module(name):
            return types.ModuleType(name)
        stubs = {name: module(name) for name in (
            "homeassistant", "homeassistant.exceptions", self.pkg,
            self.pkg + ".api",
        )}
        stubs[self.pkg].__path__ = [str(ROOT)]
        stubs["homeassistant.exceptions"].HomeAssistantError = type(
            "HomeAssistantError", (Exception,), {})
        stubs[self.pkg + ".api"].CarrierError = type("CarrierError", (Exception,), {})
        stubs[self.pkg + ".api"].CarrierRateLimitError = type(
            "CarrierRateLimitError", (stubs[self.pkg + ".api"].CarrierError,), {})
        self.stubs = patch.dict(sys.modules, stubs)
        self.stubs.start()
        self.loaded = []
        for name in ("models", "control"):
            full = self.pkg + "." + name
            loader = importlib.util.spec_from_file_location(full, ROOT / (name + ".py"))
            loaded = importlib.util.module_from_spec(loader)
            sys.modules[full] = loaded
            self.loaded.append(full)
            loader.loader.exec_module(loaded)
            setattr(self, name, loaded)
        self.CarrierError = stubs[self.pkg + ".api"].CarrierError
        self.HomeAssistantError = stubs["homeassistant.exceptions"].HomeAssistantError
        self.control.READBACK_DELAYS = (0,)
        self.control.DETAIL_CHECK_ATTEMPTS = frozenset((0,))

    async def asyncTearDown(self):
        for name in self.loaded:
            sys.modules.pop(name, None)
        self.stubs.stop()

    def coordinator(self, detail_mode="cool"):
        import types
        from unittest.mock import AsyncMock
        class Coordinator:
            def __init__(self, parent):
                self.parent = parent
                self.data = {"SENSITIVE-SERIAL": {
                    "serial": "SENSITIVE-SERIAL",
                    "connection": {"isConnected": True},
                    "zones": [{"index": 0, "mode": "off", "fan_mode": "auto",
                               "htsp": {"current": 68, "max": 90},
                               "clsp": {"current": 75, "min": 60}}]}}
                self.last_update_success = True
                self.write_lock = parent.asyncio.Lock()
                self.change_count = 0
                self.optimistic = optimistic.OptimisticControlTracker(self.notify)
                self.async_refresh = AsyncMock()
                self.client = types.SimpleNamespace(
                    async_update_zone=AsyncMock(),
                    async_get_system_detail=AsyncMock(return_value={
                        "serial": "SENSITIVE-SERIAL",
                        "connection": {"isConnected": True},
                        "zones": [{"index": 0, "mode": detail_mode,
                                   "htsp": {"current": 68},
                                   "clsp": {"current": 75}}],
                    }),
                )
            def notify(self):
                self.change_count += 1
            def begin_control(self, serial, zone, desired):
                return self.optimistic.begin(serial, zone, desired,
                     self.parent.models.zone_values(self.data[serial]["zones"][zone]), 1)
            def publish_verified_detail(self, serial, zone, detail, desired):
                values = self.parent.models.zone_values(detail["zones"][0])
                if values["mode"] != desired.get("mode"):
                    return False
                self.data[serial]["zones"][0]["mode"] = values["mode"]
                return True
        return Coordinator(self)

    async def test_mode_shows_requested_state_before_cloud_mutation_completes(self):
        c = self.coordinator()
        entered, release = self.asyncio.Event(), self.asyncio.Event()
        async def held_mutation(*_args, **_kwargs):
            entered.set()
            await release.wait()
        c.client.async_update_zone.side_effect = held_mutation
        task = self.asyncio.create_task(self.control.async_set_mode_verified(
            c, "SENSITIVE-SERIAL", 0, "cool"))
        try:
            await self.asyncio.wait_for(entered.wait(), 1)
            self.assertEqual(c.optimistic.overlay("SENSITIVE-SERIAL", 0), {"mode": "cool"})
            self.assertEqual(c.data["SENSITIVE-SERIAL"]["zones"][0]["mode"], "off")
        finally:
            release.set()
        await task
        self.assertEqual(c.optimistic.overlay("SENSITIVE-SERIAL", 0), {})
        self.assertEqual(c.data["SENSITIVE-SERIAL"]["zones"][0]["mode"], "cool")
        c.client.async_update_zone.assert_awaited_once()
        self.assertIn("verification_confirmed",
                      [e["stage"] for e in c.optimistic.events])
        self.assertEqual(c.change_count, 2)

    async def test_mutation_rejection_rolls_back(self):
        c = self.coordinator()
        c.client.async_update_zone.side_effect = self.CarrierError("secret token")
        with self.assertRaises(self.HomeAssistantError):
            await self.control.async_set_mode_verified(c, "SENSITIVE-SERIAL", 0, "cool")
        self.assertEqual(c.data["SENSITIVE-SERIAL"]["zones"][0]["mode"], "off")
        self.assertEqual(c.optimistic.overlay("SENSITIVE-SERIAL", 0), {})
        self.assertEqual(c.optimistic.events[-1]["stage"], "optimistic_rollback")
        self.assertNotIn("secret token", repr(c.optimistic.events))
        c.client.async_update_zone.assert_awaited_once()

    async def test_acknowledged_but_stale_cloud_is_unconfirmed(self):
        c = self.coordinator(detail_mode="off")
        with self.assertRaises(self.HomeAssistantError):
            await self.control.async_set_mode_verified(c, "SENSITIVE-SERIAL", 0, "cool")
        self.assertEqual(c.data["SENSITIVE-SERIAL"]["zones"][0]["mode"], "off")
        self.assertEqual(c.optimistic.overlay("SENSITIVE-SERIAL", 0), {})
        self.assertIn("unconfirmed", [e["stage"] for e in c.optimistic.events])
        c.client.async_update_zone.assert_awaited_once()

    async def test_failed_preflight_never_writes_and_reverts(self):
        c = self.coordinator()
        c.async_refresh.side_effect = RuntimeError("temporary outage")
        with self.assertRaises(self.HomeAssistantError):
            await self.control.async_set_mode_verified(c, "SENSITIVE-SERIAL", 0, "cool")
        c.client.async_update_zone.assert_not_awaited()
        self.assertEqual(c.optimistic.overlay("SENSITIVE-SERIAL", 0), {})
        self.assertIn("preflight_failed", [e["stage"] for e in c.optimistic.events])

    async def test_overlap_rejected_without_replacing_active_overlay(self):
        c = self.coordinator()
        await c.write_lock.acquire()
        try:
            with self.assertRaises(self.HomeAssistantError):
                await self.control.async_set_mode_verified(c, "SENSITIVE-SERIAL", 0, "cool")
            self.assertEqual(c.optimistic.overlay("SENSITIVE-SERIAL", 0), {})
            self.assertIn("command_blocked", [e["stage"] for e in c.optimistic.events])
            c.client.async_update_zone.assert_not_awaited()
        finally:
            c.write_lock.release()

    async def test_explicit_offline_never_displays_optimistic_mode(self):
        c = self.coordinator()
        c.data["SENSITIVE-SERIAL"]["connection"]["isConnected"] = False
        with self.assertRaises(self.HomeAssistantError):
            await self.control.async_set_mode_verified(c, "SENSITIVE-SERIAL", 0, "cool")
        self.assertEqual(c.optimistic.overlay("SENSITIVE-SERIAL", 0), {})
        c.client.async_update_zone.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

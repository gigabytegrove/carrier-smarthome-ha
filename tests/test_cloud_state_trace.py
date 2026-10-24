"""Offline tests for privacy-safe Carrier cloud state transition history."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"
spec = importlib.util.spec_from_file_location("carrier_state_trace_tests", ROOT / "state_trace.py")
trace_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = trace_mod
spec.loader.exec_module(trace_mod)


class CloudStateTraceTests(unittest.TestCase):
    def setUp(self):
        self.trace = trace_mod.CloudControlTrace()
        self.serial = "VERY-PRIVATE-SERIAL-ID"
        self.base = {
            "mode": "off", "fan_mode": "auto",
            "heat_setpoint": 57, "cool_setpoint": 74,
            "schedule_enabled": True,
        }

    def test_baseline_then_only_changes_in_same_source(self):
        self.trace.observe(self.serial, 0, "listing", self.base, 1)
        self.trace.observe(self.serial, 0, "listing", dict(self.base), 1)
        self.assertEqual(len(self.trace.events), 1)
        self.assertEqual(self.trace.events[0]["stage"], "baseline")
        self.trace.observe(self.serial, 0, "listing",
                           {**self.base, "mode": "cool"}, 1, 6)
        self.assertEqual(len(self.trace.events), 2)
        event = self.trace.events[1]
        self.assertEqual(event["stage"], "reported_change")
        self.assertEqual(event["previous"], {"mode": "off"})
        self.assertEqual(event["current"], {"mode": "cool"})
        self.assertEqual(event["command_pending_when_observed"], 6)
        self.assertNotIn(self.serial, repr(self.trace.events))

    def test_different_query_sources_are_independent(self):
        self.trace.observe(self.serial, 0, "listing", self.base, 1)
        self.trace.observe(self.serial, 0, "detail",
                           {**self.base, "mode": "cool"}, 1)
        self.assertEqual([e["stage"] for e in self.trace.events],
                         ["baseline", "baseline"])
        self.trace.observe(self.serial, 0, "listing",
                           {**self.base, "mode": "cool"}, 1)
        self.assertEqual(self.trace.events[-1]["source"], "listing")
        self.assertEqual(self.trace.events[-1]["previous"], {"mode": "off"})

    def test_unknown_or_missing_fields_are_not_changes(self):
        self.trace.observe(self.serial, 0, "listing", self.base, 1)
        self.trace.observe(self.serial, 0, "listing",
                           {"mode": None, "fan_mode": {},
                            "cool_setpoint": float("nan")}, 1)
        self.assertEqual(len(self.trace.events), 1)
        self.trace.observe(self.serial, 0, "listing",
                           {**self.base, "mode": "heat"}, 1)
        self.assertEqual(self.trace.events[-1]["previous"], {"mode": "off"})

    def test_schedule_toggle_is_observed_without_claiming_causation(self):
        self.trace.observe(self.serial, 0, "listing", self.base, 1)
        self.trace.observe(self.serial, 0, "listing",
                           {**self.base, "schedule_enabled": False}, 1)
        event = self.trace.events[-1]
        self.assertEqual(event["current"], {"schedule_enabled": False})
        self.assertNotIn("origin", event)

    def test_history_is_bounded_and_privacy_sanitized(self):
        self.trace.observe(self.serial, 0, "listing", self.base, 1)
        for x in range(150):
            mode = "heat" if x % 2 else "cool"
            self.trace.observe(self.serial, 0, "listing",
                               {**self.base, "mode": mode}, 1)
        self.assertEqual(len(self.trace.events), 100)
        self.assertNotIn(self.serial, repr(self.trace.events))

    def test_untrusted_source_cannot_be_exported(self):
        with self.assertRaises(ValueError):
            self.trace.observe(self.serial, 0, "email:a@example.com",
                               self.base, 1)


if __name__ == "__main__":
    unittest.main()

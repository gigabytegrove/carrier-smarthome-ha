"""Read-only owner-guided app/cloud A/B comparison (synthetic identities only)."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "Compare-AppChange.py"
spec = importlib.util.spec_from_file_location("app_change_probe", TOOL)
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def system(cool: float, heat: float = 70.0, online: bool = False) -> dict:
    return {
        "serial": "synthetic_device_id",
        "model": "TSTATCCEEF-01",
        "connection": {"isConnected": online, "macaddress": "DONOTPRINT_ABC123"},
        "name": "private family home",
        "zones": [{"index": 0, "mode": "off", "fan_mode": "auto",
                   "htsp": {"current": heat}, "clsp": {"current": cool}}],
    }


class PureComparison(unittest.TestCase):
    def test_identity_has_no_effect_on_setpoint_detection(self):
        before = probe.clean_values(system(76)["zones"][0])
        after = probe.clean_values(system(77)["zones"][0])
        self.assertEqual(probe.changed_targets(before, after), ["cool_setpoint"])
        self.assertEqual(probe.interpretation(before, after, before),
                         "APP_TO_GRAPHQL_CHANGE_AND_FULL_OBSERVED_BASELINE_RESTORE_CONFIRMED")

    def test_no_change_is_not_painted_as_live(self):
        baseline = probe.clean_values(system(76)["zones"][0])
        self.assertEqual(probe.interpretation(baseline, baseline, baseline),
                         "NO_SETPOINT_CHANGE_OBSERVED")
        self.assertEqual(probe.interpretation(baseline, None, None),
                         "NO_SETPOINT_CHANGE_OBSERVED")

    def test_change_without_restore_is_flagged(self):
        before = probe.clean_values(system(76)["zones"][0])
        modified = probe.clean_values(system(77)["zones"][0])
        self.assertEqual(probe.interpretation(before, modified, None),
                         "SETPOINT_CHANGE_OBSERVED_RESTORE_NOT_CONFIRMED")
        self.assertEqual(probe.interpretation(before, modified, modified),
                         "SETPOINT_CHANGE_OBSERVED_RESTORE_NOT_CONFIRMED")

    def test_offline_flag_does_not_affect_change_classification(self):
        a = system(76, online=False)
        b = system(77, online=False)
        before = probe.clean_values(a["zones"][0])
        after = probe.clean_values(b["zones"][0])
        self.assertEqual(probe.changed_targets(before, after), ["cool_setpoint"])
        self.assertEqual(probe.interpretation(before, after, before),
                         "APP_TO_GRAPHQL_CHANGE_AND_FULL_OBSERVED_BASELINE_RESTORE_CONFIRMED")

    def test_output_does_not_contain_private_device_identifiers(self):
        sample = {"connection": "offline", "list": probe.clean_values(system(76)["zones"][0]),
                  "detail": probe.clean_values(system(76)["zones"][0])}
        with patch("builtins.print") as printed:
            probe.display("BASELINE", sample)
        logged = str(printed.call_args_list)
        for secret in ("synthetic_device_id", "DONOTPRINT_ABC123", "private family home"):
            self.assertNotIn(secret, logged)
        self.assertIn("offline", logged)

    def test_owner_observed_cooling_restore_did_not_restore_mode_or_heat(self):
        before = {"heat_setpoint": 70.0, "cool_setpoint": 76.0, "mode": "off",
                  "fan_mode": "auto", "schedule_enabled": True}
        changed = {**before, "cool_setpoint": 73.0, "mode": "cool"}
        final = {**before, "heat_setpoint": 69.0, "mode": "cool"}
        self.assertEqual(probe.changed_targets(before, changed), ["cool_setpoint"])
        self.assertTrue(probe.matches_baseline(before, final, ["cool_setpoint"]))
        self.assertEqual(probe.baseline_differences(before, final), ["heat_setpoint", "mode"])
        self.assertFalse(probe.matches_complete_baseline(before, final))
        self.assertEqual(probe.interpretation(before, changed, final),
                         "SETPOINT_RESTORED_OTHER_SETTINGS_DIFFER")

    def test_unreported_baseline_fields_do_not_block_reversible_test(self):
        before = {"heat_setpoint": 70.0, "cool_setpoint": 76.0,
                  "mode": "off", "fan_mode": None, "schedule_enabled": None}
        self.assertTrue(probe.matches_complete_baseline(before, before))
        self.assertFalse(probe.baseline_differences(before, before))

    def test_missing_known_baseline_values_count_as_differences(self):
        before = {"heat_setpoint": 70.0, "cool_setpoint": 76.0, "mode": "cool"}
        after = {"heat_setpoint": 70.0, "cool_setpoint": 76.0}
        self.assertEqual(probe.baseline_differences(before, after), ["mode"])
        self.assertFalse(probe.matches_complete_baseline(before, after))

    def test_missing_values_not_claimed_to_change_or_restore(self):
        self.assertEqual(probe.changed_targets({"cool_setpoint": None}, {"cool_setpoint": 75}), [])
        self.assertFalse(probe.matches_baseline({"cool_setpoint": None}, {"cool_setpoint": None}, ["cool_setpoint"]))
        self.assertFalse(probe.matches_baseline({"cool_setpoint": 76}, {"cool_setpoint": 76}, []))


class CloudPair(unittest.IsolatedAsyncioTestCase):
    async def test_reads_both_sources_with_same_identity(self):
        client = type("FakeClient", (), {})()
        client.async_get_systems = AsyncMock(return_value=[system(76)])
        client.async_get_system_detail = AsyncMock(return_value=system(76))
        result = await probe.read_pair(client, "synthetic_device_id", 0)
        self.assertEqual(result["connection"], "offline")
        self.assertEqual(result["list"]["cool_setpoint"], 76)
        self.assertEqual(result["detail"]["cool_setpoint"], 76)
        client.async_get_system_detail.assert_awaited_once_with("synthetic_device_id")

    async def test_refuses_wrong_device(self):
        client = type("FakeClient", (), {})()
        client.async_get_systems = AsyncMock(return_value=[system(76)])
        client.async_get_system_detail = AsyncMock()
        with self.assertRaisesRegex(ValueError, "no longer uniquely available"):
            await probe.read_pair(client, "other_device", 0)
        client.async_get_system_detail.assert_not_awaited()

    async def test_optional_detail_failure_retains_baseline(self):
        client = type("FakeClient", (), {})()
        client.async_get_systems = AsyncMock(return_value=[system(76)])
        client.async_get_system_detail = AsyncMock(side_effect=probe.CarrierError("no detail"))
        result = await probe.read_pair(client, "synthetic_device_id", 0)
        self.assertEqual(result["list"]["cool_setpoint"], 76)
        self.assertEqual(result["detail"], {})

    async def test_restore_stops_only_when_changed_source_restores(self):
        # A *different, unchanged* API view must not produce a false restore PASS.
        base = {"connection": "offline", "list": {"heat_setpoint": 70.0, "cool_setpoint": 76.0},
                "detail": {"heat_setpoint": 70.0, "cool_setpoint": 76.0}}
        not_restored = {"connection": "offline", "list": {"heat_setpoint": 70.0, "cool_setpoint": 77.0},
                        "detail": {"heat_setpoint": 70.0, "cool_setpoint": 76.0}}
        restored = {"connection": "offline", "list": {"heat_setpoint": 70.0, "cool_setpoint": 76.0},
                    "detail": {"heat_setpoint": 70.0, "cool_setpoint": 76.0}}
        with patch.object(probe, "read_pair", new_callable=AsyncMock, side_effect=[not_restored, restored]) as read, \
                patch.object(probe.asyncio, "sleep", new_callable=AsyncMock):
            found, last = await probe.read_sequence(object(), "not_displayed", 0, base,
                                                    attempts=2, interval=15, label="TEST",
                                                    changed={"list": ["cool_setpoint"], "detail": []})
        self.assertEqual(read.await_count, 2)
        self.assertEqual(found, restored)
        self.assertEqual(last, restored)

    async def test_restore_waits_for_mode_and_other_setpoint_too(self):
        base_list = {"heat_setpoint": 70.0, "cool_setpoint": 76.0,
                     "mode": "off", "fan_mode": "auto", "schedule_enabled": True}
        start = {"connection": "online", "list": base_list, "detail": dict(base_list)}
        mismatch = dict(base_list, heat_setpoint=69.0, mode="cool")
        partial = {"connection": "online", "list": mismatch, "detail": dict(mismatch)}
        fully_restored = {"connection": "online", "list": dict(base_list), "detail": dict(base_list)}
        with patch.object(probe, "read_pair", new_callable=AsyncMock,
                          side_effect=[partial, fully_restored]) as read, \
             patch.object(probe.asyncio, "sleep", new_callable=AsyncMock):
            found, last = await probe.read_sequence(object(), "synthetic", 0, start,
                            attempts=2, interval=15, label="RESTORE", changed={"list": ["cool_setpoint"],
                                                                         "detail": ["cool_setpoint"]})
        self.assertEqual(read.await_count, 2)
        self.assertEqual(found, fully_restored)
        self.assertEqual(last, fully_restored)

    async def test_restore_not_confirmed_if_only_cooling_reverts(self):
        base_list = {"heat_setpoint": 70.0, "cool_setpoint": 76.0, "mode": "off"}
        before = {"connection": "online", "list": base_list, "detail": dict(base_list)}
        mismatch = dict(base_list, mode="cool")
        after = {"connection": "online", "list": mismatch, "detail": dict(mismatch)}
        with patch.object(probe, "read_pair", new_callable=AsyncMock,
                          return_value=after), \
             patch.object(probe.asyncio, "sleep", new_callable=AsyncMock):
            found, last = await probe.read_sequence(object(), "synthetic", 0, before,
                            attempts=2, interval=15, label="RESTORE", changed={"list": ["cool_setpoint"]})
        self.assertIsNone(found)
        self.assertEqual(last, after)

    async def test_readonly_probe_does_not_issue_mutations(self):
        # The test tool uses only the well-known read methods; even when app changes,
        # it has no method to invoke a Carrier write or automatically undo one.
        text = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("async_update_zone(", text)
        self.assertNotIn("client._graphql(", text)
        self.assertIn("async_get_systems()", text)
        self.assertIn("async_get_system_detail(serial)", text)


if __name__ == "__main__":
    unittest.main()

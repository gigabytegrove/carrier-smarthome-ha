"""Strict restore verification and privacy-safe current-state checker tests."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'tools' / 'Check-CarrierState.py'
spec = importlib.util.spec_from_file_location('carrier_readonly_state', PATH)
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


class StateComparison(unittest.TestCase):
    def setUp(self):
        self.sample = {'connection': 'online',
                       'list': {'heat_setpoint': 70.0, 'cool_setpoint': 76.0,
                                'mode': 'off', 'fan_mode': 'auto', 'schedule_enabled': True},
                       'detail': {'heat_setpoint': 70.0, 'cool_setpoint': 76.0,
                                  'mode': 'off', 'fan_mode': 'auto', 'schedule_enabled': True}}

    def test_matches_both_cloud_views(self):
        r = checker.compare_expectations(self.sample, {'cool_setpoint': 76.0, 'heat_setpoint': 70.0, 'mode': 'off'})
        self.assertEqual(r, {'list': [], 'detail': []})

    def test_mismatched_heat_and_mode_are_flagged(self):
        modified = {**self.sample, 'detail': dict(self.sample['detail'], heat_setpoint=69.0, mode='cool')}
        r = checker.compare_expectations(modified, {'heat_setpoint': 70.0, 'cool_setpoint': 76.0, 'mode': 'off'})
        self.assertEqual(r['list'], [])
        self.assertEqual(r['detail'], ['heat_setpoint', 'mode'])

    def test_missing_detail_is_not_a_pass(self):
        modified = {**self.sample, 'detail': {}}
        self.assertEqual(checker.compare_expectations(modified, {'mode': 'off'})['detail'], ['source_unavailable'])

    def test_does_not_interpret_one_source_as_both(self):
        changed = {**self.sample, 'list': dict(self.sample['list'], cool_setpoint=75.0)}
        self.assertEqual(checker.compare_expectations(changed, {'cool_setpoint': 76.0})['list'], ['cool_setpoint'])
        self.assertEqual(checker.compare_expectations(changed, {'cool_setpoint': 76.0})['detail'], [])

    def test_nonfinite_input_rejected(self):
        args = type('Args', (), {'heat_setpoint': float('nan'), 'cool_setpoint': None,
                                 'mode': None, 'fan_mode': None, 'schedule_enabled': None})()
        with self.assertRaisesRegex(ValueError, 'finite'):
            checker.expectation_values(args)

    def test_no_write_method_referenced(self):
        text = PATH.read_text(encoding='utf-8')
        self.assertNotIn('async_update_zone', text)
        self.assertNotIn('updateEntryLevelZone', text)


if __name__ == '__main__':
    unittest.main()

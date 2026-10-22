"""Offline checks for read-only Carrier field inventory and HA diagnostics."""
from __future__ import annotations

import asyncio
from importlib import util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components' / 'carrier_smarthome'


def load(module_name, path):
    spec = util.spec_from_file_location('alpha4_' + module_name, path)
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


models = load('models', COMPONENT / 'models.py')
api = load('api', COMPONENT / 'api.py')
values = load('values', ROOT / 'tools' / 'Get-CarrierValues.py')


def payload(*, connection=False):
    return {
        'serial': 'EXAMPLE-NOT-PRINTABLE',
        'name': 'Family Home Secret',
        'model': 'TSTATCCEEF-01',
        'temp_unit_format': 'F',
        'connection': {'isConnected': connection, 'ssid': 'Home Secret Network'},
        'zones': [{
            'index': 0, 'mode': 'off', 'rt': 73, 'rh': 47, 'outside_temp': 51,
            'htsp': {'current': 70, 'max': 90},
            'clsp': {'current': 76, 'min': 62},
            'fan_mode': 'auto', 'stage_status': 'idle',
            'schedule_enabled': False, 'hold_countdown': 180,
        }],
    }


class FieldNormalization(unittest.TestCase):
    def test_normalized_stage_fan_limits_schedule_hold(self):
        z = models.zone_values(payload()['zones'][0])
        self.assertEqual(z['fan_mode'], 'auto')
        self.assertEqual(z['stage_status'], 'idle')
        self.assertIs(z['schedule_enabled'], False)
        self.assertEqual(z['heat_max'], 90.0)
        self.assertEqual(z['cool_min'], 62.0)
        self.assertEqual(z['hold_countdown_raw'], 180.0)
        self.assertIsNone(z['current_scene'])

    def test_untrusted_string_data_and_numeric_outliers_not_leaked(self):
        bad = payload()
        bad['zones'][0].update({'stage_status': 'user@example.com', 'fan_mode': '/priv/secret',
                                 'mode': '<unexpected>', 'current_scene_name': 'My Apartment - User Name',
                                 'schedule_enabled': 'false', 'hold_countdown': 'nan',
                                 'rt': 'NaN', 'rh': float('inf')})
        result = values.build_report([bad], [None], ['unavailable'])
        as_text = values.format_values(result)
        for secret in ('EXAMPLE-NOT-PRINTABLE', 'Family Home Secret', 'Home Secret Network',
                       'user@example.com', '/priv/secret', 'My Apartment - User Name'):
            self.assertNotIn(secret, as_text)
        zone = result['devices'][0]['zones'][0]
        self.assertEqual(zone['mode'], 'unknown')
        self.assertIsNone(zone['stage_status'])
        self.assertIsNone(zone['fan_mode'])
        self.assertIsNone(zone['schedule_enabled'])
        self.assertIsNone(zone['humidity_percent'])
        self.assertIsNone(zone['room_temperature'])

    def test_unknown_cloud_connection_does_not_mean_offline(self):
        system = payload()
        system['connection'].pop('isConnected')
        self.assertEqual(values.build_report([system], [None], ['not_available'])['devices'][0]['cloud_connection'], 'unknown')

    def test_optional_detail_enriches_only_safe_scene_without_overriding_baseline(self):
        sys1 = payload()
        extended = payload(connection=True)
        extended['zones'][0]['rt'] = 99
        extended['zones'][0]['current_scene_name'] = 'home'
        report = values.build_report([sys1], [extended], ['pass'])
        zone = report['devices'][0]['zones'][0]
        self.assertEqual(zone['room_temperature'], 73)
        self.assertEqual(zone['current_scene'], 'home')
        self.assertEqual(report['devices'][0]['cloud_connection'], 'offline')

    def test_mismatched_model_does_not_enrich(self):
        sys1 = payload()
        extended = payload()
        extended['model'] = 'TSTATCCCEF-OTHER'
        extended['zones'][0]['current_scene_name'] = 'away'
        report = values.build_report([sys1], [extended], ['pass'])
        self.assertIsNone(report['devices'][0]['zones'][0]['current_scene'])

    def test_format_never_claims_fresh(self):
        message = values.format_values(values.build_report([payload()], [None], ['unavailable']))
        self.assertIn('OFFLINE cloud readings can be cached', message)
        self.assertIn('No credentials, serials, MACs', message)


class OptionalExtendedDetail(unittest.IsolatedAsyncioTestCase):
    async def test_query_exact_routing_and_serial_match(self):
        cl = api.CarrierSmartHomeClient(object(), 'owner', 'secret')
        cl._graphql = AsyncMock(return_value={'entryLevelSystem': payload()})
        result = await cl.async_get_extended_detail(payload()['serial'])
        self.assertEqual(result['model'], 'TSTATCCEEF-01')
        (operation, document, variables) = cl._graphql.await_args.args
        self.assertEqual(operation, 'getEntryLevelSystemData')
        self.assertEqual(variables, {'serial': payload()['serial']})
        self.assertIn('current_scene_name', document)
        self.assertIn('schedule_enabled', document)
        self.assertNotIn('mutation', document.lower())

    async def test_mismatch_does_not_export_wrong_thermostat(self):
        cl = api.CarrierSmartHomeClient(object(), 'owner', 'secret')
        cl._graphql = AsyncMock(return_value={'entryLevelSystem': payload()})
        with self.assertRaises(api.CarrierQueryError):
            await cl.async_get_extended_detail('other-thermostat')

    async def test_invalid_serial_never_sends_request(self):
        cl = api.CarrierSmartHomeClient(object(), 'owner', 'secret')
        cl._graphql = AsyncMock()
        for serial in ('', None, 'x' * 129):
            with self.assertRaises(ValueError):
                await cl.async_get_extended_detail(serial)
        cl._graphql.assert_not_awaited()

    async def test_detail_rejection_keeps_baseline(self):
        data = payload()
        cl = api.CarrierSmartHomeClient(object(), 'owner', 'secret')
        cl.async_get_systems = AsyncMock(return_value=[data])
        cl.async_get_extended_detail = AsyncMock(side_effect=api.CarrierQueryError('rejected'))
        # Validate safe fallback behavior independent of real Carrier credentials.
        systems = await cl.async_get_systems()
        try:
            extra = await cl.async_get_extended_detail(data['serial'])
            status = 'pass'
        except api.CarrierError:
            extra, status = None, 'not_available_baseline_preserved'
        out = values.build_report(systems, [extra], [status])
        self.assertEqual(out['devices'][0]['zones'][0]['room_temperature'], 73)
        self.assertEqual(out['extended_detail_status'][0], 'not_available_baseline_preserved')


if __name__ == '__main__':
    unittest.main()

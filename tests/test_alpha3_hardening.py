"""Release-blocking regression tests for Carrier SmartHome alpha 3."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'custom_components/carrier_smarthome'
TOOLS = ROOT / 'tools'
sys.path.insert(0, str(TOOLS))


def load(name, path):
    spec = importlib.util.spec_from_file_location('alpha3_' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


api = load('api', API / 'api.py')
local = load('local', TOOLS / 'Probe-VerifiedCarrierLAN.py')
observer = load('observer', TOOLS / 'Observe-SmartHomeCloud.py')


class RateLimitTests(unittest.TestCase):
    def test_retry_after_seconds(self):
        self.assertEqual(api.retry_after_seconds('120'), 120)
        self.assertEqual(api.retry_after_seconds('-10'), 1)
        self.assertEqual(api.retry_after_seconds('99999'), 3600)
        self.assertEqual(api.retry_after_seconds('NaN'), 120)
        self.assertEqual(api.retry_after_seconds('gibberish'), 120)
        self.assertEqual(api.retry_after_seconds(None), 120)

    def test_retry_after_http_date(self):
        now = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
        self.assertEqual(api.retry_after_seconds('Thu, 22 Oct 2026 09:02:00 GMT', now=now), 120)

    def test_exceptions_do_not_log_response_body(self):
        self.assertNotIn('secret', str(api.CarrierRateLimitError(45)))


class NewValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.c = api.CarrierSmartHomeClient(object(), 'me@example.com', 'secret')
        self.c._graphql = AsyncMock(return_value={'updateEntryLevelZone': {'success': True}})

    async def test_non_finite_control_values_rejected_without_network(self):
        for invalid in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                await self.c.async_update_zone('sample', 0, heat=invalid, cool=75)
        self.assertEqual(self.c._graphql.await_count, 0)

    async def test_boolean_zone_index_rejected(self):
        with self.assertRaises(ValueError):
            await self.c.async_update_zone('sample', True, mode='off')
        self.assertEqual(self.c._graphql.await_count, 0)

    async def test_password_not_exposed(self):
        with self.assertRaises(ValueError):
            await self.c.async_update_zone('sample', 0, heat=90, cool=70)
        self.assertEqual(self.c._graphql.await_count, 0)


class LocalIdentityTests(unittest.TestCase):
    def test_refuses_stale_ip(self):
        with self.assertRaisesRegex(ValueError, 'not connected'):
            local.connected_target({'status': 'NOT CONNECTED IN EXPORT', 'last_ip': '172.20.0.151'})

    def test_refuses_other_network(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            local.connected_target({'status': 'CONNECTED', 'current_ip': '192.168.0.51'})

    def test_refuses_ambiguous_lease(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            local.connected_target({'status': 'CONNECTED', 'current_ip': '172.20.0.151', 'same_ip_other_macs': 1})

    def test_current_known_host_allows_check(self):
        self.assertEqual(local.connected_target({'status': 'CONNECTED', 'current_ip': '172.20.0.151', 'same_ip_other_macs': 0}), '172.20.0.151')

    def test_no_credentials_or_commands_in_ports(self):
        self.assertEqual(local.PORTS, (80, 443, 8080, 8443, 1883, 8883))


class ObserverTests(unittest.TestCase):
    def test_snapshot_has_no_account_identity(self):
        sample = observer.snapshot([{'serial': 'secret-serial', 'name': 'home', 'connection': {'isConnected': False},
                                   'model': 'TSTATCCEEF-01', 'zones': [{'index': 0, 'rt': 73, 'mode': 'off'}]}])
        text = str(sample)
        self.assertNotIn('secret-serial', text)
        self.assertNotIn("'home'", text)
        self.assertEqual(sample['summary']['offline_count'], 1)

    def test_changes_detected(self):
        prior = {'devices': [{'cloud_connection': 'offline', 'zones': [{'room_temperature': 73}]}]}
        later = {'devices': [{'cloud_connection': 'online', 'zones': [{'room_temperature': 74}]}]}
        changes = observer.compare(prior, later)
        self.assertTrue(any('cloud state' in c for c in changes))
        self.assertTrue(any('room_temperature' in c for c in changes))

    def test_identical_samples_do_not_prove_freshness(self):
        prior = {'devices': [{'cloud_connection': 'offline', 'zones': [{'room_temperature': 73}]}]}
        result = observer.compare(prior, prior)
        self.assertIn('does not prove data are stale', result[0])


class DiagnosticsTests(unittest.TestCase):
    def test_safe_diagnostics(self):
        # Loads package-relative module without a Home Assistant install.
        package = types.ModuleType('alpha3_package')
        package.__path__ = [str(API)]
        sys.modules['alpha3_package'] = package
        for name in ('const', 'models'):
            spec = importlib.util.spec_from_file_location('alpha3_package.' + name, API / (name+'.py'))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
        spec = importlib.util.spec_from_file_location('alpha3_package.diagnostics', API / 'diagnostics.py')
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        coord = types.SimpleNamespace(data={'private-serial': {'serial': 'private-serial', 'name':'my house',
            'model': 'TSTATCCEEF-01', 'connection': {'isConnected': False, 'deviceId':'private-id'},
            'zones':[{'index':0, 'rt':73}]}}, last_update_success=True)
        record = mod.build_diagnostics(coord)
        text = str(record)
        self.assertNotIn('private-serial', text)
        self.assertNotIn('private-id', text)
        self.assertNotIn('my house', text)
        self.assertEqual(record['devices'][0]['cloud_connection'], 'offline')
        self.assertTrue(record['telemetry_may_be_stale'])
        self.assertFalse(record['matter_enabled'])


if __name__ == '__main__':
    unittest.main()

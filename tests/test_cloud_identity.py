"""Offline regression tests for conflicting API online/offline evidence."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock

ROOT = pathlib.Path(__file__).resolve().parents[1]
API_DIR = ROOT / 'custom_components' / 'carrier_smarthome'


def load(name, path):
    spec = importlib.util.spec_from_file_location('identity_test_' + name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


models = load('models', API_DIR / 'models.py')
api = load('api', API_DIR / 'api.py')
probe = load('probe', ROOT / 'tools' / 'Verify-CarrierConnectivity.py')


class IdentityNormalizationTest(unittest.TestCase):
    def test_mac_formats(self):
        self.assertEqual(models.normalize_hardware_id('A1:B2:C3:D4:E5:F6'), 'A1B2C3D4E5F6')
        self.assertEqual(models.normalize_hardware_id('a1-b2-c3-d4-e5-f6'), 'A1B2C3D4E5F6')
        self.assertIsNone(models.normalize_hardware_id('not-a-mac'))

    def test_unknown_not_bad_match(self):
        self.assertEqual(models.hardware_identity_match('A1:B2:C3:D4:E5:F6', None), 'unverified')
        self.assertEqual(models.hardware_identity_match('A1:B2:C3:D4:E5:F6', '111111111111'), 'different_mac')
        self.assertEqual(models.hardware_identity_match('A1:B2:C3:D4:E5:F6', 'A1B2C3D4E5F6'), 'matched')

    def test_all_three_status_sources_and_identity_without_leak(self):
        system = {'serial':'A1B2C3D4E5F6','model':'TSTATCCEEF-01','connection':{'isConnected':False},'zones':[{'index':0}]}
        detail = {'serial':'A1B2C3D4E5F6','connection':{'isConnected':False}}
        inventory = [{'serial':'A1B2C3D4E5F6','connection':{'isConnected':True,'macaddress':'A1:B2:C3:D4:E5:F6'}}]
        rec = probe.analyze([system], [detail], inventory, 'A1:B2:C3:D4:E5:F6')
        self.assertEqual(rec[0]['entry_level_list'], 'offline')
        self.assertEqual(rec[0]['apk_device_detail'], 'offline')
        self.assertEqual(rec[0]['apk_user_location'], 'online')
        self.assertEqual(rec[0]['identity_to_physical_thermostat'], 'matched')
        for secret in ('A1B2C3D4E5F6','A1:B2:C3:D4:E5:F6'):
            self.assertNotIn(secret, probe.render(rec, 'pass'))

    def test_different_cloud_device_without_mac(self):
        system = {'serial': 'some-non-mac-serial', 'model': 'other', 'connection':{}, 'zones':[]}
        rec = probe.analyze([system], [None], [], 'A1B2C3D4E5F6')[0]
        self.assertEqual(rec['identity_to_physical_thermostat'], 'unverified')
        self.assertEqual(rec['apk_device_detail'], 'not_available')
        self.assertEqual(rec['apk_user_location'], 'not_listed')

    def test_missing_user_query_not_offline(self):
        x = probe.analyze([{'serial':'A1B2C3D4E5F6','connection':{'isConnected':False}}],
                          [], None, None)[0]
        self.assertEqual(x['apk_user_location'], 'query_unavailable')


class ConnectionClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_user_locations_query(self):
        client = api.CarrierSmartHomeClient(object(), 'owner', 'password')
        client._graphql = AsyncMock(return_value={'user': {'locations': [
            {'entryLevels':[{'serial':'synthetic', 'connection':{'isConnected':False,'macaddress':'AA:BB:CC:DD:EE:FF'}}]}
        ]}})
        devices = await client.async_get_user_connection_inventory()
        self.assertEqual(devices[0]['serial'], 'synthetic')
        self.assertEqual(devices[0]['connection']['isConnected'], False)
        args = client._graphql.call_args.args
        self.assertEqual(args[0], 'getUserWithDevices')
        self.assertIn('macaddress', args[1])
        self.assertNotIn('mutation', args[1].lower())

    async def test_invalid_user_query_shape(self):
        client = api.CarrierSmartHomeClient(object(), 'owner', 'password')
        client._graphql = AsyncMock(return_value={'user': None})
        with self.assertRaises(api.CarrierQueryError):
            await client.async_get_user_connection_inventory()


if __name__ == '__main__':
    unittest.main()

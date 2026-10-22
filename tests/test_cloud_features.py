"""APK-derived optional cloud capability query tests (all offline)."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

p = Path(__file__).resolve().parents[1]/'custom_components'/'carrier_smarthome'/'api.py'
spec = importlib.util.spec_from_file_location('cloud_feature_alpha3_api', p)
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)


class FeatureProbes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = api.CarrierSmartHomeClient(object(), 'account', 'secret')
        self.client._graphql = AsyncMock()

    async def test_schedules_readonly(self):
        self.client._graphql.return_value = {'entryLevelSchedules':[{'day': 1}]}
        self.assertEqual(len(await self.client.async_get_entry_level_feature('test-device', 'schedules')), 1)
        op, doc, variables = self.client._graphql.call_args.args
        self.assertEqual(op, 'getEntryLevelSchedules')
        self.assertNotIn('mutation', doc)
        self.assertEqual(variables, {'serial': 'test-device'})

    async def test_reminders_readonly(self):
        self.client._graphql.return_value = {'entryLevelReminders':[]}
        self.assertEqual(await self.client.async_get_entry_level_feature('test-device', 'reminders'), [])
        self.assertEqual(self.client._graphql.call_args.args[0], 'getEntryLevelReminders')

    async def test_preferences_readonly(self):
        self.client._graphql.return_value = {'entryLevelNotificationPrefs':{'push':{}}}
        result = await self.client.async_get_entry_level_feature('test-device', 'notification_prefs')
        self.assertIn('push', result)
        self.assertEqual(self.client._graphql.call_args.args[0], 'getEntryLevelNotificationPrefs')

    async def test_invalid_feature_never_network(self):
        with self.assertRaises(ValueError):
            await self.client.async_get_entry_level_feature('serial', 'updateEntryLevelZone')
        self.client._graphql.assert_not_called()

    async def test_invalid_serial_never_network(self):
        with self.assertRaises(ValueError):
            await self.client.async_get_entry_level_feature('', 'schedules')
        self.client._graphql.assert_not_called()

    async def test_graphql_auth_code_is_handled(self):
        with self.assertRaises(api.CarrierAuthError):
            api.CarrierSmartHomeClient._graphql_data({'errors': [{'extensions': {'code':'UNAUTHENTICATED'}, 'message':'PRIVATE'}]})

    async def test_other_error_does_not_disclose_payload(self):
        with self.assertRaises(api.CarrierQueryError) as context:
            api.CarrierSmartHomeClient._graphql_data({'errors': [{'extensions': {'code':'BAD_USER_INPUT'}, 'message':'PRIVATE'}]})
        self.assertNotIn('PRIVATE', str(context.exception))


if __name__ == '__main__':
    unittest.main()

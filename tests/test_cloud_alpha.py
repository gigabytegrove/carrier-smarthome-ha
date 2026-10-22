"""Offline unit tests for the installable native Carrier SmartHome cloud alpha."""
from __future__ import annotations
import asyncio
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock

MODULES = pathlib.Path(__file__).resolve().parents[1] / 'custom_components' / 'carrier_smarthome'


def load(name):
    spec = importlib.util.spec_from_file_location('alpha_test_' + name, MODULES / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


api = load('api')
model = load('models')


class ModelTests(unittest.TestCase):
    def test_zone_normalization(self):
        result = model.zone_values({'rt': 72, 'rh': 51, 'mode': 'cool',
                                    'htsp': {'current': 67, 'max': 90},
                                    'clsp': {'current': 75, 'min': 60},
                                    'outside_temp': '82.5'})
        self.assertEqual(result['heat_setpoint'], 67)
        self.assertEqual(result['cool_setpoint'], 75)
        self.assertEqual(result['outside_temperature'], 82.5)
        self.assertEqual(result['mode'], 'cool')

    def test_rejects_invalid_numbers(self):
        for value in ('nan', 'inf', 'not-a-number', [], {}, None, True):
            self.assertIsNone(model.zone_values({'rt': value})['temperature'])

    def test_zone_order_and_duplicates(self):
        self.assertEqual(model.zone_indices({'zones': [{'index': 2}, {'index': 0}, {'index': 2}, {'index': -1}, {'index': '0'}]}), [0, 2])

    def test_zone_lookup(self):
        zone = {'index': 1, 'rt': 21}
        self.assertEqual(model.get_zone({'zones': [zone]}, 1), zone)
        self.assertIsNone(model.get_zone({'zones': [zone]}, 0))

    def test_safe_device_summary(self):
        d = model.sanitize_device_summary([{'serial':'secret','model':'TSTATCCEWF-01',
                  'location_id':'HOME', 'zones':[{'index':0}], 'connection':{'isConnected':True}}])
        self.assertEqual(d['entry_level_count'], 1)
        self.assertNotIn('secret', str(d))
        self.assertNotIn('HOME', str(d))

    def test_units(self):
        self.assertEqual(model.temperature_unit('F'), '°F')
        self.assertEqual(model.temperature_unit('celsius'), '°C')
        self.assertIsNone(model.temperature_unit('unknown'))


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = api.CarrierSmartHomeClient(object(), 'user@example.com', 'SECRET_PASSWORD')

    async def test_login_uses_observed_graphql_route(self):
        self.client._post = AsyncMock(return_value={'data': {'assistedLogin': {
            'success': True, 'data': {'access_token': 'access-secret',
             'refresh_token': 'refresh-secret', 'token_type': 'Bearer', 'expires_in': 3600}}}})
        token = await self.client._token()
        self.assertEqual(token, 'access-secret')
        args, kwargs = self.client._post.call_args
        self.assertEqual(args[0], api.NO_AUTH)
        self.assertEqual(args[1]['operationName'], 'assistedLogin')
        self.assertEqual(args[1]['variables']['input']['password'], 'SECRET_PASSWORD')
        self.assertNotIn('SECRET_PASSWORD', repr(self.client))

    async def test_cached_access_token(self):
        self.client._post = AsyncMock(return_value={'data': {'assistedLogin': {
            'success': True, 'data': {'access_token':'abc', 'expires_in':3600}}}})
        await self.client._token()
        await self.client._token()
        self.assertEqual(self.client._post.call_count, 1)

    async def test_bad_login(self):
        self.client._post = AsyncMock(return_value={'data': {'assistedLogin': {'success': False}}})
        with self.assertRaises(api.CarrierAuthError):
            await self.client._token()

    async def test_bad_refresh_expires(self):
        with self.assertRaises(api.CarrierAuthError):
            self.client._set_tokens({'access_token': 'a', 'expires_in': 0})

    async def test_bad_token_type(self):
        with self.assertRaises(api.CarrierAuthError):
            self.client._set_tokens({'access_token':'a','expires_in': 3600,'token_type':'Basic'})

    async def test_refresh(self):
        self.client._refresh_token = 'old-refresh'
        self.client._post = AsyncMock(return_value={'access_token': 'new-token',
                 'refresh_token': 'new-refresh', 'expires_in': 1800, 'token_type':'Bearer'})
        token = await self.client._token()
        self.assertEqual(token, 'new-token')
        self.assertEqual(self.client._refresh_token, 'new-refresh')
        self.assertEqual(self.client._post.call_args.args[0], api.REFRESH)
        self.assertTrue(self.client._post.call_args.kwargs['form'])

    async def test_discover_systems(self):
        self.client._graphql = AsyncMock(return_value={'entryLevelSystems': [{'serial':'serial1','zones':[]}]})
        systems = await self.client.async_get_systems()
        self.assertEqual(systems[0]['serial'], 'serial1')
        self.assertEqual(self.client._graphql.call_args.args[0], 'getEntryLevelSystems')

    async def test_invalid_systems(self):
        self.client._graphql = AsyncMock(return_value={'someOtherKey': []})
        with self.assertRaises(api.CarrierTransportError):
            await self.client.async_get_systems()

    async def test_zone_writes_validate_pair(self):
        self.client._graphql = AsyncMock(return_value={'updateEntryLevelZone': {'success': True}})
        await self.client.async_update_zone('serial1', 0, heat=69, cool=75)
        variables = self.client._graphql.call_args.args[2]
        self.assertEqual(variables['input']['htsp'], {'current':69})
        self.assertEqual(variables['input']['clsp'], {'current':75})
        self.assertEqual(variables['input']['serial'], 'serial1')

    async def test_reject_partial_setpoint(self):
        with self.assertRaises(ValueError):
            await self.client.async_update_zone('a', 0, cool=75)

    async def test_reject_crossed_setpoints(self):
        with self.assertRaises(ValueError):
            await self.client.async_update_zone('a', 0, heat=80, cool=70)

    async def test_reject_boolean_setpoint(self):
        with self.assertRaises(ValueError):
            await self.client.async_update_zone('a', 0, heat=True, cool=80)

    async def test_reject_empty_mutation(self):
        with self.assertRaises(ValueError):
            await self.client.async_update_zone('a', 0)

    async def test_mode_write(self):
        self.client._graphql = AsyncMock(return_value={'updateEntryLevelZone': {'success': True}})
        await self.client.async_update_zone('a', 0, mode='heat')
        self.assertEqual(self.client._graphql.call_args.args[2]['input']['mode'], 'heat')

    async def test_mutation_failed(self):
        self.client._graphql = AsyncMock(return_value={'updateEntryLevelZone': {'success': False}})
        with self.assertRaises(api.CarrierTransportError):
            await self.client.async_update_zone('a', 0, mode='cool')

    async def test_graphql_error_redacted(self):
        with self.assertRaises(api.CarrierTransportError) as ctx:
            self.client._graphql_data({'errors': [{'message':'serial=hidden PRIVATE TOKEN'}]})
        self.assertNotIn('PRIVATE', str(ctx.exception))

    async def test_no_plaintext_redirect(self):
        # Auth and GraphQL POSTs must never follow a redirect to another domain.
        self.assertEqual(api.NO_AUTH, 'https://dataservice.infinity.iot.carrier.com/graphql-no-auth')
        self.assertEqual(api.GRAPHQL, 'https://dataservice.infinity.iot.carrier.com/graphql')


if __name__ == '__main__':
    unittest.main()

class FallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_from_independent_client_query_to_apk_queries(self):
        client = api.CarrierSmartHomeClient(object(), 'account', 'pw')
        async def gql(name, _document, variables):
            if name == 'getEntryLevelSystems':
                raise api.CarrierQueryError('query not supported')
            if name == 'getUserWithDevices':
                return {'user': {'locations': [
                    {'entryLevels': [{'serial': 'device-A'}, {'serial': 'device-A'}]},
                    {'entryLevels': [{'serial': 'device-B'}]}]}}
            if name == 'getEntryLevelSystemData':
                return {'entryLevelSystem': {'serial': variables['serial'], 'zones':[{'index':0}]}}
            raise AssertionError(name)
        client._graphql = AsyncMock(side_effect=gql)
        systems = await client.async_get_systems()
        self.assertEqual([s['serial'] for s in systems], ['device-A', 'device-B'])
        self.assertEqual(client._discovery_method, 'user_devices')
        self.assertEqual(client._graphql.await_count, 4)
        await client.async_get_systems()
        self.assertEqual(client._graphql.await_count, 7)

    async def test_no_fallback_on_network_failure(self):
        client = api.CarrierSmartHomeClient(object(), 'account', 'pw')
        client._graphql = AsyncMock(side_effect=api.CarrierTransportError('offline'))
        with self.assertRaises(api.CarrierTransportError):
            await client.async_get_systems()
        self.assertEqual(client._discovery_method, 'systems')
        self.assertEqual(client._graphql.await_count, 1)

class FakeContent:
    def __init__(self, body):
        self.body = body
    async def read(self, _size):
        return self.body


class FakeResponse:
    def __init__(self, status, body=b'{}', content_length=None):
        self.status = status
        self.content_length = content_length
        self.content = FakeContent(body)
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_args):
        return False


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_never_follow_redirects(self):
        session = FakeSession(FakeResponse(302))
        client = api.CarrierSmartHomeClient(session, 'user', 'password')
        with self.assertRaises(api.CarrierTransportError):
            await client._post(api.GRAPHQL, {'hello':'world'})
        self.assertEqual(session.calls[0][1]['allow_redirects'], False)

    async def test_sanitized_auth_failure(self):
        session = FakeSession(FakeResponse(401, b'password=hidden-abc'))
        client = api.CarrierSmartHomeClient(session, 'user', 'password')
        with self.assertRaises(api.CarrierAuthError) as e:
            await client._post(api.GRAPHQL, {'hello':'world'})
        self.assertNotIn('hidden-abc', str(e.exception))

    async def test_rejects_oversize_response(self):
        session = FakeSession(FakeResponse(200, b'{}', api.MAX_BODY+1))
        client = api.CarrierSmartHomeClient(session, 'user', 'password')
        with self.assertRaises(api.CarrierTransportError):
            await client._post(api.GRAPHQL, {})

    async def test_rejects_invalid_json(self):
        session = FakeSession(FakeResponse(200, b'<html>login form</html>'))
        client = api.CarrierSmartHomeClient(session, 'user', 'password')
        with self.assertRaises(api.CarrierTransportError):
            await client._post(api.GRAPHQL, {})

    async def test_form_auth_body_correct(self):
        session = FakeSession(FakeResponse(200, b'{"access_token":"token"}'))
        client = api.CarrierSmartHomeClient(session, 'user', 'password')
        value = await client._post(api.REFRESH, {'refresh_token': 'a'}, form=True)
        self.assertEqual(value['access_token'], 'token')
        self.assertEqual(session.calls[0][1]['data']['refresh_token'], 'a')
        self.assertNotIn('Authorization', session.calls[0][1]['headers'])

    async def test_rejected_refresh_classified_as_auth(self):
        session = FakeSession(FakeResponse(400, b'{"error":"invalid_grant"}'))
        client = api.CarrierSmartHomeClient(session, 'user', 'password')
        with self.assertRaises(api.CarrierAuthError):
            await client._post(api.REFRESH, {'refresh_token': 'a'}, form=True)

    async def test_good_json(self):
        session = FakeSession(FakeResponse(200, b'{"data":{"ok":true}}'))
        client = api.CarrierSmartHomeClient(session, 'user', 'password')
        self.assertTrue((await client._post(api.GRAPHQL, {}))['data']['ok'])


class EmptyPrimaryListTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_primary_list_tries_apk_location_discovery(self):
        client = api.CarrierSmartHomeClient(object(), 'account', 'pw')
        async def gql(name, _document, _variables):
            if name == 'getEntryLevelSystems':
                return {'entryLevelSystems': []}
            if name == 'getUserWithDevices':
                return {'user': {'locations': [{'entryLevels': [{'serial': 'active-serial'}]}]}}
            return {'entryLevelSystem': {'serial': 'active-serial', 'zones': [{'index': 0}]}}
        client._graphql = AsyncMock(side_effect=gql)
        result = await client.async_get_systems()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['serial'], 'active-serial')

"""Pure offline tests; no thermostat, tokens, secrets or internet required."""
from __future__ import annotations
import importlib.util
import ipaddress
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def import_tool(name):
    import sys
    root = str(ROOT / 'tools')
    if root not in sys.path:
        sys.path.insert(0, root)
    spec = importlib.util.spec_from_file_location('carrier_' + name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

lan = import_tool('auto_discover')
har = import_tool('analyze_har')
protocol = import_tool('cloud_protocol')

class NetworkTests(unittest.TestCase):
    def test_select_192_network(self):
        net, selected = lan.select_network([{'ip': '192.168.4.33', 'prefix': 24,
                                            'gateway': '192.168.4.1', 'metric': 1}])
        self.assertEqual(str(net), '192.168.4.0/24')

    def test_select_10_network_bounded(self):
        net, _ = lan.select_network([{'ip': '10.40.3.142', 'prefix': 16, 'gateway': '10.40.0.1'}])
        self.assertEqual(str(net), '10.40.3.0/24')

    def test_select_small_network(self):
        net, _ = lan.select_network([{'ip': '192.168.4.4', 'prefix': 28,
                                     'gateway': '192.168.4.1'}])
        self.assertEqual(str(net), '192.168.4.0/28')

    def test_no_public_network(self):
        with self.assertRaises(RuntimeError):
            lan.select_network([{'ip': '8.8.8.8', 'prefix': 24, 'gateway': '8.8.8.1'}])

    def test_no_loopback(self):
        with self.assertRaises(RuntimeError):
            lan.select_network([{'ip': '127.0.0.1', 'prefix': 8, 'gateway': '127.0.0.1'}])

    def test_reject_public_gateway(self):
        with self.assertRaises(RuntimeError):
            lan.select_network([{'ip': '192.168.0.30', 'prefix': 24, 'gateway': '1.1.1.1'}])

    def test_best_route(self):
        net, _ = lan.select_network([{'ip': '10.1.1.2', 'prefix': 24, 'gateway': '10.1.1.1', 'metric': 800},
                                      {'ip': '192.168.1.9', 'prefix': 24, 'gateway': '192.168.1.1', 'metric': 5}])
        self.assertEqual(str(net), '192.168.1.0/24')

    def test_report_does_not_claim_model(self):
        with patch.object(lan, 'neighbors', return_value=[{'ip': '192.168.5.71', 'mac': 'aa:bb:cc:dd:ee:ff'}]), \
                patch.object(lan, 'discover_mdns', return_value=([], [])), \
                patch.object(lan, 'scan_hosts', return_value=[]):
            r = lan.report(ipaddress.ip_network('192.168.5.0/24'), {'ip': '192.168.5.33'})
        self.assertIs(r['candidate_devices'][0]['thermostat_confirmed'], False)
        self.assertEqual(r['scope'], '192.168.5.0/24')

    def test_report_refuses_large_range(self):
        with self.assertRaises(ValueError):
            lan.report(ipaddress.ip_network('192.168.0.0/16'), {'ip': '192.168.0.20'})

class HARTests(unittest.TestCase):
    def test_carrier_domains_only(self):
        self.assertIsNotNone(har.carrier_host('https://prod.consumerportal.carrier.com/graphql'))
        self.assertIsNone(har.carrier_host('https://carrier.com.evil.org/graphql'))
        self.assertIsNone(har.carrier_host('http://carrier.com/graphql'))
        self.assertIsNone(har.carrier_host('https://user:pw@carrier.com/graphql'))

    def test_sanitize_paths(self):
        self.assertEqual(har.sanitized_path('/graphql'), '/graphql')
        self.assertEqual(har.sanitized_path('/api/12345/token'), '/api/{segment}/token')
        self.assertNotIn('private', har.sanitized_path('/api/private@example.net/graphql'))

    def test_graphql_name_and_keys_only(self):
        req = {'postData': {'text': json.dumps({'operationName': 'getUserWithDevices',
                        'variables': {'email': 'secret@home.test', 'serial': 'TOPSECRET'}})}}
        r = har.graphql_shape(req)
        self.assertEqual(r['operation'], 'getUserWithDevices')
        self.assertEqual(r['variable_keys'], ['email', 'serial'])
        self.assertNotIn('TOPSECRET', repr(r))

    def test_full_har_redaction(self):
        raw = {'log': {'entries': [{'request': {
            'url': 'https://dataservice.infinity.iot.carrier.com/graphql?token=THIS_MUST_NOT_LEAK',
            'method': 'POST',
            'headers': [{'name': 'Authorization', 'value': 'Bearer HIGHLY_SECRET'},
                        {'name': 'Cookie', 'value': 'session=HIGHLY_SECRET'}],
            'postData': {'text': json.dumps({'operationName': 'getEntryLevelSystemData',
                                          'variables': {'serial': 'TOPSECRET'},
                                          'query': 'query getEntryLevelSystemData($serial:String!){entryLevelSystem(serial:$serial){serial}}'})}
        }, 'response': {'content': {'text': 'OTHER_SECRET'}}}]}}
        output = har.summarize_har(raw)
        displayed = json.dumps(output)
        for secret in ('THIS_MUST_NOT_LEAK', 'HIGHLY_SECRET', 'TOPSECRET', 'OTHER_SECRET'):
            self.assertNotIn(secret, displayed)
        self.assertEqual(output['records'][0]['authentication_headers']['authorization'], 'bearer')
        self.assertEqual(output['records'][0]['graphql_operation'], 'getEntryLevelSystemData')

    def test_reject_broken_har(self):
        with self.assertRaises(ValueError):
            har.summarize_har({'log': {'entries': 3}})

    def test_ignore_other_domains(self):
        r = har.summarize_har({'log': {'entries': [{'request': {'url': 'https://evil.com/a', 'method': 'GET'}}]}})
        self.assertEqual(r['carrier_requests'], 0)

class CloudTests(unittest.TestCase):
    def test_valid_operation(self):
        op = protocol.parse_operation('query getUserWithDevices($userName:String!){user(userName:$userName){email}}')
        self.assertEqual(op.name, 'getUserWithDevices')
        self.assertTrue(op.readonly)

    def test_mutation_is_identified(self):
        op = protocol.parse_operation('mutation updateEntryLevelZone($input: EntryLevelZoneInput!){updateEntryLevelZone(input:$input){success}}')
        self.assertFalse(op.readonly)

    def test_multi_operation_rejected(self):
        with self.assertRaises(ValueError):
            protocol.parse_operation('query One{foo}\nquery Two{bar}')

    def test_endpoint_validation(self):
        self.assertEqual(protocol.validate_carrier_endpoint('https://dataservice.infinity.iot.carrier.com/graphql'),
                         'https://dataservice.infinity.iot.carrier.com/graphql')
        for url in ('http://carrier.com/graphql', 'https://carrier.com.evil.org/graphql',
                    'https://user:pw@carrier.com/graphql', 'https://carrier.com/api/secret',
                    'https://carrier.com/graphql?token=a', 'https://carrier.com/graphql#frag'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    protocol.validate_carrier_endpoint(url)

    def test_read_only_enforced_without_network(self):
        transport = protocol.CarrierCloudTransport('https://dataservice.infinity.iot.carrier.com/graphql', lambda: 'safesecret')
        op = protocol.parse_operation('mutation Test {updateEntryLevelZone {success}}')
        with self.assertRaises(PermissionError):
            transport.execute(op)

    def test_token_validation(self):
        transport = protocol.CarrierCloudTransport('https://dataservice.infinity.iot.carrier.com/graphql', lambda: 'a\nb')
        op = protocol.parse_operation('query Test {viewer{id}}')
        with self.assertRaises(protocol.CarrierAuthenticationError):
            transport.execute(op)

    def test_mocked_response(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, num): return b'{"data":{"user":{"locations":[]}}}'
        transport = protocol.CarrierCloudTransport('https://dataservice.infinity.iot.carrier.com/graphql', lambda: 'token')
        with patch.object(transport._opener, 'open', return_value=Response()):
            self.assertEqual(transport.execute(protocol.parse_operation('query Test{user{locations}}')),
                             {'user': {'locations': []}})

    def test_error_body_redacted(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, num): return b'{"errors":[{"message":"secret value"}]}'
        transport = protocol.CarrierCloudTransport('https://dataservice.infinity.iot.carrier.com/graphql', lambda: 'token')
        with patch.object(transport._opener, 'open', return_value=Response()):
            with self.assertRaises(protocol.CarrierGraphQLError) as caught:
                transport.execute(protocol.parse_operation('query Test{user{id}}'))
        self.assertNotIn('secret', str(caught.exception).lower())

if __name__ == '__main__':
    unittest.main()

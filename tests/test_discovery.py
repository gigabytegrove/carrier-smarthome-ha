"""Pure offline evidence tests; never request Carrier endpoints."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


cloud = module('tools/discover_cloud.py', 'cloud_discovery')
native = module('research/analyze_native_apk.py', 'native_analyzer')
catalog = module('research/build_graphql_catalog.py', 'graphql_catalog')


class CloudDiscoveryTests(unittest.TestCase):
    def test_carrier_only_urls_without_credentials(self):
        self.assertEqual(cloud.carrier_https('https://api.carrier.com/graphql?token=secret'),
                         'https://api.carrier.com/graphql')
        for value in ('http://api.carrier.com', 'https://evil.example/secret',
                      'https://carrier.com.evil.example', 'https://user:pass@api.carrier.com',
                      'https://api.carrier.com:8080/graphql'):
            self.assertIsNone(cloud.carrier_https(value))

    def test_public_script_detection(self):
        parser = cloud.AssetParser()
        parser.feed('<html><script src="/assets/app.js"></script><script src="https://x.invalid/x.js"></script></html>')
        self.assertEqual(parser.scripts, ['/assets/app.js', 'https://x.invalid/x.js'])

    def test_evidence_scrubs_query(self):
        data = cloud.public_evidence('const REST_API_URL="https://api.carrier.com/graphql?access_token=SECRET";')
        self.assertEqual(data['embedded_api_config'], [{'key': 'REST_API_URL', 'value': 'https://api.carrier.com/graphql'}])
        self.assertNotIn('SECRET', str(data))


class NativeDexTests(unittest.TestCase):
    def test_uleb(self):
        self.assertEqual(native.uleb(b'\xac\x02', 0), (300, 2))
        with self.assertRaises(ValueError):
            native.uleb(b'\x80', 0)

    def test_synthetic_dex_strings(self):
        # DEX minimum header, string_ids_size at 56, string_ids_off at 60.
        blob = bytearray(b'dex\n035\x00' + b'\x00' * 120)
        struct.pack_into('<II', blob, 56, 2, 112)
        s1 = b'\x03api\x00'
        s2 = b'\x04test\x00'
        struct.pack_into('<II', blob, 112, 120, 120 + len(s1))
        blob[120:120 + len(s1)] = s1
        blob[120 + len(s1):120 + len(s1) + len(s2)] = s2
        self.assertEqual(list(native.dex_strings(bytes(blob))), ['api', 'test'])


class CatalogTests(unittest.TestCase):
    def test_entry_level_documents(self):
        raw = json.loads((ROOT/'research/graphql-index.json').read_text())
        result = catalog.catalog(raw, ROOT/'research')
        self.assertEqual(len(result), 140)
        query = next(x for x in result if x['name'] == 'getEntryLevelSystemData')
        self.assertEqual(query['variables'], [{'name': 'serial', 'type': 'String!'}])
        self.assertEqual(sum(x['kind'] == 'mutation' for x in result), 77)
        self.assertEqual(sum(x['kind'] == 'query' for x in result), 58)


if __name__ == '__main__':
    unittest.main()

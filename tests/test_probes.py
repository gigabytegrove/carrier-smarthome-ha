"""Offline stdlib-only tests: no network or Carrier account needed."""
import importlib.util
from pathlib import Path
import socket
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


local = load('probe_local')
cloud = load('probe_cloud')


class LocalTests(unittest.TestCase):
    def test_restricted_network(self):
        self.assertEqual(str(local.private_net('192.168.12.7/24')), '192.168.12.0/24')
        for invalid in ('8.8.8.0/24', '127.0.0.0/24', '192.168.0.0/16', '169.254.1.0/24'):
            with self.assertRaises(Exception):
                local.private_net(invalid)

    def test_local_ip(self):
        self.assertEqual(str(local.private_ip('10.1.2.3')), '10.1.2.3')
        for invalid in ('8.8.8.8', '127.0.0.1', '169.254.2.3', '::1', 'foobar'):
            with self.assertRaises(Exception):
                local.private_ip(invalid)

    def test_dns_name_valid(self):
        self.assertEqual(local.dns_name('_matter._tcp.local'), b'\x07_matter\x04_tcp\x05local\x00')
        self.assertEqual(local.parse_name(b'\x03foo\x05local\x00', 0), ('foo.local', 11))

    def test_dns_pointer_loop(self):
        with self.assertRaises(ValueError):
            local.parse_name(b'\xc0\x00', 0)

    def test_mdns_answer(self):
        name = local.dns_name('thermostat.local')
        response = struct.pack('!HHHHHH', 0, 0x8400, 0, 1, 0, 0)
        response += name + struct.pack('!HHIH', 1, 1, 120, 4) + socket.inet_aton('192.168.0.56')
        self.assertEqual(local.parse_mdns(response), [
            {'service': 'thermostat.local', 'type': 'A', 'value': '192.168.0.56'}])

    def test_mdns_truncated(self):
        self.assertEqual(local.parse_mdns(b'\x00'), [])
        self.assertEqual(local.parse_mdns(b'\x00' * 12), [])


class CloudTests(unittest.TestCase):
    def test_no_values_in_shape(self):
        result = cloud.inspect_shape({'user': {'email': 'private@example.org', 'serial': 'SECRET', 'zones': [{'temp': 73}]}})
        text = str(result)
        self.assertIn('email', text)
        self.assertNotIn('SECRET', text)
        self.assertNotIn('private@example.org', text)
        self.assertNotIn('73', text)


if __name__ == '__main__':
    unittest.main()

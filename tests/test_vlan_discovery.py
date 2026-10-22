"""Multi-VLAN network-selection tests; no devices, LANs, or cloud hosts contacted."""
from __future__ import annotations
import importlib.util
import ipaddress
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('carrier_vlan', TOOLS / 'auto_discover.py')
lan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lan
spec.loader.exec_module(lan)


class VLANScopeTests(unittest.TestCase):
    def interfaces(self):
        return [
            {'ip': '192.168.0.133', 'prefix': 24, 'interface': 'Ethernet 2'},
            {'ip': '192.168.50.16', 'prefix': 24, 'interface': 'Ethernet 2.50'},
        ]

    def test_two_connected_vlan_subnets_are_detected(self):
        result, warnings = lan.discovery_scopes(self.interfaces(), [])
        self.assertEqual([str(s['network']) for s in result],
                         ['192.168.0.0/24', '192.168.50.0/24'])
        self.assertEqual(warnings, [])

    def test_specific_route_enables_remote_vlan(self):
        result, _ = lan.discovery_scopes(self.interfaces()[:1], ['192.168.80.0/24'])
        self.assertEqual(str(result[1]['network']), '192.168.80.0/24')
        self.assertEqual(result[1]['sources'], ['specific_route'])
        self.assertEqual(result[1]['local_ips'], [])

    def test_default_route_cannot_reveal_other_vlan(self):
        scopes, _ = lan.discovery_scopes(self.interfaces()[:1], ['0.0.0.0/0', 'default'])
        self.assertEqual(len(scopes), 1)
        self.assertEqual(str(scopes[0]['network']), '192.168.0.0/24')

    def test_explicit_authorized_vlan(self):
        scopes, _ = lan.discovery_scopes(self.interfaces()[:1], [], ['192.168.90.0/24'])
        self.assertEqual(scopes[1]['sources'], ['user_authorized'])

    def test_public_explicit_network_refused(self):
        for candidate in ('8.8.8.0/24', '1.1.1.1/32', '0.0.0.0/0', '127.0.0.0/24'):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                lan.discovery_scopes(self.interfaces(), [], [candidate])

    def test_private_wide_explicit_network_refused(self):
        with self.assertRaises(ValueError):
            lan.discovery_scopes(self.interfaces()[:1], [], ['10.20.0.0/16'])

    def test_duplicate_sources_are_combined_without_duplicate_scan(self):
        scopes, _ = lan.discovery_scopes(self.interfaces()[:1], ['192.168.0.0/24'],
                                          ['192.168.0.0/24'])
        self.assertEqual(len(scopes), 1)
        self.assertEqual(len(scopes[0]['sources']), 3)

    def test_multi_vlan_cap_is_enforced(self):
        extra = [f'10.0.{i}.0/24' for i in range(10)]
        scopes, warnings = lan.discovery_scopes([], [], extra, max_networks=3)
        self.assertEqual(len(scopes), 3)
        self.assertTrue(any('limited' in w for w in warnings))

    def test_cap_input_bounds(self):
        for n in (-1, 0, 17, 999):
            with self.subTest(n=n), self.assertRaises(ValueError):
                lan.discovery_scopes(self.interfaces(), [], max_networks=n)

    def test_broad_interface_scans_only_host_24_and_warns(self):
        scopes, warnings = lan.discovery_scopes([{'ip': '10.20.12.10', 'prefix': 16,
                                                   'interface': 'eth0'}], [])
        self.assertEqual(str(scopes[0]['network']), '10.20.12.0/24')
        self.assertIn('wider than /24', warnings[0])

    def test_no_visible_private_interfaces(self):
        scopes, _ = lan.discovery_scopes([{'ip': '169.254.1.4', 'prefix': 24},
                                           {'ip': '8.8.8.1', 'prefix': 24}], [])
        self.assertEqual(scopes, [])

    def test_filtered_neighbors_only_in_the_relevant_subnet(self):
        records = [{'ip': '192.168.0.2', 'mac': 'aa:bb:cc:dd:ee:01'},
                   {'ip': '192.168.90.10', 'mac': 'aa:bb:cc:dd:ee:02'}]
        with patch.object(lan, 'neighbors', return_value=records), \
             patch.object(lan, 'scan_hosts', return_value=[]):
            row = lan.report(ipaddress.ip_network('192.168.90.0/24'),
                             {'ip': ''}, do_tcp=False, mdns_seconds=0)
        self.assertEqual([d['ip'] for d in row['candidate_devices']], ['192.168.90.10'])

    def test_subnet_safety_rejects_public_and_wide(self):
        for candidate in ('8.8.8.0/24', '10.0.0.0/8'):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                lan.safe_cidr(candidate)

    def test_ineligible_host_routes_not_inferred(self):
        scopes, _ = lan.discovery_scopes(self.interfaces()[:1], ['10.9.1.1/32',
                                                                   '192.168.33.0/23'])
        self.assertEqual(len(scopes), 1)


if __name__ == '__main__':
    unittest.main()
